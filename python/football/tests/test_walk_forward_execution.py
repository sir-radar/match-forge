from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from football.forecasting.artifacts import (
    PortableModelArtifactStore,
    PublishedModelArtifactV1,
)
from football.forecasting.contracts import (
    BaselineForecastV1,
    ModelFitSpecV1,
    PointInTimeScopeV1,
)
from football.forecasting.corner import CornerModelConfig
from football.forecasting.dataset import (
    CompletedMatchV1,
    EligibleForecastTargetV1,
    EvaluationMatchOutcomeV1,
    ForecastMatchContextV1,
    WalkForwardDatasetSpecV1,
    WalkForwardTargetBatchV1,
    WalkForwardTargetPlanV1,
)
from football.forecasting.dixon_coles import DixonColesConfig
from football.forecasting.elo import EloConfig
from football.forecasting.execution import (
    FittedSprint2BatchV1,
    PersistedSprint2BatchV1,
    Sprint2BatchModeler,
    Sprint2ExecutionPolicyV1,
    Sprint2RawForecastV1,
    Sprint2WalkForwardExecutor,
)
from football.forecasting.execution_publication import (
    Sprint2BatchPublisher,
    Sprint2ExecutionProvenanceV1,
)
from football.forecasting.publication import (
    ImmutableForecastStore,
    PublishedBaselineForecastV1,
)
from football.forecasting.scoring import Sprint2Scorer
from football.forecasting.uncertainty import BootstrapPolicyV1, paired_moving_block_bootstrap

COMPETITION = UUID("10000000-0000-4000-8000-000000000001")
SEASON = UUID("20000000-0000-4000-8000-000000000001")
TEAMS = tuple(UUID(int=index) for index in range(1, 5))
START = datetime(2015, 8, 1, 14, 0, tzinfo=UTC)


def test_batch_modeler_fits_prior_history_and_emits_every_raw_baseline() -> None:
    history = _history()
    outcomes = tuple(
        EvaluationMatchOutcomeV1(
            match_id=match.match_id,
            kickoff_at=match.kickoff_at,
            home_score=match.home_score,
            away_score=match.away_score,
            home_corners=4 + index % 4,
            away_corners=3 + (index + 1) % 3,
            outcome_known_at=match.kickoff_at + timedelta(hours=2),
        )
        for index, match in enumerate(history)
    )
    cutoff = history[-1].kickoff_at + timedelta(days=7)
    targets = (
        ForecastMatchContextV1(UUID(int=101), COMPETITION, SEASON, cutoff, TEAMS[0], TEAMS[1]),
        ForecastMatchContextV1(UUID(int=102), COMPETITION, SEASON, cutoff, TEAMS[2], TEAMS[3]),
    )
    policy = Sprint2ExecutionPolicyV1(
        elo_config=EloConfig(model_version="sprint2-elo-v1", time_decay_half_life_days=None),
        dixon_coles_config=DixonColesConfig(
            model_version="sprint2-dixon-coles-v1",
            time_decay_half_life_days=None,
            max_iterations=400,
        ),
        corner_config=CornerModelConfig(
            model_version="sprint2-corners-v1",
            time_decay_half_life_days=None,
            max_iterations=400,
        ),
        elo_draw_propensity=0.5,
    )
    modeler = Sprint2BatchModeler(policy)

    fitted = modeler.fit(history, outcomes, cutoff)
    forecasts = modeler.forecast_batch(fitted, targets)
    repeated = modeler.forecast_batch(fitted, tuple(reversed(targets)))

    assert [forecast.context.match_id for forecast in forecasts] == [UUID(int=101), UUID(int=102)]
    assert repeated == tuple(reversed(forecasts))
    assert all(forecast.elo_result.home > 0.0 for forecast in forecasts)
    assert all(forecast.dixon_coles_result.draw > 0.0 for forecast in forecasts)
    assert all(forecast.goal.score_labels[-1] == "5+" for forecast in forecasts)
    assert all(forecast.corner_poisson.distribution == "poisson" for forecast in forecasts)
    assert all(
        forecast.corner_negative_binomial.distribution == "negative_binomial"
        for forecast in forecasts
    )
    assert all(forecast.result_reference.home > 0.0 for forecast in forecasts)
    assert all(forecast.goal_reference.lambda_home > 0.0 for forecast in forecasts)
    assert all(forecast.corner_reference.distribution == "poisson" for forecast in forecasts)
    assert all("score" not in forecast.context.to_dict() for forecast in forecasts)
    assert fitted.training_match_count == len(history)
    assert len(policy.sha256) == 64

    target_outcomes = (
        EvaluationMatchOutcomeV1(UUID(int=101), cutoff, 2, 1, 6, 4, cutoff + timedelta(hours=2)),
        EvaluationMatchOutcomeV1(UUID(int=102), cutoff, 0, 0, 5, 5, cutoff + timedelta(hours=2)),
    )
    metrics = Sprint2Scorer().evaluate(forecasts, target_outcomes)
    comparison_rows = Sprint2Scorer().comparison_rows(forecasts, target_outcomes)
    bootstrap = paired_moving_block_bootstrap(
        Sprint2Scorer().paired_metric_series(comparison_rows),
        BootstrapPolicyV1(replicates=20, block_size=2, seed=7),
    )

    assert metrics.elo_result.sample_count == 2
    assert metrics.dixon_coles_result.sample_count == 2
    assert metrics.goals.sample_count == 2
    assert metrics.corner_poisson.total.sample_count == 2
    assert metrics.corner_negative_binomial.home.sample_count == 2
    assert metrics.result_reference.sample_count == 2
    assert metrics.goal_reference.joint_score_nll > 0.0
    assert metrics.corner_reference.total.negative_log_likelihood > 0.0
    assert len(comparison_rows) == 2
    assert {interval.comparison for interval in bootstrap.intervals} >= {
        "elo_vs_result_reference",
        "dixon_coles_vs_result_reference",
        "dixon_coles_goals_vs_goal_reference",
        "corner_poisson_vs_corner_reference",
    }


