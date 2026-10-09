from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from football.forecasting.cold_start import (
    ColdStartConfig,
    ColdStartStrengthV1,
    HistoryTeamState,
    PromotionStatus,
    shrinkage_weight,
)
from football.forecasting.cold_start_fitting import (
    L2_GRID,
    SHRINKAGE_GRID,
    ColdStartDevelopmentObservation,
    chronological_development_split,
    select_cold_start_config,
)
from football.forecasting.ensemble import (
    EnsembleWeights,
    build_full_coverage_ensemble_forecast,
)
from football.forecasting.full_coverage_evaluation import (
    CoverageObservation,
    assert_full_coverage,
    coverage_report,
)
from football.forecasting.hybrid_models import (
    HybridArtifactRuntime,
    HybridGoalModel,
    build_hybrid_artifact,
    hybrid_artifact_manifest,
)
from football.forecasting.model_contracts import (
    CompetitionContext,
    FittedModelArtifact,
    ForecastFallbackReason,
    ForecastInputSnapshot,
    ForecastLineage,
    ForecastMode,
    HistoricalMatch,
    ModelForecast,
    ModelRole,
    ModelStatus,
    derive_markets,
    distributions,
)
from football.forecasting.multimodel_cli import _forecast_dict, _forecast_from_dict
from football.forecasting.penaltyblog_models import default_penaltyblog_models
from football.forecasting.snapshot import build_forecast_snapshot

HOME = UUID(int=1)
AWAY = UUID(int=2)
UNSEEN = UUID(int=3)
COMPETITION = UUID(int=4)
OTHER_COMPETITION = UUID(int=5)
TARGET = UUID(int=6)
KICKOFF = datetime(2026, 10, 7, 18, tzinfo=UTC)


@pytest.mark.parametrize(
    ("n", "k", "expected"),
    ((0, 10.0, 0.0), (10, 10.0, 0.5), (30, 10.0, 0.75)),
)
def test_shrinkage_weight_limits(n: int, k: float, expected: float) -> None:
    assert shrinkage_weight(n, k) == pytest.approx(expected)
    assert shrinkage_weight(n, k) < 1.0


def test_shrinkage_weight_is_monotonic_and_larger_k_shrinks_more() -> None:
    values = [shrinkage_weight(n, 10.0) for n in range(20)]
    assert values == sorted(values)
    assert shrinkage_weight(5, 20.0) < shrinkage_weight(5, 2.0)


def test_zero_history_uses_competition_prior_and_preserves_xg_missingness() -> None:
    snapshot = _snapshot(_competition_history(), away=UNSEEN)

    strength = ColdStartStrengthV1(ColdStartConfig(shrinkage_k=10.0)).estimate(snapshot, UNSEEN)

    assert strength.history_state is HistoryTeamState.ZERO_HISTORY
    assert strength.attack_log_strength == 0.0
    assert strength.defence_log_strength == 0.0
    assert strength.history_weight == 0.0
    assert strength.xg_signal is None
    assert "XG_UNAVAILABLE" in strength.missingness
    assert strength.promotion_status is PromotionStatus.PROMOTION_STATUS_UNKNOWN


def test_transfer_history_requires_explicit_competition_weight() -> None:
    transfer = _match(
        90,
        KICKOFF - timedelta(days=2),
        UNSEEN,
        HOME,
        2,
        1,
        competition=OTHER_COMPETITION,
    )
    snapshot = _snapshot(_competition_history() + (transfer,), away=UNSEEN)

    unknown = ColdStartStrengthV1(ColdStartConfig(shrinkage_k=10.0)).estimate(snapshot, UNSEEN)
    qualified = ColdStartStrengthV1(
        ColdStartConfig(
            shrinkage_k=10.0,
            competition_transfer_weights=((OTHER_COMPETITION, COMPETITION, 0.5),),
        )
    ).estimate(snapshot, UNSEEN)

    assert unknown.history_state is HistoryTeamState.ZERO_HISTORY
    assert unknown.effective_history_matches == 0.0
    assert qualified.history_state is HistoryTeamState.TRANSFER_HISTORY
    assert qualified.effective_history_matches == pytest.approx(0.5)
    assert qualified.source_competition_context == (str(OTHER_COMPETITION),)


