from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from football.ingestion.quarantine import QuarantineRecordV1

QuarantineRecordRegistrationStatusV1 = Literal["inserted", "verified_existing"]


class QuarantineRecordStorageError(ValueError):
    """A persisted quarantine record conflicts with immutable evidence."""


@dataclass(frozen=True, slots=True)
class RegisteredQuarantineRecordV1:
    quarantine_record_id: UUID
    finding_key: str
    status: QuarantineRecordRegistrationStatusV1


class PostgresQuarantineRecordStoreV1:
    """Persist active quarantine evidence against an acquired provider resource."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        acquisition_job_id: UUID,
        source_resource_id: UUID,
        record: QuarantineRecordV1,
    ) -> RegisteredQuarantineRecordV1:
        _verify_link(cursor, acquisition_job_id, source_resource_id, record)
        if record.status not in {"OPEN", "RETRYABLE", "NEEDS_REVIEW"}:
            raise QuarantineRecordStorageError("only active quarantine records can be registered")
        values = (
            acquisition_job_id,
            source_resource_id,
            record.sha256,
            record.reason_code,
            Jsonb(record.to_dict()),
            "open",
            record.first_seen_at,
            None,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.quarantine_records
                (acquisition_job_id, source_resource_id, finding_key, reason_code, details,
                 status, created_at, resolved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (finding_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, acquisition_job_id, source_resource_id, finding_key, reason_code,
                   details, status, created_at, resolved_at
            FROM football.quarantine_records
            WHERE finding_key = %s
            """,
            (record.sha256,),
        ).fetchone()
        expected = values[:4] + (record.to_dict(),) + values[5:]
        if row is None or row[1:] != expected:
            raise QuarantineRecordStorageError(
                "quarantine record key conflicts with immutable evidence"
            )
        status: QuarantineRecordRegistrationStatusV1 = (
            "inserted" if inserted == 1 else "verified_existing"
        )
        return RegisteredQuarantineRecordV1(
            quarantine_record_id=UUID(str(row[0])), finding_key=record.sha256, status=status
        )


def _verify_link(
    cursor: Cursor[Any],
    acquisition_job_id: UUID,
    source_resource_id: UUID,
    record: QuarantineRecordV1,
) -> None:
    row = cursor.execute(
        """
        SELECT provider.code, snapshot.manifest_sha256, resource.sha256
        FROM football.acquired_resources AS acquired
        JOIN football.acquisition_jobs AS job ON job.id = acquired.acquisition_job_id
        JOIN football.source_resources AS resource ON resource.id = acquired.source_resource_id
        JOIN football.source_snapshots AS snapshot ON snapshot.id = resource.source_snapshot_id
        JOIN football.providers AS provider ON provider.id = snapshot.provider_id
        WHERE acquired.acquisition_job_id = %s
          AND acquired.source_resource_id = %s
          AND job.provider_id = snapshot.provider_id
        """,
        (acquisition_job_id, source_resource_id),
    ).fetchone()
    expected = (
        record.provider_id,
        record.source_snapshot_sha256,
        record.source_resource_sha256,
    )
    if row != expected:
        raise QuarantineRecordStorageError(
            "acquisition job and source resource do not match quarantine evidence"
        )
