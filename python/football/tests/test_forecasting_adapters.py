from __future__ import annotations

import math

import pytest
from football.forecasting.adapters import (
    CornerTotalDistributionV1,
    EloOneXTwoAdapterV1,
    ForecastAdapterError,
    corner_forecast_payload,
    dixon_coles_result_probabilities,
    goal_forecast_payload,
)
from football.forecasting.corner import CornerForecast
from football.forecasting.dixon_coles import GoalForecast, GoalMarkets, ScoreMatrix


def test_elo_adapter_produces_symmetric_draw_aware_probabilities() -> None:
    adapter = EloOneXTwoAdapterV1(draw_propensity=0.5)

    probabilities = adapter.forecast(1500.0, 1500.0)

    assert probabilities.home == pytest.approx(probabilities.away)
    assert probabilities.draw > 0.0
    assert probabilities.home + probabilities.draw + probabilities.away == pytest.approx(1.0)


def test_elo_adapter_is_numerically_stable_and_applies_home_advantage() -> None:
    adapter = EloOneXTwoAdapterV1(draw_propensity=0.5, home_advantage=100.0)

    ordinary = adapter.forecast(1500.0, 1500.0)
    extreme = adapter.forecast(100_000.0, -100_000.0)

    assert ordinary.home > ordinary.away
    assert extreme.home == pytest.approx(1.0)
    assert all(math.isfinite(value) for value in (extreme.home, extreme.draw, extreme.away))
    with pytest.raises(ForecastAdapterError, match="positive"):
        EloOneXTwoAdapterV1(draw_propensity=0.0)


def test_dixon_coles_adapter_preserves_existing_1x2_probabilities() -> None:
    forecast = GoalForecast(
        lambda_home=1.2,
        lambda_away=0.8,
        low_score_correlation=0.0,
        score_matrix=ScoreMatrix(labels=("0", "1"), probabilities=((0.3, 0.2), (0.2, 0.3))),
        markets=GoalMarkets(
            home_win=0.5,
            draw=0.3,
            away_win=0.2,
            over_1_5=0.5,
            over_2_5=0.3,
            over_3_5=0.1,
            both_teams_to_score=0.4,
            home_clean_sheet=0.4,
            away_clean_sheet=0.3,
        ),
    )

    probabilities = dixon_coles_result_probabilities(forecast)

    assert (probabilities.home, probabilities.draw, probabilities.away) == (0.5, 0.3, 0.2)


def test_model_adapters_preserve_complete_goal_and_corner_payloads() -> None:
    goal_forecast = GoalForecast(
        lambda_home=1.2,
        lambda_away=0.8,
        low_score_correlation=0.0,
        score_matrix=ScoreMatrix(
            labels=("0", "1", "2+"),
            probabilities=((0.12, 0.10, 0.08), (0.11, 0.14, 0.10), (0.09, 0.12, 0.14)),
        ),
        markets=GoalMarkets(0.5, 0.3, 0.2, 0.5, 0.3, 0.1, 0.4, 0.4, 0.3),
    )
    corner_forecast = CornerForecast(
        distribution="negative_binomial",
        lambda_home=5.0,
        lambda_away=4.0,
        home_variance=7.5,
        away_variance=5.6,
        dispersion=0.1,
    )

    goal = goal_forecast_payload(goal_forecast)
    corners = corner_forecast_payload(corner_forecast)

    assert goal.score_labels == goal_forecast.score_matrix.labels
    assert goal.over_0_5 > goal.over_4_5
    assert goal.btts_yes == goal_forecast.markets.both_teams_to_score
    assert corners.distribution == "negative_binomial"
    assert corners.lambda_home == corner_forecast.lambda_home


def test_corner_total_distribution_is_convolution_with_intervals() -> None:
    forecast = CornerForecast(
        distribution="poisson",
        lambda_home=2.0,
        lambda_away=3.0,
        home_variance=2.0,
        away_variance=3.0,
        dispersion=None,
    )
    total = CornerTotalDistributionV1(forecast)

    assert total.probability(0) == pytest.approx(math.exp(-5.0))
    assert sum(total.probability(value) for value in range(40)) == pytest.approx(1.0)
    summary = total.summary()
    assert summary.interval_95[0] <= summary.interval_80[0] <= summary.median
    assert summary.median <= summary.interval_80[1] <= summary.interval_95[1]


def test_corner_total_distribution_rejects_truncated_summary() -> None:
    total = CornerTotalDistributionV1(CornerForecast("poisson", 20.0, 20.0, 20.0, 20.0, None))

    with pytest.raises(ForecastAdapterError, match="probability mass"):
        total.summary(max_count=1)
