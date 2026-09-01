from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid5

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.adapters import EloOneXTwoAdapterV1
from football.forecasting.artifacts import (
    LoadedPortableModelStateV1,
    PublishedModelArtifactV1,
    deserialize_corner_fit,
    deserialize_dixon_coles_fit,
    deserialize_elo_run,
    serialize_corner_fit,
    serialize_dixon_coles_fit,
    serialize_elo_run,
)
from football.forecasting.contracts import (
    BaselineForecastV1,
    CornerForecastPayloadV1,
    GoalForecastPayloadV1,
    MatchResultProbabilitiesV1,
    ModelFamily,
    ModelFitSpecV1,
    PointInTimeScopeV1,
    forecast_payload_sha256,
)
from football.forecasting.execution import (
    FittedSprint2BatchV1,
    PersistedSprint2BatchV1,
    Sprint2BatchModeler,
    Sprint2ExecutionError,
    Sprint2ExecutionPolicyV1,
    Sprint2RawForecastV1,
)
from football.forecasting.publication import PublishedBaselineForecastV1

_ARTIFACT_NAMESPACE = UUID("67e158cd-bb0e-4b3e-9de1-f1bb642a391b")
_FORECAST_NAMESPACE = UUID("4e6df0bc-e808-4fa0-938c-44ad2e3528b1")


class Sprint2ArtifactPublisherPort(Protocol):
    def publish(
        self,
        *,
        model_artifact_id: UUID,
        fit_spec: ModelFitSpecV1,
        state: Mapping[str, object],
        created_at: datetime,
    ) -> PublishedModelArtifactV1: ...


class Sprint2ArtifactLoaderPort(Protocol):
    def load(
        self,
        publication: PublishedModelArtifactV1,
        *,
        expected_feature_contract_version: str,
    ) -> LoadedPortableModelStateV1: ...


class Sprint2ForecastPublisherPort(Protocol):
    def publish(
        self, forecast: BaselineForecastV1, published_at: datetime
    ) -> PublishedBaselineForecastV1: ...


@dataclass(frozen=True, slots=True)
class Sprint2ExecutionProvenanceV1:
    code_commit_sha: str
    dependency_lock_sha256: str
    published_at: datetime

    def __post_init__(self) -> None:
        _aware(self.published_at, "Sprint 2 publication time")


@dataclass(frozen=True, slots=True)
class _ArtifactInput:
    family: ModelFamily
    algorithm_version: str
    config_sha256: str
    state: Mapping[str, object]


