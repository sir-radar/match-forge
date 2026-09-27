from __future__ import annotations

import math

import pytest
from football.forecasting.pitchapi_calibration_successor import (
    CalibrationRowV1,
    CalibrationSuccessorError,
    fit_global_vector_scaling,
    paired_moving_block_interval,
    probability_scores,
    rows_sha256,
)


def _rows(count: int = 45) -> tuple[CalibrationRowV1, ...]:
    probabilities = ((0.55, 0.25, 0.20), (0.30, 0.40, 0.30), (0.20, 0.25, 0.55))
    return tuple(
        CalibrationRowV1(
            match_id=f"match-{index:03d}",
            kickoff_at=f"2026-01-{index // 3 + 1:02d}T12:00:00Z",
            kickoff_batch=index // 3,
            probabilities=probabilities[index % 3],
            outcome=index % 3,
        )
        for index in range(count)
    )


def test_vector_scaling_is_deterministic_shrunk_and_normalized() -> None:
    first = fit_global_vector_scaling(_rows(), shrinkage_strength=10.0)
    second = fit_global_vector_scaling(_rows(), shrinkage_strength=10.0)

    assert first == second
    calibrated = first.calibrate((0.50, 0.30, 0.20))
    assert sum(calibrated) == pytest.approx(1.0)
    assert all(0.0 < value < 1.0 for value in calibrated)
    assert first.to_dict()["identification"] == "away_intercept_fixed_zero"


def test_shrinkage_moves_parameters_toward_identity() -> None:
    unshrunk = fit_global_vector_scaling(_rows(), shrinkage_strength=0.0)
    shrunk = fit_global_vector_scaling(_rows(), shrinkage_strength=10.0)

    identity = (0.0, 0.0, 1.0, 1.0, 1.0)
    unshrunk_distance = math.dist(unshrunk.parameters, identity)
    shrunk_distance = math.dist(shrunk.parameters, identity)
    assert shrunk_distance < unshrunk_distance


def test_invalid_probabilities_and_missing_classes_fail_closed() -> None:
    with pytest.raises(CalibrationSuccessorError, match="inside"):
        CalibrationRowV1("bad", "2026-01-01T00:00:00Z", 0, (0.0, 0.5, 0.5), 0)
    with pytest.raises(CalibrationSuccessorError, match="every outcome class"):
        fit_global_vector_scaling(_rows(2), shrinkage_strength=10.0)


def test_probability_scores_use_home_draw_away_order() -> None:
    scores = probability_scores((0.6, 0.25, 0.15), 0)
    assert scores["one_x_two_log_loss"] == pytest.approx(-math.log(0.6))
    assert scores["one_x_two_brier"] == pytest.approx(0.245)
    assert scores["one_x_two_rps"] == pytest.approx(0.09125)


def test_bootstrap_and_row_manifest_are_deterministic() -> None:
    rows = _rows()
    reference = [1.0] * len(rows)
    challenger = [0.99] * len(rows)
    batches = [row.kickoff_batch for row in rows]

    assert paired_moving_block_interval(reference, challenger, batches) == pytest.approx(
        (-0.01, -0.01)
    )
    assert rows_sha256(rows) == rows_sha256(rows)
