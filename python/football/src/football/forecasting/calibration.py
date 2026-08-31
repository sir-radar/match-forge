from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from datetime import datetime

from scipy.optimize import minimize

from football.forecasting.contracts import MatchResultProbabilitiesV1
from football.forecasting.evaluation import (
    EvaluatedMatchResultV1,
    MatchOutcome,
    MatchResultMetricsV1,
    evaluate_match_results,
)

_EPSILON = 1e-12


class CalibrationContractError(ValueError):
    """Calibration data, fitted state, or gate policy is invalid."""


@dataclass(frozen=True, slots=True)
class BinaryPlattCalibratorV1:
    state: PlattClassStateV1
    contract: str = "BinaryPlattCalibratorV1"

    def __post_init__(self) -> None:
        if self.contract != "BinaryPlattCalibratorV1":
            raise CalibrationContractError("unsupported binary Platt calibrator contract")

    @classmethod
    def fit(
        cls, probabilities: tuple[float, ...], targets: tuple[float, ...]
    ) -> BinaryPlattCalibratorV1:
        _binary_training(probabilities, targets)
        return cls(_fit_platt_class(probabilities, targets))

    def calibrate(self, probability: float) -> float:
        return _platt_probability(probability, self.state)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "slope": self.state.slope,
            "intercept": self.state.intercept,
        }


@dataclass(frozen=True, slots=True)
class BinaryIsotonicCalibratorV1:
    state: IsotonicClassStateV1
    contract: str = "BinaryIsotonicCalibratorV1"

    def __post_init__(self) -> None:
        if self.contract != "BinaryIsotonicCalibratorV1":
            raise CalibrationContractError("unsupported binary isotonic calibrator contract")

    @classmethod
    def fit(
        cls, probabilities: tuple[float, ...], targets: tuple[float, ...]
    ) -> BinaryIsotonicCalibratorV1:
        _binary_training(probabilities, targets)
        return cls(_fit_isotonic_class(probabilities, targets))

    def calibrate(self, probability: float) -> float:
        return _isotonic_probability(probability, self.state)

    def to_dict(self) -> dict[str, object]:
        return {"contract": self.contract, **_isotonic_dict(self.state)}


@dataclass(frozen=True, slots=True)
class MulticlassVectorCalibratorV1:
    weights: tuple[tuple[float, float, float], ...]
    intercepts: tuple[float, float, float]
    contract: str = "MulticlassVectorCalibratorV1"

    def __post_init__(self) -> None:
        if self.contract != "MulticlassVectorCalibratorV1":
            raise CalibrationContractError("unsupported multiclass vector calibrator contract")
        if len(self.weights) != 3 or any(len(row) != 3 for row in self.weights):
            raise CalibrationContractError("multiclass vector weights must be three by three")
        for value in (*self.intercepts, *(item for row in self.weights for item in row)):
            _finite(value, "multiclass vector parameter")

    @classmethod
    def fit(
        cls,
        observations: tuple[EvaluatedMatchResultV1, ...],
        *,
        calibration_cutoff: datetime,
    ) -> MulticlassVectorCalibratorV1:
        _training_observations(observations, calibration_cutoff)
        logits = tuple(
            tuple(math.log(max(value, _EPSILON)) for value in _probabilities(item.probabilities))
            for item in observations
        )
        targets = tuple(_outcomes().index(item.outcome) for item in observations)

        def objective(parameters: tuple[float, ...]) -> float:
            weights = tuple(
                tuple(parameters[row * 3 + column] for column in range(3)) for row in range(3)
            )
            intercepts = parameters[9:12]
            loss = 0.0
            for values, target in zip(logits, targets, strict=True):
                calibrated = _softmax(
                    tuple(
                        sum(weights[row][column] * values[column] for column in range(3))
                        + intercepts[row]
                        for row in range(3)
                    )
                )
                loss -= math.log(max(calibrated[target], _EPSILON))
            return loss + 1e-8 * sum(value * value for value in parameters)

        initial = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        result = minimize(objective, initial, method="L-BFGS-B")
        if not bool(result.success) or any(not math.isfinite(float(value)) for value in result.x):
            raise CalibrationContractError(
                f"multiclass vector calibration did not converge: {result.message}"
            )
        values = tuple(float(value) for value in result.x)
        weights = tuple(
            (values[index], values[index + 1], values[index + 2]) for index in (0, 3, 6)
        )
        return cls(weights, (values[9], values[10], values[11]))

    def calibrate(self, probabilities: MatchResultProbabilitiesV1) -> MatchResultProbabilitiesV1:
        logits = tuple(math.log(max(value, _EPSILON)) for value in _probabilities(probabilities))
        values = _softmax(
            tuple(
                sum(self.weights[row][column] * logits[column] for column in range(3))
                + self.intercepts[row]
                for row in range(3)
            )
        )
        return MatchResultProbabilitiesV1(*values)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "weights": [list(row) for row in self.weights],
            "intercepts": list(self.intercepts),
        }


