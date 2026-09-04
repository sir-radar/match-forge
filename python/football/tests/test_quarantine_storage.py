from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from football.ingestion import QuarantineRecordV1
from football.ingestion.quarantine_storage import (
    PostgresQuarantineRecordStoreV1,
    QuarantineRecordStorageError,
)


def test_store_persists_the_p1_conflict_as_an_open_quarantine_and_verifies_retry() -> None:
    cursor = _Cursor()
    store = PostgresQuarantineRecordStoreV1()

    first = store.register(
        cast(Any, cursor),
        acquisition_job_id=_Cursor.JOB_ID,
        source_resource_id=_Cursor.RESOURCE_ID,
        record=_p1_record(),
    )
    retry = store.register(
        cast(Any, cursor),
        acquisition_job_id=_Cursor.JOB_ID,
        source_resource_id=_Cursor.RESOURCE_ID,
        record=_p1_record(),
    )

    assert first.quarantine_record_id == _Cursor.QUARANTINE_ID
    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert cursor.stored is not None
    assert cursor.stored[5] == "open"
    assert cast(Any, cursor.stored[4]).obj["status"] == "NEEDS_REVIEW"


def test_store_rejects_a_resource_not_linked_to_the_acquisition_job() -> None:
    with pytest.raises(QuarantineRecordStorageError, match="do not match"):
        PostgresQuarantineRecordStoreV1().register(
            cast(Any, _Cursor(linked=False)),
            acquisition_job_id=_Cursor.JOB_ID,
            source_resource_id=_Cursor.RESOURCE_ID,
            record=_p1_record(),
        )


def test_store_rejects_conflicting_existing_quarantine_evidence() -> None:
    with pytest.raises(QuarantineRecordStorageError, match="conflicts"):
        PostgresQuarantineRecordStoreV1().register(
            cast(Any, _Cursor(conflicting_existing=True)),
            acquisition_job_id=_Cursor.JOB_ID,
            source_resource_id=_Cursor.RESOURCE_ID,
            record=_p1_record(),
        )


def test_store_defers_terminal_quarantine_transitions_to_reprocessing() -> None:
    with pytest.raises(QuarantineRecordStorageError, match="only active"):
        PostgresQuarantineRecordStoreV1().register(
            cast(Any, _Cursor()),
            acquisition_job_id=_Cursor.JOB_ID,
            source_resource_id=_Cursor.RESOURCE_ID,
            record=replace(_p1_record(), status="RESOLVED"),
        )


def _p1_record() -> QuarantineRecordV1:
    return QuarantineRecordV1(
        quarantine_id="football-data-uk-p1-synthetic-score-conflict-v1",
        provider_id="football_data_uk",
        resource_identity=(
            "football_data_uk/mmz4281/1516/E0.csv/sha256/"
            "bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085"
        ),
        source_snapshot_sha256="507d51f57ebcda6565d5877823cd57f12720fe7f26c02a2e279f26691843f955",
        source_resource_sha256="bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085",
        canonical_candidate_id=None,
        reason_code="CONFLICT_UNRESOLVED",
        details={
            "conflict_id": "01a06e50-3756-7836-b66f-92e2c4bc76d9",
            "conflict_key": "2f76ac98a735a08a0d0720d6dfb8f9231473ddf81c5e104af3d35e105218aad6",
            "observation_refs": [
                "statsbomb:match/fixture",
                "football_data_uk:record/synthetic-fixture",
            ],
            "score_pairs": [[1, 0], [1, 1]],
        },
        policy_version="FootballDataUkPhase1BScoreReconciliationV1",
        first_seen_at=datetime(2026, 9, 4, 17, 32, tzinfo=UTC),
        last_seen_at=datetime(2026, 9, 4, 17, 32, tzinfo=UTC),
        attempt_count=1,
        status="NEEDS_REVIEW",
    )


class _Cursor:
    JOB_ID = UUID("00000000-0000-0000-0000-000000000001")
    RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000002")
    QUARANTINE_ID = UUID("00000000-0000-0000-0000-000000000003")

    def __init__(self, *, linked: bool = True, conflicting_existing: bool = False) -> None:
        self.linked = linked
        self.conflicting_existing = conflicting_existing
        self.stored: tuple[object, ...] | None = None
        self.rowcount = 0
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Cursor:
        if "SELECT provider.code" in query:
            self._row = (
                (
                    "football_data_uk",
                    "507d51f57ebcda6565d5877823cd57f12720fe7f26c02a2e279f26691843f955",
                    "bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085",
                )
                if self.linked
                else None
            )
        elif "INSERT INTO football.quarantine_records" in query:
            if self.stored is None:
                self.stored = params
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, acquisition_job_id, source_resource_id" in query:
            assert self.stored is not None
            details = cast(Any, self.stored[4]).obj
            if self.conflicting_existing:
                details = {**details, "attempt_count": 2}
            self._row = (
                self.QUARANTINE_ID,
                self.stored[0],
                self.stored[1],
                self.stored[2],
                self.stored[3],
                details,
                self.stored[5],
                self.stored[6],
                self.stored[7],
            )
        else:
            raise AssertionError(f"unexpected query: {query}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row
