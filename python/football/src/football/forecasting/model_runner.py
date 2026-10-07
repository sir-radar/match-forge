from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

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

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RegisteredModel:
    adapter: ForecastModel
    artifact: FittedModelArtifact | None
    enabled: bool
    minimum_team_history: int = 5


class ModelRegistry:
    def __init__(self, models: tuple[RegisteredModel, ...]) -> None:
        identifiers = [item.adapter.model_id for item in models]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("model registry IDs must be unique")
        if sum(item.enabled and item.adapter.role is ModelRole.CHAMPION for item in models) > 1:
            raise ValueError("model registry may contain at most one enabled champion")
        self._models = models

    @property
    def models(self) -> tuple[RegisteredModel, ...]:
        return self._models


class ModelRunner:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def run(self, fixture: ForecastInputSnapshot) -> ModelRunResult:
        forecasts = []
        availability = []
        for registered in self.registry.models:
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


def _eligibility(
    registered: RegisteredModel, fixture: ForecastInputSnapshot
) -> ModelAvailability | None:
    adapter = registered.adapter
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