@dataclass(frozen=True, slots=True)
class PlattClassStateV1:
    slope: float
    intercept: float

    def __post_init__(self) -> None:
        _finite(self.slope, "slope")
        _finite(self.intercept, "intercept")


@dataclass(frozen=True, slots=True)
class MulticlassPlattCalibratorV1:
    home: PlattClassStateV1
    draw: PlattClassStateV1
    away: PlattClassStateV1
    contract: str = "MulticlassPlattCalibratorV1"

    def __post_init__(self) -> None:
        if self.contract != "MulticlassPlattCalibratorV1":
            raise CalibrationContractError("unsupported Platt calibrator contract")

    @classmethod
    def fit(
        cls,
        observations: tuple[EvaluatedMatchResultV1, ...],
        *,
        calibration_cutoff: datetime,
    ) -> MulticlassPlattCalibratorV1:
        _training_observations(observations, calibration_cutoff)
        probabilities = [
            (item.probabilities.home, item.probabilities.draw, item.probabilities.away)
            for item in observations
        ]
        states = tuple(
            _fit_platt_class(
                tuple(values[class_index] for values in probabilities),
                tuple(float(item.outcome == outcome) for item in observations),
            )
            for class_index, outcome in enumerate(_outcomes())
        )
        return cls(home=states[0], draw=states[1], away=states[2])

    def calibrate(self, probabilities: MatchResultProbabilitiesV1) -> MatchResultProbabilitiesV1:
        values = (
            _platt_probability(probabilities.home, self.home),
            _platt_probability(probabilities.draw, self.draw),
            _platt_probability(probabilities.away, self.away),
        )
        return _normalize(values, probabilities)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "classes": {
                "HOME": {"slope": self.home.slope, "intercept": self.home.intercept},
                "DRAW": {"slope": self.draw.slope, "intercept": self.draw.intercept},
                "AWAY": {"slope": self.away.slope, "intercept": self.away.intercept},
            },
        }


@dataclass(frozen=True, slots=True)
class IsotonicClassStateV1:
    thresholds: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.thresholds or len(self.thresholds) != len(self.values):
            raise CalibrationContractError("isotonic thresholds and values must align")
        if any(not 0.0 <= value <= 1.0 for value in (*self.thresholds, *self.values)):
            raise CalibrationContractError("isotonic state must remain in [0, 1]")
        if any(
            left >= right for left, right in zip(self.thresholds, self.thresholds[1:], strict=False)
        ):
            raise CalibrationContractError("isotonic thresholds must increase")
        if any(left > right for left, right in zip(self.values, self.values[1:], strict=False)):
            raise CalibrationContractError("isotonic values must not decrease")


@dataclass(frozen=True, slots=True)
class MulticlassIsotonicCalibratorV1:
    home: IsotonicClassStateV1
    draw: IsotonicClassStateV1
    away: IsotonicClassStateV1
    contract: str = "MulticlassIsotonicCalibratorV1"

    def __post_init__(self) -> None:
        if self.contract != "MulticlassIsotonicCalibratorV1":
            raise CalibrationContractError("unsupported isotonic calibrator contract")

    @classmethod
    def fit(
        cls,
        observations: tuple[EvaluatedMatchResultV1, ...],
        *,
        calibration_cutoff: datetime,
    ) -> MulticlassIsotonicCalibratorV1:
        _training_observations(observations, calibration_cutoff)
        probabilities = [
            (item.probabilities.home, item.probabilities.draw, item.probabilities.away)
            for item in observations
        ]
        states = tuple(
            _fit_isotonic_class(
                tuple(values[class_index] for values in probabilities),
                tuple(float(item.outcome == outcome) for item in observations),
            )
            for class_index, outcome in enumerate(_outcomes())
        )
        return cls(home=states[0], draw=states[1], away=states[2])

    def calibrate(self, probabilities: MatchResultProbabilitiesV1) -> MatchResultProbabilitiesV1:
        values = (
            _isotonic_probability(probabilities.home, self.home),
            _isotonic_probability(probabilities.draw, self.draw),
            _isotonic_probability(probabilities.away, self.away),
        )
        return _normalize(values, probabilities)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "classes": {
                "HOME": _isotonic_dict(self.home),
                "DRAW": _isotonic_dict(self.draw),
                "AWAY": _isotonic_dict(self.away),
            },
        }


