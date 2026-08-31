from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from football.contracts.source import canonical_json_bytes
from football.forecasting.adapters import (
    EloOneXTwoAdapterV1,
    corner_forecast_payload,
    dixon_coles_result_probabilities,
    goal_forecast_payload,
)
from football.forecasting.contracts import (
    CornerForecastPayloadV1,
    GoalForecastPayloadV1,
    MatchResultProbabilitiesV1,
    PointInTimeScopeV1,
)
from football.forecasting.corner import (
    CornerFeatures,
    CornerFit,
    CornerFixture,
    CornerForecast,
    CornerMatch,
    CornerModelConfig,
    CornerModels,
)
from football.forecasting.dataset import (
    CompletedMatchV1,
    EvaluationMatchOutcomeV1,
    ForecastMatchContextV1,
    WalkForwardDatasetSpecV1,
    WalkForwardTargetPlanV1,
)
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesFit,
    DixonColesModel,
    DixonColesParameters,
    GoalMatch,
)
from football.forecasting.elo import EloConfig, EloMatch, EloRun, TeamEloModel

if TYPE_CHECKING:
    from football.forecasting.scoring import Sprint2RawMetricsV1


class Sprint2ExecutionError(RuntimeError):
    """Sprint 2 batch fitting or forecasting violated its frozen execution policy."""


@dataclass(frozen=True, slots=True)
class Sprint2ExecutionPolicyV1:
    elo_config: EloConfig = field(default_factory=lambda: EloConfig(model_version="sprint2-elo-v1"))
    dixon_coles_config: DixonColesConfig = field(
        default_factory=lambda: DixonColesConfig(model_version="sprint2-dixon-coles-v1")
    )
    corner_config: CornerModelConfig = field(
        default_factory=lambda: CornerModelConfig(model_version="sprint2-corners-v1")
    )
    elo_draw_propensity: float = 0.5
    feature_set_version: str = "sprint2-team-counts-v1"
    result_reference_version: str = "competition_result_prior_v1"
    goal_reference_version: str = "competition_goal_poisson_prior_v1"
    corner_reference_version: str = "competition_corner_poisson_prior_v1"
    contract: str = "Sprint2ExecutionPolicyV1"

    def __post_init__(self) -> None:
        if self.contract != "Sprint2ExecutionPolicyV1":
            raise Sprint2ExecutionError("unsupported Sprint 2 execution policy")
        if (
            isinstance(self.elo_draw_propensity, bool)
            or not isinstance(self.elo_draw_propensity, (int, float))
            or not math.isfinite(self.elo_draw_propensity)
            or self.elo_draw_propensity <= 0.0
        ):
            raise Sprint2ExecutionError("Elo draw propensity must be finite and positive")
        for field_name, value in (
            ("feature_set_version", self.feature_set_version),
            ("result_reference_version", self.result_reference_version),
            ("goal_reference_version", self.goal_reference_version),
            ("corner_reference_version", self.corner_reference_version),
        ):
            if not value or value.lower() != value or " " in value:
                raise Sprint2ExecutionError(f"{field_name} must be a lowercase version")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "elo_config": self.elo_config.to_dict(),
            "dixon_coles_config": self.dixon_coles_config.to_dict(),
            "corner_config": self.corner_config.to_dict(),
            "elo_draw_propensity": self.elo_draw_propensity,
            "feature_set_version": self.feature_set_version,
            "result_reference_version": self.result_reference_version,
            "goal_reference_version": self.goal_reference_version,
            "corner_reference_version": self.corner_reference_version,
        }


@dataclass(frozen=True, slots=True)
class FittedSprint2BatchV1:
    cutoff: datetime
    training_match_count: int
    elo_run: EloRun
    dixon_coles_fit: DixonColesFit
    corner_poisson_fit: CornerFit
    corner_negative_binomial_fit: CornerFit
    result_reference: MatchResultProbabilitiesV1
    goal_reference: GoalForecastPayloadV1
    corner_reference: CornerForecastPayloadV1


