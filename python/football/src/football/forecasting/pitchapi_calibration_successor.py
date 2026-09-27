"""Development-only shrinkage vector scaling for the PitchAPI V5 successor."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from scipy.optimize import minimize

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_v3_evaluation import calibration_fit

RESEARCH_ID = "PITCHAPI_V5_CALIBRATION_SUCCESSOR_RESEARCH_V1"
ALGORITHM_VERSION = "shrinkage-global-vector-scaling-v1"
DEVELOPMENT_MANIFEST_SHA256 = "be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e"
V5_CHALLENGER_SHA256 = "314e1e0891ffaae6d7fe3885f5bf7e9087bed4b02bdc323e685ee49c11f0675a"
TARGET_COUNT = 216
FORECAST_WARMUP_TARGETS = 72
OOS_BLOCK_TARGETS = 36
SHRINKAGE_STRENGTH = 10.0
SENSITIVITY_STRENGTHS = (5.0, 20.0)
MAX_ITERATIONS = 2_000
FUNCTION_TOLERANCE = 1e-12
GRADIENT_TOLERANCE = 1e-8
PARAMETER_BOUNDS = ((-3.0, 3.0), (-3.0, 3.0), (0.25, 4.0), (0.25, 4.0), (0.25, 4.0))
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20_260_924
BOOTSTRAP_BLOCK_BATCHES = 10


class CalibrationSuccessorError(ValueError):
    """Development calibration input or fitted state violates the frozen contract."""


@dataclass(frozen=True, slots=True)
class CalibrationRowV1:
    match_id: str
    kickoff_at: str
    kickoff_batch: int
    probabilities: tuple[float, float, float]
    outcome: int

    def __post_init__(self) -> None:
        _probabilities(self.probabilities)
        if self.outcome not in (0, 1, 2):
            raise CalibrationSuccessorError("outcome must be home, draw, or away")
        if self.kickoff_batch < 0:
            raise CalibrationSuccessorError("kickoff batch must be non-negative")


@dataclass(frozen=True, slots=True)
class GlobalVectorScalingV1:
    intercept_home: float
    intercept_draw: float
    scale_home: float
    scale_draw: float
    scale_away: float
    shrinkage_strength: float
    training_row_count: int
    converged: bool
    objective: float
    parameter_standard_errors: tuple[float, float, float, float, float]

    def __post_init__(self) -> None:
        values = self.parameters
        if any(
            not math.isfinite(value)
            for value in (*values, *self.parameter_standard_errors, self.objective)
        ):
            raise CalibrationSuccessorError("calibration parameters must be finite")
        if any(value < 0.0 for value in self.parameter_standard_errors):
            raise CalibrationSuccessorError("parameter standard errors must be non-negative")
        if self.shrinkage_strength < 0.0:
            raise CalibrationSuccessorError("shrinkage strength must be non-negative")
        if self.training_row_count <= 0 or not self.converged:
            raise CalibrationSuccessorError("calibration fit must be non-empty and converged")

    @property
    def parameters(self) -> tuple[float, float, float, float, float]:
        return (
            self.intercept_home,
            self.intercept_draw,
            self.scale_home,
            self.scale_draw,
            self.scale_away,
        )

    def calibrate(self, probabilities: tuple[float, float, float]) -> tuple[float, float, float]:
        _probabilities(probabilities)
        logits = (
            self.intercept_home + self.scale_home * math.log(probabilities[0]),
            self.intercept_draw + self.scale_draw * math.log(probabilities[1]),
            self.scale_away * math.log(probabilities[2]),
        )
        maximum = max(logits)
        weights = tuple(math.exp(value - maximum) for value in logits)
        total = sum(weights)
        calibrated = tuple(value / total for value in weights)
        result = (calibrated[0], calibrated[1], calibrated[2])
        _probabilities(result)
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "converged": self.converged,
            "identification": "away_intercept_fixed_zero",
            "objective": self.objective,
            "parameters": {
                "intercept_away": 0.0,
                "intercept_draw": self.intercept_draw,
                "intercept_home": self.intercept_home,
                "scale_away": self.scale_away,
                "scale_draw": self.scale_draw,
                "scale_home": self.scale_home,
            },
            "parameter_standard_errors": {
                "intercept_draw": self.parameter_standard_errors[1],
                "intercept_home": self.parameter_standard_errors[0],
                "scale_away": self.parameter_standard_errors[4],
                "scale_draw": self.parameter_standard_errors[3],
                "scale_home": self.parameter_standard_errors[2],
            },
            "shrinkage_strength": self.shrinkage_strength,
            "training_row_count": self.training_row_count,
        }


def fit_global_vector_scaling(
    rows: Sequence[CalibrationRowV1], *, shrinkage_strength: float
) -> GlobalVectorScalingV1:
    if not rows:
        raise CalibrationSuccessorError("calibration fitting requires rows")
    if not math.isfinite(shrinkage_strength) or shrinkage_strength < 0.0:
        raise CalibrationSuccessorError("shrinkage strength must be finite and non-negative")
    probabilities = np.asarray([row.probabilities for row in rows], dtype=float)
    outcomes = np.asarray([row.outcome for row in rows], dtype=int)
    if set(outcomes.tolist()) != {0, 1, 2}:
        raise CalibrationSuccessorError("calibration fitting requires every outcome class")
    log_probabilities = np.log(probabilities)

    def objective(values: np.ndarray) -> tuple[float, np.ndarray]:
        intercepts = np.asarray([values[0], values[1], 0.0])
        scales = values[2:5]
        linear = intercepts + scales * log_probabilities
        maximum = np.max(linear, axis=1, keepdims=True)
        weights = np.exp(linear - maximum)
        fitted = weights / np.sum(weights, axis=1, keepdims=True)
        observed_linear = linear[np.arange(len(rows)), outcomes]
        loss = float(np.sum(np.log(np.sum(weights, axis=1)) + maximum[:, 0] - observed_linear))
        centred = np.asarray(
            [values[0], values[1], values[2] - 1.0, values[3] - 1.0, values[4] - 1.0]
        )
        loss += 0.5 * shrinkage_strength * float(centred @ centred)
        residual = fitted
        residual[np.arange(len(rows)), outcomes] -= 1.0
        gradient = np.asarray(
            [
                np.sum(residual[:, 0]),
                np.sum(residual[:, 1]),
                np.sum(residual[:, 0] * log_probabilities[:, 0]),
                np.sum(residual[:, 1] * log_probabilities[:, 1]),
                np.sum(residual[:, 2] * log_probabilities[:, 2]),
            ]
        )
        gradient += shrinkage_strength * centred
        return loss, gradient

    result = minimize(
        objective,
        np.asarray([0.0, 0.0, 1.0, 1.0, 1.0]),
        jac=True,
        method="L-BFGS-B",
        bounds=PARAMETER_BOUNDS,
        options={
            "ftol": FUNCTION_TOLERANCE,
            "gtol": GRADIENT_TOLERANCE,
            "maxiter": MAX_ITERATIONS,
        },
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise CalibrationSuccessorError(f"vector scaling did not converge: {result.message}")
    covariance = np.linalg.inv(_penalized_hessian(log_probabilities, result.x, shrinkage_strength))
    standard_errors = np.sqrt(np.diag(covariance))
    if not np.all(np.isfinite(standard_errors)):
        raise CalibrationSuccessorError("vector scaling uncertainty is invalid")
    return GlobalVectorScalingV1(
        intercept_home=float(result.x[0]),
        intercept_draw=float(result.x[1]),
        scale_home=float(result.x[2]),
        scale_draw=float(result.x[3]),
        scale_away=float(result.x[4]),
        shrinkage_strength=shrinkage_strength,
        training_row_count=len(rows),
        converged=True,
        objective=float(result.fun),
        parameter_standard_errors=cast(
            tuple[float, float, float, float, float],
            tuple(float(value) for value in standard_errors),
        ),
    )


def probability_scores(probabilities: tuple[float, float, float], outcome: int) -> dict[str, float]:
    _probabilities(probabilities)
    if outcome not in (0, 1, 2):
        raise CalibrationSuccessorError("score outcome is invalid")
    actual = tuple(float(index == outcome) for index in range(3))
    return {
        "one_x_two_log_loss": -math.log(probabilities[outcome]),
        "one_x_two_brier": sum(
            (probability - target) ** 2
            for probability, target in zip(probabilities, actual, strict=True)
        ),
        "one_x_two_rps": (
            (probabilities[0] - actual[0]) ** 2
            + (probabilities[0] + probabilities[1] - actual[0] - actual[1]) ** 2
        )
        / 2.0,
    }


def calibration_summary(rows: Sequence[CalibrationRowV1]) -> dict[str, object]:
    if not rows:
        raise CalibrationSuccessorError("calibration summary requires rows")
    names = ("home", "draw", "away")
    output: dict[str, object] = {}
    for index, name in enumerate(names):
        fit = calibration_fit(
            tuple(row.probabilities[index] for row in rows),
            tuple(int(row.outcome == index) for row in rows),
        )
        output[name] = {
            "intercept": fit.intercept,
            "intercept_standard_error": fit.intercept_standard_error,
            "slope": fit.slope,
            "slope_standard_error": fit.slope_standard_error,
        }
    return output


def reliability_summary(rows: Sequence[CalibrationRowV1]) -> dict[str, object]:
    if not rows:
        raise CalibrationSuccessorError("reliability summary requires rows")
    bins: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for row in rows:
        for index, probability in enumerate(row.probabilities):
            bins[min(int(probability * 10), 9)].append((probability, int(row.outcome == index)))
    weighted_error = sum(
        len(values)
        * abs(
            sum(item[0] for item in values) / len(values)
            - sum(item[1] for item in values) / len(values)
        )
        for values in bins
        if values
    ) / (3 * len(rows))
    return {
        "expected_calibration_error": weighted_error,
        "bins": [
            {
                "lower": index / 10.0,
                "mean_forecast": sum(item[0] for item in values) / len(values) if values else None,
                "observed_rate": sum(item[1] for item in values) / len(values) if values else None,
                "target_count": len(values),
                "upper": (index + 1) / 10.0,
            }
            for index, values in enumerate(bins)
        ],
    }


def paired_moving_block_interval(
    reference: Sequence[float],
    challenger: Sequence[float],
    kickoff_batches: Sequence[int],
) -> tuple[float, float]:
    if not reference or len(reference) != len(challenger) or len(reference) != len(kickoff_batches):
        raise CalibrationSuccessorError("bootstrap metric series is misaligned")
    batches: list[list[int]] = []
    for index, batch_id in enumerate(kickoff_batches):
        if not batches or kickoff_batches[batches[-1][0]] != batch_id:
            batches.append([index])
        else:
            batches[-1].append(index)
    if len(batches) < BOOTSTRAP_BLOCK_BATCHES:
        raise CalibrationSuccessorError("validation has fewer than 10 kickoff batches")
    randomizer = random.Random(BOOTSTRAP_SEED)
    maximum_start = len(batches) - BOOTSTRAP_BLOCK_BATCHES
    replicates: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        indexes: list[int] = []
        while len(indexes) < len(reference):
            start = randomizer.randrange(maximum_start + 1)
            for selected_batch in batches[start : start + BOOTSTRAP_BLOCK_BATCHES]:
                indexes.extend(selected_batch)
                if len(indexes) >= len(reference):
                    break
        indexes = indexes[: len(reference)]
        replicates.append(
            sum(challenger[index] - reference[index] for index in indexes) / len(indexes)
        )
    ordered = sorted(replicates)
    return _quantile(ordered, 0.025), _quantile(ordered, 0.975)


def rows_sha256(rows: Sequence[CalibrationRowV1]) -> str:
    payload = [
        {
            "kickoff_at": row.kickoff_at,
            "kickoff_batch": row.kickoff_batch,
            "match_id": row.match_id,
            "outcome": row.outcome,
            "probabilities": list(row.probabilities),
        }
        for row in rows
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _probabilities(values: tuple[float, float, float]) -> None:
    if any(not math.isfinite(value) or value <= 0.0 or value >= 1.0 for value in values):
        raise CalibrationSuccessorError("probabilities must be finite and inside (0,1)")
    if abs(sum(values) - 1.0) > 1e-12:
        raise CalibrationSuccessorError("probabilities must sum to one")


def _penalized_hessian(
    log_probabilities: np.ndarray, values: np.ndarray, shrinkage_strength: float
) -> np.ndarray:
    hessian = np.eye(5) * shrinkage_strength
    intercepts = np.asarray([values[0], values[1], 0.0])
    linear = intercepts + values[2:5] * log_probabilities
    weights = np.exp(linear - np.max(linear, axis=1, keepdims=True))
    fitted = weights / np.sum(weights, axis=1, keepdims=True)
    for index, probabilities in enumerate(fitted):
        design = np.asarray(
            [
                [1.0, 0.0, log_probabilities[index, 0], 0.0, 0.0],
                [0.0, 1.0, 0.0, log_probabilities[index, 1], 0.0],
                [0.0, 0.0, 0.0, 0.0, log_probabilities[index, 2]],
            ]
        )
        weight = np.diag(probabilities) - np.outer(probabilities, probabilities)
        hessian += design.T @ weight @ design
    return hessian


def _quantile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction
