"""Public presentation features keep history windows and censored target outcomes explicit."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from football.product.public_context import context_features


def source() -> dict[str, Any]:
    kickoff = datetime(2026, 10, 20, 12, tzinfo=UTC)
    return {
        "fixture_id": "target",
        "home_team_id": "home",
        "away_team_id": "away",
        "kickoff_at": kickoff.isoformat(),
        "history": [
            {
                "fixture_id": str(index),
                "kickoff_at": (kickoff - timedelta(days=index + 1)).isoformat(),
                "home_team_id": "home" if index % 2 == 0 else "away",
                "away_team_id": "away" if index % 2 == 0 else "home",
                "home_team": "Home" if index % 2 == 0 else "Away",
                "away_team": "Away" if index % 2 == 0 else "Home",
                "home_goals": 2,
                "away_goals": 1,
                "home_xg": None,
                "away_xg": None,
            }
            for index in range(12)
        ],
        "coaches": [
            {
                "team_id": "home",
                "coach_id": "coach",
                "prior_lineups": [
                    {"kickoff_at": (kickoff - timedelta(days=3)).isoformat()},
                    {"kickoff_at": (kickoff - timedelta(days=1)).isoformat()},
                ],
            }
        ],
        "upcoming": [
            {"team_id": "home", "next_kickoff": (kickoff + timedelta(days=4)).isoformat()}
        ],
    }


def test_features_use_five_form_ten_meetings_and_existing_rest_helper() -> None:
    inputs = source()
    original = deepcopy(inputs)
    report = context_features(inputs)
    assert inputs == original
    assert len(report["home_form"]) == len(report["away_form"]) == 5
    assert len(report["h2h"]) == 10 and report["h2h_summary"]["home_wins"] == 10
    assert report["home_form"][1]["result"] == "L"
    assert report["away_form"][1]["result"] == "W"
    assert report["home_team_statistics"]["goals_for"] == 8
    assert report["rest_context"]["home"] == {
        "days_since_last_match": 1,
        "matches_last_3_days": 3,
        "matches_last_7_days": 7,
        "matches_last_14_days": 12,
        "matches_last_30_days": 12,
        "days_to_next_match": 4,
    }
    assert report["coach_context"] == [
        {
            "team_id": "home",
            "coach_id": "coach",
            "coach_tenure_days": 3,
            "matches_under_coach": 2,
            "coach_changed_recently": True,
        }
    ]


def test_target_fixture_is_rejected_before_calculations() -> None:
    inputs = source()
    inputs["history"][0]["fixture_id"] = "target"
    with pytest.raises(ValueError, match="target outcomes"):
        context_features(inputs)


def test_absent_history_keeps_unknown_statistics_and_rest_days() -> None:
    inputs = source()
    inputs.update(history=[], coaches=[], upcoming=[])
    report = context_features(inputs)
    assert report["home_form"] == report["away_form"] == report["h2h"] == []
    assert report["home_team_statistics"] is None and report["away_team_statistics"] is None
    assert report["h2h_summary"]["meetings"] == 0
    assert report["rest_context"]["home"]["days_since_last_match"] is None
    assert report["rest_context"]["away"]["days_to_next_match"] is None


def test_coaches_keep_home_then_away_order_and_existing_five_match_boundary() -> None:
    inputs = source()
    inputs["coaches"].insert(
        0,
        {
            "team_id": "away",
            "coach_id": "away-coach",
            "prior_lineups": [
                {"kickoff_at": inputs["history"][index]["kickoff_at"]} for index in range(5)
            ],
        },
    )
    report = context_features(inputs)
    assert [row["team_id"] for row in report["coach_context"]] == ["home", "away"]
    assert report["coach_context"][1]["coach_changed_recently"] is False