def test_history_and_promotion_classification_use_explicit_point_in_time_data() -> None:
    history = _competition_history()
    full_snapshot = _snapshot(history)
    partial_snapshot = _snapshot(history[:4])
    promoted_snapshot = build_forecast_snapshot(
        fixture_id=TARGET,
        competition_id=COMPETITION,
        competition_context=CompetitionContext.LEAGUE,
        season_label="2026",
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        football_cutoff=KICKOFF,
        knowledge_cutoff=KICKOFF,
        knowledge_mode="bitemporal",
        history=history,
        home_promoted=True,
        away_promoted=False,
    )
    estimator = ColdStartStrengthV1(ColdStartConfig(shrinkage_k=10.0))

    assert estimator.classify_history(full_snapshot, HOME) is HistoryTeamState.FULL_HISTORY
    assert estimator.classify_history(partial_snapshot, HOME) is HistoryTeamState.PARTIAL_HISTORY
    assert (
        estimator.estimate(promoted_snapshot, HOME).promotion_status
        is PromotionStatus.PROMOTED_TEAM
    )
    assert (
        estimator.estimate(promoted_snapshot, AWAY).promotion_status is PromotionStatus.NOT_PROMOTED
    )


def test_zero_xg_is_observed_but_missing_xg_stays_unavailable() -> None:
    snapshot = _snapshot(_competition_history(), away=UNSEEN)
    zero_xg = replace(
        snapshot,
        away_form_10=replace(
            snapshot.away_form_10,
            xg_for=0.0,
            xg_against=0.0,
            xg_difference=0.0,
            xg_sample_count=1,
        ),
    )
    estimator = ColdStartStrengthV1(ColdStartConfig(shrinkage_k=10.0))

    missing = estimator.estimate(snapshot, UNSEEN)
    observed_zero = estimator.estimate(zero_xg, UNSEEN)

    assert missing.xg_signal is None
    assert observed_zero.xg_signal is not None
    assert all(value == value and abs(value) != float("inf") for value in observed_zero.xg_signal)


@pytest.mark.parametrize("model_index", (0, 2, 3))
def test_v2a_uses_native_for_fitted_teams_and_whole_champion_for_unseen(
    model_index: int,
) -> None:
    primary = default_penaltyblog_models()[model_index]
    history = _competition_history()
    primary_artifact = primary.fit(history, {"code_commit_sha": "a" * 40})
    champion = _ChampionModel()
    champion_artifact = _artifact("transferable-rolling-goals-poisson-v1")
    model = HybridGoalModel.v2a(primary, champion)
    artifact = build_hybrid_artifact(model, primary_artifact, champion_artifact)

    native = model.predict(artifact, _snapshot(history))
    unseen = model.predict(artifact, _snapshot(history, away=UNSEEN))
    champion_expected = champion.predict(champion_artifact, _snapshot(history, away=UNSEEN))

    assert native.lineage is not None
    assert native.lineage.forecast_mode is ForecastMode.NATIVE
    assert native.lineage.native_component_used
    assert unseen.lineage is not None
    assert unseen.lineage.forecast_mode is ForecastMode.CHAMPION_FALLBACK
    assert unseen.lineage.fallback_reason is ForecastFallbackReason.AWAY_UNSEEN
    assert unseen.lineage.champion_fallback_used
    assert unseen.score_matrix == champion_expected.score_matrix
    assert unseen.model_id.endswith("-hybrid-v2a")


def test_v2b_dixon_coles_cold_start_returns_valid_distribution() -> None:
    primary = default_penaltyblog_models()[0]
    history = _competition_history()
    primary_artifact = primary.fit(history, {"code_commit_sha": "a" * 40})
    champion = _ChampionModel()
    champion_artifact = _artifact("transferable-rolling-goals-poisson-v1")
    model = HybridGoalModel.v2b(
        primary,
        champion,
        ColdStartConfig(shrinkage_k=10.0),
    )
    artifact = build_hybrid_artifact(model, primary_artifact, champion_artifact)

    forecast = model.predict(artifact, _snapshot(history, away=UNSEEN))

    assert forecast.lineage is not None
    assert forecast.lineage.forecast_mode is ForecastMode.COLD_START_AWAY
    assert forecast.lineage.cold_start_component_used
    assert not forecast.lineage.champion_fallback_used
    assert sum(sum(row) for row in forecast.score_matrix) == pytest.approx(1.0)
    assert all(value >= 0 for row in forecast.score_matrix for value in row)


