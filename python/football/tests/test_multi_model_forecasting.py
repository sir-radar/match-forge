from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from football.forecasting.ensemble import (
    EnsembleDevelopmentObservation,
    EnsembleWeights,
    build_ensemble_forecast,
    learn_ensemble_weights,
)
from football.forecasting.model_contracts import (
    CompetitionContext,
    FittedModelArtifact,
    ForecastInputSnapshot,
    HistoricalMatch,
    ModelAvailability,
    ModelForecast,
    ModelRole,
    ModelRunResult,
    ModelStatus,
    derive_markets,
    distributions,
    rust_score_atoms,
)
from football.forecasting.model_runner import (
    ModelRegistry,
    ModelRunner,
    RegisteredModel,
    penaltyblog_registry_from_environment,
)
from football.forecasting.multimodel_cli import _forecast_dict, _forecast_from_dict
from football.forecasting.penaltyblog_models import default_penaltyblog_models
from football.forecasting.snapshot import build_forecast_snapshot
from football.product.api_football import ApiResponse
from football.product.model_forecasts import persist_model_run
from football.product.probability_benchmarks import (
    BenchmarkStatus,
    SportmonksPredictionClient,
    parse_api_football_prediction,
    parse_sportmonks_probability,
    persist_probability_benchmark,
)

HOME = UUID(int=1)
AWAY = UUID(int=2)
THIRD = UUID(int=3)
COMPETITION = UUID(int=4)
TARGET = UUID(int=5)
KICKOFF = datetime(2026, 10, 7, 18, tzinfo=UTC)


def test_snapshot_excludes_future_same_kickoff_and_late_known_facts() -> None:
    history = list(_training_history())
    history.extend(
        (
            _match(100, KICKOFF, HOME, AWAY, 99, 0),
            _match(101, KICKOFF + timedelta(days=1), HOME, AWAY, 99, 0),
            _match(
                102,
                KICKOFF - timedelta(days=1),
                HOME,
                AWAY,
                99,
                0,
                known_at=KICKOFF + timedelta(minutes=1),
            ),
        )
    )

    snapshot = _snapshot(tuple(history))

    assert {item.fixture_id.int for item in snapshot.qualified_history}.isdisjoint({100, 101, 102})
    assert snapshot.home_form_5.goals_for is not None
    assert snapshot.home_form_5.goals_for < 10


def test_non_predictive_context_changes_only_context_hash() -> None:
    snapshot = _snapshot(_training_history())
    enriched = replace(
        snapshot,
        availability=({"player_id": "1", "state": "UNAVAILABLE_INJURY"},),
        context_missingness=("LINEUP_UNAVAILABLE",),
    )

    assert enriched.predictive_input_snapshot_sha256 == snapshot.predictive_input_snapshot_sha256
    assert enriched.context_snapshot_sha256 != snapshot.context_snapshot_sha256


def test_snapshot_keeps_league_and_cup_h2h_separate_and_missing_xg_explicit() -> None:
    history = list(_training_history())
    history.extend(
        (
            _match(200, KICKOFF - timedelta(days=5), HOME, AWAY, 2, 0),
            _match(
                201,
                KICKOFF - timedelta(days=4),
                AWAY,
                HOME,
                3,
                0,
                context=CompetitionContext.DOMESTIC_CUP,
            ),
            _match(
                202,
                KICKOFF - timedelta(days=3),
                HOME,
                AWAY,
                1,
                1,
                context=CompetitionContext.FRIENDLY,
            ),
        )
    )

    snapshot = _snapshot(tuple(history))
    by_context = {item.competition_context: item for item in snapshot.h2h}

    assert by_context[CompetitionContext.LEAGUE].sample_size > 1
    assert by_context[CompetitionContext.DOMESTIC_CUP].sample_size == 1
    assert by_context[CompetitionContext.FRIENDLY].sample_size == 1
    assert by_context[CompetitionContext.UNKNOWN].sample_size == 0
    assert snapshot.home_form_10.xg_sample_count == 0
    assert snapshot.home_form_10.xg_for is None
    assert "HOME_XG_UNAVAILABLE" in snapshot.missingness


@pytest.mark.parametrize("model_index", [0, 2, 3])
def test_penaltyblog_classic_adapters_fit_and_return_coherent_distributions(
    model_index: int,
) -> None:
    adapter = default_penaltyblog_models()[model_index]
    history = _training_history()
    artifact = adapter.fit(history, {"half_life_days": 365.0, "code_commit_sha": "a" * 40})

    forecast = adapter.predict(artifact, _snapshot(history))

    assert forecast.model_id == adapter.model_id
    assert sum(sum(row) for row in forecast.score_matrix) == pytest.approx(1.0, abs=1e-10)
    assert (
        forecast.home_probability + forecast.draw_probability + forecast.away_probability
        == pytest.approx(1.0)
    )
    assert all(value >= 0 for row in forecast.score_matrix for value in row)


