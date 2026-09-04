from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from football.ingestion.conflicts import ConflictRecordV1

ReconciliationConflictRegistrationStatusV1 = Literal["inserted", "verified_existing"]


class ReconciliationConflictStorageError(ValueError):
    """A persisted reconciliation conflict conflicts with immutable evidence."""


@dataclass(frozen=True, slots=True)
class RegisteredReconciliationConflictV1:
    conflict_id: UUID
    conflict_key: str
    status: ReconciliationConflictRegistrationStatusV1


class PostgresReconciliationConflictStoreV1:
    """Persist conflict records append-only; never choose a winner on retry."""

    def register(
        self, cursor: Cursor[Any], conflict: ConflictRecordV1
    ) -> RegisteredReconciliationConflictV1:
        values = (
            conflict.sha256,
            conflict.subject_type,
            Jsonb(list(conflict.observation_refs)),
            conflict.policy_version,
            conflict.disposition,
            conflict.selected_observation_ref,
            conflict.reason,
            conflict.created_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.reconciliation_conflicts
                (conflict_key, subject_type, observation_refs, policy_version, disposition,
                 selected_observation_ref, reason, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (conflict_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, subject_type, observation_refs, policy_version, disposition,
                   selected_observation_ref, reason, created_at
            FROM football.reconciliation_conflicts
            WHERE conflict_key = %s
            """,
            (conflict.sha256,),
        ).fetchone()
        expected = values[1:2] + (list(conflict.observation_refs),) + values[3:]
        if row is None or row[1:] != expected:
            raise ReconciliationConflictStorageError(
                "reconciliation conflict key conflicts with immutable evidence"
            )
        status: ReconciliationConflictRegistrationStatusV1 = (
            "inserted" if inserted == 1 else "verified_existing"
        )
        return RegisteredReconciliationConflictV1(
            conflict_id=UUID(str(row[0])), conflict_key=conflict.sha256, status=status
        )