class Sprint2BatchPublisher:
    """Freeze one fitted batch and its raw forecasts before outcome reveal."""

    def __init__(
        self,
        *,
        artifact_publisher: Sprint2ArtifactPublisherPort,
        artifact_loader: Sprint2ArtifactLoaderPort,
        forecast_publisher: Sprint2ForecastPublisherPort,
        policy: Sprint2ExecutionPolicyV1,
        provenance: Sprint2ExecutionProvenanceV1,
    ) -> None:
        self._artifacts = artifact_publisher
        self._loader = artifact_loader
        self._forecasts = forecast_publisher
        self._policy = policy
        self._provenance = provenance

    def publish_batch(
        self,
        scope: PointInTimeScopeV1,
        fitted: FittedSprint2BatchV1,
        forecasts: tuple[Sprint2RawForecastV1, ...],
    ) -> PersistedSprint2BatchV1:
        self._validate_batch(scope, fitted, forecasts)
        artifacts, loaded = self._publish_artifacts(scope, fitted)
        reload_delta = self._reload_prediction_delta(fitted, forecasts, loaded)
        published_forecasts = tuple(
            self._publish_target(scope, forecast, artifacts) for forecast in forecasts
        )
        return PersistedSprint2BatchV1(
            cutoff=fitted.cutoff,
            target_match_ids=tuple(forecast.context.match_id for forecast in forecasts),
            model_artifact_ids=(
                artifacts["TEAM_ELO"].manifest.model_artifact_id,
                artifacts["DIXON_COLES_GOALS"].manifest.model_artifact_id,
                artifacts["CORNER_POISSON"].manifest.model_artifact_id,
                artifacts["CORNER_NEGATIVE_BINOMIAL"].manifest.model_artifact_id,
            ),
            forecast_ids=tuple(
                publication.forecast.forecast_id
                for target_publications in published_forecasts
                for publication in target_publications
            ),
            forecast_count=sum(len(target) for target in published_forecasts),
            artifact_reload_max_probability_delta=reload_delta,
        )

    def _validate_batch(
        self,
        scope: PointInTimeScopeV1,
        fitted: FittedSprint2BatchV1,
        forecasts: tuple[Sprint2RawForecastV1, ...],
    ) -> None:
        if scope.football_cutoff != fitted.cutoff:
            raise Sprint2ExecutionError("artifact scope does not match fitted batch cutoff")
        if scope.feature_set_version != self._policy.feature_set_version:
            raise Sprint2ExecutionError("artifact scope does not match execution feature contract")
        if not forecasts:
            raise Sprint2ExecutionError("artifact publication requires target forecasts")
        if any(forecast.context.kickoff_at != fitted.cutoff for forecast in forecasts):
            raise Sprint2ExecutionError("artifact publication batch mixes forecast cutoffs")
        if fitted.elo_run.config != self._policy.elo_config:
            raise Sprint2ExecutionError("fitted Elo state conflicts with execution policy")
        if fitted.dixon_coles_fit.config != self._policy.dixon_coles_config:
            raise Sprint2ExecutionError("fitted Dixon-Coles state conflicts with execution policy")
        if fitted.corner_poisson_fit.config != self._policy.corner_config or (
            fitted.corner_negative_binomial_fit.config != self._policy.corner_config
        ):
            raise Sprint2ExecutionError("fitted corner state conflicts with execution policy")

    def _publish_artifacts(
        self, scope: PointInTimeScopeV1, fitted: FittedSprint2BatchV1
    ) -> tuple[
        dict[ModelFamily, PublishedModelArtifactV1],
        dict[ModelFamily, LoadedPortableModelStateV1],
    ]:
        publications: dict[ModelFamily, PublishedModelArtifactV1] = {}
        loaded_states: dict[ModelFamily, LoadedPortableModelStateV1] = {}
        for item in self._artifact_inputs(fitted):
            fit_spec = ModelFitSpecV1(
                model_family=item.family,
                algorithm_version=item.algorithm_version,
                config_sha256=item.config_sha256,
                scope=scope,
                code_commit_sha=self._provenance.code_commit_sha,
                dependency_lock_sha256=self._provenance.dependency_lock_sha256,
            )
            publication = self._artifacts.publish(
                model_artifact_id=uuid5(_ARTIFACT_NAMESPACE, fit_spec.sha256),
                fit_spec=fit_spec,
                state=item.state,
                created_at=self._provenance.published_at,
            )
            loaded = self._loader.load(
                publication,
                expected_feature_contract_version=scope.feature_set_version,
            )
            _verify_loaded_state(item.family, item.state, loaded)
            publications[item.family] = publication
            loaded_states[item.family] = loaded
        return publications, loaded_states

    def _reload_prediction_delta(
        self,
        fitted: FittedSprint2BatchV1,
        forecasts: tuple[Sprint2RawForecastV1, ...],
        loaded: Mapping[ModelFamily, LoadedPortableModelStateV1],
    ) -> float:
        reloaded = FittedSprint2BatchV1(
            cutoff=fitted.cutoff,
            training_match_count=fitted.training_match_count,
            elo_run=deserialize_elo_run(loaded["TEAM_ELO"].state),
            dixon_coles_fit=deserialize_dixon_coles_fit(loaded["DIXON_COLES_GOALS"].state),
            corner_poisson_fit=deserialize_corner_fit(loaded["CORNER_POISSON"].state),
            corner_negative_binomial_fit=deserialize_corner_fit(
                loaded["CORNER_NEGATIVE_BINOMIAL"].state
            ),
            result_reference=fitted.result_reference,
            goal_reference=fitted.goal_reference,
            corner_reference=fitted.corner_reference,
        )
        reproduced = Sprint2BatchModeler(self._policy).forecast_batch(
            reloaded, tuple(item.context for item in forecasts)
        )
        return max(
            _maximum_numeric_delta(expected.to_dict(), actual.to_dict())
            for expected, actual in zip(forecasts, reproduced, strict=True)
        )

    def _artifact_inputs(self, fitted: FittedSprint2BatchV1) -> tuple[_ArtifactInput, ...]:
        adapter = EloOneXTwoAdapterV1(
            draw_propensity=self._policy.elo_draw_propensity,
            home_advantage=self._policy.elo_config.home_advantage,
        )
        adapter_state = {
            "contract": "EloOneXTwoAdapterV1",
            "algorithm_version": adapter.algorithm_version,
            "draw_propensity": adapter.draw_propensity,
            "home_advantage": adapter.home_advantage,
        }
        elo_state = {**serialize_elo_run(fitted.elo_run), "one_x_two_adapter": adapter_state}
        elo_config_sha256 = sha256_bytes(
            canonical_json_bytes(
                {
                    "elo_config": self._policy.elo_config.to_dict(),
                    "one_x_two_adapter": adapter_state,
                }
            )
        )
        return (
            _ArtifactInput(
                "TEAM_ELO",
                self._policy.elo_config.model_version,
                elo_config_sha256,
                elo_state,
            ),
            _ArtifactInput(
                "DIXON_COLES_GOALS",
                self._policy.dixon_coles_config.model_version,
                self._policy.dixon_coles_config.sha256,
                serialize_dixon_coles_fit(fitted.dixon_coles_fit),
            ),
            _ArtifactInput(
                "CORNER_POISSON",
                self._policy.corner_config.model_version,
                self._policy.corner_config.sha256,
                serialize_corner_fit(fitted.corner_poisson_fit),
            ),
            _ArtifactInput(
                "CORNER_NEGATIVE_BINOMIAL",
                self._policy.corner_config.model_version,
                self._policy.corner_config.sha256,
                serialize_corner_fit(fitted.corner_negative_binomial_fit),
            ),
        )

    def _publish_target(
        self,
        scope: PointInTimeScopeV1,
        raw: Sprint2RawForecastV1,
        artifacts: Mapping[ModelFamily, PublishedModelArtifactV1],
    ) -> tuple[PublishedBaselineForecastV1, ...]:
        context_sha256 = sha256_bytes(canonical_json_bytes(raw.context.to_dict()))
        candidates = (
            _forecast(
                scope,
                raw,
                artifacts["TEAM_ELO"].manifest.model_artifact_id,
                "team-elo",
                context_sha256,
                match_result=raw.elo_result,
            ),
            _forecast(
                scope,
                raw,
                artifacts["DIXON_COLES_GOALS"].manifest.model_artifact_id,
                "dixon-coles-goals",
                context_sha256,
                match_result=raw.dixon_coles_result,
                goal=raw.goal,
            ),
            _forecast(
                scope,
                raw,
                artifacts["CORNER_POISSON"].manifest.model_artifact_id,
                "corner-poisson",
                context_sha256,
                corners=raw.corner_poisson,
            ),
            _forecast(
                scope,
                raw,
                artifacts["CORNER_NEGATIVE_BINOMIAL"].manifest.model_artifact_id,
                "corner-negative-binomial",
                context_sha256,
                corners=raw.corner_negative_binomial,
            ),
        )
        return tuple(
            self._forecasts.publish(candidate, self._provenance.published_at)
            for candidate in candidates
        )