def test_penaltyblog_adapter_rejects_unseen_team() -> None:
    adapter = default_penaltyblog_models()[0]
    history = _training_history()
    artifact = adapter.fit(history, {"half_life_days": 365.0, "code_commit_sha": "a" * 40})
    unseen = replace(_snapshot(history), away_team_id=UUID(int=999))

    with pytest.raises(RuntimeError, match="UNSEEN_TEAM"):
        adapter.predict(artifact, unseen)


def test_hierarchical_adapter_checks_diagnostics_and_forecasts() -> None:
    adapter = default_penaltyblog_models()[1]
    history = _training_history()
    artifact = adapter.fit(
        history,
        {
            "random_seed": 7,
            "code_commit_sha": "a" * 40,
            "maximum_rhat": 10.0,
            "minimum_effective_sample_size": 1.0,
            "fit_options": {
                "n_samples": 40,
                "burn": 20,
                "n_chains": 2,
                "thin": 1,
                "n_cores": 1,
            },
        },
    )

    forecast = adapter.predict(artifact, _snapshot(history))

    assert artifact.diagnostics
    assert forecast.status is ModelStatus.SUCCESS
    assert sum(sum(row) for row in forecast.score_matrix) == pytest.approx(1.0, abs=1e-10)


def test_rust_score_atoms_preserve_probability_mass() -> None:
    atoms = rust_score_atoms(_forecast("one", ((0.4, 0.1), (0.2, 0.3))))

    assert sum(cast(float, atom["probability"]) for atom in atoms) == pytest.approx(1.0)
    assert atoms[-1]["home_goals"] is None
    assert atoms[-1]["away_goals"] is None


def test_cli_forecast_payload_round_trips_dense_score_matrix() -> None:
    forecast = _forecast("one", ((0.4, 0.1), (0.2, 0.3)))

    restored = _forecast_from_dict(_forecast_dict(forecast))

    assert restored.score_matrix == forecast.score_matrix
    assert restored.home_probability == forecast.home_probability


def test_forecast_contract_rejects_inconsistent_derived_distribution() -> None:
    forecast = _forecast("one", ((0.4, 0.1), (0.2, 0.3)))

    with pytest.raises(ValueError, match="home_goal_distribution"):
        replace(forecast, home_goal_distribution=(0.6, 0.4))


def test_model_runner_isolates_one_failure() -> None:
    good = _Adapter("good", fail=False)
    bad = _Adapter("bad", fail=True)
    artifact = _artifact("artifact")
    runner = ModelRunner(
        ModelRegistry(
            (
                RegisteredModel(good, artifact, True, minimum_team_history=1),
                RegisteredModel(bad, artifact, True, minimum_team_history=1),
            )
        )
    )

    result = runner.run(_snapshot(_training_history()))

    assert [item.model_id for item in result.forecasts] == ["good"]
    statuses = {item.model_id: item.status for item in result.availability}
    assert statuses == {"good": ModelStatus.SUCCESS, "bad": ModelStatus.MODEL_ERROR}


def test_model_registry_uses_explicit_disabled_by_default_flags() -> None:
    artifact = _artifact("pb-dixon-coles-v1")
    registry = penaltyblog_registry_from_environment(
        {"pb-dixon-coles-v1": artifact},
        {"MATCHFORGE_MODEL_DIXON_COLES_ENABLED": "true"},
    )

    by_id = {item.adapter.model_id: item for item in registry.models}
    assert by_id["pb-dixon-coles-v1"].enabled
    assert by_id["pb-dixon-coles-v1"].artifact is artifact
    assert not by_id["pb-hierarchical-bayes-v1"].enabled


def test_ensemble_weights_and_missing_component_renormalization() -> None:
    first = _forecast("one", ((0.4, 0.1), (0.2, 0.3)))
    second = _forecast("two", ((0.3, 0.2), (0.1, 0.4)))
    observations = (
        EnsembleDevelopmentObservation(TARGET, (first, second), 1, 1),
        EnsembleDevelopmentObservation(UUID(int=6), (first, second), 0, 0),
    )
    weights = learn_ensemble_weights(observations)

    assert all(value >= 0 for _, value in weights.model_weights)
    assert sum(value for _, value in weights.model_weights) == pytest.approx(1.0)
    only_one = build_ensemble_forecast(
        forecasts=(first,),
        weights=weights,
        minimum_components=1,
        minimum_trained_weight=0.0,
        model_artifact_sha256="f" * 64,
    )
    assert only_one is not None
    assert only_one.component_weights == (("one", 1.0),)
    assert sum(sum(row) for row in only_one.score_matrix) == pytest.approx(1.0)
    assert only_one.home_probability == derive_markets(only_one.score_matrix)["home_probability"]