def test_executor_persists_complete_batch_before_revealing_target_outcomes() -> None:
    history = _history()
    history_outcomes = _history_outcomes(history)
    cutoff = history[-1].kickoff_at + timedelta(days=7)
    contexts = (
        ForecastMatchContextV1(UUID(int=101), COMPETITION, SEASON, cutoff, TEAMS[0], TEAMS[1]),
        ForecastMatchContextV1(UUID(int=102), COMPETITION, SEASON, cutoff, TEAMS[2], TEAMS[3]),
    )
    spec = WalkForwardDatasetSpecV1(
        dataset_version_id=UUID(int=301),
        source_snapshot_id=UUID(int=302),
        feature_set_version="sprint2-team-counts-v1",
        knowledge_cutoff=cutoff + timedelta(days=1),
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256="a" * 64,
        minimum_team_history=10,
        minimum_competition_history=10,
    )
    batch = WalkForwardTargetBatchV1(
        cutoff,
        tuple(EligibleForecastTargetV1(context, 10, 10, 12) for context in contexts),
    )
    plan = WalkForwardTargetPlanV1(
        spec=spec,
        competition_id=COMPETITION,
        season_id=SEASON,
        batches=(batch,),
        corpus_match_count=14,
        excluded_target_count=12,
    )
    persistence = _Persistence()
    provider = _Dataset(history, history_outcomes, persistence)
    executor = Sprint2WalkForwardExecutor(
        provider=provider,
        persistence=persistence,
        modeler=Sprint2BatchModeler(_policy()),
    )

    result = executor.execute(plan)

    assert result.batch_count == 1
    assert result.target_count == 2
    assert result.persisted_forecast_count == 8
    assert result.metrics.elo_result.sample_count == 2
    assert provider.target_revealed_after_persistence


def test_batch_publisher_freezes_four_artifacts_and_forecasts_with_retry(
    tmp_path: Path,
) -> None:
    history = _history()
    history_outcomes = _history_outcomes(history)
    cutoff = history[-1].kickoff_at + timedelta(days=7)
    context = ForecastMatchContextV1(UUID(int=101), COMPETITION, SEASON, cutoff, TEAMS[0], TEAMS[1])
    policy = _policy()
    fitted = Sprint2BatchModeler(policy).fit(history, history_outcomes, cutoff)
    forecasts = Sprint2BatchModeler(policy).forecast_batch(fitted, (context,))
    scope = PointInTimeScopeV1(
        dataset_version_id=UUID(int=301),
        source_snapshot_id=UUID(int=302),
        feature_set_version=policy.feature_set_version,
        football_cutoff=cutoff,
        knowledge_cutoff=cutoff + timedelta(days=1),
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256="a" * 64,
        target_set_sha256="b" * 64,
    )
    artifact_store = PortableModelArtifactStore(tmp_path)
    forecast_store = ImmutableForecastStore(tmp_path)
    publisher = Sprint2BatchPublisher(
        artifact_publisher=_ArtifactPublisher(artifact_store),
        artifact_loader=artifact_store,
        forecast_publisher=_ForecastPublisher(forecast_store),
        policy=policy,
        provenance=Sprint2ExecutionProvenanceV1(
            code_commit_sha="c" * 40,
            dependency_lock_sha256="d" * 64,
            published_at=cutoff + timedelta(days=2),
        ),
    )

    first = publisher.publish_batch(scope, fitted, forecasts)
    retry = publisher.publish_batch(scope, fitted, forecasts)

    assert first == retry
    assert first.forecast_count == 4
    assert len(first.model_artifact_ids) == 4
    assert len(list(tmp_path.glob("models/family=*/artifact=*/model-state-v1.json"))) == 4
    assert len(list(tmp_path.glob("forecasts/match=*/cutoff=*/variant=*/forecast=*.json"))) == 4


