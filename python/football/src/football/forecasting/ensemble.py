from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import numpy as np
from scipy.optimize import minimize

from football.forecasting.model_contracts import (
    ForecastFallbackReason,
    ForecastLineage,
    ForecastMode,
    ModelForecast,
    ModelStatus,
    derive_markets,
    distributions,
)


@dataclass(frozen=True, slots=True)
class EnsembleDevelopmentObservation:
    fixture_id: UUID
    forecasts: tuple[ModelForecast, ...]
    home_goals: int
    away_goals: int
    dataset_role: str = "DEVELOPMENT"


@dataclass(frozen=True, slots=True)
class EnsembleWeights:
    model_weights: tuple[tuple[str, float], ...]
    development_fixture_ids: tuple[UUID, ...]
    objective: str = "JOINT_SCORE_LOG_LOSS"

    def __post_init__(self) -> None:
        values = tuple(weight for _, weight in self.model_weights)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("ensemble weights must be finite and non-negative")
        if not math.isclose(sum(values), 1.0, abs_tol=1e-12):
            raise ValueError("ensemble weights must sum to one")


def learn_ensemble_weights(
    observations: tuple[EnsembleDevelopmentObservation, ...],
) -> EnsembleWeights:
    if not observations:
        raise ValueError("ensemble fitting requires development observations")
    if any(item.dataset_role != "DEVELOPMENT" for item in observations):
        raise ValueError("ensemble weights may be learned only from DEVELOPMENT predictions")
    model_ids = tuple(
        sorted({forecast.model_id for item in observations for forecast in item.forecasts})
    )
    if len(model_ids) < 2:
        raise ValueError("ensemble fitting requires at least two models")

    def objective(values: np.ndarray[Any, Any]) -> float:
        total = 0.0
        for item in observations:
            by_id = {forecast.model_id: forecast for forecast in item.forecasts}
            available = [
                (index, by_id[model_id])
                for index, model_id in enumerate(model_ids)
                if model_id in by_id
            ]
            trained_mass = sum(float(values[index]) for index, _ in available)
            if trained_mass <= 0:
                return math.inf
            probability = sum(
                float(values[index])
                / trained_mass
                * _score_probability(forecast, item.home_goals, item.away_goals)
                for index, forecast in available
            )
            total -= math.log(max(probability, 1e-15))
        return total / len(observations)

    initial = np.full(len(model_ids), 1.0 / len(model_ids), dtype=float)
    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * len(model_ids),
        constraints={"type": "eq", "fun": lambda values: float(np.sum(values) - 1.0)},
    )
    if not result.success or not math.isfinite(float(result.fun)):
        raise ValueError(f"ensemble optimizer failed: {result.message}")
    values = np.maximum(np.asarray(result.x, dtype=float), 0.0)
    values /= values.sum()
    return EnsembleWeights(
        model_weights=tuple(zip(model_ids, (float(value) for value in values), strict=True)),
        development_fixture_ids=tuple(item.fixture_id for item in observations),
    )


def build_ensemble_forecast(
    *,
    forecasts: tuple[ModelForecast, ...],
    weights: EnsembleWeights,
    minimum_components: int = 2,
    minimum_trained_weight: float = 0.5,
    model_artifact_sha256: str,
    model_id: str = "matchforge-ensemble-v1",
    lineage: ForecastLineage | None = None,
) -> ModelForecast | None:
    if minimum_components < 1:
        raise ValueError("minimum_components must be positive")
    configured = dict(weights.model_weights)
    available = tuple(
        forecast
        for forecast in forecasts
        if forecast.status is ModelStatus.SUCCESS and configured.get(forecast.model_id, 0.0) > 0
    )
    trained_mass = sum(configured[forecast.model_id] for forecast in available)
    if len(available) < minimum_components or trained_mass < minimum_trained_weight:
        return None
    effective = tuple(
        (forecast.model_id, configured[forecast.model_id] / trained_mass) for forecast in available
    )
    # Align at the smallest exact support. Expanding an existing tail bucket would
    # invent a distribution inside that bucket; collapsing larger grids preserves
    # every component's declared probability mass without that assumption.
    exact_support = min(_exact_support(forecast) for forecast in available)
    support = exact_support + 1
    combined = np.zeros((support, support), dtype=float)
    for forecast in available:
        combined += dict(effective)[forecast.model_id] * _aligned_matrix(forecast, support)
    matrix = tuple(tuple(float(value) for value in row) for row in combined)
    markets = derive_markets(matrix)
    home_goals, away_goals, total_goals = distributions(matrix)
    first = available[0]
    labels = tuple(str(index) for index in range(exact_support)) + (f"{exact_support}+",)
    return ModelForecast(
        fixture_id=first.fixture_id,
        model_id=model_id,
        model_family="LINEAR_SCORE_DISTRIBUTION_POOL",
        model_version=model_id,
        model_artifact_sha256=model_artifact_sha256,
        football_cutoff=first.football_cutoff,
        knowledge_cutoff=first.knowledge_cutoff,
        created_at=datetime.now(UTC),
        expected_home_goals=sum(index * value for index, value in enumerate(home_goals)),
        expected_away_goals=sum(index * value for index, value in enumerate(away_goals)),
        score_labels=labels,
        score_matrix=matrix,
        home_goal_distribution=home_goals,
        away_goal_distribution=away_goals,
        total_goal_distribution=total_goals,
        status=ModelStatus.SUCCESS,
        warnings=(),
        input_snapshot_sha256=first.input_snapshot_sha256,
        component_weights=effective,
        lineage=lineage,
        **markets,
    )


