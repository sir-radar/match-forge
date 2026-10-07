from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from football.forecasting.h2h_residual import (
    ContextualGoalAdjustmentV1,
    H2HMeeting,
    H2HResidualStatus,
    H2HResidualV1,
    H2HTarget,
)

HOME = UUID(int=1)
AWAY = UUID(int=2)
OTHER = UUID(int=3)
KICKOFF = datetime(2025, 8, 1, 15, tzinfo=UTC)


def target(**changes: object) -> H2HTarget:
    values: dict[str, object] = {
        "fixture_id": UUID(int=100),
        "competition": "Premier League",
        "season_label": "2025/2026",
        "kickoff_at": KICKOFF,
        "knowledge_cutoff": KICKOFF,
        "home_team_id": HOME,
        "away_team_id": AWAY,
    }
    values.update(changes)
    return H2HTarget(**values)  # type: ignore[arg-type]


def meeting(index: int, age_days: float, **changes: object) -> H2HMeeting:
    kickoff = KICKOFF - timedelta(days=age_days)
    values: dict[str, object] = {
        "fixture_id": UUID(int=200 + index),
        "competition": "Premier League",
        "season_label": "2024/2025",
        "kickoff_at": kickoff,
        "known_at": kickoff + timedelta(hours=3),
        "home_team_id": HOME,
        "away_team_id": AWAY,
        "home_npxg": 2.0,
        "away_npxg": 1.0,
        "lambda_home": 1.0,
        "lambda_away": 1.0,
    }
    values.update(changes)
    return H2HMeeting(**values)  # type: ignore[arg-type]


def test_orientation_and_reversal_use_future_target_orientation() -> None:
    same = H2HResidualV1().build(target(), (meeting(1, 10), meeting(2, 20)))
    reversed_rows = (
        meeting(
            3,
            10,
            home_team_id=AWAY,
            away_team_id=HOME,
            home_npxg=1.0,
            away_npxg=2.0,
            lambda_home=1.0,
            lambda_away=1.0,
        ),
        meeting(
            4,
            20,
            home_team_id=AWAY,
            away_team_id=HOME,
            home_npxg=1.0,
            away_npxg=2.0,
            lambda_home=1.0,
            lambda_away=1.0,
        ),
    )
    reversed_result = H2HResidualV1().build(target(), reversed_rows)
    assert same.secondary_matchup_prior > 0
    assert reversed_result.secondary_matchup_prior > 0
    assert same.h2h_same_orientation_count == 2
    assert reversed_result.h2h_reversed_orientation_count == 2


def test_recency_has_180_day_half_life() -> None:
    result = H2HResidualV1().build(target(), (meeting(1, 1), meeting(2, 181)))
    assert result.h2h_effective_weight == pytest.approx(
        0.65 * (2 ** (-1 / 180) + 2 ** (-181 / 180))
    )


@pytest.mark.parametrize(
    ("changes", "expected_count"),
    [
        ({"competition": "La Liga"}, 0),
        ({"season_label": "2023/2024"}, 0),
        ({"home_team_id": HOME, "away_team_id": OTHER}, 0),
        ({"pair_complete": False}, 0),
    ],
)
def test_competition_era_pair_and_completeness_filters(
    changes: dict[str, object], expected_count: int
) -> None:
    rows = (meeting(1, 20, **changes), meeting(2, 40, **changes))
    assert H2HResidualV1().build(target(), rows).h2h_usable_meeting_count == expected_count


def test_730_day_maximum_future_and_same_kickoff_exclusion() -> None:
    rows = (
        meeting(1, 731),
        meeting(2, -1),
        meeting(3, 0, known_at=KICKOFF),
    )
    assert H2HResidualV1().build(target(), rows).status is H2HResidualStatus.INSUFFICIENT_H2H


def test_continuity_decay_applies_to_older_meeting() -> None:
    result = H2HResidualV1().build(target(), (meeting(1, 10), meeting(2, 380)))
    expected = 0.65 * (2 ** (-10 / 180) + 2 ** (-380 / 180) * math.exp(-(370 - 270) / 365))
    assert result.h2h_effective_weight == pytest.approx(expected)


def test_maximum_five_and_minimum_two_with_neutral_zero() -> None:
    rows = tuple(meeting(index, index * 10) for index in range(1, 8))
    assert H2HResidualV1().build(target(), rows).h2h_usable_meeting_count == 5
    neutral = H2HResidualV1().build(target(), rows[:1])
    assert neutral.secondary_matchup_prior == 0.0
    assert neutral.status is H2HResidualStatus.INSUFFICIENT_H2H


def test_residual_and_feature_are_clipped() -> None:
    rows = (
        meeting(1, 1, home_npxg=20.0, away_npxg=0.0),
        meeting(2, 2, home_npxg=20.0, away_npxg=0.0),
    )
    assert H2HResidualV1().build(target(), rows).secondary_matchup_prior <= 1.5


def test_contextual_adjustment_is_neutral_at_zero_and_antisymmetric() -> None:
    adjustment = ContextualGoalAdjustmentV1(0.1)
    assert adjustment.adjust(1.5, 1.2, 0.0) == (1.5, 1.2)
    home, away = adjustment.adjust(1.5, 1.2, 0.5)
    assert home == pytest.approx(1.5 * math.exp(0.05))
    assert away == pytest.approx(1.2 * math.exp(-0.05))
