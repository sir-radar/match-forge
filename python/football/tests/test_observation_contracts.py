from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from football.contracts.observation_schema import observation_schema
from football.contracts.observations import (
    OBSERVATION_TYPES,
    EntityReference,
    FixtureObservationV1,
    ObservationError,
    ObservationProvenance,
    ObservationTime,
    ObservationVersions,
    ResultObservationV1,
    ShotObservationV1,
    observation_from_bytes,
)

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
IDENTIFIER = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")


def fixture() -> FixtureObservationV1:
    return FixtureObservationV1(
        provenance=ObservationProvenance("fotmob", "42", IDENTIFIER, IDENTIFIER, "a" * 64),
        time=ObservationTime(observed_at=NOW, acquired_at=NOW, known_at=NOW),
        versions=ObservationVersions(adapter_version="fotmob-v1", normalizer_version="fixtures-v1"),
        fixture=EntityReference("42"),
        competition=EntityReference("47"),
        home_team=EntityReference("1"),
        away_team=EntityReference("2"),
        kickoff_at=NOW + timedelta(days=1),
        status="SCHEDULED",
        kickoff_precision="EXACT",
    )


def test_fixture_round_trip_is_typed_and_deterministic() -> None:
    item = fixture()
    decoded = observation_from_bytes(item.to_bytes())
    assert decoded == item
    assert isinstance(decoded, FixtureObservationV1)
    assert decoded.provenance.source_resource_id == IDENTIFIER
    assert decoded.home_team.canonical_id is None
    assert decoded.to_bytes() == item.to_bytes()
    assert decoded.observation_id == item.observation_id
    assert (
        replace(item, time=replace(item.time, known_at=NOW + timedelta(seconds=1))).sha256
        != item.sha256
    )


def test_fixture_contract_structurally_excludes_target_outcomes() -> None:
    payload = json.loads(fixture().to_bytes())
    payload["home_goals"] = 3
    with pytest.raises(ObservationError):
        observation_from_bytes(json.dumps(payload).encode())


@pytest.mark.parametrize("status", ["AWARDED", "ABANDONED", "CANCELLED"])
def test_non_played_results_retain_status_without_invented_goals(
    status: Literal["AWARDED", "ABANDONED", "CANCELLED"],
) -> None:
    item = ResultObservationV1(
        provenance=fixture().provenance,
        time=fixture().time,
        versions=fixture().versions,
        fixture=fixture().fixture,
        status=status,
        score_basis="UNKNOWN",
    )
    assert observation_from_bytes(item.to_bytes()) == item
    assert item.home_goals is None and item.away_goals is None


def test_time_rejects_backdated_knowledge_and_naive_timestamps() -> None:
    with pytest.raises(ObservationError, match="known_at"):
        replace(fixture(), time=replace(fixture().time, known_at=NOW - timedelta(seconds=1)))
    with pytest.raises(ObservationError, match="timezone"):
        replace(fixture(), kickoff_at=NOW.replace(tzinfo=None))


def test_malformed_or_unknown_contracts_are_rejected() -> None:
    for payload in (b"null", b"{}", b'{"contract":"FutureObservationV99"}', b'{"x":NaN}'):
        with pytest.raises(ObservationError):
            observation_from_bytes(payload)


def test_checked_in_schema_matches_typed_contracts() -> None:
    path = Path("schemas/contracts/resource-observations-v1.schema.json")
    assert json.loads(path.read_text()) == observation_schema()
    assert len(OBSERVATION_TYPES) == 16


def test_scores_are_complete_and_cannot_be_boolean_or_negative() -> None:
    result = ResultObservationV1(
        provenance=fixture().provenance,
        time=fixture().time,
        versions=fixture().versions,
        fixture=fixture().fixture,
        status="FINISHED",
        score_basis="REGULATION_90",
        home_goals=0,
        away_goals=0,
    )
    for home, away in ((1, None), (-1, 0), (True, 0)):
        payload = json.loads(result.to_bytes())
        payload.update(home_goals=home, away_goals=away)
        with pytest.raises(ObservationError):
            observation_from_bytes(json.dumps(payload).encode())


REF = {"provider_native_id": "42", "canonical_id": None}
RESOURCE_EXAMPLES: dict[str, dict[str, object]] = {
    "FixtureObservationV1": {},
    "ResultObservationV1": {
        "fixture": REF,
        "status": "FINISHED",
        "score_basis": "REGULATION_90",
        "home_goals": 2,
        "away_goals": 0,
    },
    "CompetitionObservationV1": {"competition": REF, "name": "Premier League"},
    "TeamObservationV1": {"team": REF, "name": "United"},
    "PlayerObservationV1": {"player": REF, "name": "Player"},
    "CoachObservationV1": {"coach": REF, "team": REF},
    "LineupObservationV1": {
        "fixture": REF,
        "team": REF,
        "lineup_mode": "CONFIRMED",
        "players": [{"player": REF, "role": "STARTER"}],
    },
    "AvailabilityObservationV1": {
        "team": REF,
        "player": REF,
        "availability_type": "INJURY",
        "availability_state": "UNAVAILABLE_INJURY",
    },
    "FormationObservationV1": {
        "fixture": REF,
        "team": REF,
        "formation": "4-3-3",
        "mode": "CONFIRMED",
    },
    "EventObservationV1": {"fixture": REF, "event_type": "CORNER", "minute": 0},
    "ShotObservationV1": {
        "fixture": REF,
        "team": REF,
        "expected_goals": 1,
        "x_norm": 0,
        "y_norm": 1,
        "is_penalty": False,
    },
    "ExpectedGoalsObservationV1": {
        "fixture": REF,
        "team": REF,
        "expected_goals": 2,
        "scope": "MATCH_TOTAL",
    },
    "TeamStatisticObservationV1": {
        "fixture": REF,
        "team": REF,
        "period": "FULL_TIME",
        "corners": 0,
    },
    "PlayerStatisticObservationV1": {
        "fixture": REF,
        "team": REF,
        "player": REF,
        "minutes_played": 90,
    },
    "StandingObservationV1": {
        "competition": REF,
        "team": REF,
        "season_label": "2026/27",
        "rank": 1,
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "goals_for": 0,
        "goals_against": 0,
        "points": -3,
    },
    "OddsObservationV1": {
        "fixture": REF,
        "bookmaker": "source-bookmaker",
        "market": "1X2",
        "home_decimal": 2,
        "draw_decimal": 3.5,
        "away_decimal": 4,
    },
}