def test_v2b_falls_back_when_global_family_state_is_not_supported() -> None:
    primary = default_penaltyblog_models()[3]
    history = _competition_history()
    primary_artifact = primary.fit(history, {"code_commit_sha": "a" * 40})
    champion = _ChampionModel()
    champion_artifact = _artifact("transferable-rolling-goals-poisson-v1")
    model = HybridGoalModel.v2b(primary, champion, ColdStartConfig(shrinkage_k=10.0))
    artifact = build_hybrid_artifact(model, primary_artifact, champion_artifact)

    forecast = model.predict(artifact, _snapshot(history, away=UNSEEN))

    assert forecast.lineage is not None
    assert forecast.lineage.forecast_mode is ForecastMode.CHAMPION_FALLBACK
    assert forecast.lineage.fallback_reason is ForecastFallbackReason.COLD_START_UNAVAILABLE


def test_hybrid_artifact_keeps_v1_artifacts_immutable() -> None:
    primary = _artifact("pb-dixon-coles-v1")
    champion = _artifact("transferable-rolling-goals-poisson-v1")
    model = HybridGoalModel.v2a(default_penaltyblog_models()[0], _ChampionModel())

    artifact = build_hybrid_artifact(model, primary, champion)

    assert isinstance(artifact.runtime_model, HybridArtifactRuntime)
    assert artifact.runtime_model.primary_artifact is primary
    assert artifact.runtime_model.fallback_artifact is champion
    assert artifact.artifact_sha256 not in {
        primary.artifact_sha256,
        champion.artifact_sha256,
    }


def test_hybrid_artifact_uses_verified_team_id_alias_for_native_forecast() -> None:
    primary = default_penaltyblog_models()[0]
    history = _competition_history()
    primary_artifact = primary.fit(history, {"code_commit_sha": "a" * 40})
    champion = _ChampionModel()
    model = HybridGoalModel.v2a(primary, champion)
    artifact = build_hybrid_artifact(
        model,
        primary_artifact,
        _artifact("transferable-rolling-goals-poisson-v1"),
        team_id_aliases=((str(UNSEEN), str(AWAY)),),
    )

    forecast = model.predict(artifact, _snapshot(history, away=UNSEEN))

    assert forecast.lineage is not None
    assert forecast.lineage.forecast_mode is ForecastMode.NATIVE
    assert forecast.input_snapshot_sha256 == _snapshot(history, away=UNSEEN).sha256


def test_hybrid_artifact_manifest_records_reproducibility_contract() -> None:
    primary = _artifact("pb-dixon-coles-v1")
    champion = _artifact("transferable-rolling-goals-poisson-v1")
    model = HybridGoalModel.v2b(
        default_penaltyblog_models()[0],
        _ChampionModel(),
        ColdStartConfig(shrinkage_k=20.0, l2_regularization=0.1),
    )

    artifact = build_hybrid_artifact(
        model,
        primary,
        champion,
        code_commit_sha="c" * 40,
        dependency_lock_sha256="d" * 64,
    )
    manifest = hybrid_artifact_manifest(artifact)

    assert manifest["artifact_sha256"] == artifact.artifact_sha256
    assert manifest["primary_model_artifact_sha256"] == primary.artifact_sha256
    assert manifest["fallback_model_artifact_sha256"] == champion.artifact_sha256
    assert manifest["code_commit_sha"] == "c" * 40
    assert manifest["configuration"] == artifact.configuration
    assert artifact.configuration["dependency_lock_sha256"] == "d" * 64
    cold_start = artifact.configuration["cold_start"]
    assert isinstance(cold_start, dict)
    assert cold_start["l2_regularization"] == 0.1
    assert cold_start["shrinkage_k"] == 20.0
    assert cold_start["competition_transfer_weights"] == []


