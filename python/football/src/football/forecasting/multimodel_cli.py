from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO, cast
from uuid import UUID

import psycopg

from football.forecasting.model_contracts import (
    CompetitionContext,
    FittedModelArtifact,
    ForecastFallbackReason,
    ForecastInputSnapshot,
    ForecastLineage,
    ForecastMode,
    HistoricalMatch,
    ModelAvailability,
    ModelForecast,
    ModelRunResult,
    ModelStatus,
)
from football.forecasting.multi_model_evaluation import (
    ScoredModelForecast,
    evaluate_model_forecasts,
)
from football.forecasting.penaltyblog_models import (
    PENALTYBLOG_MODEL_IDS,
    PenaltyblogGoalModel,
    default_penaltyblog_models,
    persist_research_artifact,
)
from football.forecasting.snapshot import build_forecast_snapshot
from football.product.api_football import ApiFootballClient
from football.product.model_forecasts import (
    model_forecast_payload,
    persist_model_artifact,
    persist_model_run,
)
from football.product.probability_benchmarks import (
    BenchmarkStatus,
    ProbabilityBenchmark,
    SportmonksPredictionClient,
    parse_api_football_prediction,
    persist_probability_benchmark,
)


def add_multimodel_commands(commands: argparse._SubParsersAction[Any]) -> None:
    models = commands.add_parser("models", help="fit, forecast, or evaluate research models")
    scopes = models.add_subparsers(dest="scope", required=True)
    fit = scopes.add_parser("fit")
    fit.add_argument("--model-id", required=True, choices=_model_ids())
    fit.add_argument("--training-data", required=True, type=Path)
    fit.add_argument("--config", required=True, type=Path)
    fit.add_argument("--artifact-root", required=True, type=Path)
    forecast = scopes.add_parser("forecast")
    forecast.add_argument("--manifest", required=True, type=Path)
    forecast.add_argument("--snapshot", required=True, type=Path)
    forecast.add_argument("--persist", action="store_true")
    evaluate = scopes.add_parser("evaluate")
    evaluate.add_argument("--observations", required=True, type=Path)

    benchmarks = commands.add_parser("benchmarks", help="collect probabilistic benchmarks")
    benchmark_scopes = benchmarks.add_subparsers(dest="scope", required=True)
    collect = benchmark_scopes.add_parser("collect")
    collect.add_argument("--provider", required=True, choices=("api_football", "sportmonks"))
    collect.add_argument("--provider-fixture-id", required=True)


def run_multimodel_command(
    args: argparse.Namespace,
    environment: Mapping[str, str],
    output: TextIO,
    errors: TextIO,
) -> int:
    try:
        if args.command == "models" and args.scope == "fit":
            result = _fit(args)
        elif args.command == "models" and args.scope == "forecast":
            result = _forecast(args, environment)
        elif args.command == "models":
            result = _evaluate(args)
        else:
            result = _benchmark(args, environment)
    except (OSError, ValueError, RuntimeError, psycopg.Error) as error:
        print(f"error: {error}", file=errors)
        return 4
    print(json.dumps(result, sort_keys=True, allow_nan=False), file=output)
    return 0


def _fit(args: argparse.Namespace) -> dict[str, object]:
    adapter = _adapter(args.model_id)
    rows = _load_history(args.training_data)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("model configuration must be a JSON object")
    artifact = adapter.fit(rows, cast(dict[str, object], config))
    manifest, runtime = persist_research_artifact(artifact, args.artifact_root)
    return {
        "model_id": artifact.model_id,
        "artifact_sha256": artifact.artifact_sha256,
        "manifest": str(manifest),
        "trusted_local_runtime_cache": str(runtime),
    }


