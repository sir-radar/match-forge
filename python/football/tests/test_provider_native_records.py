from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from football.providers.fotmob import parse_fotmob_fixture
from football.providers.native.api_football import ApiFootballFixture
from football.providers.native.cli import main
from football.providers.native.fotmob import FotmobFixture
from football.providers.native.models import NATIVE_MODELS
from football.providers.native.openfootball import OpenFootballMatch
from football.providers.native.pitchapi import PitchApiMatch
from football.providers.native.reader import NativeRecordError, native_record
from football.providers.pitchapi import parse_pitchapi_match

FOTMOB_TEAM: dict[str, object] = {"id": 8455, "name": "Chelsea", "score": 0}
PITCH_TEAM: dict[str, object] = {"id": "t_9aB2xQ", "name": "Home"}
API_TEAM: dict[str, object] = {"id": 33, "name": "United"}
ORG_TEAM: dict[str, object] = {"id": 57, "name": "Arsenal"}
FOTMOB_FIXTURE: dict[str, object] = {
    "id": 5795427,
    "home": FOTMOB_TEAM,
    "away": {"id": "10204", "name": "Brighton"},
    "status": {
        "utcTime": "2026-10-09T20:00:00.000Z",
        "started": False,
        "finished": False,
        "cancelled": False,
        "reason": {"short": "FUTURE_CODE"},
    },
}
PITCH_MATCH: dict[str, object] = {
    "id": "m_B8x2K9",
    "home_team": PITCH_TEAM,
    "away_team": {"id": "t_7YtX4q", "name": "Away"},
    "time_utc": "2026-10-09T21:00:00+01:00",
    "status": "Not_Started",
    "score_home": None,
    "score_away": None,
}
API_FIXTURE: dict[str, object] = {
    "fixture": {"id": 42, "date": "2026-10-16T18:00:00Z", "status": {"short": "NS"}},
    "league": {"id": 39, "season": 2026},
    "teams": {"home": API_TEAM, "away": {"id": 34}},
    "goals": {"home": None, "away": None},
}
OPEN_MATCH: dict[str, object] = {
    "date": "2026-10-16",
    "team1": "United",
    "team2": {"title": "City"},
}

EXAMPLES: dict[str, dict[str, object]] = {
    "FotmobTeam": FOTMOB_TEAM,
    "FotmobPlayer": {"id": 1, "name": "Player"},
    "FotmobFixture": FOTMOB_FIXTURE,
    "FotmobCompetition": {"primaryId": "47", "name": "League", "matches": [FOTMOB_FIXTURE]},
    "FotmobEvent": {"type": "Goal", "eventId": 1, "time": 0, "isHome": False},
    "FotmobShot": {"teamId": 8455, "expectedGoals": 0.0, "isOnTarget": False},
    "FotmobStatistic": {"key": "BallPossesion", "stats": ["55%", "45%"]},
    "FotmobLineup": {"home": {"starters": [{"id": 1}]}},
    "PitchApiTeam": PITCH_TEAM,
    "PitchApiCompetition": {"id": "l_0bfbkO", "name": "League"},
    "PitchApiMatch": PITCH_MATCH,
    "PitchApiEvent": {"event_type": "goal", "team_id": "t_9aB2xQ", "minute": 0},
    "PitchApiShot": {"team_id": "t_9aB2xQ", "expected_goals": None},
    "PitchApiStatistic": {"key": "possession", "home": "55%", "away": "45%"},
    "ApiFootballTeam": API_TEAM,
    "ApiFootballPlayer": {"id": 1, "pos": "G", "grid": None},
    "ApiFootballCoach": {"id": None, "name": None},
    "ApiFootballCompetition": {"league": {"id": 39}, "seasons": [{"year": 2026}]},
    "ApiFootballFixture": API_FIXTURE,
    "ApiFootballInjury": {
        "team": API_TEAM,
        "player": {"id": 1, "type": "Missing Fixture", "reason": "Injury"},
    },
    "ApiFootballLineup": {
        "team": API_TEAM,
        "formation": None,
        "coach": {"id": None},
        "startXI": [{"player": {"id": 1, "pos": "G"}}],
        "substitutes": [],
    },
    "ApiFootballStatistic": {
        "team": API_TEAM,
        "statistics": [{"type": "Ball Possession", "value": "55%"}],
    },
    "ApiFootballStanding": {"rank": 1, "team": API_TEAM, "points": -3, "all": {}},
    "FootballDataOrgTeam": ORG_TEAM,
    "FootballDataOrgCompetition": {"id": 2021, "code": "PL"},
    "FootballDataOrgFixture": {
        "id": 42,
        "utcDate": "2026-10-16T18:00:00Z",
        "status": "TIMED",
        "competition": {"id": 2021, "code": "PL"},
        "homeTeam": ORG_TEAM,
        "awayTeam": {"id": None, "name": None},
        "score": {"duration": "REGULAR", "fullTime": {"home": None, "away": None}},
    },
    "FootballDataOrgStanding": {
        "position": 1,
        "team": ORG_TEAM,
        "playedGames": 0,
        "won": 0,
        "draw": 0,
        "lost": 0,
        "points": -3,
        "goalsFor": 0,
        "goalsAgainst": 0,
        "goalDifference": 0,
    },
    "OpenFootballMatch": OPEN_MATCH,
    "OpenFootballCompetition": {"matches": [OPEN_MATCH]},
}