def test_v2_ensemble_renormalizes_frozen_weights_and_falls_back_below_half_mass() -> None:
    champion_model = _ChampionModel()
    champion_artifact = _artifact("transferable-rolling-goals-poisson-v1")
    snapshot = _snapshot(_competition_history())
    champion = champion_model.predict(champion_artifact, snapshot)
    component = replace(
        champion,
        model_id="pb-dixon-coles-hybrid-v2a",
        lineage=ForecastLineage(
            forecast_mode=ForecastMode.NATIVE,
            primary_model_id="pb-dixon-coles-v1",
            primary_model_artifact_sha256="a" * 64,
            fallback_model_id=champion.model_id,
            fallback_model_artifact_sha256=champion.model_artifact_sha256,
            fallback_reason=ForecastFallbackReason.NONE,
            home_artifact_state="FITTED",
            away_artifact_state="FITTED",
            home_history_state="FULL_HISTORY",
            away_history_state="FULL_HISTORY",
            home_promoted=None,
            away_promoted=None,
            native_component_used=True,
            cold_start_component_used=False,
            champion_fallback_used=False,
        ),
    )
    enough = EnsembleWeights(
        (("pb-dixon-coles-v1", 0.6), ("pb-negative-binomial-v1", 0.4)),
        (TARGET,),
    )
    insufficient = EnsembleWeights(
        (("pb-dixon-coles-v1", 0.4), ("pb-negative-binomial-v1", 0.6)),
        (TARGET,),
    )

    pooled = build_full_coverage_ensemble_forecast(
        model_id="matchforge-ensemble-v2a",
        forecasts=(component,),
        champion_forecast=champion,
        weights=enough,
        model_artifact_sha256="e" * 64,
    )
    fallback = build_full_coverage_ensemble_forecast(
        model_id="matchforge-ensemble-v2a",
        forecasts=(component,),
        champion_forecast=champion,
        weights=insufficient,
        model_artifact_sha256="f" * 64,
    )

    assert pooled.component_weights == ((component.model_id, 1.0),)
    assert pooled.lineage is not None
    assert pooled.lineage.ensemble_mode == "ENSEMBLE_RENORMALIZED"
    assert fallback.score_matrix == champion.score_matrix
    assert fallback.lineage is not None
    assert fallback.lineage.ensemble_mode == "ENSEMBLE_FULL_CHAMPION_FALLBACK"
    assert fallback.lineage.champion_fallback_used


def test_v2_ensemble_uses_whole_champion_when_every_challenger_falls_back() -> None:
    champion_model = _ChampionModel()
    champion_artifact = _artifact("transferable-rolling-goals-poisson-v1")
    snapshot = _snapshot(_competition_history(), away=UNSEEN)
    champion = champion_model.predict(champion_artifact, snapshot)
    component = replace(
        champion,
        model_id="pb-dixon-coles-hybrid-v2a",
        lineage=ForecastLineage(
            forecast_mode=ForecastMode.CHAMPION_FALLBACK,
            primary_model_id="pb-dixon-coles-v1",
            primary_model_artifact_sha256="a" * 64,
            fallback_model_id=champion.model_id,
            fallback_model_artifact_sha256=champion.model_artifact_sha256,
            fallback_reason=ForecastFallbackReason.AWAY_UNSEEN,
            home_artifact_state="FITTED",
            away_artifact_state="UNSEEN_TEAM",
            home_history_state="FULL_HISTORY",
            away_history_state="ZERO_HISTORY",
            home_promoted=False,
            away_promoted=None,
            native_component_used=False,
            cold_start_component_used=False,
            champion_fallback_used=True,
        ),
    )
    weights = EnsembleWeights(
        (("pb-dixon-coles-v1", 0.6), (champion.model_id, 0.4)),
        (TARGET,),
    )

    result = build_full_coverage_ensemble_forecast(
        model_id="matchforge-ensemble-v2a",
        forecasts=(champion, component),
        champion_forecast=champion,
        weights=weights,
        model_artifact_sha256="e" * 64,
    )

    assert result.score_matrix == champion.score_matrix
    assert result.lineage is not None
    assert result.lineage.forecast_mode is ForecastMode.CHAMPION_FALLBACK
    assert result.lineage.champion_fallback_used