def _forecast(args: argparse.Namespace, environment: Mapping[str, str]) -> dict[str, object]:
    manifest = cast(dict[str, Any], json.loads(args.manifest.read_text(encoding="utf-8")))
    adapter = _adapter(str(manifest["model_id"]))
    runtime = cast(Mapping[str, Any], manifest["runtime_cache"])
    runtime_path = args.manifest.parent / str(runtime["filename"])
    actual_sha = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
    if actual_sha != runtime["sha256"]:
        raise ValueError("trusted local runtime cache checksum mismatch")
    loaded = adapter.load_trusted_runtime(runtime_path)
    artifact = FittedModelArtifact(
        model_id=str(manifest["model_id"]),
        model_family=str(manifest["model_family"]),
        model_version=str(manifest["model_version"]),
        artifact_sha256=str(manifest["artifact_sha256"]),
        training_start=_datetime(manifest["training_start"]),
        training_cutoff=_datetime(manifest["training_cutoff"]),
        dataset_sha256=str(manifest["dataset_sha256"]),
        configuration=cast(dict[str, object], manifest["configuration"]),
        dependency_version=str(manifest["dependency_version"]),
        code_commit_sha=str(manifest["code_commit_sha"]),
        feature_contract=str(manifest["feature_contract"]),
        random_seed=cast(int | None, manifest.get("random_seed")),
        runtime_model=loaded,
        diagnostics=cast(dict[str, object], manifest.get("diagnostics", {})),
    )
    snapshot = _load_snapshot(args.snapshot)
    forecast = adapter.predict(artifact, snapshot)
    result = _forecast_dict(forecast)
    if args.persist:
        database_url = (
            args.database_url
            or environment.get("FOOTBALL_DATABASE_URL")
            or environment.get("DATABASE_URL")
        )
        if not database_url:
            raise ValueError("DATABASE_URL is required with --persist")
        run_result = ModelRunResult(
            (forecast,), (ModelAvailability(forecast.model_id, ModelStatus.SUCCESS),)
        )
        with psycopg.connect(database_url) as connection:
            persist_model_artifact(connection, artifact)
            inserted = persist_model_run(
                connection,
                run_result,
                roles={forecast.model_id: adapter.role},
                fixture_id=forecast.fixture_id,
                football_cutoff=forecast.football_cutoff,
                knowledge_cutoff=forecast.knowledge_cutoff,
                knowledge_mode=snapshot.knowledge_mode,
                input_snapshot_sha256=snapshot.sha256,
            )
        result["persisted_rows"] = inserted
    return result


