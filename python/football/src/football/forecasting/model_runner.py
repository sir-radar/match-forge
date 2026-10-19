from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from football.forecasting.features import FixtureFeatureSnapshotV1
from football.forecasting.model_contracts import (
    FittedModelArtifact,
    ForecastInputSnapshot,
    ForecastModel,
    ModelAvailability,
    ModelRole,
    ModelRunResult,
    ModelStatus,
)
from football.forecasting.penaltyblog_models import (
    PenaltyblogModelError,
    default_penaltyblog_models,
)
from football.forecasting.runtime_models import ModelRegistration

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RegisteredModel:
    adapter: ForecastModel
    artifact: FittedModelArtifact | None
    enabled: bool
    minimum_team_history: int = 5
    registration: ModelRegistration | None = None


class ModelRegistry:
    def __init__(self, models: tuple[RegisteredModel, ...]) -> None:
        identifiers = [item.adapter.model_id for item in models]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("model registry IDs must be unique")
        if sum(item.enabled and item.adapter.role is ModelRole.CHAMPION for item in models) > 1:
            raise ValueError("model registry may contain at most one enabled champion")
        self._models = models

    @classmethod
    def from_registrations(
        cls,
        registrations: tuple[ModelRegistration, ...],
        adapters: tuple[ForecastModel, ...],
        artifacts: Mapping[str, FittedModelArtifact],
        *,
        enabled: frozenset[str],
    ) -> ModelRegistry:
        by_id = {adapter.model_id: adapter for adapter in adapters}
        if len(by_id) != len(adapters) or not enabled.issubset(
            {entry.model_id for entry in registrations}
        ):
            raise ValueError("runtime model selection contains duplicate or unregistered adapters")
        models = []
        for entry in registrations:
            adapter = by_id.get(entry.model_id)
            artifact = artifacts.get(entry.artifact_hash)
            if adapter is None or artifact is None:
                raise ValueError("runtime model implementation or artifact is unavailable")
            _validate_registration(entry, adapter, artifact)
            models.append(
                RegisteredModel(
                    adapter,
                    artifact,
                    entry.model_id in enabled and entry.lifecycle_state != "RETIRED",
                    10 if entry.model_id == "transferable-rolling-goals-poisson-v1" else 5,
                    entry,
                )
            )
        return cls(tuple(models))

    @property
    def models(self) -> tuple[RegisteredModel, ...]:
        return self._models


class ModelRunner:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def run(self, fixture: ForecastInputSnapshot | FixtureFeatureSnapshotV1) -> ModelRunResult:
        features = (
            fixture
            if isinstance(fixture, FixtureFeatureSnapshotV1)
            else FixtureFeatureSnapshotV1(fixture)
        )
        forecasts = []
        availability = []
        for registered in self.registry.models:
            fixture = features.model_input
            adapter = registered.adapter
            if not registered.enabled:
                availability.append(
                    ModelAvailability(
                        adapter.model_id, ModelStatus.MODEL_FIT_UNAVAILABLE, "DISABLED"
                    )
                )
                continue
            if registered.artifact is None:
                availability.append(
                    ModelAvailability(
                        adapter.model_id,
                        ModelStatus.MODEL_FIT_UNAVAILABLE,
                        "NO_ELIGIBLE_FITTED_ARTIFACT",
                    )
                )
                continue
            eligibility = _eligibility(registered, fixture)
            if eligibility is not None:
                availability.append(eligibility)
                continue
            try:
                forecast = adapter.predict(registered.artifact, fixture)
            except PenaltyblogModelError as error:
                status = (
                    ModelStatus.UNSEEN_TEAM
                    if str(error) == ModelStatus.UNSEEN_TEAM
                    else ModelStatus.MODEL_ERROR
                )
                availability.append(ModelAvailability(adapter.model_id, status, str(error)))
                LOGGER.warning(
                    "model forecast unavailable",
                    extra={
                        "fixture_id": str(fixture.fixture_id),
                        "model_id": adapter.model_id,
                        "artifact_sha256": registered.artifact.artifact_sha256,
                        "status": status,
                    },
                )
                continue
            except (ArithmeticError, RuntimeError, ValueError) as error:
                availability.append(
                    ModelAvailability(adapter.model_id, ModelStatus.MODEL_ERROR, str(error))
                )
                LOGGER.exception(
                    "model forecast failed",
                    extra={"fixture_id": str(fixture.fixture_id), "model_id": adapter.model_id},
                )
                continue
            forecasts.append(forecast)
            availability.append(ModelAvailability(adapter.model_id, ModelStatus.SUCCESS))
            LOGGER.info(
                "model predicted",
                extra={
                    "fixture_id": str(fixture.fixture_id),
                    "model_id": adapter.model_id,
                    "artifact_sha256": registered.artifact.artifact_sha256,
                },
            )
        return ModelRunResult(tuple(forecasts), tuple(availability))