class _Dataset:
    def __init__(
        self,
        history: tuple[CompletedMatchV1, ...],
        history_outcomes: tuple[EvaluationMatchOutcomeV1, ...],
        persistence: _Persistence,
    ) -> None:
        self.history = history
        self.history_outcomes = history_outcomes
        self.persistence = persistence
        self.target_revealed_after_persistence = False

    def completed_history(
        self, scope: PointInTimeScopeV1, competition_id: UUID, season_id: UUID
    ) -> tuple[CompletedMatchV1, ...]:
        assert competition_id == COMPETITION
        assert season_id == SEASON
        return self.history

    def reveal_outcomes(
        self, spec: WalkForwardDatasetSpecV1, match_ids: tuple[UUID, ...]
    ) -> tuple[EvaluationMatchOutcomeV1, ...]:
        history_ids = tuple(match.match_id for match in self.history)
        if match_ids == history_ids:
            return self.history_outcomes
        assert self.persistence.published
        self.target_revealed_after_persistence = True
        cutoff = self.history[-1].kickoff_at + timedelta(days=7)
        return (
            EvaluationMatchOutcomeV1(
                UUID(int=101), cutoff, 2, 1, 6, 4, cutoff + timedelta(hours=2)
            ),
            EvaluationMatchOutcomeV1(
                UUID(int=102), cutoff, 0, 0, 5, 5, cutoff + timedelta(hours=2)
            ),
        )


class _Persistence:
    def __init__(self) -> None:
        self.published = False

    def publish_batch(
        self,
        scope: PointInTimeScopeV1,
        fitted: FittedSprint2BatchV1,
        forecasts: tuple[Sprint2RawForecastV1, ...],
    ) -> PersistedSprint2BatchV1:
        self.published = True
        return PersistedSprint2BatchV1(
            cutoff=START + timedelta(days=84),
            target_match_ids=(UUID(int=101), UUID(int=102)),
            model_artifact_ids=(
                UUID(int=201),
                UUID(int=202),
                UUID(int=203),
                UUID(int=204),
            ),
            forecast_count=8,
        )


class _ArtifactPublisher:
    def __init__(self, store: PortableModelArtifactStore) -> None:
        self.store = store

    def publish(
        self,
        *,
        model_artifact_id: UUID,
        fit_spec: ModelFitSpecV1,
        state: Mapping[str, object],
        created_at: datetime,
    ) -> PublishedModelArtifactV1:
        return self.store.publish(
            model_artifact_id=model_artifact_id,
            fit_spec=fit_spec,
            state=state,
            created_at=created_at,
        )


class _ForecastPublisher:
    def __init__(self, store: ImmutableForecastStore) -> None:
        self.store = store

    def publish(
        self, forecast: BaselineForecastV1, published_at: datetime
    ) -> PublishedBaselineForecastV1:
        return self.store.publish(forecast, published_at)


def _history() -> tuple[CompletedMatchV1, ...]:
    results = (
        (0, 1, 2, 0),
        (2, 3, 1, 0),
        (1, 2, 1, 1),
        (3, 0, 0, 1),
        (0, 2, 3, 1),
        (1, 3, 2, 1),
        (2, 0, 1, 1),
        (3, 1, 0, 2),
        (0, 3, 2, 1),
        (2, 1, 0, 0),
        (1, 0, 1, 2),
        (3, 2, 1, 1),
    )
    return tuple(
        CompletedMatchV1(
            match_id=UUID(int=index + 1),
            competition_id=COMPETITION,
            season_id=SEASON,
            kickoff_at=START + timedelta(days=index * 7),
            home_team_id=TEAMS[home],
            away_team_id=TEAMS[away],
            home_score=home_score,
            away_score=away_score,
        )
        for index, (home, away, home_score, away_score) in enumerate(results)
    )


def _history_outcomes(
    history: tuple[CompletedMatchV1, ...],
) -> tuple[EvaluationMatchOutcomeV1, ...]:
    return tuple(
        EvaluationMatchOutcomeV1(
            match_id=match.match_id,
            kickoff_at=match.kickoff_at,
            home_score=match.home_score,
            away_score=match.away_score,
            home_corners=4 + index % 4,
            away_corners=3 + (index + 1) % 3,
            outcome_known_at=match.kickoff_at + timedelta(hours=2),
        )
        for index, match in enumerate(history)
    )


def _policy() -> Sprint2ExecutionPolicyV1:
    return Sprint2ExecutionPolicyV1(
        elo_config=EloConfig(model_version="sprint2-elo-v1", time_decay_half_life_days=None),
        dixon_coles_config=DixonColesConfig(
            model_version="sprint2-dixon-coles-v1",
            time_decay_half_life_days=None,
            max_iterations=400,
        ),
        corner_config=CornerModelConfig(
            model_version="sprint2-corners-v1",
            time_decay_half_life_days=None,
            max_iterations=400,
        ),
        elo_draw_propensity=0.5,
    )
