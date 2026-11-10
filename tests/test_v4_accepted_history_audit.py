from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from football.product.domain import fixture_identity
from football.providers.native.api_football import ApiFootballFixture
from football.providers.native.reader import native_record

from scripts.inspect_v4_accepted_history import verify_result


def evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    kickoff = datetime(2026, 10, 3, 15, tzinfo=UTC)
    competition, home, away = UUID(int=1), UUID(int=2), UUID(int=3)
    history = {
        "fixture_id": str(fixture_identity(competition, "2027", kickoff, home, away)),
        "competition_id": str(competition),
        "home_team_id": str(home),
        "away_team_id": str(away),
        "kickoff_at": kickoff.isoformat(),
        "home_goals": 2,
        "away_goals": 0,
        "source_kickoff_precision": "EXACT",
    }
    row = {
        "fixture": {
            "id": 42,
            "date": kickoff.isoformat(),
            "timestamp": int(kickoff.timestamp()),
            "timezone": "UTC",
            "status": {"short": "FT", "elapsed": 90},
        },
        "league": {"id": 399, "season": 2027},
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "goals": {"home": 2, "away": 0},
        "score": {
            "fulltime": {"home": 2, "away": 0},
            "halftime": {"home": 1, "away": 0},
            "extratime": {"home": None, "away": None},
            "penalty": {"home": None, "away": None},
        },
    }
    return row, history


def test_accepted_regulation_pair_reproduces_original_fixture_identity() -> None:
    row, history = evidence()
    verify_result(native_record(ApiFootballFixture, row), history)


@pytest.mark.parametrize("short", ["NS", "HT", "AET", "PEN", "ABD", "AWD"])
def test_incomplete_or_nonregulation_score_is_not_research_qualified(short: str) -> None:
    row, history = evidence()
    row["fixture"]["status"]["short"] = short
    with pytest.raises(ValueError, match="completed regulation"):
        verify_result(native_record(ApiFootballFixture, row), history)


@pytest.mark.parametrize(
    "mutation", ["epoch", "fulltime", "goals", "extra", "shootout", "identity"]
)
def test_contradictory_source_evidence_fails_closed(mutation: str) -> None:
    row, history = evidence()
    if mutation == "epoch":
        row["fixture"]["timestamp"] += 60
    elif mutation in {"fulltime", "goals"}:
        (row["goals"] if mutation == "goals" else row["score"]["fulltime"])["home"] = 3
    elif mutation in {"extra", "shootout"}:
        row["score"]["extratime" if mutation == "extra" else "penalty"]["home"] = 0
    else:
        history["fixture_id"] = str(UUID(int=4))
    with pytest.raises(ValueError):
        verify_result(native_record(ApiFootballFixture, row), history)


def test_date_only_history_cannot_be_counted_as_utc_qualified() -> None:
    row, history = evidence()
    history["source_kickoff_precision"] = "DATE_ONLY"
    with pytest.raises(ValueError, match="exact"):
        verify_result(native_record(ApiFootballFixture, row), history)


def test_timezone_metadata_must_agree_with_source_date_offset() -> None:
    row, history = evidence()
    row["fixture"]["date"] = "2026-10-03T16:00:00+01:00"
    with pytest.raises(ValueError, match="UTC"):
        verify_result(native_record(ApiFootballFixture, row), history)
