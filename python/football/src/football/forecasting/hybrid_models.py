from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import numpy as np
from penaltyblog.models.probabilities import (
    compute_dixon_coles_probabilities,
    compute_negative_binomial_probabilities,
)

from football.forecasting.cold_start import (
    ArtifactTeamState,
    ColdStartConfig,
    ColdStartError,
    ColdStartStrength,
    ColdStartStrengthV1,
    rate_context_adjustments,
)
from football.forecasting.model_contracts import (
    FittedModelArtifact,
    ForecastFallbackReason,
    ForecastInputSnapshot,
    ForecastLineage,
    ForecastMode,
    ForecastModel,
    HistoricalMatch,
    ModelForecast,
    ModelRole,
    ModelStatus,
    derive_markets,
    distributions,
)
from football.forecasting.penaltyblog_models import PenaltyblogGoalModel

_TAIL_TOLERANCE = 1e-10
_INITIAL_SUPPORT = 12
_MAX_SUPPORT = 96
_MODEL_IDS = {
    ("pb-dixon-coles-v1", "V2A"): "pb-dixon-coles-hybrid-v2a",
    ("pb-negative-binomial-v1", "V2A"): "pb-negative-binomial-hybrid-v2a",
    ("pb-weibull-copula-v1", "V2A"): "pb-weibull-copula-hybrid-v2a",
    ("pb-dixon-coles-v1", "V2B"): "pb-dixon-coles-transferable-v2b",
    ("pb-negative-binomial-v1", "V2B"): "pb-negative-binomial-transferable-v2b",
    ("pb-weibull-copula-v1", "V2B"): "pb-weibull-copula-transferable-v2b",
}


class HybridMode(StrEnum):
    V2A = "V2A"
    V2B = "V2B"


class HybridModelError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HybridArtifactRuntime:
    primary_artifact: FittedModelArtifact
    fallback_artifact: FittedModelArtifact


