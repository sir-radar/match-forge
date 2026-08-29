from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from football.forecasting.elo import EloConfig, EloContractError, EloMatch, TeamEloModel

COMPETITION_A = UUID("10000000-0000-4000-8000-000000000001")
COMPETITION_B = UUID("10000000-0000-4000-8000-000000000002")
HOME = UUID("20000000-0000-4000-8000-000000000001")
AWAY = UUID("20000000-0000-4000-8000-000000000002")
THIRD = UUID("20000000-0000-4000-8000-000000000003")
FIRST_MATCH = UUID("30000000-0000-4000-8000-000000000001")
SECOND_MATCH = UUID("30000000-0000-4000-8000-000000000002")
KICKOFF = datetime(2026, 1, 1, 15, 0, tzinfo=UTC)


def test_neutral_win_updates_equal_ratings_symmetrically() -> None:
    model = TeamEloModel(
        EloConfig(
            model_version="elo-test-v1",
            k_factor=20.0,
            home_advantage=0.0,
            time_decay_half_life_days=None,
        )
    )

    result = model.rate((_match(home_score=1, away_score=0),))

    rated = result.matches[0]
    assert rated.expected_home_score == pytest.approx(0.5)
    assert rated.actual_home_score == 1.0
    assert rated.home_pre_match_rating == 1500.0
    assert rated.away_pre_match_rating == 1500.0
    assert rated.home_post_match_rating == pytest.approx(1510.0)
    assert rated.away_post_match_rating == pytest.approx(1490.0)
    assert sum(item.rating for item in result.history) == pytest.approx(3000.0)


def test_home_advantage_changes_pre_match_probability() -> None:
    model = TeamEloModel(EloConfig(model_version="elo-home-v1", home_advantage=100.0))

    rated = model.rate((_match(home_score=0, away_score=0),)).matches[0]

    expected = 1.0 / (1.0 + 10.0 ** (-100.0 / 400.0))
    assert rated.expected_home_score == pytest.approx(expected)
    assert rated.expected_home_score > 0.5


def test_goal_difference_and_competition_weight_scale_update() -> None:
    base = TeamEloModel(EloConfig(model_version="elo-margin-v1", home_advantage=0.0)).rate(
        (_match(home_score=1, away_score=0),)
    )
    margin = TeamEloModel(EloConfig(model_version="elo-margin-v1", home_advantage=0.0)).rate(
        (_match(home_score=3, away_score=0),)
    )
    weighted = TeamEloModel(
        EloConfig(
            model_version="elo-margin-v1",
            home_advantage=0.0,
            competition_weights={COMPETITION_A: 2.0},
        )
    ).rate((_match(home_score=1, away_score=0),))

    assert base.matches[0].home_post_match_rating == pytest.approx(1510.0)
    assert margin.matches[0].home_post_match_rating == pytest.approx(
        1500.0 + 10.0 * (1.0 + math.log(3.0))
    )
    assert weighted.matches[0].home_post_match_rating == pytest.approx(1520.0)


def test_time_decay_regresses_inactive_team_toward_initial_rating() -> None:
    config = EloConfig(
        model_version="elo-decay-v1",
        home_advantage=0.0,
        time_decay_half_life_days=365.0,
    )
    second = EloMatch(
        match_id=SECOND_MATCH,
        competition_id=COMPETITION_A,
        kickoff_at=KICKOFF + timedelta(days=365),
        home_team_id=HOME,
        away_team_id=THIRD,
        home_score=0,
        away_score=0,
    )

    result = TeamEloModel(config).rate((second, _match(home_score=1, away_score=0)))

    assert [match.match_id for match in result.matches] == [FIRST_MATCH, SECOND_MATCH]
    assert result.matches[1].home_pre_match_rating == pytest.approx(1505.0)
    assert result.matches[1].away_pre_match_rating == 1500.0


def test_rejects_duplicate_match_and_same_team_timestamp() -> None:
    model = TeamEloModel(EloConfig(model_version="elo-order-v1"))
    match = _match(home_score=1, away_score=0)
    simultaneous = EloMatch(
        match_id=SECOND_MATCH,
        competition_id=COMPETITION_A,
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=THIRD,
        home_score=0,
        away_score=0,
    )

    with pytest.raises(EloContractError, match="duplicate match"):
        model.rate((match, match))
    with pytest.raises(EloContractError, match="same timestamp"):
        model.rate((match, simultaneous))


def test_config_identity_is_stable_and_validated() -> None:
    first = EloConfig(
        model_version="elo-config-v1",
        competition_weights={COMPETITION_A: 1.5, COMPETITION_B: 0.75},
    )
    second = EloConfig(
        model_version="elo-config-v1",
        competition_weights={COMPETITION_B: 0.75, COMPETITION_A: 1.5},
    )

    assert first.sha256 == second.sha256
    assert first.to_dict() == second.to_dict()
    with pytest.raises(EloContractError, match="model_version"):
        EloConfig(model_version="Invalid Version")
    with pytest.raises(EloContractError, match="competition weight"):
        EloConfig(model_version="elo-config-v2", competition_weights={COMPETITION_A: 0.0})


def _match(*, home_score: int, away_score: int) -> EloMatch:
    return EloMatch(
        match_id=FIRST_MATCH,
        competition_id=COMPETITION_A,
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        home_score=home_score,
        away_score=away_score,
    )
