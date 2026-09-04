from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from football.ingestion import ResolutionDecisionV1
from football.ingestion.resolution_storage import (
    PostgresResolutionDecisionStoreV1,
    ResolutionDecisionStorageError,
)


def test_store_publishes_and_idempotently_verifies_an_append_only_decision() -> None:
    cursor = _Cursor()
    store = PostgresResolutionDecisionStoreV1()

    first = store.register(cast(Any, cursor), provider_id=_Cursor.PROVIDER_ID, decision=_decision())
    retry = store.register(cast(Any, cursor), provider_id=_Cursor.PROVIDER_ID, decision=_decision())

    assert first.decision_id == _Cursor.DECISION_ID
    assert first.status == "inserted"
    assert retry.decision_id == _Cursor.DECISION_ID
    assert retry.status == "verified_existing"
    assert cursor.stored is not None
    assert cursor.stored[0] == _decision().sha256
    assert cursor.stored[2] == _Cursor.PROVIDER_ID


def test_store_rejects_conflicting_existing_decision_key() -> None:
    cursor = _Cursor(conflicting_existing=True)

    with pytest.raises(ResolutionDecisionStorageError, match="conflicts"):
        PostgresResolutionDecisionStoreV1().register(
            cast(Any, cursor), provider_id=_Cursor.PROVIDER_ID, decision=_decision()
        )


def _decision() -> ResolutionDecisionV1:
    canonical_team_id = "00000000-0000-0000-0000-000000000003"
    return ResolutionDecisionV1(
        decision_id="football-data-uk-team-arsenal-v1",
        subject_type="team",
        provider_id="football_data_uk",
        provider_entity_id="Arsenal",
        evidence_refs=("source-row/1", "crosswalk/2026-09-04"),
        candidate_canonical_ids=(canonical_team_id,),
        rule_version="FootballDataUkStatsBombTeamCrosswalkV1",
        confidence=1.0,
        status="MANUALLY_APPROVED",
        selected_canonical_id=canonical_team_id,
        actor="phase1b-football-data-crosswalk",
        reason="explicit reviewed Football-Data team crosswalk",
        created_at=datetime(2026, 9, 4, 17, 20, tzinfo=UTC),
    )


class _Cursor:
    PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000001")
    DECISION_ID = UUID("00000000-0000-0000-0000-000000000002")

    def __init__(self, *, conflicting_existing: bool = False) -> None:
        self.conflicting_existing = conflicting_existing
        self.stored: tuple[object, ...] | None = None
        self.rowcount = 0
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Cursor:
        if "INSERT INTO football.resolution_decisions" in query:
            if self.stored is None:
                self.stored = params
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, subject_type, provider_id" in query:
            if self.stored is None:
                raise AssertionError("lookup without registration")
            stored = self.stored
            candidate_ids = cast(Any, stored[5]).obj
            evidence_refs = cast(Any, stored[4]).obj
            selected = stored[9]
            if self.conflicting_existing:
                selected = UUID("00000000-0000-0000-0000-000000000099")
            self._row = (
                self.DECISION_ID,
                stored[1],
                stored[2],
                stored[3],
                evidence_refs,
                candidate_ids,
                stored[6],
                stored[7],
                stored[8],
                selected,
                stored[10],
                stored[11],
                stored[12],
                stored[13],
            )
        else:
            raise AssertionError(f"unexpected query: {query}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row