class HybridGoalModel:
    role = ModelRole.CHALLENGER
    supports_unseen_teams = True
    requires_xg = False

    def __init__(
        self,
        *,
        mode: HybridMode,
        primary: PenaltyblogGoalModel,
        fallback: ForecastModel,
        cold_start_config: ColdStartConfig | None,
    ) -> None:
        try:
            self.model_id = _MODEL_IDS[(primary.model_id, mode.value)]
        except KeyError as error:
            raise ValueError(f"unsupported hybrid primary model: {primary.model_id}") from error
        self.model_family = f"{primary.model_family}_{mode.value}"
        self.model_version = self.model_id
        self.mode = mode
        self.primary = primary
        self.fallback = fallback
        self.cold_start_config = cold_start_config

    @classmethod
    def v2a(cls, primary: PenaltyblogGoalModel, fallback: ForecastModel) -> HybridGoalModel:
        return cls(
            mode=HybridMode.V2A,
            primary=primary,
            fallback=fallback,
            cold_start_config=None,
        )

    @classmethod
    def v2b(
        cls,
        primary: PenaltyblogGoalModel,
        fallback: ForecastModel,
        cold_start_config: ColdStartConfig,
    ) -> HybridGoalModel:
        return cls(
            mode=HybridMode.V2B,
            primary=primary,
            fallback=fallback,
            cold_start_config=cold_start_config,
        )

    def fit(
        self, training_data: tuple[HistoricalMatch, ...], config: dict[str, object]
    ) -> FittedModelArtifact:
        raise HybridModelError("fit primary and fallback models separately")

    def predict(
        self, artifact: FittedModelArtifact, fixture: ForecastInputSnapshot
    ) -> ModelForecast:
        runtime = self._runtime(artifact)
        trained = _trained_teams(runtime.primary_artifact)
        home_state = _artifact_state(fixture.home_team_id, trained)
        away_state = _artifact_state(fixture.away_team_id, trained)
        estimator = ColdStartStrengthV1(self.cold_start_config or ColdStartConfig(shrinkage_k=10.0))
        home_history = estimator.classify_history(fixture, fixture.home_team_id)
        away_history = estimator.classify_history(fixture, fixture.away_team_id)
        fitted = home_state is away_state is ArtifactTeamState.FITTED
        if fitted:
            try:
                forecast = self.primary.predict(runtime.primary_artifact, fixture)
            except (ArithmeticError, RuntimeError, ValueError):
                return self._fallback(
                    artifact,
                    runtime,
                    fixture,
                    ForecastFallbackReason.MODEL_ERROR,
                    home_state,
                    away_state,
                    home_history.value,
                    away_history.value,
                )
            return self._relabel(
                forecast,
                artifact,
                ForecastLineage(
                    forecast_mode=ForecastMode.NATIVE,
                    primary_model_id=self.primary.model_id,
                    primary_model_artifact_sha256=runtime.primary_artifact.artifact_sha256,
                    fallback_model_id=self.fallback.model_id,
                    fallback_model_artifact_sha256=runtime.fallback_artifact.artifact_sha256,
                    fallback_reason=ForecastFallbackReason.NONE,
                    home_artifact_state=home_state.value,
                    away_artifact_state=away_state.value,
                    home_history_state=home_history.value,
                    away_history_state=away_history.value,
                    home_promoted=fixture.home_promoted,
                    away_promoted=fixture.away_promoted,
                    native_component_used=True,
                    cold_start_component_used=False,
                    champion_fallback_used=False,
                ),
            )
        if self.mode is HybridMode.V2A:
            return self._fallback(
                artifact,
                runtime,
                fixture,
                _unseen_reason(home_state, away_state),
                home_state,
                away_state,
                home_history.value,
                away_history.value,
            )
        try:
            forecast = self._cold_start_forecast(
                artifact,
                runtime.primary_artifact,
                fixture,
                home_state,
                away_state,
                estimator,
            )
        except (ArithmeticError, ColdStartError, HybridModelError, ValueError):
            return self._fallback(
                artifact,
                runtime,
                fixture,
                ForecastFallbackReason.COLD_START_UNAVAILABLE,
                home_state,
                away_state,
                home_history.value,
                away_history.value,
            )
        return forecast

    def _cold_start_forecast(
        self,
        artifact: FittedModelArtifact,
        primary_artifact: FittedModelArtifact,
        fixture: ForecastInputSnapshot,
        home_state: ArtifactTeamState,
        away_state: ArtifactTeamState,
        estimator: ColdStartStrengthV1,
    ) -> ModelForecast:
        home_strength = (
            estimator.estimate(fixture, fixture.home_team_id)
            if home_state is ArtifactTeamState.UNSEEN_TEAM
            else None
        )
        away_strength = (
            estimator.estimate(fixture, fixture.away_team_id)
            if away_state is ArtifactTeamState.UNSEEN_TEAM
            else None
        )
        labels, matrix = _cold_start_matrix(
            self.primary.model_id,
            primary_artifact,
            fixture,
            home_strength,
            away_strength,
            self.cold_start_config,
        )
        mode = (
            ForecastMode.COLD_START_BOTH
            if home_strength is not None and away_strength is not None
            else ForecastMode.COLD_START_HOME
            if home_strength is not None
            else ForecastMode.COLD_START_AWAY
        )
        markets = derive_markets(matrix)
        home_goals, away_goals, total_goals = distributions(matrix)
        lineage = ForecastLineage(
            forecast_mode=mode,
            primary_model_id=self.primary.model_id,
            primary_model_artifact_sha256=primary_artifact.artifact_sha256,
            fallback_model_id=self.fallback.model_id,
            fallback_model_artifact_sha256=self._runtime(
                artifact
            ).fallback_artifact.artifact_sha256,
            fallback_reason=ForecastFallbackReason.NONE,
            home_artifact_state=home_state.value,
            away_artifact_state=away_state.value,
            home_history_state=(
                home_strength.history_state.value
                if home_strength is not None
                else estimator.classify_history(fixture, fixture.home_team_id).value
            ),
            away_history_state=(
                away_strength.history_state.value
                if away_strength is not None
                else estimator.classify_history(fixture, fixture.away_team_id).value
            ),
            home_promoted=fixture.home_promoted,
            away_promoted=fixture.away_promoted,
            native_component_used=True,
            cold_start_component_used=True,
            champion_fallback_used=False,
        )
        return ModelForecast(
            fixture_id=fixture.fixture_id,
            model_id=self.model_id,
            model_family=self.model_family,
            model_version=self.model_version,
            model_artifact_sha256=artifact.artifact_sha256,
            football_cutoff=fixture.football_cutoff,
            knowledge_cutoff=fixture.knowledge_cutoff,
            created_at=_created_at(primary_artifact),
            expected_home_goals=sum(i * value for i, value in enumerate(home_goals)),
            expected_away_goals=sum(i * value for i, value in enumerate(away_goals)),
            score_labels=labels,
            score_matrix=matrix,
            home_goal_distribution=home_goals,
            away_goal_distribution=away_goals,
            total_goal_distribution=total_goals,
            status=ModelStatus.SUCCESS,
            warnings=("PENALTYBLOG_1_13_0_PROBABILITY_COMPATIBILITY_ADAPTER",),
            input_snapshot_sha256=fixture.sha256,
            lineage=lineage,
            home_probability=markets["home_probability"],
            draw_probability=markets["draw_probability"],
            away_probability=markets["away_probability"],
            btts_yes=markets["btts_yes"],
            btts_no=markets["btts_no"],
            total_over_2_5=markets["total_over_2_5"],
            total_under_2_5=markets["total_under_2_5"],
            home_clean_sheet=markets["home_clean_sheet"],
            away_clean_sheet=markets["away_clean_sheet"],
        )

    def _fallback(
        self,
        artifact: FittedModelArtifact,
        runtime: HybridArtifactRuntime,
        fixture: ForecastInputSnapshot,
        reason: ForecastFallbackReason,
        home_state: ArtifactTeamState,
        away_state: ArtifactTeamState,
        home_history: str,
        away_history: str,
    ) -> ModelForecast:
        champion = self.fallback.predict(runtime.fallback_artifact, fixture)
        lineage = ForecastLineage(
            forecast_mode=ForecastMode.CHAMPION_FALLBACK,
            primary_model_id=self.primary.model_id,
            primary_model_artifact_sha256=runtime.primary_artifact.artifact_sha256,
            fallback_model_id=self.fallback.model_id,
            fallback_model_artifact_sha256=runtime.fallback_artifact.artifact_sha256,
            fallback_reason=reason,
            home_artifact_state=home_state.value,
            away_artifact_state=away_state.value,
            home_history_state=home_history,
            away_history_state=away_history,
            home_promoted=fixture.home_promoted,
            away_promoted=fixture.away_promoted,
            native_component_used=False,
            cold_start_component_used=False,
            champion_fallback_used=True,
        )
        return self._relabel(champion, artifact, lineage)

    def _relabel(
        self,
        forecast: ModelForecast,
        artifact: FittedModelArtifact,
        lineage: ForecastLineage,
    ) -> ModelForecast:
        return replace(
            forecast,
            model_id=self.model_id,
            model_family=self.model_family,
            model_version=self.model_version,
            model_artifact_sha256=artifact.artifact_sha256,
            lineage=lineage,
        )

    def _runtime(self, artifact: FittedModelArtifact) -> HybridArtifactRuntime:
        if artifact.model_id != self.model_id:
            raise HybridModelError("artifact model identity does not match hybrid adapter")
        if not isinstance(artifact.runtime_model, HybridArtifactRuntime):
            raise HybridModelError("hybrid artifact runtime is invalid")
        return artifact.runtime_model