@dataclass(frozen=True, slots=True)
class Sprint2RawForecastV1:
    context: ForecastMatchContextV1
    elo_result: MatchResultProbabilitiesV1
    dixon_coles_result: MatchResultProbabilitiesV1
    goal: GoalForecastPayloadV1
    corner_poisson: CornerForecastPayloadV1
    corner_negative_binomial: CornerForecastPayloadV1
    result_reference: MatchResultProbabilitiesV1
    goal_reference: GoalForecastPayloadV1
    corner_reference: CornerForecastPayloadV1

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "Sprint2RawForecastV1",
            "context": self.context.to_dict(),
            "elo_result": self.elo_result.to_dict(),
            "dixon_coles_result": self.dixon_coles_result.to_dict(),
            "goal": self.goal.to_dict(),
            "corner_poisson": self.corner_poisson.to_dict(),
            "corner_negative_binomial": self.corner_negative_binomial.to_dict(),
            "result_reference": self.result_reference.to_dict(),
            "goal_reference": self.goal_reference.to_dict(),
            "corner_reference": self.corner_reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PersistedSprint2BatchV1:
    cutoff: datetime
    target_match_ids: tuple[UUID, ...]
    model_artifact_ids: tuple[UUID, UUID, UUID, UUID]
    forecast_count: int

    def __post_init__(self) -> None:
        _aware(self.cutoff, "persisted batch cutoff")
        if not self.target_match_ids or len(self.target_match_ids) != len(
            set(self.target_match_ids)
        ):
            raise Sprint2ExecutionError(
                "persisted Sprint 2 batch requires unique target identities"
            )
        if len(set(self.model_artifact_ids)) != 4:
            raise Sprint2ExecutionError(
                "persisted Sprint 2 batch requires four distinct model artifacts"
            )
        if self.forecast_count != 4 * len(self.target_match_ids):
            raise Sprint2ExecutionError(
                "persisted Sprint 2 batch must contain four forecasts per target"
            )


@dataclass(frozen=True, slots=True)
class Sprint2ExecutionResultV1:
    target_count: int
    batch_count: int
    persisted_forecast_count: int
    forecasts: tuple[Sprint2RawForecastV1, ...]
    outcomes: tuple[EvaluationMatchOutcomeV1, ...]
    metrics: Sprint2RawMetricsV1


class Sprint2DatasetPort(Protocol):
    def completed_history(
        self,
        scope: PointInTimeScopeV1,
        competition_id: UUID,
        season_id: UUID,
    ) -> tuple[CompletedMatchV1, ...]: ...

    def reveal_outcomes(
        self,
        spec: WalkForwardDatasetSpecV1,
        match_ids: tuple[UUID, ...],
    ) -> tuple[EvaluationMatchOutcomeV1, ...]: ...


class Sprint2PersistencePort(Protocol):
    def publish_batch(
        self,
        scope: PointInTimeScopeV1,
        fitted: FittedSprint2BatchV1,
        forecasts: tuple[Sprint2RawForecastV1, ...],
    ) -> PersistedSprint2BatchV1: ...


class Sprint2WalkForwardExecutor:
    def __init__(
        self,
        *,
        provider: Sprint2DatasetPort,
        persistence: Sprint2PersistencePort,
        modeler: Sprint2BatchModeler | None = None,
    ) -> None:
        self._provider = provider
        self._persistence = persistence
        self._modeler = modeler or Sprint2BatchModeler()

    def execute(self, plan: WalkForwardTargetPlanV1) -> Sprint2ExecutionResultV1:
        if not plan.batches:
            raise Sprint2ExecutionError("Sprint 2 execution plan has no eligible batches")
        all_forecasts: list[Sprint2RawForecastV1] = []
        all_outcomes: list[EvaluationMatchOutcomeV1] = []
        persisted_forecasts = 0
        for batch in plan.batches:
            scope = plan.scope_for(batch)
            history = self._provider.completed_history(scope, plan.competition_id, plan.season_id)
            history_outcomes = self._provider.reveal_outcomes(
                plan.spec, tuple(match.match_id for match in history)
            )
            fitted = self._modeler.fit(history, history_outcomes, batch.kickoff_at)
            forecasts = self._modeler.forecast_batch(
                fitted, tuple(target.context for target in batch.targets)
            )
            persisted = self._persistence.publish_batch(scope, fitted, forecasts)
            _verify_persisted_batch(batch.kickoff_at, forecasts, persisted)
            target_outcomes = self._provider.reveal_outcomes(
                plan.spec, tuple(forecast.context.match_id for forecast in forecasts)
            )
            all_forecasts.extend(forecasts)
            all_outcomes.extend(target_outcomes)
            persisted_forecasts += persisted.forecast_count
        from football.forecasting.scoring import Sprint2Scorer

        metrics = Sprint2Scorer().evaluate(tuple(all_forecasts), tuple(all_outcomes))
        if len(all_forecasts) != plan.target_count:
            raise Sprint2ExecutionError("Sprint 2 execution coverage does not match target plan")
        return Sprint2ExecutionResultV1(
            target_count=len(all_forecasts),
            batch_count=len(plan.batches),
            persisted_forecast_count=persisted_forecasts,
            forecasts=tuple(all_forecasts),
            outcomes=tuple(all_outcomes),
            metrics=metrics,
        )