def penaltyblog_registry_from_environment(
    artifacts: Mapping[str, FittedModelArtifact], environment: Mapping[str, str]
) -> ModelRegistry:
    """Build the research registry from explicit feature flags and loaded artifacts."""
    flags = {
        "pb-dixon-coles-v1": "MATCHFORGE_MODEL_DIXON_COLES_ENABLED",
        "pb-hierarchical-bayes-v1": "MATCHFORGE_MODEL_HIERARCHICAL_BAYES_ENABLED",
        "pb-negative-binomial-v1": "MATCHFORGE_MODEL_NEGATIVE_BINOMIAL_ENABLED",
        "pb-weibull-copula-v1": "MATCHFORGE_MODEL_WEIBULL_ENABLED",
    }
    return ModelRegistry(
        tuple(
            RegisteredModel(
                adapter=model,
                artifact=artifacts.get(model.model_id),
                enabled=environment.get(flags[model.model_id], "false").casefold() == "true",
            )
            for model in default_penaltyblog_models()
        )
    )


def _validate_registration(
    entry: ModelRegistration, adapter: ForecastModel, artifact: FittedModelArtifact
) -> None:
    if (
        (
            entry.model_id,
            entry.family,
            entry.version,
            entry.feature_contract,
            entry.training_manifest,
            entry.training_start,
            entry.training_cutoff,
            entry.artifact_hash,
            entry.implementation_version,
        )
        != (
            artifact.model_id,
            artifact.model_family,
            artifact.model_version,
            artifact.feature_contract,
            artifact.dataset_sha256,
            artifact.training_start,
            artifact.training_cutoff,
            artifact.artifact_sha256,
            adapter.model_version,
        )
        or adapter.model_id != entry.model_id
        or adapter.model_family != entry.family
    ):
        raise ValueError("runtime model identity conflicts with implementation or fitted artifact")
    if entry.lifecycle_state != "RETIRED" and adapter.role.value != entry.lifecycle_state:
        raise ValueError("runtime lifecycle does not match the approved adapter role")


def _eligibility(
    registered: RegisteredModel, fixture: ForecastInputSnapshot
) -> ModelAvailability | None:
    adapter = registered.adapter
    entry = registered.registration
    if (
        entry is not None
        and entry.eligible_competitions is not None
        and fixture.competition_id not in entry.eligible_competitions
    ):
        return ModelAvailability(
            adapter.model_id, ModelStatus.INSUFFICIENT_DATA, "COMPETITION_NOT_ELIGIBLE"
        )
    if entry is not None and "SCORE_DISTRIBUTION" not in entry.eligible_products:
        return ModelAvailability(
            adapter.model_id, ModelStatus.INSUFFICIENT_DATA, "PRODUCT_NOT_ELIGIBLE"
        )
    home_count = sum(
        fixture.home_team_id in (match.home_team_id, match.away_team_id)
        for match in fixture.qualified_history
    )
    away_count = sum(
        fixture.away_team_id in (match.home_team_id, match.away_team_id)
        for match in fixture.qualified_history
    )
    if min(home_count, away_count) < registered.minimum_team_history:
        return ModelAvailability(
            adapter.model_id,
            ModelStatus.INSUFFICIENT_DATA,
            f"MINIMUM_TEAM_HISTORY_{registered.minimum_team_history}_NOT_MET",
        )
    if adapter.requires_xg and (
        fixture.home_form_10.xg_sample_count == 0 or fixture.away_form_10.xg_sample_count == 0
    ):
        return ModelAvailability(adapter.model_id, ModelStatus.INSUFFICIENT_DATA, "XG_UNAVAILABLE")
    return None
