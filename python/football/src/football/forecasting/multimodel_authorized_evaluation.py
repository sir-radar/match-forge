"""Authorized development selection and protected multi-model evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

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
    ModelForecast,
    ModelStatus,
    derive_markets,
    distributions,
)
from football.forecasting.multi_model_evaluation import (
    ScoredModelForecast,
    evaluate_model_forecasts,
    forecast_losses,
)
from football.forecasting.penaltyblog_models import (
    PENALTYBLOG_MODEL_IDS,
    PenaltyblogGoalModel,
    default_penaltyblog_models,
)
from football.forecasting.pitchapi_v3_runtime import (
    CORPUS_SHA256,
    FIREWALL_SHA256,
    SNAPSHOT_SHA256,
    PitchApiSnapshotCorpusV3,
)
from football.forecasting.snapshot import build_forecast_snapshot
from football.product.domain import FinishedMatch, forecast_from_history, stable_id

PROTOCOL_ID = "MATCHFORGE_MULTIMODEL_CHALLENGER_EVALUATION_V1"
DEVELOPMENT_DOMAIN = "bundesliga_2021_22"
DEVELOPMENT_MANIFEST = "be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e"
EVALUATION_DOMAINS = {
    "bundesliga_2022_23": (
        "893b888a36474c7cf55a207cb266d32a60351c0c87e9659a38a2cdc962784f74",
        216,
    ),
    "bundesliga_2023_24": (
        "0700ee9d976366db3a12b0c3bc4c9e3d6a953d95b7fbe1dac153773553ae9b87",
        216,
    ),
    "ligue1_2022_23": (
        "ded84fa1ce6f2695469f1e258bffd8c2b3ac79ee5edec5afa24be0e4d0b0939d",
        280,
    ),
}
CHAMPION_ID = "transferable-rolling-goals-poisson-v1"
HALF_LIFE_CANDIDATES = (180.0, 365.0, 730.0)
DEVELOPMENT_FOLDS = 4
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20_260_924
BOOTSTRAP_BLOCK_BATCHES = 10
RANDOM_SEED = 20_261_007
METRICS = (
    "joint_score_log_loss",
    "result_log_loss",
    "multiclass_brier",
    "ranked_probability_score",
    "total_goal_crps",
)


class AuthorizedEvaluationError(RuntimeError):
    """Frozen evaluation input or execution violated the authorized protocol."""


@dataclass(frozen=True, slots=True)
class CorpusMatch:
    domain: str
    target: bool
    match: HistoricalMatch


@dataclass(frozen=True, slots=True)
class SeasonCorpus:
    domain: str
    matches: tuple[CorpusMatch, ...]
    target_count: int


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    domain: str
    kickoff_batch: int
    scored: ScoredModelForecast


def execute_authorized_evaluation(
    *,
    snapshot_root: Path,
    champion_artifact_path: Path,
    code_commit_sha: str,
    preregistration_sha256: str,
) -> dict[str, object]:
    if len(code_commit_sha) != 40:
        raise AuthorizedEvaluationError("evaluation requires an exact Git commit SHA")
    development = load_season(snapshot_root, DEVELOPMENT_DOMAIN, DEVELOPMENT_MANIFEST, 216)
    adapters = {model.model_id: model for model in default_penaltyblog_models()}

    selected_configs: dict[str, dict[str, object]] = {}
    development_predictions: dict[str, tuple[PredictionRecord, ...]] = {
        CHAMPION_ID: _champion_predictions(development, champion_artifact_path)
    }
    selection: dict[str, object] = {}
    for model_id in (
        "pb-dixon-coles-v1",
        "pb-negative-binomial-v1",
        "pb-weibull-copula-v1",
    ):
        adapter = adapters[model_id]
        candidates: dict[str, tuple[PredictionRecord, ...]] = {}
        candidate_metrics: dict[str, dict[str, float | int | None]] = {}
        for half_life in HALF_LIFE_CANDIDATES:
            config = _model_config(model_id, code_commit_sha, half_life)
            rows = _development_oos_predictions(development, adapter, config)
            candidates[str(int(half_life))] = rows
            candidate_metrics[str(int(half_life))] = {
                "coverage": len(rows),
                "joint_score_log_loss": _mean_joint_loss(rows) if rows else None,
            }
        selected = min(
            HALF_LIFE_CANDIDATES,
            key=lambda value: (
                -cast(int, candidate_metrics[str(int(value))]["coverage"]),
                cast(float | None, candidate_metrics[str(int(value))]["joint_score_log_loss"])
                or math.inf,
                value,
            ),
        )
        selected_configs[model_id] = _model_config(model_id, code_commit_sha, selected)
        development_predictions[model_id] = candidates[str(int(selected))]
        selection[model_id] = {
            "candidate_development_results": candidate_metrics,
            "selected_half_life_days": selected,
            "selection_source": "DEVELOPMENT_ONLY",
        }

    bayes_id = "pb-hierarchical-bayes-v1"
    selected_configs[bayes_id] = _model_config(bayes_id, code_commit_sha, 365.0)
    development_predictions[bayes_id] = _development_oos_predictions(
        development, adapters[bayes_id], selected_configs[bayes_id]
    )
    selection[bayes_id] = {
        "configuration": selected_configs[bayes_id],
        "development_coverage": len(development_predictions[bayes_id]),
        "selection_source": "PRECOMMITTED_NO_SEARCH",
    }

    ensemble_components = {
        model_id: rows
        for model_id, rows in development_predictions.items()
        if len(rows) == development.target_count
    }
    weights = _learn_weights(ensemble_components)
    ensemble_artifact_sha = _sha256_json(
        {
            "model_id": "matchforge-ensemble-v1",
            "objective": weights.objective,
            "weights": weights.model_weights,
            "development_fixture_ids": [str(value) for value in weights.development_fixture_ids],
        }
    )
    development_predictions["matchforge-ensemble-v1"] = _ensemble_predictions(
        ensemble_components,
        weights,
        ensemble_artifact_sha,
    )
    equal_component_ids = tuple(sorted(ensemble_components))
    equal_weights = EnsembleWeights(
        model_weights=tuple(
            (model_id, 1.0 / len(equal_component_ids)) for model_id in equal_component_ids
        ),
        development_fixture_ids=tuple(
            row.scored.forecast.fixture_id for row in ensemble_components[CHAMPION_ID]
        ),
    )
    equal_development = _ensemble_predictions(
        ensemble_components,
        equal_weights,
        "0" * 64,
    )
    selection["matchforge-ensemble-v1"] = {
        "equal_weight_development_joint_score_log_loss": _mean_joint_loss(equal_development),
        "optimized_development_joint_score_log_loss": _mean_joint_loss(
            development_predictions["matchforge-ensemble-v1"]
        ),
        "optimized_weights": dict(weights.model_weights),
        "selection_source": "DEVELOPMENT_OOS_PREDICTIONS_ONLY",
    }

    final_artifacts, artifact_errors = _fit_final_artifacts(development, adapters, selected_configs)
    development_freeze = {
        "configs": selected_configs,
        "ensemble_artifact_sha256": ensemble_artifact_sha,
        "ensemble_weights": dict(weights.model_weights),
        "final_artifacts": {
            model_id: _artifact_summary(artifact) for model_id, artifact in final_artifacts.items()
        },
        "final_artifact_errors": artifact_errors,
        "selection": selection,
    }

    # Protected outcomes are not loaded until every model configuration, final
    # development-only fit, and ensemble weight is frozen above.
    preflight = dict(PitchApiSnapshotCorpusV3(snapshot_root).preflight())
    evaluation = tuple(
        load_season(snapshot_root, domain, digest, expected)
        for domain, (digest, expected) in EVALUATION_DOMAINS.items()
    )
    predictions: dict[str, list[PredictionRecord]] = defaultdict(list)
    for season in evaluation:
        season_models = _fixed_artifact_predictions(
            season,
            champion_artifact_path,
            adapters,
            final_artifacts,
        )
        for model_id, rows in season_models.items():
            predictions[model_id].extend(rows)
        ensemble_rows = _ensemble_predictions(season_models, weights, ensemble_artifact_sha)
        predictions["matchforge-ensemble-v1"].extend(ensemble_rows)

    frozen_predictions = {key: tuple(value) for key, value in predictions.items()}
    report = _evaluation_report(frozen_predictions)
    return {
        "contract": "MatchForgeMultiModelAuthorizedEvaluationV1",
        "protocol_id": PROTOCOL_ID,
        "code_commit_sha": code_commit_sha,
        "preregistration_sha256": preregistration_sha256,
        "snapshot": {
            **preflight,
            "snapshot_sha256": SNAPSHOT_SHA256,
            "corpus_sha256": CORPUS_SHA256,
            "firewall_sha256": FIREWALL_SHA256,
        },
        "firewall": {
            "development_completed_before_evaluation_load": True,
            "evaluation_outcomes_used_for_fit_tune_calibrate_or_ensemble": False,
            "evaluation_refits": 0,
            "same_kickoff_outcomes_revealed_after_batch": True,
        },
        "development_freeze": development_freeze,
        "feature_ablation": {
            "rating": "DESCRIPTIVE_ONLY_ZERO_PREDICTIVE_INFLUENCE",
            "h2h": "DESCRIPTIVE_ONLY_ZERO_PREDICTIVE_INFLUENCE",
            "xg_xga": "DESCRIPTIVE_ONLY_ZERO_PREDICTIVE_INFLUENCE",
            "reason": (
                "Integrated penaltyblog goal-model APIs consume goals, teams, and time "
                "weights only; "
                "the production champion artifact has beta_xg_for=0.0. No unsupported covariate "
                "effect was invented."
            ),
        },
        "results": report,
        "prediction_manifest_sha256": _prediction_manifest_sha256(frozen_predictions),
    }


def load_season(root: Path, domain: str, digest: str, expected_targets: int) -> SeasonCorpus:
    season = _load_hashed(root, "manifests", digest)
    target_ids = frozenset(cast(dict[str, Any], season["target_plan"])["target_ids"])
    if len(target_ids) != expected_targets:
        raise AuthorizedEvaluationError(f"{domain} target count mismatch")
    output: list[CorpusMatch] = []
    competition_id = stable_id("competition", domain.split("_")[0])
    for entry in cast(list[dict[str, Any]], season["matches"]):
        output.append(_read_corpus_match(root, entry, domain, competition_id, target_ids))
    ordered = tuple(
        sorted(output, key=lambda row: (row.match.kickoff_at, str(row.match.fixture_id)))
    )
    return SeasonCorpus(domain, ordered, len(target_ids))


def _read_corpus_match(
    root: Path,
    entry: dict[str, Any],
    domain: str,
    competition_id: UUID,
    target_ids: frozenset[str],
) -> CorpusMatch:
    path = root / str(entry["manifest_path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["manifest_sha256"]:
        raise AuthorizedEvaluationError("match manifest hash mismatch")
    manifest = _load_path(path)
    normalized = _load_hashed(root, "normalized", str(manifest["normalized_sha256"]))
    home_provider = str(manifest["home_provider_team_id"])
    away_provider = str(manifest["away_provider_team_id"])
    goals = {home_provider: 0, away_provider: 0}
    npxg = {home_provider: 0.0, away_provider: 0.0}
    for period in cast(list[dict[str, Any]], normalized["data"]["periods"]):
        if period["period"] not in ("FirstHalf", "SecondHalf"):
            continue
        _accumulate_period(period, goals, npxg)
    kickoff = datetime.fromisoformat(str(manifest["kickoff_at"]).replace("Z", "+00:00"))
    fixture_id = UUID(str(manifest["canonical_match_id"]))
    return CorpusMatch(
        domain=domain,
        target=str(fixture_id) in target_ids,
        match=HistoricalMatch(
            fixture_id=fixture_id,
            competition_id=competition_id,
            competition_context=CompetitionContext.LEAGUE,
            kickoff_at=kickoff,
            known_at=kickoff + timedelta(hours=3),
            home_team_id=UUID(str(manifest["home_canonical_team_id"])),
            away_team_id=UUID(str(manifest["away_canonical_team_id"])),
            home_goals=goals[home_provider],
            away_goals=goals[away_provider],
            home_xg=npxg[home_provider],
            away_xg=npxg[away_provider],
        ),
    )


def _accumulate_period(
    period: dict[str, Any], goals: dict[str, int], npxg: dict[str, float]
) -> None:
    for shot in cast(list[dict[str, object]], period["shots"]):
        team_id = str(shot["team_id"])
        if shot["event_type"] == "Goal":
            goals[team_id] += 1
        if shot["situation"] == "Penalty":
            continue
        value = shot["expected_goals"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AuthorizedEvaluationError("expected_goals is not numeric")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0.0:
            raise AuthorizedEvaluationError("expected_goals is invalid")
        npxg[team_id] += numeric


def _development_oos_predictions(
    season: SeasonCorpus,
    adapter: PenaltyblogGoalModel,
    config: dict[str, object],
) -> tuple[PredictionRecord, ...]:
    target_batches = _target_batches(season)
    folds = _folds(target_batches, DEVELOPMENT_FOLDS)
    output: list[PredictionRecord] = []
    for fold in folds:
        cutoff = fold[0][1][0].match.kickoff_at
        training = tuple(row.match for row in season.matches if row.match.kickoff_at < cutoff)
        try:
            artifact = adapter.fit(training, config)
        except (RuntimeError, ValueError):
            continue
        for batch_id, batch in fold:
            for row in batch:
                snapshot = _snapshot(row, (item.match for item in season.matches))
                try:
                    forecast = adapter.predict(artifact, snapshot)
                except (RuntimeError, ValueError):
                    continue
                output.append(_record(row, batch_id, forecast))
    return tuple(output)


def _champion_predictions(
    season: SeasonCorpus, artifact_path: Path
) -> tuple[PredictionRecord, ...]:
    output: list[PredictionRecord] = []
    history: tuple[HistoricalMatch, ...] = ()
    batch_id = 0
    for batch in _all_batches(season.matches):
        for row in batch:
            if not row.target:
                continue
            forecast = _champion_forecast(row, history, artifact_path)
            if forecast is None:
                raise AuthorizedEvaluationError("champion missing a frozen target")
            output.append(_record(row, batch_id, forecast))
        if any(row.target for row in batch):
            batch_id += 1
        history += tuple(row.match for row in batch)
    return tuple(output)


def _fixed_artifact_predictions(
    season: SeasonCorpus,
    champion_artifact_path: Path,
    adapters: dict[str, PenaltyblogGoalModel],
    artifacts: dict[str, FittedModelArtifact],
) -> dict[str, tuple[PredictionRecord, ...]]:
    output: dict[str, list[PredictionRecord]] = defaultdict(list)
    history: tuple[HistoricalMatch, ...] = ()
    batch_id = 0
    for batch in _all_batches(season.matches):
        targets = tuple(row for row in batch if row.target)
        for row in targets:
            champion = _champion_forecast(row, history, champion_artifact_path)
            if champion is None:
                raise AuthorizedEvaluationError("champion missing an evaluation target")
            output[CHAMPION_ID].append(_record(row, batch_id, champion))
            snapshot = _snapshot(row, history)
            for model_id, artifact in artifacts.items():
                adapter = adapters[model_id]
                trained = {str(team) for team in artifact.runtime_model.teams}  # type: ignore[attr-defined]
                if {str(row.match.home_team_id), str(row.match.away_team_id)}.issubset(trained):
                    try:
                        forecast = adapter.predict(artifact, snapshot)
                    except (RuntimeError, ValueError):
                        continue
                    output[model_id].append(_record(row, batch_id, forecast))
        if targets:
            batch_id += 1
        # Same-kickoff results become history only after every target forecast is frozen.
        history += tuple(row.match for row in batch)
    return {key: tuple(value) for key, value in output.items()}


def _champion_forecast(
    row: CorpusMatch,
    history: tuple[HistoricalMatch, ...],
    artifact_path: Path,
) -> ModelForecast | None:
    product = forecast_from_history(
        artifact_path=artifact_path,
        target_kickoff=row.match.kickoff_at,
        home_team_id=row.match.home_team_id,
        away_team_id=row.match.away_team_id,
        history=tuple(
            FinishedMatch(
                fixture_id=item.fixture_id,
                kickoff_at=item.kickoff_at,
                home_team_id=item.home_team_id,
                away_team_id=item.away_team_id,
                home_goals=item.home_goals,
                away_goals=item.away_goals,
                home_xg=item.home_xg,
                away_xg=item.away_xg,
            )
            for item in history
            if item.known_at <= row.match.kickoff_at
        ),
    )
    if product is None:
        return None
    size = round(math.sqrt(len(product.score_matrix)))
    matrix = [[0.0] * size for _ in range(size)]
    for cell in product.score_matrix:
        matrix[int(cell["home_goals"])][int(cell["away_goals"])] = float(cell["probability"])
    frozen = tuple(tuple(values) for values in matrix)
    home, away, total = distributions(frozen)
    markets = derive_markets(frozen)
    return ModelForecast(
        fixture_id=row.match.fixture_id,
        model_id=CHAMPION_ID,
        model_family="MATCHFORGE_TRANSFERABLE_POISSON",
        model_version=CHAMPION_ID,
        model_artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        football_cutoff=row.match.kickoff_at,
        knowledge_cutoff=row.match.kickoff_at,
        created_at=row.match.kickoff_at,
        expected_home_goals=sum(index * value for index, value in enumerate(home)),
        expected_away_goals=sum(index * value for index, value in enumerate(away)),
        score_labels=("0", "1", "2", "3", "4", "5+"),
        score_matrix=frozen,
        home_goal_distribution=home,
        away_goal_distribution=away,
        total_goal_distribution=total,
        status=ModelStatus.SUCCESS,
        warnings=(),
        input_snapshot_sha256=_sha256_json(
            {
                "fixture_id": str(row.match.fixture_id),
                "history": [str(item.fixture_id) for item in history],
            }
        ),
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


def _snapshot(row: CorpusMatch, history: Iterable[HistoricalMatch]) -> ForecastInputSnapshot:
    return build_forecast_snapshot(
        fixture_id=row.match.fixture_id,
        competition_id=row.match.competition_id,
        competition_context=CompetitionContext.LEAGUE,
        season_label=row.domain,
        kickoff_at=row.match.kickoff_at,
        home_team_id=row.match.home_team_id,
        away_team_id=row.match.away_team_id,
        football_cutoff=row.match.kickoff_at,
        knowledge_cutoff=row.match.kickoff_at,
        knowledge_mode="RETROSPECTIVE_SNAPSHOT_POINT_IN_TIME_REPLAY",
        history=history,
        source_references=(SNAPSHOT_SHA256,),
    )


def _learn_weights(
    predictions: dict[str, tuple[PredictionRecord, ...]],
) -> EnsembleWeights:
    by_model = {
        model_id: {row.scored.forecast.fixture_id: row.scored for row in rows}
        for model_id, rows in predictions.items()
    }
    common = set.intersection(*(set(rows) for rows in by_model.values()))
    champion = by_model[CHAMPION_ID]
    observations = tuple(
        EnsembleDevelopmentObservation(
            fixture_id=fixture_id,
            forecasts=tuple(
                by_model[model_id][fixture_id].forecast for model_id in sorted(by_model)
            ),
            home_goals=champion[fixture_id].home_goals,
            away_goals=champion[fixture_id].away_goals,
        )
        for fixture_id in sorted(common, key=str)
    )
    return learn_ensemble_weights(observations)


def _ensemble_predictions(
    predictions: dict[str, tuple[PredictionRecord, ...]],
    weights: EnsembleWeights,
    artifact_sha: str,
) -> tuple[PredictionRecord, ...]:
    source = {key: value for key, value in predictions.items() if key != "matchforge-ensemble-v1"}
    by_model = {
        model_id: {row.scored.forecast.fixture_id: row for row in rows}
        for model_id, rows in source.items()
    }
    fixtures = sorted(set().union(*(set(rows) for rows in by_model.values())), key=str)
    output: list[PredictionRecord] = []
    for fixture_id in fixtures:
        available = tuple(
            by_model[model_id][fixture_id].scored.forecast
            for model_id in sorted(by_model)
            if fixture_id in by_model[model_id]
        )
        ensemble = build_ensemble_forecast(
            forecasts=available,
            weights=weights,
            minimum_components=2,
            minimum_trained_weight=0.5,
            model_artifact_sha256=artifact_sha,
        )
        if ensemble is None:
            continue
        source_row = next(rows[fixture_id] for rows in by_model.values() if fixture_id in rows)
        output.append(
            PredictionRecord(
                source_row.domain,
                source_row.kickoff_batch,
                ScoredModelForecast(
                    ensemble,
                    source_row.scored.kickoff_at,
                    source_row.scored.outcome_known_at,
                    source_row.scored.home_goals,
                    source_row.scored.away_goals,
                    source_row.scored.competition_id,
                    source_row.scored.season_label,
                ),
            )
        )
    return tuple(
        sorted(output, key=lambda row: (row.scored.kickoff_at, str(row.scored.forecast.fixture_id)))
    )


def _evaluation_report(predictions: dict[str, tuple[PredictionRecord, ...]]) -> dict[str, object]:
    champion = predictions[CHAMPION_ID]
    models: dict[str, object] = {}
    comparisons: dict[str, object] = {}
    model_ids = (CHAMPION_ID, *PENALTYBLOG_MODEL_IDS, "matchforge-ensemble-v1")
    for model_id in model_ids:
        rows = predictions.get(model_id, ())
        models[model_id] = {
            "coverage": len(rows) / 712.0,
            "target_count": len(rows),
            "overall": _metrics(rows) if rows else None,
            "by_competition": {
                domain: _metrics(tuple(row for row in rows if row.domain == domain))
                for domain in EVALUATION_DOMAINS
                if any(row.domain == domain for row in rows)
            },
        }
        if model_id != CHAMPION_ID:
            comparisons[model_id] = _comparison(rows, champion)
    eligible = [
        model_id
        for model_id, value in models.items()
        if cast(dict[str, object], value)["target_count"] == 712
    ]
    winner = min(
        eligible,
        key=lambda model_id: cast(
            dict[str, float], cast(dict[str, object], models[model_id])["overall"]
        )["joint_score_log_loss"],
    )
    promotion = winner != CHAMPION_ID and cast(dict[str, Any], comparisons[winner])["gate_pass"]
    return {
        "models": models,
        "paired_vs_champion": comparisons,
        "winning_model": winner,
        "production_promotion_justified": promotion,
        "disposition": "PROMOTE_CHALLENGER" if promotion else "RETAIN_CHAMPION",
    }


def _metrics(rows: tuple[PredictionRecord, ...]) -> dict[str, object]:
    values = evaluate_model_forecasts(tuple(row.scored for row in rows))
    return asdict(values)


def _comparison(
    candidate: tuple[PredictionRecord, ...], champion: tuple[PredictionRecord, ...]
) -> dict[str, object]:
    candidate_by_id = {row.scored.forecast.fixture_id: row for row in candidate}
    champion_by_id = {row.scored.forecast.fixture_id: row for row in champion}
    common = sorted(candidate_by_id.keys() & champion_by_id.keys(), key=str)
    by_domain: dict[str, object] = {}
    for domain in EVALUATION_DOMAINS:
        pairs = tuple(
            (champion_by_id[key], candidate_by_id[key])
            for key in common
            if candidate_by_id[key].domain == domain
        )
        if not pairs:
            continue
        by_domain[domain] = {
            metric: _metric_delta(pairs, metric, BOOTSTRAP_SEED + index)
            for index, metric in enumerate(METRICS)
        }
        cast(dict[str, object], by_domain[domain])["calibration"] = _calibration_comparison(pairs)
    macro, failure_reasons = _acceptance(by_domain, len(common))
    return {
        "common_target_count": len(common),
        "coverage_required": 712,
        "by_competition": _drop_replicates(by_domain),
        "macro": macro,
        "gate_pass": not failure_reasons,
        "failure_reasons": failure_reasons,
    }


def _acceptance(
    by_domain: dict[str, object], common_count: int
) -> tuple[dict[str, object], list[str]]:
    if common_count != 712:
        return {}, ["INCOMPLETE_COMMON_TARGET_COVERAGE"]
    macro: dict[str, object] = {}
    for metric in METRICS:
        domain_values = [
            cast(dict[str, Any], by_domain[name])[metric] for name in EVALUATION_DOMAINS
        ]
        replicates = [
            sum(value["replicates"][index] for value in domain_values) / 3.0
            for index in range(BOOTSTRAP_REPLICATES)
        ]
        macro[metric] = {
            "delta": sum(value["delta"] for value in domain_values) / 3.0,
            "confidence_interval_95": _interval(replicates),
        }
    failures = _macro_failures(macro)
    for domain in EVALUATION_DOMAINS:
        joint = cast(
            dict[str, Any], cast(dict[str, Any], by_domain[domain])["joint_score_log_loss"]
        )
        if joint["confidence_interval_95"][1] > 0.05:
            failures.append(f"DOMAIN_JOINT_LOG_LOSS_{domain}")
        calibration = cast(dict[str, Any], cast(dict[str, Any], by_domain[domain])["calibration"])
        for outcome, values in calibration.items():
            if values["intercept_worsening"] is None or values["intercept_worsening"] > 0.05:
                failures.append(f"CALIBRATION_INTERCEPT_{domain}_{outcome}")
            if values["slope_worsening"] is None or values["slope_worsening"] > 0.1:
                failures.append(f"CALIBRATION_SLOPE_{domain}_{outcome}")
    return macro, failures


def _macro_failures(macro: dict[str, object]) -> list[str]:
    failures: list[str] = []
    primary = cast(dict[str, Any], macro["joint_score_log_loss"])
    if primary["delta"] > -0.01:
        failures.append("PRIMARY_POINT_DELTA")
    if primary["confidence_interval_95"][1] >= 0:
        failures.append("PRIMARY_INTERVAL")
    guardrails = {
        "result_log_loss": 0.02,
        "multiclass_brier": 0.01,
        "ranked_probability_score": 0.01,
        "total_goal_crps": 0.02,
    }
    for metric, maximum in guardrails.items():
        if cast(dict[str, Any], macro[metric])["confidence_interval_95"][1] > maximum:
            failures.append(f"MACRO_GUARDRAIL_{metric}")
    return failures


def _metric_delta(
    pairs: tuple[tuple[PredictionRecord, PredictionRecord], ...], metric: str, seed: int
) -> dict[str, object]:
    losses = tuple(
        (
            getattr(forecast_losses(reference.scored), metric),
            getattr(forecast_losses(candidate.scored), metric),
            reference.kickoff_batch,
        )
        for reference, candidate in sorted(
            pairs,
            key=lambda pair: (pair[0].scored.kickoff_at, str(pair[0].scored.forecast.fixture_id)),
        )
    )
    differences = tuple(candidate - reference for reference, candidate, _ in losses)
    replicates = _moving_block_replicates(losses, seed)
    return {
        "delta": sum(differences) / len(differences),
        "confidence_interval_95": _interval(replicates),
        "target_count": len(losses),
        "replicates": replicates,
    }


def _calibration_comparison(
    pairs: tuple[tuple[PredictionRecord, PredictionRecord], ...],
) -> dict[str, object]:
    reference = evaluate_model_forecasts(tuple(row.scored for row, _ in pairs))
    candidate = evaluate_model_forecasts(tuple(row.scored for _, row in pairs))
    output: dict[str, object] = {}
    for reference_fit, candidate_fit in zip(
        reference.calibration, candidate.calibration, strict=True
    ):
        intercept_worsening = None
        slope_worsening = None
        if reference_fit.intercept is not None and candidate_fit.intercept is not None:
            intercept_worsening = abs(candidate_fit.intercept) - abs(reference_fit.intercept)
        if reference_fit.slope is not None and candidate_fit.slope is not None:
            slope_worsening = abs(candidate_fit.slope - 1.0) - abs(reference_fit.slope - 1.0)
        output[candidate_fit.outcome] = {
            "candidate_intercept": candidate_fit.intercept,
            "candidate_slope": candidate_fit.slope,
            "champion_intercept": reference_fit.intercept,
            "champion_slope": reference_fit.slope,
            "intercept_worsening": intercept_worsening,
            "slope_worsening": slope_worsening,
        }
    return output


def _moving_block_replicates(rows: tuple[tuple[float, float, int], ...], seed: int) -> list[float]:
    batches: list[list[int]] = []
    for index, row in enumerate(rows):
        if not batches or rows[batches[-1][0]][2] != row[2]:
            batches.append([index])
        else:
            batches[-1].append(index)
    if len(batches) < BOOTSTRAP_BLOCK_BATCHES:
        raise AuthorizedEvaluationError("comparison has fewer than 10 kickoff batches")
    randomizer = random.Random(seed)
    maximum_start = len(batches) - BOOTSTRAP_BLOCK_BATCHES
    output: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        indexes: list[int] = []
        while len(indexes) < len(rows):
            start = randomizer.randrange(maximum_start + 1)
            for batch in batches[start : start + BOOTSTRAP_BLOCK_BATCHES]:
                indexes.extend(batch)
                if len(indexes) >= len(rows):
                    break
        output.append(
            sum(rows[index][1] - rows[index][0] for index in indexes[: len(rows)]) / len(rows)
        )
    return output


def _model_config(model_id: str, code_sha: str, half_life: float) -> dict[str, object]:
    config: dict[str, object] = {
        "code_commit_sha": code_sha,
        "feature_contract": "forecast-input-snapshot-v1",
        "half_life_days": half_life,
        "random_seed": RANDOM_SEED,
    }
    if model_id == "pb-hierarchical-bayes-v1":
        config.update(
            {
                "maximum_rhat": 1.1,
                "minimum_effective_sample_size": 100.0,
                "fit_options": {
                    "n_samples": 3_000,
                    "burn": 1_500,
                    "n_chains": 4,
                    "thin": 1,
                    "n_cores": 1,
                },
            }
        )
    return config


def _target_batches(season: SeasonCorpus) -> tuple[tuple[int, tuple[CorpusMatch, ...]], ...]:
    output = []
    batch_id = 0
    for batch in _all_batches(season.matches):
        targets = tuple(row for row in batch if row.target)
        if targets:
            output.append((batch_id, targets))
            batch_id += 1
    return tuple(output)


def _all_batches(rows: Sequence[CorpusMatch]) -> tuple[tuple[CorpusMatch, ...], ...]:
    output: list[tuple[CorpusMatch, ...]] = []
    position = 0
    while position < len(rows):
        end = position + 1
        while end < len(rows) and rows[end].match.kickoff_at == rows[position].match.kickoff_at:
            end += 1
        output.append(tuple(rows[position:end]))
        position = end
    return tuple(output)


def _folds(
    batches: tuple[tuple[int, tuple[CorpusMatch, ...]], ...], count: int
) -> tuple[tuple[tuple[int, tuple[CorpusMatch, ...]], ...], ...]:
    return tuple(
        batches[len(batches) * index // count : len(batches) * (index + 1) // count]
        for index in range(count)
    )


def _record(row: CorpusMatch, batch_id: int, forecast: ModelForecast) -> PredictionRecord:
    return PredictionRecord(
        row.domain,
        batch_id,
        ScoredModelForecast(
            forecast=forecast,
            kickoff_at=row.match.kickoff_at,
            outcome_known_at=row.match.known_at,
            home_goals=row.match.home_goals,
            away_goals=row.match.away_goals,
            competition_id=str(row.match.competition_id),
            season_label=row.domain,
        ),
    )


def _mean_joint_loss(rows: tuple[PredictionRecord, ...]) -> float:
    return sum(forecast_losses(row.scored).joint_score_log_loss for row in rows) / len(rows)


def _fit_final_artifacts(
    development: SeasonCorpus,
    adapters: dict[str, PenaltyblogGoalModel],
    configs: dict[str, dict[str, object]],
) -> tuple[dict[str, FittedModelArtifact], dict[str, str]]:
    artifacts: dict[str, FittedModelArtifact] = {}
    errors: dict[str, str] = {}
    training = tuple(row.match for row in development.matches)
    for model_id, adapter in adapters.items():
        try:
            artifacts[model_id] = adapter.fit(training, configs[model_id])
        except (RuntimeError, ValueError) as error:
            errors[model_id] = f"{type(error).__name__}: {error}"
    return artifacts, errors


def _artifact_summary(artifact: FittedModelArtifact) -> dict[str, object]:
    return {
        "artifact_sha256": artifact.artifact_sha256,
        "configuration": artifact.configuration,
        "dataset_sha256": artifact.dataset_sha256,
        "dependency_version": artifact.dependency_version,
        "diagnostics": artifact.diagnostics,
        "model_family": artifact.model_family,
        "model_id": artifact.model_id,
        "training_cutoff": artifact.training_cutoff.astimezone(UTC).isoformat(),
        "training_start": artifact.training_start.astimezone(UTC).isoformat(),
    }


def _prediction_manifest_sha256(predictions: dict[str, tuple[PredictionRecord, ...]]) -> str:
    payload = [
        {
            "domain": row.domain,
            "fixture_id": str(row.scored.forecast.fixture_id),
            "kickoff_batch": row.kickoff_batch,
            "model_artifact_sha256": row.scored.forecast.model_artifact_sha256,
            "model_id": model_id,
            "probability_sha256": _sha256_json(row.scored.forecast.score_matrix),
        }
        for model_id, rows in sorted(predictions.items())
        for row in rows
    ]
    return _sha256_json(payload)


def _drop_replicates(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], _without_replicates(value))


def _without_replicates(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _without_replicates(item)
            for key, item in value.items()
            if key != "replicates"
        }
    if isinstance(value, (list, tuple)):
        return [_without_replicates(item) for item in value]
    return value


def _interval(values: Sequence[float]) -> list[float]:
    ordered = sorted(values)
    return [_quantile(ordered, 0.025), _quantile(ordered, 0.975)]


def _quantile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _load_hashed(root: Path, kind: str, digest: str) -> dict[str, Any]:
    path = root / kind / "sha256" / digest[:2] / f"{digest}.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise AuthorizedEvaluationError(f"{kind} resource hash mismatch")
    return _load_path(path)


def _load_path(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