@dataclass(frozen=True, slots=True)
class CalibrationGatePolicyV1:
    max_log_loss_regression: float = 0.0
    max_brier_regression: float = 0.0
    max_ece_regression: float = 0.0
    minimum_improved_metrics: int = 1

    def __post_init__(self) -> None:
        for field_name, value in (
            ("max_log_loss_regression", self.max_log_loss_regression),
            ("max_brier_regression", self.max_brier_regression),
            ("max_ece_regression", self.max_ece_regression),
        ):
            _finite(value, field_name)
            if value < 0.0:
                raise CalibrationContractError(f"{field_name} must not be negative")
        if (
            isinstance(self.minimum_improved_metrics, bool)
            or not isinstance(self.minimum_improved_metrics, int)
            or not 1 <= self.minimum_improved_metrics <= 3
        ):
            raise CalibrationContractError("minimum_improved_metrics must be between 1 and 3")


@dataclass(frozen=True, slots=True)
class CalibrationGateDecisionV1:
    accepted: bool
    raw_metrics: MatchResultMetricsV1
    calibrated_metrics: MatchResultMetricsV1
    reasons: tuple[str, ...]


def evaluate_calibration_gate(
    raw: tuple[EvaluatedMatchResultV1, ...],
    calibrated: tuple[EvaluatedMatchResultV1, ...],
    policy: CalibrationGatePolicyV1 | None = None,
) -> CalibrationGateDecisionV1:
    if len(raw) != len(calibrated) or not raw:
        raise CalibrationContractError("raw and calibrated evaluations must align")
    for raw_item, calibrated_item in zip(raw, calibrated, strict=True):
        if (
            raw_item.kickoff_at != calibrated_item.kickoff_at
            or raw_item.prediction_cutoff != calibrated_item.prediction_cutoff
            or raw_item.outcome_known_at != calibrated_item.outcome_known_at
            or raw_item.outcome != calibrated_item.outcome
        ):
            raise CalibrationContractError("raw and calibrated evaluations must align")
    resolved_policy = policy or CalibrationGatePolicyV1()
    raw_metrics = evaluate_match_results(raw)
    calibrated_metrics = evaluate_match_results(calibrated)
    comparisons = (
        (
            "log_loss",
            raw_metrics.log_loss,
            calibrated_metrics.log_loss,
            resolved_policy.max_log_loss_regression,
        ),
        (
            "brier_score",
            raw_metrics.brier_score,
            calibrated_metrics.brier_score,
            resolved_policy.max_brier_regression,
        ),
        (
            "expected_calibration_error",
            raw_metrics.expected_calibration_error,
            calibrated_metrics.expected_calibration_error,
            resolved_policy.max_ece_regression,
        ),
    )
    reasons = tuple(
        f"{name} regression exceeds tolerance"
        for name, baseline, candidate, tolerance in comparisons
        if candidate > baseline + tolerance
    )
    improved = sum(candidate < baseline - _EPSILON for _, baseline, candidate, _ in comparisons)
    if improved < resolved_policy.minimum_improved_metrics:
        reasons += ("insufficient metric improvement",)
    return CalibrationGateDecisionV1(
        accepted=not reasons,
        raw_metrics=raw_metrics,
        calibrated_metrics=calibrated_metrics,
        reasons=reasons,
    )


def _fit_platt_class(
    probabilities: tuple[float, ...], targets: tuple[float, ...]
) -> PlattClassStateV1:
    if min(targets) == max(targets):
        raise CalibrationContractError("each calibrated class requires positive and negative cases")
    logits = tuple(_logit(value) for value in probabilities)

    def objective(parameters: tuple[float, float]) -> float:
        slope, intercept = float(parameters[0]), float(parameters[1])
        loss = 0.0
        for logit, target in zip(logits, targets, strict=True):
            prediction = _sigmoid(slope * logit + intercept)
            loss -= target * math.log(max(prediction, _EPSILON))
            loss -= (1.0 - target) * math.log(max(1.0 - prediction, _EPSILON))
        return loss + 1e-8 * (slope * slope + intercept * intercept)

    result = minimize(objective, (1.0, 0.0), method="L-BFGS-B")
    if not bool(result.success) or any(not math.isfinite(float(value)) for value in result.x):
        raise CalibrationContractError(f"Platt calibration did not converge: {result.message}")
    return PlattClassStateV1(float(result.x[0]), float(result.x[1]))