def test_ensemble_rejects_evaluation_targets_for_weight_fitting() -> None:
    forecast = _forecast("one", ((0.4, 0.1), (0.2, 0.3)))
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        learn_ensemble_weights(
            (EnsembleDevelopmentObservation(TARGET, (forecast,), 1, 0, dataset_role="EVALUATION"),)
        )


def test_ensemble_alignment_collapses_larger_support_without_losing_tail_mass() -> None:
    small = _forecast("small", ((0.4, 0.1), (0.2, 0.3)))
    large = _forecast(
        "large",
        (
            (0.1, 0.1, 0.1),
            (0.1, 0.1, 0.1),
            (0.2, 0.1, 0.1),
        ),
    )
    weights = EnsembleWeights(
        model_weights=(("large", 0.5), ("small", 0.5)),
        development_fixture_ids=(TARGET,),
    )

    forecast = build_ensemble_forecast(
        forecasts=(small, large),
        weights=weights,
        minimum_components=2,
        minimum_trained_weight=1.0,
        model_artifact_sha256="b" * 64,
    )

    assert forecast is not None
    assert forecast.score_labels == ("0", "1+")
    assert forecast.score_matrix[0][1] == pytest.approx(0.15)
    assert forecast.score_matrix[1][0] == pytest.approx(0.25)
    assert sum(sum(row) for row in forecast.score_matrix) == pytest.approx(1.0)


def test_external_probabilities_are_normalized_and_fail_closed() -> None:
    response = ApiResponse(
        "/predictions",
        KICKOFF,
        b"{}",
        ({"predictions": {"percent": {"home": "51%", "draw": "25%", "away": "25%"}}},),
        None,
    )
    api = parse_api_football_prediction(response, "123")
    sportmonks = parse_sportmonks_probability(
        ({"predictions": {"home": 40, "draw": 30, "away": 30}},), "456", KICKOFF
    )
    malformed = parse_sportmonks_probability(
        ({"predictions": {"home": "bad", "draw": 30, "away": 30}},), "456", KICKOFF
    )

    assert api.status is BenchmarkStatus.SUCCESS
    assert sum(
        cast(float, value)
        for value in (api.home_probability, api.draw_probability, api.away_probability)
    ) == pytest.approx(1.0)
    assert sportmonks.status is BenchmarkStatus.SUCCESS
    assert malformed.status is BenchmarkStatus.MISSING_PROBABILITIES
    assert (
        SportmonksPredictionClient(None).fixture_probability("1").status
        is BenchmarkStatus.DISABLED_NOT_CONFIGURED
    )


def test_ambiguous_external_mapping_fails_closed_and_stays_benchmark_only() -> None:
    connection = _BenchmarkConnection(((TARGET,), (UUID(int=9),)))
    benchmark = parse_sportmonks_probability(
        ({"predictions": {"home": 40, "draw": 30, "away": 30}},), "456", KICKOFF
    )

    result = persist_probability_benchmark(cast(Any, connection), benchmark)

    assert result.mapping_status == "AMBIGUOUS"
    assert result.collection_status is BenchmarkStatus.MAPPING_FAILURE
    insert_sql, insert_values = connection.executions[-1]
    assert "'BENCHMARK_ONLY'" in insert_sql
    assert insert_values[4] is None
    assert insert_values[6] == "MAPPING_FAILURE"


def test_migration_and_product_query_preserve_champion_and_allow_multiple_models() -> None:
    migration = Path(
        "infrastructure/migrations/202610070100_multi_model_forecasting.sql"
    ).read_text()
    sync = Path("python/football/src/football/product/sync.py").read_text()

    assert "CREATE TABLE football.product_model_forecasts" in migration
    assert (
        "UNIQUE (fixture_id, model_id, model_artifact_sha256, input_snapshot_sha256)" in migration
    )
    assert "forecast_role IN ('RESEARCH', 'SHADOW', 'CHAMPION')" in migration
    assert "model_algorithm_version =" in sync


def test_model_forecast_persistence_keeps_models_distinct_and_is_idempotent() -> None:
    connection = _ModelForecastConnection()
    forecasts = (
        _forecast("one", ((0.4, 0.1), (0.2, 0.3))),
        _forecast("two", ((0.3, 0.2), (0.1, 0.4))),
    )
    result = ModelRunResult(
        forecasts,
        tuple(ModelAvailability(item.model_id, ModelStatus.SUCCESS) for item in forecasts),
    )

    def persist() -> int:
        return persist_model_run(
            cast(Any, connection),
            result,
            roles={"one": ModelRole.RESEARCH, "two": ModelRole.CHALLENGER},
            fixture_id=TARGET,
            football_cutoff=KICKOFF,
            knowledge_cutoff=KICKOFF,
            knowledge_mode="bitemporal",
            input_snapshot_sha256="d" * 64,
            created_at=KICKOFF,
        )

    assert persist() == 2
    assert persist() == 0
    assert {values[3] for _, values in connection.executions} == {"one", "two"}
    assert {values[7] for _, values in connection.executions} == {"RESEARCH", "SHADOW"}