def build_hybrid_artifact(
    model: HybridGoalModel,
    primary_artifact: FittedModelArtifact,
    fallback_artifact: FittedModelArtifact,
    *,
    code_commit_sha: str | None = None,
    dependency_lock_sha256: str | None = None,
) -> FittedModelArtifact:
    if primary_artifact.model_id != model.primary.model_id:
        raise ValueError("primary artifact identity does not match hybrid model")
    if fallback_artifact.model_id != model.fallback.model_id:
        raise ValueError("fallback artifact identity does not match hybrid model")
    primary_params = (
        primary_artifact.runtime_model.get_params()
        if hasattr(primary_artifact.runtime_model, "get_params")
        else {}
    )
    global_parameters = {
        str(key): float(value)
        for key, value in primary_params.items()
        if not str(key).startswith(("attack_", "defence_", "defense_"))
    }
    resolved_code_commit = code_commit_sha or primary_artifact.code_commit_sha
    training_start = min(primary_artifact.training_start, fallback_artifact.training_start)
    training_cutoff = max(primary_artifact.training_cutoff, fallback_artifact.training_cutoff)
    configuration = {
        "contract": "MatchForgeHybridGoalModelV2",
        "artifact_schema_version": "matchforge-hybrid-goal-model-v2",
        "serializer_version": "canonical-json-v1",
        "mode": model.mode.value,
        "primary_model_id": primary_artifact.model_id,
        "primary_model_artifact_sha256": primary_artifact.artifact_sha256,
        "fallback_model_id": fallback_artifact.model_id,
        "fallback_model_artifact_sha256": fallback_artifact.artifact_sha256,
        "code_commit_sha": resolved_code_commit,
        "dependency_lock_sha256": dependency_lock_sha256,
        "dependency_version": primary_artifact.dependency_version,
        "feature_contract": primary_artifact.feature_contract,
        "global_family_parameters": global_parameters,
        "cold_start": _json_value(asdict(model.cold_start_config))
        if model.cold_start_config is not None
        else None,
    }
    identity = {
        "model_id": model.model_id,
        "model_version": model.model_version,
        "training_start": training_start.isoformat(),
        "training_cutoff": training_cutoff.isoformat(),
        "dataset_sha256": primary_artifact.dataset_sha256,
        "configuration": configuration,
        "code_commit_sha": resolved_code_commit,
    }
    artifact_sha = hashlib.sha256(_canonical_json(identity)).hexdigest()
    return FittedModelArtifact(
        model_id=model.model_id,
        model_family=model.model_family,
        model_version=model.model_version,
        artifact_sha256=artifact_sha,
        training_start=training_start,
        training_cutoff=training_cutoff,
        dataset_sha256=primary_artifact.dataset_sha256,
        configuration=configuration,
        dependency_version=primary_artifact.dependency_version,
        code_commit_sha=resolved_code_commit,
        feature_contract=primary_artifact.feature_contract,
        random_seed=primary_artifact.random_seed,
        runtime_model=HybridArtifactRuntime(primary_artifact, fallback_artifact),
        diagnostics={
            "primary_diagnostics": primary_artifact.diagnostics,
            "fallback_diagnostics": fallback_artifact.diagnostics,
        },
    )