def _fit_isotonic_class(
    probabilities: tuple[float, ...], targets: tuple[float, ...]
) -> IsotonicClassStateV1:
    grouped: list[list[float]] = []
    for probability, target in sorted(zip(probabilities, targets, strict=True)):
        if grouped and probability == grouped[-1][0]:
            grouped[-1][1] += target
            grouped[-1][2] += 1.0
        else:
            grouped.append([probability, target, 1.0])
    blocks = [[index, index, total, weight] for index, (_x, total, weight) in enumerate(grouped)]
    index = 0
    while index < len(blocks) - 1:
        if blocks[index][2] / blocks[index][3] <= blocks[index + 1][2] / blocks[index + 1][3]:
            index += 1
            continue
        blocks[index : index + 2] = [
            [
                blocks[index][0],
                blocks[index + 1][1],
                blocks[index][2] + blocks[index + 1][2],
                blocks[index][3] + blocks[index + 1][3],
            ]
        ]
        index = max(index - 1, 0)
    fitted = [0.0] * len(grouped)
    for start, end, total, weight in blocks:
        fitted[int(start) : int(end) + 1] = [total / weight] * (int(end) - int(start) + 1)
    return IsotonicClassStateV1(
        thresholds=tuple(value[0] for value in grouped),
        values=tuple(fitted),
    )


def _platt_probability(probability: float, state: PlattClassStateV1) -> float:
    return _sigmoid(state.slope * _logit(probability) + state.intercept)


def _isotonic_probability(probability: float, state: IsotonicClassStateV1) -> float:
    index = bisect.bisect_left(state.thresholds, probability)
    if index == 0:
        return state.values[0]
    if index == len(state.thresholds):
        return state.values[-1]
    left_x = state.thresholds[index - 1]
    right_x = state.thresholds[index]
    weight = (probability - left_x) / (right_x - left_x)
    return state.values[index - 1] + weight * (state.values[index] - state.values[index - 1])


def _normalize(
    values: tuple[float, float, float], fallback: MatchResultProbabilitiesV1
) -> MatchResultProbabilitiesV1:
    total = sum(values)
    if total <= _EPSILON:
        return fallback
    return MatchResultProbabilitiesV1(
        home=values[0] / total,
        draw=values[1] / total,
        away=values[2] / total,
    )


def _training_observations(
    observations: tuple[EvaluatedMatchResultV1, ...], calibration_cutoff: datetime
) -> None:
    if calibration_cutoff.tzinfo is None or calibration_cutoff.utcoffset() is None:
        raise CalibrationContractError("calibration_cutoff must include a timezone")
    if len(observations) < 3:
        raise CalibrationContractError("calibration requires at least three observations")
    if any(item.outcome_known_at >= calibration_cutoff for item in observations):
        raise CalibrationContractError(
            "calibration observations must be known before calibration_cutoff"
        )
    observed = {item.outcome for item in observations}
    if observed != set(_outcomes()):
        raise CalibrationContractError("calibration requires every match-result class")


def _binary_training(probabilities: tuple[float, ...], targets: tuple[float, ...]) -> None:
    if not probabilities or len(probabilities) != len(targets):
        raise CalibrationContractError("binary calibration probabilities and targets must align")
    if any(not 0.0 <= probability <= 1.0 for probability in probabilities):
        raise CalibrationContractError("binary calibration probabilities must remain in [0, 1]")
    if any(target not in (0.0, 1.0) for target in targets) or min(targets) == max(targets):
        raise CalibrationContractError("binary calibration requires positive and negative events")


def _probabilities(probabilities: MatchResultProbabilitiesV1) -> tuple[float, float, float]:
    return probabilities.home, probabilities.draw, probabilities.away


def _softmax(values: tuple[float, ...]) -> tuple[float, float, float]:
    maximum = max(values)
    weights = tuple(math.exp(value - maximum) for value in values)
    total = sum(weights)
    return weights[0] / total, weights[1] / total, weights[2] / total


def _outcomes() -> tuple[MatchOutcome, MatchOutcome, MatchOutcome]:
    return "HOME", "DRAW", "AWAY"


def _logit(probability: float) -> float:
    clipped = min(max(probability, _EPSILON), 1.0 - _EPSILON)
    return math.log(clipped / (1.0 - clipped))


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _isotonic_dict(state: IsotonicClassStateV1) -> dict[str, object]:
    return {"thresholds": list(state.thresholds), "values": list(state.values)}


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CalibrationContractError(f"{field_name} must be finite")