def test_coverage_accounting_keeps_native_cold_start_and_fallback_distinct() -> None:
    champion_model = _ChampionModel()
    champion_artifact = _artifact("transferable-rolling-goals-poisson-v1")
    base = champion_model.predict(champion_artifact, _snapshot(_competition_history()))
    modes = (
        ForecastMode.NATIVE,
        ForecastMode.COLD_START_AWAY,
        ForecastMode.CHAMPION_FALLBACK,
    )
    observations = tuple(
        CoverageObservation(
            replace(
                base,
                fixture_id=UUID(int=20 + index),
                lineage=ForecastLineage(
                    forecast_mode=mode,
                    primary_model_id="candidate",
                    primary_model_artifact_sha256="a" * 64,
                    fallback_model_id=base.model_id,
                    fallback_model_artifact_sha256=base.model_artifact_sha256,
                    fallback_reason=(
                        ForecastFallbackReason.AWAY_UNSEEN
                        if mode is ForecastMode.CHAMPION_FALLBACK
                        else ForecastFallbackReason.NONE
                    ),
                    home_artifact_state="FITTED",
                    away_artifact_state=(
                        "FITTED" if mode is ForecastMode.NATIVE else "UNSEEN_TEAM"
                    ),
                    home_history_state="FULL_HISTORY",
                    away_history_state=(
                        "FULL_HISTORY" if mode is ForecastMode.NATIVE else "ZERO_HISTORY"
                    ),
                    home_promoted=False,
                    away_promoted=None,
                    native_component_used=mode is not ForecastMode.CHAMPION_FALLBACK,
                    cold_start_component_used=mode is ForecastMode.COLD_START_AWAY,
                    champion_fallback_used=mode is ForecastMode.CHAMPION_FALLBACK,
                ),
            ),
            competition_id="league",
            season_label="2026",
        )
        for index, mode in enumerate(modes)
    )

    report = coverage_report(observations, eligible_targets=3)

    assert report["coverage"] == 1.0
    assert report["native_fitted_count"] == 1
    assert report["cold_start_away_count"] == 1
    assert report["champion_fallback_count"] == 1
    assert report["fallback_rate"] == pytest.approx(1 / 3)
    assert_full_coverage(observations, eligible_targets=3)


def test_development_split_keeps_kickoff_batches_together_and_freezes_grid() -> None:
    history = _competition_history()
    observations = tuple(
        ColdStartDevelopmentObservation(
            build_forecast_snapshot(
                fixture_id=UUID(int=500 + index),
                competition_id=COMPETITION,
                competition_context=CompetitionContext.LEAGUE,
                season_label="development",
                kickoff_at=KICKOFF + timedelta(days=index + 1),
                home_team_id=HOME,
                away_team_id=AWAY,
                football_cutoff=KICKOFF + timedelta(days=index + 1),
                knowledge_cutoff=KICKOFF + timedelta(days=index + 1),
                knowledge_mode="bitemporal",
                history=history,
            ),
            home_goals=index % 3,
            away_goals=(index + 1) % 2,
        )
        for index in range(10)
    )

    split = chronological_development_split(observations)
    selected = select_cold_start_config(observations)

    assert len(split.train) == 6
    assert len(split.validation) == 2
    assert len(split.development_holdout) == 2
    assert selected.config.shrinkage_k in SHRINKAGE_GRID
    assert selected.config.l2_regularization in L2_GRID
    assert selected.selected_transfer_weight == 0.0
    assert selected.candidate_count == len(SHRINKAGE_GRID) * len(L2_GRID)
    assert selected.development_holdout_metrics.target_count == 2


def test_v2_forecast_lineage_round_trips_through_structured_payload() -> None:
    history = _competition_history()
    primary = default_penaltyblog_models()[0]
    primary_artifact = primary.fit(history, {"code_commit_sha": "a" * 40})
    champion = _ChampionModel()
    model = HybridGoalModel.v2a(primary, champion)
    artifact = build_hybrid_artifact(
        model,
        primary_artifact,
        _artifact("transferable-rolling-goals-poisson-v1"),
    )
    forecast = model.predict(artifact, _snapshot(history, away=UNSEEN))

    restored = _forecast_from_dict(_forecast_dict(forecast))

    assert restored.lineage == forecast.lineage
    assert restored.warnings == forecast.warnings


