from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from football.forecasting.calibration import (
    CalibrationContractError,
    CalibrationGatePolicyV1,
    MulticlassIsotonicCalibratorV1,
    MulticlassPlattCalibratorV1,
    evaluate_calibration_gate,
)
from football.forecasting.contracts import MatchResultProbabilitiesV1
from football.forecasting.evaluation import EvaluatedMatchResultV1, MatchOutcome

START = datetime(2025, 1, 1, tzinfo=UTC)
CALIBRATION_CUTOFF = START + timedelta(days=20)


def test_platt_calibrator_is_deterministic_and_probability_coherent() -> None:
    training = _training_observations()

    first = MulticlassPlattCalibratorV1.fit(training, calibration_cutoff=CALIBRATION_CUTOFF)
    second = MulticlassPlattCalibratorV1.fit(training, calibration_cutoff=CALIBRATION_CUTOFF)
    calibrated = first.calibrate(MatchResultProbabilitiesV1(0.6, 0.25, 0.15))

    assert first.to_dict() == second.to_dict()
    assert calibrated.home + calibrated.draw + calibrated.away == pytest.approx(1.0)
    assert all(
        0.0 <= value <= 1.0 for value in calibrated.to_dict().values() if isinstance(value, float)
    )


def test_isotonic_calibrator_has_monotone_portable_state() -> None:
    calibrator = MulticlassIsotonicCalibratorV1.fit(
        _training_observations(), calibration_cutoff=CALIBRATION_CUTOFF
    )

    assert all(
        left <= right
        for state in (calibrator.home, calibrator.draw, calibrator.away)
        for left, right in zip(state.values, state.values[1:], strict=False)
    )
    assert calibrator.to_dict()["contract"] == "MulticlassIsotonicCalibratorV1"
    calibrated = calibrator.calibrate(MatchResultProbabilitiesV1(0.5, 0.3, 0.2))
    assert calibrated.home + calibrated.draw + calibrated.away == pytest.approx(1.0)


def test_calibration_gate_accepts_broad_improvement_and_rejects_regression() -> None:
    raw = (
        _observation(0, MatchResultProbabilitiesV1(0.05, 0.05, 0.9), "HOME"),
        _observation(1, MatchResultProbabilitiesV1(0.9, 0.05, 0.05), "DRAW"),
        _observation(2, MatchResultProbabilitiesV1(0.05, 0.9, 0.05), "AWAY"),
    )
    improved = (
        _observation(0, MatchResultProbabilitiesV1(0.7, 0.15, 0.15), "HOME"),
        _observation(1, MatchResultProbabilitiesV1(0.15, 0.7, 0.15), "DRAW"),
        _observation(2, MatchResultProbabilitiesV1(0.15, 0.15, 0.7), "AWAY"),
    )

    accepted = evaluate_calibration_gate(raw, improved)
    rejected = evaluate_calibration_gate(improved, raw)

    assert accepted.accepted
    assert not accepted.reasons
    assert not rejected.accepted
    assert "log_loss regression exceeds tolerance" in rejected.reasons
    assert "brier_score regression exceeds tolerance" in rejected.reasons


def test_calibration_requires_all_classes_and_valid_gate_policy() -> None:
    incomplete = (
        _observation(0, MatchResultProbabilitiesV1(0.6, 0.2, 0.2), "HOME"),
        _observation(1, MatchResultProbabilitiesV1(0.5, 0.3, 0.2), "HOME"),
        _observation(2, MatchResultProbabilitiesV1(0.4, 0.4, 0.2), "DRAW"),
    )

    with pytest.raises(CalibrationContractError, match="every match-result class"):
        MulticlassPlattCalibratorV1.fit(incomplete, calibration_cutoff=CALIBRATION_CUTOFF)
    with pytest.raises(CalibrationContractError, match="must not be negative"):
        CalibrationGatePolicyV1(max_log_loss_regression=-0.1)
    with pytest.raises(CalibrationContractError, match="known before"):
        MulticlassPlattCalibratorV1.fit(
            _training_observations(), calibration_cutoff=START + timedelta(days=8, hours=14)
        )


def _training_observations() -> tuple[EvaluatedMatchResultV1, ...]:
    outcomes: tuple[MatchOutcome, ...] = (
        "HOME",
        "DRAW",
        "AWAY",
        "HOME",
        "DRAW",
        "AWAY",
        "HOME",
        "DRAW",
        "AWAY",
    )
    probabilities = (
        MatchResultProbabilitiesV1(0.70, 0.20, 0.10),
        MatchResultProbabilitiesV1(0.35, 0.45, 0.20),
        MatchResultProbabilitiesV1(0.20, 0.25, 0.55),
        MatchResultProbabilitiesV1(0.60, 0.25, 0.15),
        MatchResultProbabilitiesV1(0.30, 0.50, 0.20),
        MatchResultProbabilitiesV1(0.15, 0.30, 0.55),
        MatchResultProbabilitiesV1(0.55, 0.30, 0.15),
        MatchResultProbabilitiesV1(0.25, 0.50, 0.25),
        MatchResultProbabilitiesV1(0.10, 0.25, 0.65),
    )
    return tuple(
        _observation(index, probability, outcome)
        for index, (probability, outcome) in enumerate(zip(probabilities, outcomes, strict=True))
    )


def _observation(
    day: int, probabilities: MatchResultProbabilitiesV1, outcome: MatchOutcome
) -> EvaluatedMatchResultV1:
    kickoff = START + timedelta(days=day, hours=12)
    return EvaluatedMatchResultV1(
        kickoff_at=kickoff,
        prediction_cutoff=kickoff - timedelta(hours=1),
        outcome_known_at=kickoff + timedelta(hours=2),
        probabilities=probabilities,
        outcome=outcome,
    )