@pytest.mark.parametrize("name", EXAMPLES)
def test_native_models_preserve_all_values_and_additive_fields(name: str) -> None:
    payload = {**EXAMPLES[name], "unmodeled": {"nested": [None, False, 0, ""]}}
    record = native_record(NATIVE_MODELS[name], payload)
    assert record == payload
    assert record is not payload
    record["unmodeled"]["nested"].append("changed")
    assert payload["unmodeled"] == {"nested": [None, False, 0, ""]}
    assert set(EXAMPLES) == set(NATIVE_MODELS)


def test_native_fields_stay_provider_specific_without_implied_identity() -> None:
    fotmob = native_record(FotmobFixture, FOTMOB_FIXTURE)
    pitch = native_record(PitchApiMatch, PITCH_MATCH)
    api = native_record(ApiFootballFixture, API_FIXTURE)
    opened = native_record(OpenFootballMatch, OPEN_MATCH)
    assert isinstance(fotmob["id"], int)
    assert isinstance(fotmob["away"]["id"], str)
    assert fotmob["status"]["reason"] == {"short": "FUTURE_CODE"}
    assert pitch["status"] == "Not_Started"
    assert pitch["time_utc"] == "2026-10-09T21:00:00+01:00"
    assert api["goals"] == {"home": None, "away": None}
    assert "score" not in opened and "time" not in opened
    assert "id" not in opened and "canonical_id" not in opened


@pytest.mark.parametrize(
    ("name", "changes"),
    [
        ("FotmobShot", {"teamId": True}),
        ("FotmobStatistic", {"stats": [False]}),
        ("PitchApiMatch", {"id": 42}),
        ("PitchApiMatch", {"score_home": "0"}),
        ("ApiFootballFixture", {"goals": {"home": False, "away": 0}}),
        ("ApiFootballLineup", {"startXI": [{"player": {"id": "1"}}]}),
        ("FootballDataOrgFixture", {"homeTeam": None}),
        ("OpenFootballMatch", {"score": {"ft": [True, 0]}}),
    ],
)
def test_wrong_native_types_are_rejected(name: str, changes: dict[str, object]) -> None:
    payload = {**EXAMPLES[name], **changes}
    with pytest.raises(NativeRecordError):
        native_record(NATIVE_MODELS[name], payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "bad"}, b"bytes"])
def test_additive_fields_must_still_be_finite_json(value: Any) -> None:
    with pytest.raises(NativeRecordError):
        native_record(OpenFootballMatch, {**OPEN_MATCH, "extra": value})


def test_missing_required_native_fields_are_not_filled() -> None:
    with pytest.raises(NativeRecordError, match="required native field"):
        native_record(PitchApiMatch, {"id": "m_B8x2K9"})


def test_readers_accept_immutable_mappings_without_mutating_them() -> None:
    source = MappingProxyType(FOTMOB_FIXTURE)
    assert native_record(FotmobFixture, source) == FOTMOB_FIXTURE
    assert parse_fotmob_fixture(source) == FOTMOB_FIXTURE


def test_operational_native_readers_preserve_ids_status_and_missing_scores() -> None:
    assert parse_fotmob_fixture(FOTMOB_FIXTURE) == FOTMOB_FIXTURE
    assert parse_pitchapi_match(PITCH_MATCH) == PITCH_MATCH
    with pytest.raises(ValueError, match="identifier"):
        parse_fotmob_fixture({**FOTMOB_FIXTURE, "id": True})
    with pytest.raises(ValueError, match="identifier"):
        parse_pitchapi_match({**PITCH_MATCH, "id": 42})


def test_native_cli_records_exact_source_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = json.dumps(FOTMOB_FIXTURE, indent=2).encode()
    source = tmp_path / "match.json"
    source.write_bytes(raw)
    assert main(["--model", "FotmobFixture", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["record"] == FOTMOB_FIXTURE
    assert result["source_sha256"] == hashlib.sha256(raw).hexdigest()
    source.write_bytes(b'{"date":"a","date":"b"}')
    with pytest.raises(NativeRecordError, match="duplicate"):
        main(["--model", "OpenFootballMatch", str(source)])
