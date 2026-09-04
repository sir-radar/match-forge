from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor

from football.ingestion.quarantine_reprocess import QuarantineReprocessRequestV1

QuarantineReprocessRegistrationStatusV1 = Literal["inserted", "verified_existing"]


class QuarantineReprocessStorageError(ValueError):
    """A reprocess request conflicts with stored quarantine evidence."""


@dataclass(frozen=True, slots=True)
class RegisteredQuarantineReprocessRequestV1:
    request_id: UUID
    request_key: str
    status: QuarantineReprocessRegistrationStatusV1


class PostgresQuarantineReprocessRequestStoreV1:
    """Persist one reviewed reprocess request without changing its source quarantine."""

    def register(
        self, cursor: Cursor[Any], request: QuarantineReprocessRequestV1
    ) -> RegisteredQuarantineReprocessRequestV1:
        source_id = _source_id(request.source_quarantine_id)
        values = (
            request.sha256,
            source_id,
            request.trigger,
            request.trigger_ref,
            request.policy_version,
            request.scheduled_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.quarantine_reprocess_requests
                (request_key, source_quarantine_record_id, trigger, trigger_ref,
                 policy_version, scheduled_at)
            SELECT %s, quarantine.id, %s, %s, %s, %s, %s
            FROM football.quarantine_records AS quarantine
            WHERE quarantine.id = %s AND quarantine.status = 'open'
            ON CONFLICT (request_key) DO NOTHING
            """,
            values + (source_id,),
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, source_quarantine_record_id, trigger, trigger_ref, policy_version,
                   scheduled_at
            FROM football.quarantine_reprocess_requests
            WHERE request_key = %s
            """,
            (request.sha256,),
        ).fetchone()
        if row is None:
            raise QuarantineReprocessStorageError("source quarantine must remain open")
        if row[1:] != values[1:]:
            raise QuarantineReprocessStorageError(
                "reprocess request conflicts with stored evidence"
            )
        status: QuarantineReprocessRegistrationStatusV1 = (
            "inserted" if inserted == 1 else "verified_existing"
        )
        return RegisteredQuarantineReprocessRequestV1(
            request_id=UUID(str(row[0])), request_key=request.sha256, status=status
        )


def _source_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise QuarantineReprocessStorageError("source quarantine ID must be a UUID") from error
