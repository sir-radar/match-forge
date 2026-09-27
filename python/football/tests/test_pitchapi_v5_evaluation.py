from __future__ import annotations

import math
from typing import cast

import pytest
from football.forecasting.pitchapi_v3_evaluation import (
    DomainMetricSeriesV1,
    ExactScoreDistributionV1,
    PitchApiV3EvaluationError,
    aggregate_domain_series,
    descriptive_target_metrics,
    score_target,
)
from football.forecasting.pitchapi_v5_evaluation import (
    PitchApiV5EvaluationError,
    audited_binary_auc,
    audited_reliability_diagram,
    goal_on_xg_calibration,
)


def test_own_goal_zero_is_reported_and_raw_probabilities_are_unchanged() -> None:
    probabilities = (0.0,) + (0.25,) * 4 + (0.75,) * 4
    outcomes = (1, 1, 0, 0, 0, 1, 1, 1, 0)

    result = goal_on_xg_calibration(
        probabilities,
        outcomes,
        (True,) + (False,) * 8,
    )

    assert probabilities[0] == 0.0
    assert result.raw_count == 9
    assert result.interior_count == 8
    assert result.own_goal_zero_count == 1
    assert result.fit.intercept == pytest.approx(0.0, abs=1e-7)
    assert result.fit.slope == pytest.approx(1.0, abs=1e-7)


def test_near_boundary_probabilities_remain_unclipped() -> None:
    probabilities = (1e-15, 1e-15, 1.0 - 1e-15, 1.0 - 1e-15, 0.25, 0.25, 0.75, 0.75)
    outcomes = (0, 1, 0, 1, 0, 1, 0, 1)

    result = goal_on_xg_calibration(probabilities, outcomes, (False,) * 8)

    assert result.interior_count == len(probabilities)
    assert result.own_goal_zero_count == 0
    assert math.isfinite(result.fit.intercept)
    assert math.isfinite(result.fit.slope)


@pytest.mark.parametrize(
    ("probabilities", "outcomes", "flags", "message"),
    [
        ((), (), (), "empty or misaligned"),
        ((0.0,), (0,), (False,), "unsupported calibration boundary"),
        ((0.0,), (1,), (False,), "unsupported calibration boundary"),
        ((1.0,), (1,), (True,), "unsupported calibration boundary"),
        ((-0.1,), (0,), (False,), "probability is invalid"),
        ((1.1,), (1,), (False,), "probability is invalid"),
        ((math.nan,), (0,), (False,), "probability is invalid"),
        ((math.inf,), (0,), (False,), "probability is invalid"),
        ((0.5,), (2,), (False,), "outcome is invalid"),
        ((0.5,), (0,), (), "empty or misaligned"),
        ((0.5, 0.5), (0, 0), (False, False), "both classes"),
    ],
)
def test_calibration_contract_fails_closed(
    probabilities: tuple[float, ...],
    outcomes: tuple[int, ...],
    flags: tuple[bool, ...],
    message: str,
) -> None:
    with pytest.raises(PitchApiV5EvaluationError, match=message):
        goal_on_xg_calibration(probabilities, outcomes, flags)


@pytest.mark.parametrize("probabilities", [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5)])
def test_boundary_and_constant_predictions_are_valid_for_auc_and_reliability(
    probabilities: tuple[float, ...],
) -> None:
    outcomes = (0, 1)

    assert audited_binary_auc(probabilities, outcomes) == pytest.approx(0.5)
    assert (
        sum(
            cast(int, row["target_count"])
            for row in audited_reliability_diagram(probabilities, outcomes)
        )
        == 2
    )


def test_auc_returns_none_for_constant_outcomes() -> None:
    assert audited_binary_auc((0.0, 0.5, 1.0), (0, 0, 0)) is None
    assert audited_binary_auc((0.0, 0.5, 1.0), (1, 1, 1)) is None


def test_auc_accepts_sparse_positive_outcomes() -> None:
    assert audited_binary_auc((0.1, 0.2, 0.3, 0.9), (0, 0, 0, 1)) == 1.0


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -0.1, 1.1])
def test_binary_diagnostics_reject_malformed_probabilities(value: float) -> None:
    with pytest.raises(PitchApiV5EvaluationError, match="probability is invalid"):
        audited_binary_auc((value,), (0,))


def test_binary_diagnostics_reject_empty_auc_but_allow_empty_reliability() -> None:
    with pytest.raises(PitchApiV5EvaluationError, match="empty or misaligned"):
        audited_binary_auc((), ())
    assert len(audited_reliability_diagram((), ())) == 10


def test_log_loss_accepts_observed_probability_one_and_rejects_zero() -> None:
    deterministic = ExactScoreDistributionV1(((0, 0, 1.0),), 0.0)
    impossible_observation = ExactScoreDistributionV1(((0, 0, 0.0), (1, 0, 1.0)), 0.0)

    assert score_target(deterministic, home_goals=0, away_goals=0).joint_score_log_loss == 0.0
    with pytest.raises(PitchApiV3EvaluationError, match="zero probability"):
        score_target(impossible_observation, home_goals=0, away_goals=0)
    with pytest.raises(PitchApiV3EvaluationError, match="binary market probability"):
        descriptive_target_metrics(deterministic, home_goals=0, away_goals=0)


def test_small_domains_fail_before_bootstrap_or_aggregation() -> None:
    domains = {
        "bundesliga_2022_23": DomainMetricSeriesV1.synthetic(9, 0.0),
        "bundesliga_2023_24": DomainMetricSeriesV1.synthetic(9, 0.0),
        "ligue1_2022_23": DomainMetricSeriesV1.synthetic(9, 0.0),
    }

    with pytest.raises(PitchApiV3EvaluationError, match="unexpected target count"):
        aggregate_domain_series(domains)


def test_binary_diagnostics_reject_malformed_outcomes() -> None:
    with pytest.raises(PitchApiV5EvaluationError, match="outcome is invalid"):
        audited_reliability_diagram((0.5,), (2,))