class Sprint2BatchModeler:
    def __init__(self, policy: Sprint2ExecutionPolicyV1 | None = None) -> None:
        self.policy = policy or Sprint2ExecutionPolicyV1()

    def fit(
        self,
        history: tuple[CompletedMatchV1, ...],
        outcomes: tuple[EvaluationMatchOutcomeV1, ...],
        cutoff: datetime,
    ) -> FittedSprint2BatchV1:
        _aware(cutoff, "batch cutoff")
        ordered = _validated_history(history, outcomes, cutoff)
        outcomes_by_match = {outcome.match_id: outcome for outcome in outcomes}
        elo_model = TeamEloModel(self.policy.elo_config)
        elo_run = elo_model.rate(tuple(_elo_match(match) for match in ordered))
        dixon_coles_model = DixonColesModel(self.policy.dixon_coles_config)
        dixon_coles_fit = dixon_coles_model.fit(tuple(_goal_match(match) for match in ordered))
        corner_models = CornerModels(self.policy.corner_config)
        corner_comparison = corner_models.fit(
            tuple(_corner_match(match, outcomes_by_match[match.match_id]) for match in ordered)
        )
        return FittedSprint2BatchV1(
            cutoff=cutoff,
            training_match_count=len(ordered),
            elo_run=elo_run,
            dixon_coles_fit=dixon_coles_fit,
            corner_poisson_fit=corner_comparison.poisson,
            corner_negative_binomial_fit=corner_comparison.negative_binomial,
            result_reference=_result_reference(ordered),
            goal_reference=_goal_reference(ordered, self.policy.dixon_coles_config),
            corner_reference=_corner_reference(outcomes),
        )

    def forecast_batch(
        self,
        fitted: FittedSprint2BatchV1,
        targets: tuple[ForecastMatchContextV1, ...],
    ) -> tuple[Sprint2RawForecastV1, ...]:
        if not targets:
            raise Sprint2ExecutionError("Sprint 2 forecast batch must not be empty")
        identifiers = [target.match_id for target in targets]
        if len(identifiers) != len(set(identifiers)):
            raise Sprint2ExecutionError("Sprint 2 forecast batch contains duplicate targets")
        if any(target.kickoff_at != fitted.cutoff for target in targets):
            raise Sprint2ExecutionError("Sprint 2 forecast batch mixes cutoffs")
        return tuple(self._forecast(fitted, target) for target in targets)

    def _forecast(
        self, fitted: FittedSprint2BatchV1, target: ForecastMatchContextV1
    ) -> Sprint2RawForecastV1:
        elo_model = TeamEloModel(self.policy.elo_config)
        elo_adapter = EloOneXTwoAdapterV1(
            draw_propensity=self.policy.elo_draw_propensity,
            home_advantage=self.policy.elo_config.home_advantage,
        )
        elo_result = elo_adapter.forecast(
            elo_model.rating_before(fitted.elo_run, target.home_team_id, fitted.cutoff),
            elo_model.rating_before(fitted.elo_run, target.away_team_id, fitted.cutoff),
        )
        dixon_coles_model = DixonColesModel(self.policy.dixon_coles_config)
        goal_forecast = dixon_coles_model.forecast(
            fitted.dixon_coles_fit.parameters,
            target.home_team_id,
            target.away_team_id,
        )
        corner_models = CornerModels(self.policy.corner_config)
        fixture = CornerFixture(
            competition_id=target.competition_id,
            home_team_id=target.home_team_id,
            away_team_id=target.away_team_id,
            home_features=_ZERO_FEATURES,
            away_features=_ZERO_FEATURES,
        )
        return Sprint2RawForecastV1(
            context=target,
            elo_result=elo_result,
            dixon_coles_result=dixon_coles_result_probabilities(goal_forecast),
            goal=goal_forecast_payload(goal_forecast),
            corner_poisson=corner_forecast_payload(
                corner_models.forecast(fitted.corner_poisson_fit, fixture)
            ),
            corner_negative_binomial=corner_forecast_payload(
                corner_models.forecast(fitted.corner_negative_binomial_fit, fixture)
            ),
            result_reference=fitted.result_reference,
            goal_reference=fitted.goal_reference,
            corner_reference=fitted.corner_reference,
        )


_ZERO_FEATURES = CornerFeatures(0.0, 0.0, 0.0, 0.0)


