"""V5-only input contracts for calibration and metric diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass

from football.forecasting.pitchapi_v3_evaluation import (
    CalibrationFitV1,
    PitchApiV3EvaluationError,
    binary_auc,
    calibration_fit,
    reliability_diagram,
)


class PitchApiV5EvaluationError(PitchApiV3EvaluationError):
    """V5 evaluation input violates a frozen metric-domain rule."""


@dataclass(frozen=True, slots=True)
class BoundaryAwareCalibrationV1:
    fit: CalibrationFitV1
    interior_count: int
    own_goal_zero_count: int
    raw_count: int


def goal_on_xg_calibration(
    probabilities: tuple[float, ...],
    outcomes: tuple[int, ...],
    own_goal_flags: tuple[bool, ...],
) -> BoundaryAwareCalibrationV1:
    """Fit logit calibration to shots and report own goals as a separate category.

    PitchAPI represents own goals with xG=0. They are goals, but not modelled
    shooting chances, so they are excluded from the goal-on-logit-xG fit without
    changing the raw value. Every other calibration input must be finite and in
    the open unit interval.
    """
    count = len(probabilities)
    if count == 0 or len(outcomes) != count or len(own_goal_flags) != count:
        raise PitchApiV5EvaluationError("calibration inputs are empty or misaligned")
    interior_probabilities: list[float] = []
    interior_outcomes: list[int] = []
    own_goal_zero_count = 0
    for probability, outcome, own_goal in zip(probabilities, outcomes, own_goal_flags, strict=True):
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise PitchApiV5EvaluationError("calibration probability is invalid")
        if outcome not in (0, 1):
            raise PitchApiV5EvaluationError("calibration outcome is invalid")
        if 0.0 < probability < 1.0:
            interior_probabilities.append(probability)
            interior_outcomes.append(outcome)
        elif probability == 0.0 and outcome == 1 and own_goal:
            own_goal_zero_count += 1
        else:
            raise PitchApiV5EvaluationError("unsupported calibration boundary category")
    try:
        fit = calibration_fit(tuple(interior_probabilities), tuple(interior_outcomes))
    except PitchApiV3EvaluationError as error:
        raise PitchApiV5EvaluationError(str(error)) from error
    return BoundaryAwareCalibrationV1(
        fit=fit,
        interior_count=len(interior_probabilities),
        own_goal_zero_count=own_goal_zero_count,
        raw_count=count,
    )


def audited_reliability_diagram(
    probabilities: tuple[float, ...], outcomes: tuple[int, ...]
) -> tuple[dict[str, float | int | None], ...]:
    _validate_binary_inputs(probabilities, outcomes, allow_empty=True)
    return reliability_diagram(probabilities, outcomes)


def audited_binary_auc(probabilities: tuple[float, ...], outcomes: tuple[int, ...]) -> float | None:
    _validate_binary_inputs(probabilities, outcomes, allow_empty=False)
    return binary_auc(probabilities, outcomes)


def _validate_binary_inputs(
    probabilities: tuple[float, ...], outcomes: tuple[int, ...], *, allow_empty: bool
) -> None:
    if len(probabilities) != len(outcomes) or (not allow_empty and not probabilities):
        raise PitchApiV5EvaluationError("binary metric inputs are empty or misaligned")
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities):
        raise PitchApiV5EvaluationError("binary metric probability is invalid")
    if any(value not in (0, 1) for value in outcomes):
        raise PitchApiV5EvaluationError("binary metric outcome is invalid")