def hybrid_artifact_manifest(artifact: FittedModelArtifact) -> dict[str, object]:
    if not isinstance(artifact.runtime_model, HybridArtifactRuntime):
        raise ValueError("artifact is not a hybrid goal model")
    return {
        "contract": "MatchForgeHybridGoalModelArtifactV2",
        "artifact_schema_version": "matchforge-hybrid-goal-model-v2",
        "serializer_version": "canonical-json-v1",
        "model_id": artifact.model_id,
        "model_family": artifact.model_family,
        "model_version": artifact.model_version,
        "artifact_sha256": artifact.artifact_sha256,
        "training_start": artifact.training_start.isoformat(),
        "training_cutoff": artifact.training_cutoff.isoformat(),
        "dataset_sha256": artifact.dataset_sha256,
        "configuration": artifact.configuration,
        "dependency_version": artifact.dependency_version,
        "code_commit_sha": artifact.code_commit_sha,
        "feature_contract": artifact.feature_contract,
        "primary_model_artifact_sha256": (artifact.runtime_model.primary_artifact.artifact_sha256),
        "fallback_model_artifact_sha256": (
            artifact.runtime_model.fallback_artifact.artifact_sha256
        ),
    }


def _cold_start_matrix(
    model_id: str,
    artifact: FittedModelArtifact,
    fixture: ForecastInputSnapshot,
    home_strength: ColdStartStrength | None,
    away_strength: ColdStartStrength | None,
    cold_start_config: ColdStartConfig | None,
) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    if model_id not in ("pb-dixon-coles-v1", "pb-negative-binomial-v1"):
        raise HybridModelError("model family has no tested cold-start compatibility adapter")
    runtime: Any = artifact.runtime_model
    if not hasattr(runtime, "get_params"):
        raise HybridModelError("primary artifact does not expose stable fitted parameters")
    params = {str(key): float(value) for key, value in runtime.get_params().items()}
    attacks = tuple(value for key, value in params.items() if key.startswith("attack_"))
    defence_prefix = "defence_"
    defences = tuple(value for key, value in params.items() if key.startswith(defence_prefix))
    if not attacks or not defences:
        raise HybridModelError("primary artifact team parameters are unavailable")
    home_attack = _team_parameter(
        params,
        "attack_",
        fixture.home_team_id,
        sum(attacks) / len(attacks),
        home_strength.attack_log_strength if home_strength else None,
    )
    away_attack = _team_parameter(
        params,
        "attack_",
        fixture.away_team_id,
        sum(attacks) / len(attacks),
        away_strength.attack_log_strength if away_strength else None,
    )
    home_defence = _team_parameter(
        params,
        defence_prefix,
        fixture.home_team_id,
        sum(defences) / len(defences),
        home_strength.defence_log_strength if home_strength else None,
    )
    away_defence = _team_parameter(
        params,
        defence_prefix,
        fixture.away_team_id,
        sum(defences) / len(defences),
        away_strength.defence_log_strength if away_strength else None,
    )
    global_name = "rho" if model_id == "pb-dixon-coles-v1" else "dispersion"
    home_context = away_context = 0.0
    if cold_start_config is not None:
        home_context, away_context = rate_context_adjustments(cold_start_config, fixture)
    home_attack += home_context
    away_attack += away_context
    compute = (
        compute_dixon_coles_probabilities
        if model_id == "pb-dixon-coles-v1"
        else compute_negative_binomial_probabilities
    )
    support = _INITIAL_SUPPORT
    raw: np.ndarray[Any, Any] | None = None
    unresolved = math.inf
    while support <= _MAX_SUPPORT:
        flattened = np.empty(support * support, dtype=np.float64)
        lambda_home = np.empty(1, dtype=np.float64)
        lambda_away = np.empty(1, dtype=np.float64)
        compute(
            home_attack,
            away_attack,
            home_defence,
            away_defence,
            params["home_advantage"],
            params[global_name],
            support,
            flattened,
            lambda_home,
            lambda_away,
        )
        raw = flattened.reshape((support, support))
        if np.any(~np.isfinite(raw)) or np.any(raw < -_TAIL_TOLERANCE):
            raise HybridModelError("cold-start compatibility adapter returned invalid mass")
        raw = np.maximum(raw, 0.0)
        unresolved = 1.0 - float(raw.sum())
        if -_TAIL_TOLERANCE <= unresolved <= _TAIL_TOLERANCE:
            unresolved = max(0.0, unresolved)
            break
        if unresolved < 0:
            raise HybridModelError("cold-start score mass exceeds one")
        support *= 2
    if raw is None or unresolved > _TAIL_TOLERANCE:
        raise HybridModelError("cold-start score support is insufficient")
    matrix = np.zeros((support + 1, support + 1), dtype=float)
    matrix[:support, :support] = raw
    matrix[support, support] = unresolved
    labels = tuple(str(index) for index in range(support)) + (f"{support}+",)
    return labels, tuple(tuple(float(value) for value in row) for row in matrix)


