from __future__ import annotations

import pytest
from football.forecasting.pitchapi_v3 import (
    MatchHistoryFeaturesV1,
    TeamHistoryFeaturesV1,
    TransferableGoalModelV1,
    TransferableParametersV1,
)
from football.forecasting.pitchapi_v3_evaluation import (
    DomainMetricSeriesV1,
    aggregate_domain_series,
    calibration_fit,
    exact_distribution,
    paired_domain_bootstrap,
    score_target,
)
from scipy.stats import poisson


def test_v3_bootstrap_is_reproducible_and_uses_frozen_aggregates() -> None:
    domains = {
        "bundesliga_2022_23": DomainMetricSeriesV1.synthetic(216, 0.01),
        "bundesliga_2023_24": DomainMetricSeriesV1.synthetic(216, -0.02),
        "ligue1_2022_23": DomainMetricSeriesV1.synthetic(280, -0.03),
    }

    first = paired_domain_bootstrap(domains)
    second = paired_domain_bootstrap(domains)
    aggregate = aggregate_domain_series(domains)

    assert first == second
    assert len(first.macro_replicates) == 2000
    assert aggregate.macro_delta == pytest.approx(-0.04 / 3)
    assert aggregate.weighted_delta == pytest.approx(
        ((216 * 0.01) + (216 * -0.02) + (280 * -0.03)) / 712
    )


def test_score_metrics_match_independent_poisson_reference() -> None:
    parameters = TransferableParametersV1(0.2, -0.1, 0.0, 0.0, 0.0, 1.3, 1.2)
    features = MatchHistoryFeaturesV1(
        TeamHistoryFeaturesV1(10, 1.0, 1.0, 1.0),
        TeamHistoryFeaturesV1(10, 1.0, 1.0, 1.0),
    )
    forecast = TransferableGoalModelV1(parameters).forecast_features(features)

    scores = score_target(exact_distribution(forecast), home_goals=2, away_goals=1)
    independent = -float(poisson.logpmf(2, forecast.lambda_home)) - float(
        poisson.logpmf(1, forecast.lambda_away)
    )

    assert scores.joint_score_log_loss == pytest.approx(independent, abs=1e-12)


def test_calibration_matches_exact_grouped_reference() -> None:
    probabilities = (0.25,) * 4 + (0.75,) * 4
    outcomes = (1, 0, 0, 0, 1, 1, 1, 0)

    fit = calibration_fit(probabilities, outcomes)

    assert fit.intercept == pytest.approx(0.0, abs=1e-7)
    assert fit.slope == pytest.approx(1.0, abs=1e-7)