def _forecast(
    scope: PointInTimeScopeV1,
    raw: Sprint2RawForecastV1,
    artifact_id: UUID,
    family: str,
    context_sha256: str,
    *,
    match_result: MatchResultProbabilitiesV1 | None = None,
    goal: GoalForecastPayloadV1 | None = None,
    corners: CornerForecastPayloadV1 | None = None,
) -> BaselineForecastV1:
    payload_sha256 = forecast_payload_sha256(match_result, goal=goal, corners=corners)
    identity = sha256_bytes(
        canonical_json_bytes(
            {
                "contract": "Sprint2RawForecastIdentityV1",
                "family": family,
                "scope": scope.to_dict(),
                "match_id": str(raw.context.match_id),
                "artifact_id": str(artifact_id),
                "forecast_context_sha256": context_sha256,
                "payload_sha256": payload_sha256,
            }
        )
    )
    return BaselineForecastV1(
        forecast_id=uuid5(_FORECAST_NAMESPACE, identity),
        match_id=raw.context.match_id,
        prediction_cutoff=raw.context.kickoff_at,
        scope=scope,
        probability_variant="MODEL_RAW",
        model_artifact_ids=(artifact_id,),
        forecast_context_sha256=context_sha256,
        payload_sha256=payload_sha256,
        match_result=match_result,
        goal=goal,
        corners=corners,
        probability_contract_version="sprint2-probability-products-v1",
    )


def _verify_loaded_state(
    family: ModelFamily,
    expected: Mapping[str, object],
    loaded: LoadedPortableModelStateV1,
) -> None:
    if loaded.state != dict(expected):
        raise Sprint2ExecutionError(f"reloaded {family} artifact state changed")
    if family == "TEAM_ELO":
        deserialize_elo_run(loaded.state)
    elif family == "DIXON_COLES_GOALS":
        deserialize_dixon_coles_fit(loaded.state)
    else:
        deserialize_corner_fit(loaded.state)


def _maximum_numeric_delta(expected: object, actual: object) -> float:
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected != actual:
            raise Sprint2ExecutionError("reloaded forecast structure changed")
        return 0.0
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual))
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            raise Sprint2ExecutionError("reloaded forecast structure changed")
        return max(
            (_maximum_numeric_delta(expected[key], actual[key]) for key in expected),
            default=0.0,
        )
    if isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
        if len(expected) != len(actual):
            raise Sprint2ExecutionError("reloaded forecast structure changed")
        return max(
            (
                _maximum_numeric_delta(left, right)
                for left, right in zip(expected, actual, strict=True)
            ),
            default=0.0,
        )
    if expected != actual:
        raise Sprint2ExecutionError("reloaded forecast structure changed")
    return 0.0


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise Sprint2ExecutionError(f"{field_name} must include a timezone")
