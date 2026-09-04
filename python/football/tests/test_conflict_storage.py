from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from football.ingestion import ConflictRecordV1
from football.ingestion.conflict_storage import (
    PostgresReconciliationConflictStoreV1,
    ReconciliationConflictStorageError,
)


def test_store_publishes_and_verifies_conflict_without_a_selected_winner() -> None:
    cursor = _Cursor()
    store = PostgresReconciliationConflictStoreV1()

    first = store.register(cast(Any, cursor), _conflict())
    retry = store.register(cast(Any, cursor), _conflict())

    assert first.conflict_id == _Cursor.CONFLICT_ID
    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert cursor.stored is not None
    assert cursor.stored[0] == _conflict().sha256
    assert cursor.stored[5] is None


def test_store_rejects_a_conflicting_existing_record() -> None:
    with pytest.raises(ReconciliationConflictStorageError, match="conflicts"):
        PostgresReconciliationConflictStoreV1().register(
            cast(Any, _Cursor(conflicting_existing=True)), _conflict()
        )


def _conflict() -> ConflictRecordV1:
    return ConflictRecordV1(
        conflict_id="football-data-score-conflict-1",
        subject_type="match:full_time_score",
        observation_refs=("statsbomb:match/1", "football_data_uk:record/1"),
        policy_version="football-data-p1-score-v1",
        disposition="QUARANTINED",
        selected_observation_ref=None,
        reason="field observations disagree; no automatic winner",
        created_at=datetime(2026, 9, 4, 17, 32, tzinfo=UTC),
    )


class _Cursor:
    CONFLICT_ID = UUID("00000000-0000-0000-0000-000000000001")

    def __init__(self, *, conflicting_existing: bool = False) -> None:
        self.conflicting_existing = conflicting_existing
        self.stored: tuple[object, ...] | None = None
        self.rowcount = 0
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Cursor:
        if "INSERT INTO football.reconciliation_conflicts" in query:
            if self.stored is None:
                self.stored = params
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, subject_type, observation_refs" in query:
            assert self.stored is not None
            stored = self.stored
            reason = "conflict" if self.conflicting_existing else stored[6]
            self._row = (
                self.CONFLICT_ID,
                stored[1],
                cast(Any, stored[2]).obj,
                stored[3],
                stored[4],
                stored[5],
                reason,
                stored[7],
            )
        else:
            raise AssertionError(f"unexpected query: {query}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row
