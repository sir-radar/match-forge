"""Governed additive contextual corrections for baseline goal rates."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import cast
from uuid import UUID

import numpy as np
from scipy.optimize import minimize

MODEL_ID = "MATCHFORGE_CONTEXTUAL_GOAL_MODEL_V1"
ALLOWED_L2 = (0.01, 0.1, 1.0, 10.0)
BOOTSTRAP_BLOCK_LENGTH = 10
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20_260_921


class FeatureFamily(StrEnum):
    AVAILABILITY_LINEUP = "AVAILABILITY_LINEUP"
    REST_CONGESTION = "REST_CONGESTION"
    MANAGER = "MANAGER"
    TRAVEL = "TRAVEL"


class FamilyDisposition(StrEnum):
    DEVELOPMENT_ACCEPTED = "DEVELOPMENT_ACCEPTED"
    DEVELOPMENT_REJECTED = "DEVELOPMENT_REJECTED"
    INSUFFICIENT_QUALIFIED_COVERAGE = "INSUFFICIENT_QUALIFIED_COVERAGE"
    FAIL_CLOSED_PROTOCOL_VIOLATION = "FAIL_CLOSED_PROTOCOL_VIOLATION"


_TEAM_LINEUP = (
    "unavailable_previous_starters_count",
    "injured_previous_starters_count",
    "suspended_previous_starters_count",
    "unavailable_preferred_starters_count",
    "predicted_xi_continuity",
    "confirmed_xi_continuity",
    "formation_changed",
    "coach_preference_replacement_gap",
    "replacement_count",
    "unresolved_lineup_slots",
    "lineup_mode_predicted_repeat_xi",
    "lineup_mode_confirmed",
    "prediction_confidence_high",
    "prediction_confidence_medium",
    "prediction_confidence_low",
)
_TEAM_REST = (
    "days_since_last_match",
    "matches_last_3_days",
    "matches_last_7_days",
    "matches_last_14_days",
    "matches_last_30_days",
    "days_to_next_match",
)
_TEAM_MANAGER = ("coach_tenure_days", "matches_under_coach", "coach_changed_recently")
_TEAM_TRAVEL = ("travel_distance_km", "timezone_delta_hours", "neutral_venue")


def _sided(features: tuple[str, ...], *, differences: bool = False) -> tuple[str, ...]:
    sides = tuple(f"{side}_{feature}" for feature in features for side in ("home", "away"))
    if not differences:
        return sides
    return sides + tuple(f"{feature}_difference" for feature in features)


_LINEUP = _sided(_TEAM_LINEUP)
_REST = _sided(_TEAM_REST, differences=True)
_MANAGER = _sided(_TEAM_MANAGER)
_TRAVEL = _sided(_TEAM_TRAVEL)
_BASE_FEATURES = MappingProxyType(
    {
        FeatureFamily.AVAILABILITY_LINEUP: _LINEUP,
        FeatureFamily.REST_CONGESTION: _REST,
        FeatureFamily.MANAGER: _MANAGER,
        FeatureFamily.TRAVEL: _TRAVEL,
    }
)


@dataclass(frozen=True, slots=True)
class ContextTrainingRow:
    fixture_id: UUID
    kickoff_at: datetime
    competition: str
    baseline_home_rate: float
    baseline_away_rate: float
    home_goals: int
    away_goals: int
    values: Mapping[str, float | None]

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        if not self.competition:
            raise ValueError("competition must not be empty")
        for name, value in (
            ("baseline_home_rate", self.baseline_home_rate),
            ("baseline_away_rate", self.baseline_away_rate),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        for name, value in (("home_goals", self.home_goals), ("away_goals", self.away_goals)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name, context_value in self.values.items():
            if context_value is not None and not math.isfinite(context_value):
                raise ValueError(f"context feature {name} must be finite when present")


@dataclass(frozen=True, slots=True)
class FittedContextFeature:
    feature_name: str
    home_coefficient: float
    away_coefficient: float
    mean: float
    scale: float

    def __post_init__(self) -> None:
        if self.scale <= 0.0 or any(
            not math.isfinite(value)
            for value in (self.home_coefficient, self.away_coefficient, self.mean, self.scale)
        ):
            raise ValueError("context coefficient and scaler values must be finite")


@dataclass(frozen=True, slots=True)
class ContextualGoalArtifactV1:
    model_id: str
    baseline_model: str
    included_families: tuple[FeatureFamily, ...]
    excluded_families: tuple[FeatureFamily, ...]
    family_results: tuple[tuple[FeatureFamily, FamilyDisposition], ...]
    coefficients: tuple[FittedContextFeature, ...]
    missingness_rule: str
    training_cutoff: datetime
    dataset_sha256: str
    configuration_sha256: str
    source_commit: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        _aware(self.training_cutoff, "training_cutoff")
        accepted = {
            family
            for family, result in self.family_results
            if result is FamilyDisposition.DEVELOPMENT_ACCEPTED
        }
        if accepted != set(self.included_families):
            raise ValueError("included families must exactly match accepted family results")
        allowed = {feature for family in accepted for feature in _family_columns(family)}
        if any(item.feature_name not in allowed for item in self.coefficients):
            raise ValueError("artifact coefficients must contain only authorized features")
        _sha256(self.dataset_sha256, "dataset_sha256")
        _sha256(self.configuration_sha256, "configuration_sha256")
        _sha256(self.artifact_sha256, "artifact_sha256")


class ContextualGoalAdjustmentV1:
    """Apply accepted context outside the baseline model's mathematics."""

    def __init__(self, artifact: ContextualGoalArtifactV1) -> None:
        self.artifact = artifact

    def adjust(
        self,
        lambda_home_baseline: float,
        lambda_away_baseline: float,
        values: Mapping[str, float | None],
    ) -> tuple[float, float]:
        for name, value in (
            ("lambda_home_baseline", lambda_home_baseline),
            ("lambda_away_baseline", lambda_away_baseline),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not self.artifact.included_families or not _has_covered_context(
            self.artifact.included_families, values
        ):
            return lambda_home_baseline, lambda_away_baseline
        home_delta = 0.0
        away_delta = 0.0
        for item in self.artifact.coefficients:
            transformed = _runtime_value(item, values)
            home_delta += item.home_coefficient * transformed
            away_delta += item.away_coefficient * transformed
        home = lambda_home_baseline * math.exp(home_delta)
        away = lambda_away_baseline * math.exp(away_delta)
        if not math.isfinite(home) or not math.isfinite(away) or home <= 0.0 or away <= 0.0:
            raise ValueError("context adjustment produced invalid goal rates")
        return home, away


def fit_contextual_adjustment(
    rows: tuple[ContextTrainingRow, ...], family: FeatureFamily, *, l2: float
) -> tuple[FittedContextFeature, ...]:
    """Fit deterministic L2-regularized home and away Poisson corrections."""
    if l2 not in ALLOWED_L2:
        raise ValueError(f"l2 must be one of {ALLOWED_L2}")
    if not rows:
        raise ValueError("context fitting requires training rows")
    ordered = tuple(sorted(rows, key=lambda row: (row.kickoff_at, str(row.fixture_id))))
    columns = tuple(
        column
        for feature in _BASE_FEATURES[family]
        if any(row.values.get(feature) is not None for row in ordered)
        for column in (feature, f"{feature}__coverage", f"{feature}__missing")
    )
    if not columns:
        raise ValueError("context fitting requires at least one qualified feature value")
    means, scales = _scalers(ordered, columns)
    design = np.array(
        [
            [_training_value(row, column, means[column], scales[column]) for column in columns]
            for row in ordered
        ],
        dtype=float,
    )
    base_home = np.log(np.array([row.baseline_home_rate for row in ordered], dtype=float))
    base_away = np.log(np.array([row.baseline_away_rate for row in ordered], dtype=float))
    goals_home = np.array([row.home_goals for row in ordered], dtype=float)
    goals_away = np.array([row.away_goals for row in ordered], dtype=float)
    width = len(columns)

    def objective(vector: np.ndarray[tuple[int], np.dtype[np.float64]]) -> float:
        home_coefficients = vector[:width]
        away_coefficients = vector[width:]
        home_log_rate = base_home + design @ home_coefficients
        away_log_rate = base_away + design @ away_coefficients
        if np.any(home_log_rate > 20.0) or np.any(away_log_rate > 20.0):
            return float("inf")
        loss = np.exp(home_log_rate) - goals_home * home_log_rate
        loss += np.exp(away_log_rate) - goals_away * away_log_rate
        return float(loss.sum() + l2 * np.dot(vector, vector))

    result = minimize(
        objective,
        np.zeros(width * 2, dtype=float),
        method="L-BFGS-B",
        options={"ftol": 1e-12, "gtol": 1e-9, "maxiter": 2_000},
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise ValueError(f"context coefficient fit failed: {result.message}")
    return tuple(
        FittedContextFeature(
            column,
            float(result.x[index]),
            float(result.x[index + width]),
            means[column],
            scales[column],
        )
        for index, column in enumerate(columns)
    )


def build_contextual_artifact(
    *,
    baseline_model: str,
    family_results: Mapping[FeatureFamily, FamilyDisposition],
    fitted: tuple[FittedContextFeature | tuple[str, float, float, float, float], ...],
    training_cutoff: datetime,
    dataset_sha256: str,
    configuration_sha256: str,
    source_commit: str,
) -> ContextualGoalArtifactV1:
    coefficients = tuple(
        item if isinstance(item, FittedContextFeature) else FittedContextFeature(*item)
        for item in fitted
    )
    ordered_results = tuple(
        (family, family_results[family]) for family in FeatureFamily if family in family_results
    )
    included = tuple(
        family
        for family, disposition in ordered_results
        if disposition is FamilyDisposition.DEVELOPMENT_ACCEPTED
    )
    excluded = tuple(family for family in FeatureFamily if family not in included)
    payload = {
        "baseline_model": baseline_model,
        "coefficients": [asdict(item) for item in coefficients],
        "configuration_sha256": configuration_sha256,
        "dataset_sha256": dataset_sha256,
        "excluded_families": [item.value for item in excluded],
        "family_results": [[family.value, result.value] for family, result in ordered_results],
        "included_families": [item.value for item in included],
        "missingness_rule": "FULLY_MISSING_FAMILY_IS_NEUTRAL",
        "model_id": MODEL_ID,
        "source_commit": source_commit,
        "training_cutoff": training_cutoff.isoformat(),
    }
    artifact_sha256 = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return ContextualGoalArtifactV1(
        MODEL_ID,
        baseline_model,
        included,
        excluded,
        ordered_results,
        coefficients,
        "FULLY_MISSING_FAMILY_IS_NEUTRAL",
        training_cutoff,
        dataset_sha256,
        configuration_sha256,
        source_commit,
        artifact_sha256,
    )


def _scalers(
    rows: tuple[ContextTrainingRow, ...], columns: tuple[str, ...]
) -> tuple[dict[str, float], dict[str, float]]:
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for column in columns:
        base, suffix = _column_parts(column)
        if suffix:
            values = [float(row.values.get(base) is not None) for row in rows]
            if suffix == "missing":
                values = [1.0 - value for value in values]
        else:
            values = [
                cast(float, row.values[base]) for row in rows if row.values.get(base) is not None
            ]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means[column] = mean
        scales[column] = math.sqrt(variance) or 1.0
    return means, scales


def _training_value(row: ContextTrainingRow, column: str, mean: float, scale: float) -> float:
    base, suffix = _column_parts(column)
    present = row.values.get(base) is not None
    if suffix == "coverage":
        return (float(present) - mean) / scale
    if suffix == "missing":
        return (float(not present) - mean) / scale
    if not present:
        return 0.0
    return (cast(float, row.values[base]) - mean) / scale


def _runtime_value(item: FittedContextFeature, values: Mapping[str, float | None]) -> float:
    base, suffix = _column_parts(item.feature_name)
    present = values.get(base) is not None
    if suffix == "coverage":
        raw = float(present)
    elif suffix == "missing":
        raw = float(not present)
    elif not present:
        return 0.0
    else:
        raw = cast(float, values[base])
    return (raw - item.mean) / item.scale


def _column_parts(name: str) -> tuple[str, str | None]:
    if name.endswith("__coverage"):
        return name.removesuffix("__coverage"), "coverage"
    if name.endswith("__missing"):
        return name.removesuffix("__missing"), "missing"
    return name, None


def _family_columns(family: FeatureFamily) -> tuple[str, ...]:
    return tuple(
        column
        for feature in _BASE_FEATURES[family]
        for column in (feature, f"{feature}__coverage", f"{feature}__missing")
    )


def _has_covered_context(
    families: tuple[FeatureFamily, ...], values: Mapping[str, float | None]
) -> bool:
    return any(
        values.get(feature) is not None for family in families for feature in _BASE_FEATURES[family]
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
