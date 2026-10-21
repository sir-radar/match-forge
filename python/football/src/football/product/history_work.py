"""Bind history requests and project shared work state into legacy queue detail.

Provider execution and scheduler handoff still require Phase 17 integration and
controlled parity checks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection, Error, sql
from psycopg.errors import InvalidParameterValue, ObjectNotInPrerequisiteState, UniqueViolation
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row, tuple_row

from football.contracts.source import SHA256_PATTERN
from football.product.domain import sha256_json
from football.storage.locks import LOCK_ORDER_SQLSTATE, LockClass, LockOrderError
from football.work.contracts import (
    RetryClassification,
    RetryPolicy,
    WorkClaim,
    WorkContractError,
    WorkRequest,
    WorkState,
    WorkType,
)
from football.work.storage import WorkConflict, WorkLeaseLost, WorkRegistry, claim_from_record


class _HistoryRequestChanged(Exception):
    """The request changed or became busy before registration could lock it."""


def register_history_request(connection: Connection[Any], job_id: UUID) -> UUID | None:
    """Bind one pending request atomically; leave active legacy ownership alone.

    The transaction joins its caller. Shared work precedes the domain row in the
    lock order; a busy or changed row rolls back all registration writes.
    """
    try:
        with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT job_id,provider_competition_id,season,job_status,queued_at,
                          attempt_count,next_attempt_at,updated_at
                   FROM football.product_history_sync_queue WHERE job_id=%s""",
                (job_id,),
            )
            original = cursor.fetchone()
            if original is None or original["job_status"] != "PENDING":
                return None
            cursor.execute(
                """SELECT binding.work_id,binding.provider_competition_id,binding.season,
                          binding.attempt_offset+work.attempt_count AS expected_attempts
                   FROM football.product_history_work binding
                   JOIN football.work_items work ON work.work_id=binding.work_id
                   WHERE binding.job_id=%s AND binding.queued_at=%s""",
                (job_id, original["queued_at"]),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if (
                    existing["provider_competition_id"],
                    existing["season"],
                    existing["expected_attempts"],
                ) != (
                    original["provider_competition_id"],
                    original["season"],
                    original["attempt_count"],
                ):
                    raise WorkConflict("history request identity binds different inputs")
                return UUID(str(existing["work_id"]))
            request = _history_request(connection, original)
            cursor.execute("SELECT football.authorize_worker_publication()")
            cursor.execute(
                "SELECT football.record_transaction_lock(%s,%s)",
                (int(LockClass.WORK), f"work:{request.work_id}"),
            )
            WorkRegistry(connection).enqueue(request)
            cursor.execute(
                "SELECT state,attempt_count FROM football.work_items "
                "WHERE work_id=%s FOR NO KEY UPDATE",
                (request.work_id,),
            )
            unclaimed = cursor.fetchone()
            if unclaimed is None or (unclaimed["state"], unclaimed["attempt_count"]) != (
                "PENDING",
                0,
            ):
                cursor.execute(
                    """SELECT 1 FROM football.product_history_work
                    WHERE work_id=%s AND job_id=%s AND queued_at=%s""",
                    (request.work_id, job_id, original["queued_at"]),
                )
                if cursor.fetchone() is not None:
                    # Another registrar bound and claimed this same request while
                    # our enqueue waited. Its ownership is valid; skip the candidate.
                    raise _HistoryRequestChanged
                raise WorkConflict("history request registration requires unclaimed shared work")
            cursor.execute(
                "SELECT football.record_transaction_lock(%s,%s)",
                (
                    int(LockClass.WORK_DETAIL),
                    f"history-queue:{original['provider_competition_id']}:{original['season']}",
                ),
            )
            cursor.execute(
                """SELECT job_id,provider_competition_id,season,job_status,queued_at,
                          attempt_count,next_attempt_at,updated_at
                   FROM football.product_history_sync_queue WHERE job_id=%s
                   FOR UPDATE SKIP LOCKED""",
                (job_id,),
            )
            if cursor.fetchone() != original:
                raise _HistoryRequestChanged
            cursor.execute(
                """INSERT INTO football.product_history_work
                (work_id,job_id,queued_at,provider_competition_id,season,attempt_offset)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (job_id,queued_at) DO NOTHING""",
                (
                    request.work_id,
                    job_id,
                    original["queued_at"],
                    original["provider_competition_id"],
                    original["season"],
                    original["attempt_count"],
                ),
            )
            return request.work_id
    except _HistoryRequestChanged:
        return None


def _history_request(connection: Connection[Any], row: dict[str, Any]) -> WorkRequest:
    offset = int(row["attempt_count"])
    if offset >= 2**31 - 1:
        raise WorkContractError("history attempt count exhausted PostgreSQL integer capacity")
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute("SELECT football.work_retry_seconds(60,3600,2,%s)", (offset + 1,))
        delay = cursor.fetchone()
        assert delay is not None
    queued_at = row["queued_at"].astimezone(UTC)
    inputs = {
        "job_id": str(row["job_id"]),
        "queued_at": queued_at.isoformat(),
        "provider_competition_id": row["provider_competition_id"],
        "season": row["season"],
        "attempt_offset": offset,
    }
    return WorkRequest(
        work_type=WorkType.HISTORICAL_ACQUISITION,
        semantic_key=f"product-history:{row['job_id']}:{queued_at.isoformat()}",
        input_hash=sha256_json(inputs),
        priority=0,
        available_at=row["next_attempt_at"] or queued_at,
        max_attempts=2**31 - 1 - offset,
        retry_policy=RetryPolicy(
            timedelta(seconds=delay[0]),
            timedelta(hours=1),
            2,
            lease_expiry_delay=timedelta(),
        ),
    )


def claim_history_request(
    connection: Connection[Any],
    job_id: UUID,
    owner: str,
    batch_started_at: datetime,
    *,
    lease_duration: timedelta,
) -> WorkClaim | None:
    """Claim one explicitly selected request through shared eligibility and fencing."""
    _require_idle(connection)
    if not isinstance(owner, str) or not owner.strip():
        raise WorkContractError("history claim owner is required")
    if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta():
        raise WorkContractError("history claim lease duration must be positive")
    if not isinstance(batch_started_at, datetime) or batch_started_at.utcoffset() is None:
        raise WorkContractError("history batch start requires a timezone")
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            """SELECT binding.work_id FROM football.product_history_sync_queue queue
            JOIN football.product_history_work binding USING (job_id,queued_at)
            WHERE queue.job_id=%s""",
            (job_id,),
        )
        bound = cursor.fetchone()
    identity = UUID(str(bound[0])) if bound else register_history_request(connection, job_id)
    if identity is None:
        return None
    row = _history_operation(
        connection, "claim_history_work", identity, owner, lease_duration, batch_started_at
    )
    return claim_from_record(row) if row else None