def resource_payload(contract: str) -> dict[str, object]:
    base = fixture().to_dict()
    if contract == "FixtureObservationV1":
        return base
    return {
        "contract": contract,
        "provenance": base["provenance"],
        "time": base["time"],
        "versions": base["versions"],
        **RESOURCE_EXAMPLES[contract],
    }


@pytest.mark.parametrize("contract", RESOURCE_EXAMPLES)
def test_every_resource_has_stable_typed_round_trip(contract: str) -> None:
    item = observation_from_bytes(json.dumps(resource_payload(contract)).encode())
    assert contract == item.CONTRACT
    assert observation_from_bytes(item.to_bytes()) == item
    assert observation_from_bytes(item.to_bytes()).sha256 == item.sha256
    assert {model.CONTRACT for model in OBSERVATION_TYPES} == set(RESOURCE_EXAMPLES)


def test_equivalent_numbers_and_timezones_have_identical_identity() -> None:
    payload = resource_payload("ShotObservationV1")
    first = observation_from_bytes(json.dumps(payload).encode())
    payload["expected_goals"] = 1.0
    second = observation_from_bytes(json.dumps(payload).encode())
    assert first.to_bytes() == second.to_bytes()
    item = fixture()
    offset = timezone(timedelta(hours=1))
    assert replace(item, kickoff_at=item.kickoff_at.astimezone(offset)).sha256 == item.sha256
    shot = ShotObservationV1(
        provenance=item.provenance,
        time=item.time,
        versions=item.versions,
        fixture=item.fixture,
        team=item.home_team,
        expected_goals=1,
    )
    assert observation_from_bytes(shot.to_bytes()).sha256 == shot.sha256


@pytest.mark.parametrize(
    ("contract", "changes"),
    [
        ("ResultObservationV1", {"home_goals": None, "away_goals": None}),
        ("ShotObservationV1", {"x_norm": None}),
        ("ShotObservationV1", {"expected_goals": 1.01}),
        ("ShotObservationV1", {"x_norm": -0.1}),
        ("ExpectedGoalsObservationV1", {"scope": "SHOT", "shot": REF}),
        ("ExpectedGoalsObservationV1", {"scope": "SHOT", "expected_goals": 0.2}),
        ("LineupObservationV1", {"players": []}),
        ("LineupObservationV1", {"players": [{"player": REF, "role": "STARTER"}] * 2}),
        ("TeamStatisticObservationV1", {"corners": None}),
        ("TeamStatisticObservationV1", {"possession": 101}),
        ("PlayerStatisticObservationV1", {"minutes_played": None}),
        ("StandingObservationV1", {"rank": 0}),
        ("OddsObservationV1", {"home_decimal": 0.9}),
        ("EventObservationV1", {"event_type": "UNRECOGNIZED"}),
        ("FixtureObservationV1", {"away_team": {"provider_native_id": "1"}}),
    ],
)
def test_resource_boundaries_reject_invalid_values(
    contract: str,
    changes: dict[str, object],
) -> None:
    payload = resource_payload(contract)
    payload.update(changes)
    with pytest.raises(ObservationError):
        observation_from_bytes(json.dumps(payload).encode())


def test_unknown_native_identity_requires_traceable_source_locator() -> None:
    item = fixture()
    with pytest.raises(ObservationError, match="locator"):
        replace(item, provenance=replace(item.provenance, provider_native_id=None))
    located = replace(
        item,
        provenance=replace(
            item.provenance,
            provider_native_id=None,
            source_record_key="csv:row:2",
        ),
    )
    assert observation_from_bytes(located.to_bytes()) == located
    assert located.home_team.canonical_id is None


def test_invalid_provenance_versions_and_intervals_are_rejected() -> None:
    item = fixture()
    for changes in ({"source_sha256": "invalid"}, {"provider_native_id": ""}):
        payload = json.loads(item.to_bytes())
        payload["provenance"].update(changes)
        with pytest.raises(ObservationError):
            observation_from_bytes(json.dumps(payload).encode())
    with pytest.raises(ObservationError):
        replace(item, versions=replace(item.versions, adapter_version=""))
    with pytest.raises(ObservationError, match="interval"):
        replace(item, time=replace(item.time, valid_from=NOW, valid_to=NOW))
    with pytest.raises(ObservationError):
        observation_from_bytes(b'{"contract":"a","contract":"b"}')