def _evaluate(args: argparse.Namespace) -> dict[str, object]:
    rows = json.loads(args.observations.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("evaluation observations must be a JSON array")
    observations = tuple(_scored(cast(Mapping[str, Any], row)) for row in rows)
    metrics = evaluate_model_forecasts(observations)
    return {
        "model_id": metrics.model_id,
        "target_count": metrics.target_count,
        "joint_score_log_loss": metrics.joint_score_log_loss,
        "result_log_loss": metrics.result_log_loss,
        "multiclass_brier": metrics.multiclass_brier,
        "ranked_probability_score": metrics.ranked_probability_score,
        "total_goal_crps": metrics.total_goal_crps,
        "calibration": [
            {
                "outcome": item.outcome,
                "intercept": item.intercept,
                "slope": item.slope,
                "reliability_bins": [value.to_dict() for value in item.reliability_bins],
            }
            for item in metrics.calibration
        ],
    }


def _benchmark(args: argparse.Namespace, environment: Mapping[str, str]) -> dict[str, object]:
    if args.provider == "api_football":
        enabled = environment.get("API_FOOTBALL_PREDICTIONS_ENABLED", "false").casefold()
        if enabled != "true":
            benchmark = ProbabilityBenchmark(
                "api_football",
                args.provider_fixture_id,
                datetime.now(UTC),
                status=BenchmarkStatus.DISABLED_NOT_CONFIGURED,
                failure_reason="API_FOOTBALL_PREDICTIONS_ENABLED is false",
            )
        else:
            response = ApiFootballClient(environment.get("API_FOOTBALL_API_KEY", "")).predictions(
                int(args.provider_fixture_id)
            )
            benchmark = parse_api_football_prediction(response, args.provider_fixture_id)
    else:
        enabled = environment.get("SPORTMONKS_PREDICTIONS_ENABLED", "false").casefold()
        token = environment.get("SPORTMONKS_API_TOKEN") if enabled == "true" else None
        benchmark = SportmonksPredictionClient(token).fixture_probability(args.provider_fixture_id)
    database_url = (
        args.database_url
        or environment.get("FOOTBALL_DATABASE_URL")
        or environment.get("DATABASE_URL")
    )
    if not database_url:
        raise ValueError("DATABASE_URL is required to persist external benchmarks")
    with psycopg.connect(database_url) as connection:
        persisted = persist_probability_benchmark(connection, benchmark)
    return {
        "provider": benchmark.provider_code,
        "provider_fixture_id": benchmark.provider_fixture_id,
        "status": benchmark.status,
        "home_probability": benchmark.home_probability,
        "draw_probability": benchmark.draw_probability,
        "away_probability": benchmark.away_probability,
        "captured_at": benchmark.captured_at.isoformat(),
        "failure_reason": benchmark.failure_reason,
        "benchmark_id": str(persisted.benchmark_id),
        "mapping_status": persisted.mapping_status,
        "persisted_status": persisted.collection_status,
        "inserted": persisted.inserted,
    }


def _load_history(path: Path) -> tuple[HistoricalMatch, ...]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("training data must be a JSON array")
    return tuple(_history_row(cast(Mapping[str, Any], row)) for row in rows)


def _history_row(row: Mapping[str, Any]) -> HistoricalMatch:
    return HistoricalMatch(
        fixture_id=UUID(str(row["fixture_id"])),
        competition_id=UUID(str(row["competition_id"])),
        competition_context=CompetitionContext(str(row.get("competition_context", "UNKNOWN"))),
        kickoff_at=_datetime(row["kickoff_at"]),
        known_at=_datetime(row["known_at"]),
        home_team_id=UUID(str(row["home_team_id"])),
        away_team_id=UUID(str(row["away_team_id"])),
        home_goals=int(row["home_goals"]),
        away_goals=int(row["away_goals"]),
        home_xg=float(row["home_xg"]) if row.get("home_xg") is not None else None,
        away_xg=float(row["away_xg"]) if row.get("away_xg") is not None else None,
    )


def _load_snapshot(path: Path) -> ForecastInputSnapshot:
    row = cast(Mapping[str, Any], json.loads(path.read_text(encoding="utf-8")))
    history = tuple(
        _history_row(cast(Mapping[str, Any], item)) for item in row["qualified_history"]
    )
    return build_forecast_snapshot(
        fixture_id=UUID(str(row["fixture_id"])),
        competition_id=UUID(str(row["competition_id"])),
        competition_context=CompetitionContext(str(row["competition_context"])),
        season_label=str(row["season_label"]),
        kickoff_at=_datetime(row["kickoff_at"]),
        home_team_id=UUID(str(row["home_team_id"])),
        away_team_id=UUID(str(row["away_team_id"])),
        football_cutoff=_datetime(row["football_cutoff"]),
        knowledge_cutoff=_datetime(row["knowledge_cutoff"]),
        knowledge_mode=str(row["knowledge_mode"]),
        history=history,
        source_references=tuple(str(item) for item in row.get("source_references", [])),
        availability_status=str(row.get("availability_status", "UNKNOWN")),
        home_promoted=cast(bool | None, row.get("home_promoted")),
        away_promoted=cast(bool | None, row.get("away_promoted")),
    )


def _scored(row: Mapping[str, Any]) -> ScoredModelForecast:
    return ScoredModelForecast(
        forecast=_forecast_from_dict(cast(Mapping[str, Any], row["forecast"])),
        kickoff_at=_datetime(row["kickoff_at"]),
        outcome_known_at=_datetime(row["outcome_known_at"]),
        home_goals=int(row["home_goals"]),
        away_goals=int(row["away_goals"]),
        competition_id=str(row["competition_id"]),
        season_label=str(row["season_label"]),
    )


def _forecast_dict(forecast: ModelForecast) -> dict[str, object]:
    payload = model_forecast_payload(forecast)
    assert payload is not None
    return {
        **payload,
        "fixture_id": str(forecast.fixture_id),
        "model_id": forecast.model_id,
        "model_family": forecast.model_family,
        "model_version": forecast.model_version,
        "model_artifact_sha256": forecast.model_artifact_sha256,
        "football_cutoff": forecast.football_cutoff.isoformat(),
        "knowledge_cutoff": forecast.knowledge_cutoff.isoformat(),
        "created_at": forecast.created_at.isoformat(),
        "score_labels": list(forecast.score_labels),
        "score_matrix": [list(row) for row in forecast.score_matrix],
        "input_snapshot_sha256": forecast.input_snapshot_sha256,
        "warnings": list(forecast.warnings),
    }


def _forecast_from_dict(row: Mapping[str, Any]) -> ModelForecast:
    probabilities = cast(Mapping[str, Any], row["probabilities"])
    lineage_row = cast(Mapping[str, Any] | None, row.get("lineage"))
    lineage = (
        ForecastLineage(
            forecast_mode=ForecastMode(str(lineage_row["forecast_mode"])),
            primary_model_id=str(lineage_row["primary_model_id"]),
            primary_model_artifact_sha256=str(lineage_row["primary_model_artifact_sha256"]),
            fallback_model_id=(
                str(lineage_row["fallback_model_id"])
                if lineage_row.get("fallback_model_id") is not None
                else None
            ),
            fallback_model_artifact_sha256=(
                str(lineage_row["fallback_model_artifact_sha256"])
                if lineage_row.get("fallback_model_artifact_sha256") is not None
                else None
            ),
            fallback_reason=ForecastFallbackReason(str(lineage_row["fallback_reason"])),
            home_artifact_state=str(lineage_row["home_artifact_state"]),
            away_artifact_state=str(lineage_row["away_artifact_state"]),
            home_history_state=str(lineage_row["home_history_state"]),
            away_history_state=str(lineage_row["away_history_state"]),
            home_promoted=cast(bool | None, lineage_row.get("home_promoted")),
            away_promoted=cast(bool | None, lineage_row.get("away_promoted")),
            native_component_used=bool(lineage_row["native_component_used"]),
            cold_start_component_used=bool(lineage_row["cold_start_component_used"]),
            champion_fallback_used=bool(lineage_row["champion_fallback_used"]),
            ensemble_mode=(
                str(lineage_row["ensemble_mode"])
                if lineage_row.get("ensemble_mode") is not None
                else None
            ),
        )
        if lineage_row is not None
        else None
    )
    return ModelForecast(
        fixture_id=UUID(str(row["fixture_id"])),
        model_id=str(row["model_id"]),
        model_family=str(row["model_family"]),
        model_version=str(row["model_version"]),
        model_artifact_sha256=str(row["model_artifact_sha256"]),
        football_cutoff=_datetime(row["football_cutoff"]),
        knowledge_cutoff=_datetime(row["knowledge_cutoff"]),
        created_at=_datetime(row["created_at"]),
        expected_home_goals=float(row["expected_home_goals"]),
        expected_away_goals=float(row["expected_away_goals"]),
        home_probability=float(probabilities["home"]),
        draw_probability=float(probabilities["draw"]),
        away_probability=float(probabilities["away"]),
        score_labels=tuple(str(item) for item in row["score_labels"]),
        score_matrix=tuple(
            tuple(float(value) for value in values) for values in row["score_matrix"]
        ),
        home_goal_distribution=tuple(float(value) for value in row["home_goal_distribution"]),
        away_goal_distribution=tuple(float(value) for value in row["away_goal_distribution"]),
        total_goal_distribution=tuple(float(value) for value in row["total_goal_distribution"]),
        btts_yes=float(probabilities["btts_yes"]),
        btts_no=float(probabilities["btts_no"]),
        total_over_2_5=float(probabilities["total_over_2_5"]),
        total_under_2_5=float(probabilities["total_under_2_5"]),
        home_clean_sheet=float(probabilities["home_clean_sheet"]),
        away_clean_sheet=float(probabilities["away_clean_sheet"]),
        status=ModelStatus.SUCCESS,
        warnings=tuple(str(item) for item in row.get("warnings", [])),
        input_snapshot_sha256=str(row["input_snapshot_sha256"]),
        component_weights=tuple(
            (str(model_id), float(weight))
            for model_id, weight in cast(
                Mapping[str, Any], row.get("component_weights", {})
            ).items()
        ),
        lineage=lineage,
    )


def _adapter(model_id: str) -> PenaltyblogGoalModel:
    for model in default_penaltyblog_models():
        if model.model_id == model_id:
            return model
    raise ValueError(f"unsupported model ID: {model_id}")


def _model_ids() -> tuple[str, ...]:
    return PENALTYBLOG_MODEL_IDS


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return parsed