class _ChampionModel:
    model_id = "transferable-rolling-goals-poisson-v1"
    model_family = "TRANSFERABLE_ROLLING_GOALS_POISSON"
    model_version = model_id
    role = ModelRole.CHAMPION
    supports_unseen_teams = True
    requires_xg = False

    def fit(
        self, training_data: tuple[HistoricalMatch, ...], config: dict[str, object]
    ) -> FittedModelArtifact:
        return _artifact(self.model_id)

    def predict(
        self, artifact: FittedModelArtifact, fixture: ForecastInputSnapshot
    ) -> ModelForecast:
        matrix = ((0.35, 0.15), (0.20, 0.30))
        markets = derive_markets(matrix)
        home, away, total = distributions(matrix)
        return ModelForecast(
            fixture_id=fixture.fixture_id,
            model_id=self.model_id,
            model_family=self.model_family,
            model_version=self.model_version,
            model_artifact_sha256=artifact.artifact_sha256,
            football_cutoff=fixture.football_cutoff,
            knowledge_cutoff=fixture.knowledge_cutoff,
            created_at=KICKOFF,
            expected_home_goals=sum(i * p for i, p in enumerate(home)),
            expected_away_goals=sum(i * p for i, p in enumerate(away)),
            home_probability=markets["home_probability"],
            draw_probability=markets["draw_probability"],
            away_probability=markets["away_probability"],
            score_labels=("0", "1+"),
            score_matrix=matrix,
            home_goal_distribution=home,
            away_goal_distribution=away,
            total_goal_distribution=total,
            btts_yes=markets["btts_yes"],
            btts_no=markets["btts_no"],
            total_over_2_5=markets["total_over_2_5"],
            total_under_2_5=markets["total_under_2_5"],
            home_clean_sheet=markets["home_clean_sheet"],
            away_clean_sheet=markets["away_clean_sheet"],
            status=ModelStatus.SUCCESS,
            warnings=(),
            input_snapshot_sha256=fixture.sha256,
        )


def _artifact(model_id: str) -> FittedModelArtifact:
    return FittedModelArtifact(
        model_id=model_id,
        model_family="TEST",
        model_version=model_id,
        artifact_sha256=("a" if model_id.startswith("pb-") else "b") * 64,
        training_start=KICKOFF - timedelta(days=30),
        training_cutoff=KICKOFF - timedelta(days=1),
        dataset_sha256="c" * 64,
        configuration={},
        dependency_version="1",
        code_commit_sha="d" * 40,
        feature_contract="forecast-input-snapshot-v1",
        random_seed=None,
        runtime_model=object(),
    )


def _competition_history() -> tuple[HistoricalMatch, ...]:
    teams = (HOME, AWAY, UUID(int=7))
    rows = []
    for index in range(18):
        home = teams[index % 3]
        away = teams[(index + 1) % 3]
        rows.append(
            _match(
                100 + index,
                KICKOFF - timedelta(days=30 - index),
                home,
                away,
                index % 3,
                (index + 1) % 2,
            )
        )
    return tuple(rows)


def _match(
    identifier: int,
    kickoff: datetime,
    home: UUID,
    away: UUID,
    home_goals: int,
    away_goals: int,
    *,
    competition: UUID = COMPETITION,
) -> HistoricalMatch:
    return HistoricalMatch(
        fixture_id=UUID(int=identifier),
        competition_id=competition,
        competition_context=CompetitionContext.LEAGUE,
        kickoff_at=kickoff,
        known_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
    )


def _snapshot(history: tuple[HistoricalMatch, ...], *, away: UUID = AWAY) -> ForecastInputSnapshot:
    return build_forecast_snapshot(
        fixture_id=TARGET,
        competition_id=COMPETITION,
        competition_context=CompetitionContext.LEAGUE,
        season_label="2026",
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=away,
        football_cutoff=KICKOFF,
        knowledge_cutoff=KICKOFF,
        knowledge_mode="bitemporal",
        history=history,
    )