def _validated_history(
    history: tuple[CompletedMatchV1, ...],
    outcomes: tuple[EvaluationMatchOutcomeV1, ...],
    cutoff: datetime,
) -> tuple[CompletedMatchV1, ...]:
    if not history:
        raise Sprint2ExecutionError("Sprint 2 fitting requires completed history")
    identifiers = [match.match_id for match in history]
    if len(identifiers) != len(set(identifiers)):
        raise Sprint2ExecutionError("Sprint 2 history contains duplicate matches")
    outcomes_by_match = {outcome.match_id: outcome for outcome in outcomes}
    if len(outcomes_by_match) != len(outcomes) or set(identifiers) != set(outcomes_by_match):
        raise Sprint2ExecutionError("Sprint 2 history and governed outcomes must align exactly")
    for match in history:
        outcome = outcomes_by_match[match.match_id]
        if match.kickoff_at >= cutoff:
            raise Sprint2ExecutionError("Sprint 2 history must precede batch cutoff")
        if outcome.outcome_known_at >= cutoff:
            raise Sprint2ExecutionError(
                "Sprint 2 governed history outcome must be known before batch cutoff"
            )
        if (
            outcome.kickoff_at != match.kickoff_at
            or outcome.home_score != match.home_score
            or outcome.away_score != match.away_score
        ):
            raise Sprint2ExecutionError("Sprint 2 history conflicts with governed outcomes")
    return tuple(sorted(history, key=lambda match: (match.kickoff_at, str(match.match_id))))


def _elo_match(match: CompletedMatchV1) -> EloMatch:
    return EloMatch(
        match_id=match.match_id,
        competition_id=match.competition_id,
        kickoff_at=match.kickoff_at,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_score=match.home_score,
        away_score=match.away_score,
    )


def _goal_match(match: CompletedMatchV1) -> GoalMatch:
    return GoalMatch(
        match_id=match.match_id,
        kickoff_at=match.kickoff_at,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_goals=match.home_score,
        away_goals=match.away_score,
    )


def _corner_match(match: CompletedMatchV1, outcome: EvaluationMatchOutcomeV1) -> CornerMatch:
    return CornerMatch(
        match_id=match.match_id,
        competition_id=match.competition_id,
        kickoff_at=match.kickoff_at,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_corners=outcome.home_corners,
        away_corners=outcome.away_corners,
        home_features=_ZERO_FEATURES,
        away_features=_ZERO_FEATURES,
    )


def _result_reference(history: tuple[CompletedMatchV1, ...]) -> MatchResultProbabilitiesV1:
    count = len(history)
    home = sum(match.home_score > match.away_score for match in history) / count
    draw = sum(match.home_score == match.away_score for match in history) / count
    return MatchResultProbabilitiesV1(home=home, draw=draw, away=1.0 - home - draw)


def _goal_reference(
    history: tuple[CompletedMatchV1, ...], config: DixonColesConfig
) -> GoalForecastPayloadV1:
    home_mean = sum(match.home_score for match in history) / len(history)
    away_mean = sum(match.away_score for match in history) / len(history)
    if home_mean <= 0.0 or away_mean <= 0.0:
        raise Sprint2ExecutionError("competition goal reference requires positive goal means")
    teams = {team for match in history for team in (match.home_team_id, match.away_team_id)}
    parameters = DixonColesParameters(
        attack_strengths={team: 0.0 for team in teams},
        defense_strengths={team: math.log(away_mean) for team in teams},
        home_advantage=math.log(home_mean / away_mean),
        low_score_correlation=0.0,
    )
    first = history[0]
    return goal_forecast_payload(
        DixonColesModel(config).forecast(
            parameters,
            first.home_team_id,
            first.away_team_id,
        )
    )


def _corner_reference(
    outcomes: tuple[EvaluationMatchOutcomeV1, ...],
) -> CornerForecastPayloadV1:
    home_mean = sum(outcome.home_corners for outcome in outcomes) / len(outcomes)
    away_mean = sum(outcome.away_corners for outcome in outcomes) / len(outcomes)
    if home_mean <= 0.0 or away_mean <= 0.0:
        raise Sprint2ExecutionError("competition corner reference requires positive corner means")
    return corner_forecast_payload(
        CornerForecast(
            distribution="poisson",
            lambda_home=home_mean,
            lambda_away=away_mean,
            home_variance=home_mean,
            away_variance=away_mean,
            dispersion=None,
        )
    )


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise Sprint2ExecutionError(f"{field_name} must include a timezone")


def _verify_persisted_batch(
    cutoff: datetime,
    forecasts: tuple[Sprint2RawForecastV1, ...],
    persisted: PersistedSprint2BatchV1,
) -> None:
    expected_ids = tuple(forecast.context.match_id for forecast in forecasts)
    if persisted.cutoff != cutoff or persisted.target_match_ids != expected_ids:
        raise Sprint2ExecutionError("persisted Sprint 2 batch does not match frozen forecasts")