def build_full_coverage_ensemble_forecast(
    *,
    model_id: str,
    forecasts: tuple[ModelForecast, ...],
    champion_forecast: ModelForecast,
    weights: EnsembleWeights,
    model_artifact_sha256: str,
    minimum_available_weight_mass: float = 0.5,
) -> ModelForecast:
    if model_id not in ("matchforge-ensemble-v2a", "matchforge-ensemble-v2b"):
        raise ValueError("full-coverage ensemble model ID must be V2A or V2B")
    configured = dict(weights.model_weights)

    def trained_weight(forecast: ModelForecast) -> float:
        if forecast.model_id in configured:
            return configured[forecast.model_id]
        if forecast.lineage is not None:
            return configured.get(forecast.lineage.primary_model_id, 0.0)
        return 0.0

    available = tuple(
        forecast
        for forecast in forecasts
        if forecast.status is ModelStatus.SUCCESS and trained_weight(forecast) > 0
    )
    challenger_components = tuple(
        item for item in available if item.model_id != champion_forecast.model_id
    )
    if challenger_components and all(
        item.lineage is not None and item.lineage.champion_fallback_used
        for item in challenger_components
    ):
        reference = challenger_components[0].lineage
        lineage = _ensemble_lineage(
            reference,
            model_id,
            model_artifact_sha256,
            champion_forecast,
            ForecastMode.CHAMPION_FALLBACK,
            ForecastFallbackReason.MODEL_FIT_UNAVAILABLE,
            "ENSEMBLE_FULL_CHAMPION_FALLBACK",
            champion_fallback=True,
        )
        return replace(
            champion_forecast,
            model_id=model_id,
            model_family="LINEAR_SCORE_DISTRIBUTION_POOL",
            model_version=model_id,
            model_artifact_sha256=model_artifact_sha256,
            component_weights=(),
            lineage=lineage,
        )
    available_mass = sum(trained_weight(item) for item in available)
    component_lineages = tuple(item.lineage for item in available if item.lineage is not None)
    reference = component_lineages[0] if component_lineages else None
    if available_mass < minimum_available_weight_mass:
        lineage = _ensemble_lineage(
            reference,
            model_id,
            model_artifact_sha256,
            champion_forecast,
            ForecastMode.CHAMPION_FALLBACK,
            ForecastFallbackReason.MODEL_FIT_UNAVAILABLE,
            "ENSEMBLE_FULL_CHAMPION_FALLBACK",
            champion_fallback=True,
        )
        return replace(
            champion_forecast,
            model_id=model_id,
            model_family="LINEAR_SCORE_DISTRIBUTION_POOL",
            model_version=model_id,
            model_artifact_sha256=model_artifact_sha256,
            component_weights=(),
            lineage=lineage,
        )
    mode = _ensemble_forecast_mode(component_lineages)
    ensemble_mode = (
        "ENSEMBLE_NATIVE"
        if math.isclose(available_mass, 1.0, abs_tol=1e-12)
        else "ENSEMBLE_RENORMALIZED"
    )
    champion_component_used = any(item.model_id == champion_forecast.model_id for item in available)
    if champion_component_used:
        ensemble_mode = "ENSEMBLE_CHAMPION_COMPONENT_USED"
    lineage = _ensemble_lineage(
        reference,
        model_id,
        model_artifact_sha256,
        champion_forecast,
        mode,
        ForecastFallbackReason.NONE,
        ensemble_mode,
        champion_fallback=False,
    )
    remapped_weights = EnsembleWeights(
        model_weights=tuple((item.model_id, trained_weight(item)) for item in available)
        + tuple(
            (model_name, weight)
            for model_name, weight in weights.model_weights
            if model_name not in {item.model_id for item in available}
            and model_name
            not in {item.lineage.primary_model_id for item in available if item.lineage is not None}
        ),
        development_fixture_ids=weights.development_fixture_ids,
    )
    result = build_ensemble_forecast(
        forecasts=available,
        weights=remapped_weights,
        minimum_components=1,
        minimum_trained_weight=minimum_available_weight_mass,
        model_artifact_sha256=model_artifact_sha256,
        model_id=model_id,
        lineage=lineage,
    )
    if result is None:
        raise ValueError("eligible ensemble unexpectedly failed after weight-mass validation")
    return result


