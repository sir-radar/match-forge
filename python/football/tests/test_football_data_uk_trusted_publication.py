from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, cast
from uuid import UUID

import pytest
from football.ingestion.registration import RegisteredSource
from football.providers.football_data_uk_publication import (
    FootballDataUkPostgresTrustedPublicationV1,
    FootballDataUkTrustedP1MatchV1,
    FootballDataUkTrustedPublicationError,
    RegisteredFootballDataUkTrustedPublicationV1,
)


def test_publication_persists_a_trusted_score_and_change_set_idempotently() -> None:
    cursor = _Cursor()
    first = _register(cursor)
    retry = _register(cursor)

    assert first.observation_ids == (_Cursor.OBSERVATION_ID,)
    assert first.change_set_id == _Cursor.CHANGE_SET_ID
    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert cursor.observation is not None
    assert cursor.observation[9:11] == ("completed", "completed")
    assert cursor.change_set is not None
    assert cursor.change_set[2] == "published"
    assert cast(Any, cursor.change_set[3]).obj["added_observation_refs"] == [
        f"match_observation:{_Cursor.OBSERVATION_ID}"
    ]


def test_publication_rejects_a_match_without_its_reviewed_resolution() -> None:
    with pytest.raises(FootballDataUkTrustedPublicationError, match="resolution decision"):
        _register(_Cursor(resolved=False))


def test_publication_rejects_conflicting_existing_observation() -> None:
    with pytest.raises(FootballDataUkTrustedPublicationError, match="observation conflicts"):
        _register(_Cursor(conflicting_observation=True))


def _register(cursor: _Cursor) -> RegisteredFootballDataUkTrustedPublicationV1:
    return FootballDataUkPostgresTrustedPublicationV1().register(
        cast(Any, cursor),
        sync_run_id=_Cursor.SYNC_RUN_ID,
        source=_source(),
        source_path="mmz4281/1516/E0.csv",
        matches=(_match(),),
        change_set_id="football-data-uk-p1-trusted-publication-v1",
        published_at=datetime(2026, 9, 4, 18, tzinfo=UTC),
        quality_policy_version="test-quality-v1",
    )


def _source() -> RegisteredSource:
    return RegisteredSource(
        provider_id=_Cursor.PROVIDER_ID,
        snapshot_id=_Cursor.SNAPSHOT_ID,
        resource_ids={"mmz4281/1516/E0.csv": _Cursor.RESOURCE_ID},
    )


def _match() -> FootballDataUkTrustedP1MatchV1:
    return FootballDataUkTrustedP1MatchV1(
        canonical_match_id=UUID("00000000-0000-0000-0000-000000000101"),
        provider_match_ref="football_data_uk/mmz4281/1516/E0.csv/record/1",
        provider_match_date=date(2015, 8, 8),
        provider_local_kickoff_time=time(15),
        canonical_home_team_id=UUID("00000000-0000-0000-0000-000000000102"),
        canonical_away_team_id=UUID("00000000-0000-0000-0000-000000000103"),
        full_time_home_goals=0,
        full_time_away_goals=1,
        resolution_decision_key="a" * 64,
    )


class _Cursor:
    PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000001")
    SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000002")
    RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000003")
    SYNC_RUN_ID = UUID("00000000-0000-0000-0000-000000000004")
    OBSERVATION_ID = UUID("00000000-0000-0000-0000-000000000005")
    CHANGE_SET_ID = UUID("00000000-0000-0000-0000-000000000006")

    def __init__(self, *, resolved: bool = True, conflicting_observation: bool = False) -> None:
        self.resolved = resolved
        self.conflicting_observation = conflicting_observation
        self.observation: tuple[object, ...] | None = None
        self.change_set: tuple[object, ...] | None = None
        self.rowcount = 0
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Cursor:
        if "SELECT provider.code, resource.sha256" in query:
            self._row = (
                "football_data_uk",
                "a" * 64,
                datetime(2026, 9, 4, 16, 20, tzinfo=UTC),
            )
        elif "SELECT status, selected_canonical_id" in query:
            match = _match()
            self._row = (
                (
                    "AUTO_ACCEPTED",
                    match.canonical_match_id,
                    "FootballDataUkPhase1BMatchResolutionV1",
                    match.provider_match_ref,
                )
                if self.resolved
                else None
            )
        elif "INSERT INTO football.match_observations" in query:
            if self.observation is None:
                self.observation = params
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, match_id, provider_id" in query:
            assert self.observation is not None
            values = self.observation
            if self.conflicting_observation:
                values = (*values[:7], 9, *values[8:])
            self._row = (self.OBSERVATION_ID, *values)
        elif "INSERT INTO football.canonical_change_sets" in query:
            if self.change_set is None:
                self.change_set = params
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, sync_run_id, change_key" in query:
            assert self.change_set is not None
            values = self.change_set
            self._row = (
                self.CHANGE_SET_ID,
                values[0],
                values[1],
                values[2],
                cast(Any, values[3]).obj,
                values[4],
            )
        else:
            raise AssertionError(f"unexpected query: {query}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row
