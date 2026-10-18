"""Register legacy history requests without changing their retained domain rows.

This migration step binds immutable request inputs to shared work. Execution and
legacy scheduler handoff require the separate Phase 17 adapter/parity checks.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from football.product.domain import sha256_json
from football.storage.locks import LockClass
from football.work.contracts import RetryPolicy, WorkContractError, WorkRequest, WorkType
from football.work.storage import WorkConflict, WorkRegistry


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
    with connection.cursor() as cursor:
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