def complete_history_request(
    connection: Connection[Any], claim: WorkClaim, *, result_hash: str
) -> None:
    """Complete work and its matching queue request in one short transaction."""
    if not isinstance(result_hash, str) or not SHA256_PATTERN.fullmatch(result_hash):
        raise WorkContractError("history work result hash must be lowercase SHA256")
    _history_operation(
        connection,
        "finish_history_work",
        claim.work_id,
        claim.lease_owner,
        claim.lease_token,
        claim.generation,
        result_hash,
    )


def fail_history_request(
    connection: Connection[Any],
    claim: WorkClaim,
    classification: RetryClassification,
    *,
    error_code: str,
    error_message: str,
) -> WorkState:
    """Apply shared retry classification and atomically project the domain state."""
    if not isinstance(classification, RetryClassification):
        raise WorkContractError("history failure requires shared retry classification")
    row = _history_operation(
        connection,
        "fail_history_work",
        claim.work_id,
        claim.lease_owner,
        claim.lease_token,
        claim.generation,
        classification.value,
        error_code,
        error_message,
    )
    assert row is not None
    return WorkState(row["state"])


def _require_idle(connection: Connection[Any]) -> None:
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise WorkContractError("history work control requires an idle connection")


def _history_operation(
    connection: Connection[Any], name: str, *arguments: object
) -> dict[str, Any] | None:
    _require_idle(connection)
    query = sql.SQL("SELECT * FROM football.{}({})").format(
        sql.Identifier(name), sql.SQL(",").join(sql.Placeholder() for _ in arguments)
    )
    try:
        with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, arguments)
            return cursor.fetchone()
    except ObjectNotInPrerequisiteState as error:
        raise WorkLeaseLost("history work lease ownership lost") from error
    except UniqueViolation as error:
        raise WorkConflict(str(error)) from error
    except InvalidParameterValue as error:
        raise WorkContractError(str(error)) from error
    except Error as error:
        if error.sqlstate == LOCK_ORDER_SQLSTATE:
            raise LockOrderError(str(error)) from error
        raise


def heartbeat_history_request(
    connection: Connection[Any],
    claim: WorkClaim,
    lease_duration: timedelta,
    *,
    sync_run_id: UUID | None = None,
) -> WorkClaim:
    """Renew the shared lease and its legacy operator detail atomically."""
    if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta():
        raise WorkContractError("history heartbeat lease duration must be positive")
    row = _history_operation(
        connection,
        "heartbeat_history_work",
        claim.work_id,
        claim.lease_owner,
        claim.lease_token,
        claim.generation,
        lease_duration,
        sync_run_id,
    )
    assert row is not None
    return claim_from_record(row)


def cancel_history_request(connection: Connection[Any], work_id: UUID) -> WorkState:
    """Revoke publication rights and project cancellation in one transaction."""
    row = _history_operation(connection, "cancel_history_work", work_id)
    assert row is not None
    return WorkState(row["state"])
