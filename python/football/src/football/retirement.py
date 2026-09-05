from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from psycopg import Connection

from football.contracts.retirement import ArtifactRetirementEventV1

RetirementRegistrationStatusV1 = Literal["inserted", "verified_existing"]


class ArtifactRetirementError(ValueError):
    """A requested retirement conflicts with stored immutable evidence."""


@dataclass(frozen=True, slots=True)
class RegisteredArtifactRetirementV1:
    event: ArtifactRetirementEventV1
    status: RetirementRegistrationStatusV1


APPROVED_SYNTHETIC_FORECAST_IDS = (
    UUID("01a04fc8-2e57-73b6-93e3-fada57fc8e48"),
    UUID("01a04fc8-d211-7c37-904c-0a039563d937"),
    UUID("01a051c0-2bbb-746a-bf55-49204667e289"),
    UUID("01a051c4-88de-710d-accd-73caca66ccfe"),
    UUID("390d365d-055e-5f98-a29f-5c7409c798cc"),
    UUID("0ffb6be5-3dfc-5a82-b941-de7d9cc01bc6"),
    UUID("9d1a91df-e26c-5fe2-ad67-27d4ac359269"),
    UUID("ac4e45c2-bdb6-573b-91f1-a773d350726f"),
    UUID("01a06fc4-d67b-7ccf-a4f7-b4985e895ee8"),
    UUID("4cb447db-7edd-5ee0-ad61-cce81cd5ad1f"),
    UUID("412ad71a-5b7d-5434-9d16-63c83b94fad6"),
    UUID("42716031-6b19-5fad-8b45-18dfb85238c1"),
    UUID("0eae5c6a-ba99-549c-a95c-763fa7eeaf77"),
)


class PostgresArtifactRetirementStore:
    """Append-only test-only hard-gate exclusions for retained artifacts."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def retire_forecast(
        self,
        forecast_id: UUID,
        *,
        evidence_reference: str,
        recorded_at: datetime,
        code_commit_sha: str,
    ) -> RegisteredArtifactRetirementV1:
        return self.retire_forecasts(
            (forecast_id,),
            evidence_reference=evidence_reference,
            recorded_at=recorded_at,
            code_commit_sha=code_commit_sha,
        )[0]

    def retire_forecasts(
        self,
        forecast_ids: tuple[UUID, ...],
        *,
        evidence_reference: str,
        recorded_at: datetime,
        code_commit_sha: str,
    ) -> tuple[RegisteredArtifactRetirementV1, ...]:
        if not forecast_ids or len(set(forecast_ids)) != len(forecast_ids):
            raise ArtifactRetirementError("artifact retirement IDs must be unique and non-empty")
        with self._connection.transaction(), self._connection.cursor() as cursor:
            registered = tuple(
                self._retire(cursor, forecast_id, evidence_reference, recorded_at, code_commit_sha)
                for forecast_id in forecast_ids
            )
        return registered

    @staticmethod
    def _retire(
        cursor: Any,
        forecast_id: UUID,
        evidence_reference: str,
        recorded_at: datetime,
        code_commit_sha: str,
    ) -> RegisteredArtifactRetirementV1:
        try:
            inserted = cursor.execute(
                """
                INSERT INTO football.artifact_retirement_events
                    (object_kind, object_id, retirement_scope, reason, evidence_reference,
                     recorded_at, code_commit_sha)
                VALUES ('FORECAST', %s, 'TEST_ONLY_HARD_GATE_EXCLUSION',
                        'SYNTHETIC_TEST_LINEAGE', %s, %s, %s)
                ON CONFLICT (object_kind, object_id, retirement_scope, reason) DO NOTHING
                """,
                (forecast_id, evidence_reference, recorded_at, code_commit_sha),
            ).rowcount
        except Exception as error:
            if "foreign key" in str(error).lower():
                raise ArtifactRetirementError(
                    "artifact retirement target is not registered"
                ) from error
            raise
        row = cursor.execute(
            """
            SELECT id, object_kind, object_id, retirement_scope, reason, evidence_reference,
                   recorded_at, code_commit_sha, contract_version
            FROM football.artifact_retirement_events
            WHERE object_kind = 'FORECAST' AND object_id = %s
              AND retirement_scope = 'TEST_ONLY_HARD_GATE_EXCLUSION'
              AND reason = 'SYNTHETIC_TEST_LINEAGE'
            """,
            (forecast_id,),
        ).fetchone()
        if row is None:
            raise ArtifactRetirementError("artifact retirement was not registered")
        row = cast(tuple[object, ...], row)
        event = ArtifactRetirementEventV1(
            retirement_event_id=UUID(str(row[0])),
            object_kind=str(row[1]),  # type: ignore[arg-type]
            object_id=UUID(str(row[2])),
            retirement_scope=str(row[3]),  # type: ignore[arg-type]
            reason=str(row[4]),  # type: ignore[arg-type]
            evidence_reference=str(row[5]),
            recorded_at=cast(datetime, row[6]),
            code_commit_sha=str(row[7]),
            contract_version=str(row[8]),
        )
        if (
            event.evidence_reference != evidence_reference
            or event.code_commit_sha != code_commit_sha
        ):
            raise ArtifactRetirementError("artifact retirement conflicts with immutable history")
        return RegisteredArtifactRetirementV1(
            event=event,
            status="inserted" if inserted == 1 else "verified_existing",
        )


def retire_approved_synthetic_forecasts(
    connection: Connection[Any],
    *,
    evidence_reference: str,
    recorded_at: datetime,
    code_commit_sha: str,
) -> tuple[RegisteredArtifactRetirementV1, ...]:
    with connection.cursor() as cursor:
        rows = tuple(
            cursor.execute(
                """
                SELECT forecast.id, snapshot.source_identity, snapshot.source_revision
                FROM football.baseline_forecasts AS forecast
                JOIN football.source_snapshots AS snapshot
                  ON snapshot.id = forecast.source_snapshot_id
                WHERE forecast.id = ANY(%s)
                ORDER BY forecast.id
                """,
                (list(APPROVED_SYNTHETIC_FORECAST_IDS),),
            )
        )
    if {UUID(str(row[0])) for row in rows} != set(APPROVED_SYNTHETIC_FORECAST_IDS):
        raise ArtifactRetirementError("approved synthetic forecast set is incomplete")
    if any(
        not str(row[1]).startswith("example/open-data/") or str(row[2]) != "b" * 40 for row in rows
    ):
        raise ArtifactRetirementError("approved synthetic forecast lineage conflicts with evidence")
    return PostgresArtifactRetirementStore(connection).retire_forecasts(
        APPROVED_SYNTHETIC_FORECAST_IDS,
        evidence_reference=evidence_reference,
        recorded_at=recorded_at,
        code_commit_sha=code_commit_sha,
    )