def _team_parameter(
    params: dict[str, float],
    prefix: str,
    team_id: object,
    family_mean: float,
    cold_start_adjustment: float | None,
) -> float:
    key = f"{prefix}{team_id}"
    if cold_start_adjustment is None:
        try:
            return params[key]
        except KeyError as error:
            raise HybridModelError("fitted team parameter is unavailable") from error
    return family_mean + cold_start_adjustment


def _trained_teams(artifact: FittedModelArtifact) -> frozenset[str]:
    teams = getattr(artifact.runtime_model, "teams", ())
    return frozenset(str(team) for team in teams)


def _artifact_state(team_id: object, trained: frozenset[str]) -> ArtifactTeamState:
    return ArtifactTeamState.FITTED if str(team_id) in trained else ArtifactTeamState.UNSEEN_TEAM


def _unseen_reason(home: ArtifactTeamState, away: ArtifactTeamState) -> ForecastFallbackReason:
    if home is away is ArtifactTeamState.UNSEEN_TEAM:
        return ForecastFallbackReason.BOTH_UNSEEN
    if home is ArtifactTeamState.UNSEEN_TEAM:
        return ForecastFallbackReason.HOME_UNSEEN
    return ForecastFallbackReason.AWAY_UNSEEN


def _created_at(artifact: FittedModelArtifact) -> datetime:
    return datetime.now(UTC)


def _json_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
