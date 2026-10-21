"""Thin worker adapter over the shared SQL state machine; no provider or file I/O."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection, Error, sql
from psycopg.errors import InvalidParameterValue, ObjectNotInPrerequisiteState, UniqueViolation
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from football.contracts.source import SHA256_PATTERN
from football.storage.locks import LOCK_ORDER_SQLSTATE, LockOrderError
from football.work.contracts import (
    RetryClassification,
    WorkClaim,
    WorkContractError,
    WorkRequest,
    WorkState,
    WorkType,
)


class WorkLeaseLost(RuntimeError):
    """The worker no longer has publication rights for this work item."""


class WorkConflict(WorkContractError):
    """An existing semantic key binds different inputs or scheduling policy."""


class WorkRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def enqueue(self, request: WorkRequest) -> UUID:
        """Join the caller's transaction so domain changes and downstream work commit together."""
        policy = request.retry_policy
        with self._connection.transaction():
            row = self._call(
                "enqueue_work",
                request.work_id,
                request.work_type.value,
                request.semantic_key,
                request.input_hash,
                request.priority,
                request.available_at,
                request.max_attempts,
                policy.base_delay.total_seconds(),
                policy.max_delay.total_seconds(),
                policy.multiplier,
                list(request.dependencies),
                request.parent_work_id,
                (
                    policy.lease_expiry_delay.total_seconds()
                    if policy.lease_expiry_delay is not None
                    else None
                ),
            )
            assert row is not None
            return UUID(str(row["work_id"]))

    def claim(
        self,
        owner: str,
        lease_duration: timedelta,
        allowed_types: tuple[WorkType, ...],
        *,
        work_ids: tuple[UUID, ...] | None = None,
    ) -> WorkClaim | None:
        """Claim centrally eligible work; an ID filter also limits exhausted-lease cleanup."""
        _duration(lease_duration)
        if not isinstance(owner, str) or not owner.strip():
            raise WorkContractError("claim owner is required")
        if not allowed_types or any(not isinstance(kind, WorkType) for kind in allowed_types):
            raise WorkContractError("claim requires explicit supported work types")
        arguments: tuple[object, ...] = (
            owner,
            lease_duration,
            [kind.value for kind in allowed_types],
        )
        if work_ids is not None:
            if not isinstance(work_ids, (tuple, list)) or any(
                not isinstance(identity, UUID) for identity in work_ids
            ):
                raise WorkContractError("work claim filters require UUID identities")
            arguments += (sorted(set(work_ids)),)
        with self._short_transaction():
            row = self._call("claim_work", *arguments)
            return claim_from_record(row) if row else None

    def heartbeat(self, claim: WorkClaim, lease_duration: timedelta) -> WorkClaim:
        _duration(lease_duration)
        with self._short_transaction():
            row = self._call("heartbeat_work", *_ownership(claim), lease_duration)
            assert row is not None
            return claim_from_record(row)

    @contextmanager
    def progress(self, claim: WorkClaim) -> Iterator[Connection[Any]]:
        """Fence one database step under the lease without completing the work item.

        Acquire canonical scopes first. Provider/file I/O belongs outside this
        transaction. Ownership is checked again after the step. An existing caller
        transaction retains control of the final commit.
        """
        with self._publication_transaction(claim) as connection:
            yield connection
            self._call("lock_work", *_ownership(claim))

    @contextmanager
    def publication(self, claim: WorkClaim, *, result_hash: str) -> Iterator[Connection[Any]]:
        """Publish database results and complete atomically, with lease checks at both ends.

        Acquire required canonical coordination locks before entering. Perform
        provider/file access and expensive computation before this transaction.
        A lost lease or exception rolls back every write within this context.
        """
        if not isinstance(result_hash, str) or not SHA256_PATTERN.fullmatch(result_hash):
            raise WorkContractError("work result hash must be lowercase SHA256")
        with self._publication_transaction(claim) as connection:
            yield connection
            self._call("finish_work", *_ownership(claim), result_hash)

    @contextmanager
    def _publication_transaction(self, claim: WorkClaim) -> Iterator[Connection[Any]]:
        with self._connection.transaction():
            self._call("lock_work", *_ownership(claim))
            yield self._connection

    def fail(
        self,
        claim: WorkClaim,
        classification: RetryClassification,
        *,
        error_code: str,
        error_message: str,
        retry_after: datetime | None = None,
        provider_cooldown: datetime | None = None,
    ) -> WorkState:
        if not isinstance(classification, RetryClassification):
            raise WorkContractError("failure requires the shared retry classification")
        with self._short_transaction():
            row = self._call(
                "fail_work",
                *_ownership(claim),
                classification.value,
                error_code,
                error_message,
                _deadline(retry_after),
                _deadline(provider_cooldown),
            )
            assert row is not None
            return WorkState(row["state"])

    def cancel(self, work_id: UUID) -> WorkState:
        with self._short_transaction():
            row = self._call("cancel_work", work_id)
            assert row is not None
            return WorkState(row["state"])

    def release_blocked(self, work_id: UUID, *, available_at: datetime) -> WorkState:
        with self._short_transaction():
            row = self._call("release_blocked_work", work_id, _deadline(available_at))
            assert row is not None
            return WorkState(row["state"])

    def state(self, work_id: UUID) -> WorkState | None:
        with (
            self._connection.transaction(),
            self._connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute("SELECT state FROM football.work_items WHERE work_id=%s", (work_id,))
            row = cursor.fetchone()
            return WorkState(row["state"]) if row else None

    @contextmanager
    def _short_transaction(self) -> Iterator[None]:
        if self._connection.info.transaction_status != TransactionStatus.IDLE:
            raise WorkContractError("work control operations require an idle connection")
        with self._connection.transaction():
            yield

    def _call(self, name: str, *arguments: object) -> dict[str, Any] | None:
        query = sql.SQL("SELECT * FROM football.{}({})").format(
            sql.Identifier(name), sql.SQL(",").join(sql.Placeholder() for _ in arguments)
        )
        try:
            with self._connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, arguments)
                return cursor.fetchone()
        except UniqueViolation as error:
            raise WorkConflict(str(error)) from error
        except InvalidParameterValue as error:
            raise WorkContractError(str(error)) from error
        except ObjectNotInPrerequisiteState as error:
            if name in ("lock_work", "heartbeat_work", "finish_work", "fail_work"):
                raise WorkLeaseLost("work lease ownership lost") from error
            raise
        except Error as error:
            if error.sqlstate == LOCK_ORDER_SQLSTATE:
                raise LockOrderError(str(error)) from error
            raise


def claim_from_record(row: dict[str, Any]) -> WorkClaim:
    """Decode the shared SQL claim shape for workers and domain adapters."""
    return WorkClaim(
        work_id=row["work_id"],
        work_type=WorkType(row["work_type"]),
        semantic_key=row["semantic_key"],
        input_hash=row["input_hash"],
        lease_owner=row["lease_owner"],
        lease_token=row["lease_token"],
        generation=row["generation"],
        lease_until=row["lease_until"],
        attempt_count=row["attempt_count"],
    )


def _ownership(claim: WorkClaim) -> tuple[UUID, str, UUID, int]:
    return claim.work_id, claim.lease_owner, claim.lease_token, claim.generation


def _duration(value: timedelta) -> None:
    if not isinstance(value, timedelta) or value <= timedelta():
        raise WorkContractError("work lease duration must be positive")


def _deadline(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise WorkContractError("work retry deadlines require a timezone")
    return value.astimezone(UTC)