def _ensemble_forecast_mode(lineages: tuple[ForecastLineage, ...]) -> ForecastMode:
    cold_modes = {item.forecast_mode for item in lineages}
    if ForecastMode.COLD_START_BOTH in cold_modes or (
        ForecastMode.COLD_START_HOME in cold_modes and ForecastMode.COLD_START_AWAY in cold_modes
    ):
        return ForecastMode.COLD_START_BOTH
    if ForecastMode.COLD_START_HOME in cold_modes:
        return ForecastMode.COLD_START_HOME
    if ForecastMode.COLD_START_AWAY in cold_modes:
        return ForecastMode.COLD_START_AWAY
    return ForecastMode.NATIVE


def _ensemble_lineage(
    reference: ForecastLineage | None,
    model_id: str,
    artifact_sha256: str,
    champion: ModelForecast,
    forecast_mode: ForecastMode,
    fallback_reason: ForecastFallbackReason,
    ensemble_mode: str,
    *,
    champion_fallback: bool,
) -> ForecastLineage:
    return ForecastLineage(
        forecast_mode=forecast_mode,
        primary_model_id=model_id,
        primary_model_artifact_sha256=artifact_sha256,
        fallback_model_id=champion.model_id,
        fallback_model_artifact_sha256=champion.model_artifact_sha256,
        fallback_reason=fallback_reason,
        home_artifact_state=(reference.home_artifact_state if reference else "UNSEEN_TEAM"),
        away_artifact_state=(reference.away_artifact_state if reference else "UNSEEN_TEAM"),
        home_history_state=(reference.home_history_state if reference else "ZERO_HISTORY"),
        away_history_state=(reference.away_history_state if reference else "ZERO_HISTORY"),
        home_promoted=reference.home_promoted if reference else None,
        away_promoted=reference.away_promoted if reference else None,
        native_component_used=not champion_fallback,
        cold_start_component_used=forecast_mode is not ForecastMode.NATIVE
        and not champion_fallback,
        champion_fallback_used=champion_fallback,
        ensemble_mode=ensemble_mode,
    )


def _aligned_matrix(forecast: ModelForecast, support: int) -> np.ndarray[Any, Any]:
    source = np.asarray(forecast.score_matrix, dtype=float)
    target = np.zeros((support, support), dtype=float)
    target_exact = support - 1
    for home_index in range(source.shape[0]):
        for away_index in range(source.shape[1]):
            target[min(home_index, target_exact), min(away_index, target_exact)] += source[
                home_index, away_index
            ]
    return target


def _score_probability(forecast: ModelForecast, home_goals: int, away_goals: int) -> float:
    exact = _exact_support(forecast)
    has_tail = exact < len(forecast.score_matrix)
    if not has_tail and (home_goals >= exact or away_goals >= exact):
        return 0.0
    home_index = min(home_goals, exact)
    away_index = min(away_goals, exact)
    return forecast.score_matrix[home_index][away_index]


def _exact_support(forecast: ModelForecast) -> int:
    return len(forecast.score_labels) - int(forecast.score_labels[-1].endswith("+"))