class _Adapter:
    model_family = "TEST"
    model_version = "v1"
    role = ModelRole.RESEARCH
    supports_unseen_teams = True
    requires_xg = False

    def __init__(self, model_id: str, *, fail: bool) -> None:
        self.model_id = model_id
        self.fail = fail

    def fit(self, *_args: object, **_kwargs: object) -> FittedModelArtifact:
        return _artifact(self.model_id)

    def predict(self, *_args: object, **_kwargs: object) -> ModelForecast:
        if self.fail:
            raise ValueError("failure")
        return _forecast(self.model_id, ((0.4, 0.1), (0.2, 0.3)))


class _BenchmarkCursor:
    def __init__(self, connection: _BenchmarkConnection) -> None:
        self.connection = connection
        self.rowcount = 0

    def __enter__(self) -> _BenchmarkCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, values: tuple[object, ...]) -> None:
        self.connection.executions.append((sql, values))
        self.rowcount = 1 if "INSERT INTO" in sql else 0

    def fetchall(self) -> tuple[tuple[UUID], ...]:
        return self.connection.fixture_rows


class _BenchmarkConnection:
    def __init__(self, fixture_rows: tuple[tuple[UUID], ...]) -> None:
        self.fixture_rows = fixture_rows
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self) -> _BenchmarkCursor:
        return _BenchmarkCursor(self)


class _ModelForecastCursor:
    def __init__(self, connection: _ModelForecastConnection) -> None:
        self.connection = connection
        self.rowcount = 0

    def __enter__(self) -> _ModelForecastCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, values: tuple[object, ...]) -> None:
        semantic_sha = cast(str, values[1])
        self.rowcount = int(semantic_sha not in self.connection.semantic_shas)
        self.connection.semantic_shas.add(semantic_sha)
        self.connection.executions.append((sql, values))


class _ModelForecastConnection:
    def __init__(self) -> None:
        self.semantic_shas: set[str] = set()
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self) -> _ModelForecastCursor:
        return _ModelForecastCursor(self)


def _artifact(model_id: str) -> FittedModelArtifact:
    return FittedModelArtifact(
        model_id=model_id,
        model_family="TEST",
        model_version="v1",
        artifact_sha256="a" * 64,
        training_start=KICKOFF - timedelta(days=20),
        training_cutoff=KICKOFF - timedelta(days=1),
        dataset_sha256="b" * 64,
        configuration={},
        dependency_version="1",
        code_commit_sha="c" * 40,
        feature_contract="test",
        random_seed=None,
        runtime_model=object(),
    )


def _forecast(model_id: str, matrix: tuple[tuple[float, ...], ...]) -> ModelForecast:
    markets = derive_markets(matrix)
    home, away, total = distributions(matrix)
    return ModelForecast(
        fixture_id=TARGET,
        model_id=model_id,
        model_family="TEST",
        model_version="v1",
        model_artifact_sha256="a" * 64,
        football_cutoff=KICKOFF,
        knowledge_cutoff=KICKOFF,
        created_at=KICKOFF,
        expected_home_goals=sum(index * value for index, value in enumerate(home)),
        expected_away_goals=sum(index * value for index, value in enumerate(away)),
        score_labels=tuple(str(index) for index in range(len(matrix) - 1))
        + (f"{len(matrix) - 1}+",),
        score_matrix=matrix,
        home_goal_distribution=home,
        away_goal_distribution=away,
        total_goal_distribution=total,
        status=ModelStatus.SUCCESS,
        warnings=(),
        input_snapshot_sha256="d" * 64,
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


def _snapshot(history: tuple[HistoricalMatch, ...]) -> ForecastInputSnapshot:
    return build_forecast_snapshot(
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
    )


def _training_history() -> tuple[HistoricalMatch, ...]:
    rows: list[HistoricalMatch] = []
    teams = (HOME, AWAY, THIRD)
    for index in range(18):
        home = teams[index % 3]
        away = teams[(index + 1) % 3]
        rows.append(
            _match(
                index + 1,
                KICKOFF - timedelta(days=40 - index),
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
    context: CompetitionContext = CompetitionContext.LEAGUE,
    known_at: datetime | None = None,
) -> HistoricalMatch:
    return HistoricalMatch(
        fixture_id=UUID(int=identifier),
        competition_id=COMPETITION,
        competition_context=context,
        kickoff_at=kickoff,
        known_at=known_at or kickoff + timedelta(hours=3),
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
    )
