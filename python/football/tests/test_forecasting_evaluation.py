from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from football.forecasting.contracts import MatchResultProbabilitiesV1
from football.forecasting.evaluation import (
    EvaluatedMatchResultV1,
    EvaluationContractError,
    MatchOutcome,
    WalkForwardEvaluator,
    WalkForwardPolicyV1,
    evaluate_match_results,
)

START = datetime(2025, 1, 1, tzinfo=UTC)


def test_match_result_metrics_score_perfect_predictions() -> None:
    observations = (
        _observation(0, MatchResultProbabilitiesV1(1.0, 0.0, 0.0), "HOME"),
        _observation(1, MatchResultProbabilitiesV1(0.0, 1.0, 0.0), "DRAW"),
        _observation(2, MatchResultProbabilitiesV1(0.0, 0.0, 1.0), "AWAY"),
    )

    metrics = evaluate_match_results(observations, bin_count=5)

    assert metrics.sample_count == 3
    assert metrics.log_loss == pytest.approx(0.0)
    assert metrics.brier_score == pytest.approx(0.0)
    assert metrics.ranked_probability_score == pytest.approx(0.0)
    assert metrics.accuracy == 1.0
    assert metrics.expected_calibration_error == pytest.approx(0.0)
    assert metrics.brier_decomposition.reliability == pytest.approx(0.0)


def test_match_result_metrics_match_known_uniform_baseline() -> None:
    uniform = MatchResultProbabilitiesV1(1 / 3, 1 / 3, 1 / 3)
    outcomes: tuple[MatchOutcome, ...] = ("HOME", "DRAW", "AWAY")
    observations = tuple(
        _observation(index, uniform, outcome) for index, outcome in enumerate(outcomes)
    )

    metrics = evaluate_match_results(observations, bin_count=3)

    assert metrics.log_loss == pytest.approx(-math.log(1 / 3))
    assert metrics.brier_score == pytest.approx(2 / 3)
    assert metrics.accuracy == pytest.approx(1 / 3)
    assert metrics.expected_calibration_error == pytest.approx(0.0)


def test_walk_forward_windows_are_chronological_and_never_random() -> None:
    evaluator = WalkForwardEvaluator(
        WalkForwardPolicyV1(
            initial_training_duration=timedelta(days=30),
            evaluation_duration=timedelta(days=10),
            retraining_frequency=timedelta(days=10),
            rolling_training_duration=timedelta(days=20),
        )
    )

    windows = evaluator.windows(START, START + timedelta(days=55))

    assert len(windows) == 3
    assert windows[0].training_start == START + timedelta(days=10)
    assert windows[0].training_end == windows[0].evaluation_start
    assert windows[-1].evaluation_end == START + timedelta(days=55)
    assert all(window.training_end <= window.evaluation_start for window in windows)


def test_same_kickoff_matches_remain_in_one_chronological_batch() -> None:
    first = _observation(0, MatchResultProbabilitiesV1(0.4, 0.3, 0.3), "HOME")
    second = _observation(0, MatchResultProbabilitiesV1(0.3, 0.3, 0.4), "AWAY")
    later = _observation(1, MatchResultProbabilitiesV1(0.3, 0.4, 0.3), "DRAW")

    batches = WalkForwardEvaluator.chronological_batches((later, first, second))

    assert batches == ((first, second), (later,))


def test_evaluation_rejects_temporal_leakage_and_invalid_bins() -> None:
    with pytest.raises(EvaluationContractError, match="must not follow"):
        EvaluatedMatchResultV1(
            kickoff_at=START,
            prediction_cutoff=START + timedelta(seconds=1),
            outcome_known_at=START + timedelta(hours=2),
            probabilities=MatchResultProbabilitiesV1(0.4, 0.3, 0.3),
            outcome="HOME",
        )
    with pytest.raises(EvaluationContractError, match="at least 2"):
        evaluate_match_results(
            (_observation(0, MatchResultProbabilitiesV1(0.4, 0.3, 0.3), "HOME"),),
            bin_count=1,
        )


def _observation(
    day: int,
    probabilities: MatchResultProbabilitiesV1,
    outcome: MatchOutcome,
) -> EvaluatedMatchResultV1:
    kickoff = START + timedelta(days=day, hours=12)
    return EvaluatedMatchResultV1(
        kickoff_at=kickoff,
        prediction_cutoff=kickoff - timedelta(hours=1),
        outcome_known_at=kickoff + timedelta(hours=2),
        probabilities=probabilities,
        outcome=outcome,
    )
