#!/usr/bin/env python3
"""Execute the corrected full-coverage V2 development holdout exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import numpy as np
import psycopg
from football.forecasting.champion_adapter import (
    TransferableRollingGoalsChampion,
    load_champion_artifact,
)
from football.forecasting.cold_start import ColdStartConfig
from football.forecasting.ensemble import EnsembleWeights, build_full_coverage_ensemble_forecast
from football.forecasting.full_coverage_evaluation import (
    CoverageObservation,
    assert_full_coverage,
    coverage_report,
)
from football.forecasting.hybrid_models import (
    HybridGoalModel,
    build_hybrid_artifact,
    hybrid_artifact_manifest,
)
from football.forecasting.model_contracts import (
    CompetitionContext,
    FittedModelArtifact,
    ForecastInputSnapshot,
    HistoricalMatch,
    ModelForecast,
)
from football.forecasting.multi_model_evaluation import (
    ForecastLosses,
    ScoredModelForecast,
    evaluate_model_forecasts,
    forecast_losses,
)
from football.forecasting.multimodel_authorized_evaluation import (
    DEVELOPMENT_DOMAIN,
    DEVELOPMENT_MANIFEST,
    load_season,
)
from football.forecasting.penaltyblog_models import PenaltyblogGoalModel, default_penaltyblog_models
from football.forecasting.snapshot import build_forecast_snapshot
from football.forecasting.v2_reevaluation import (
    CORPUS_ID,
    CORPUS_SHA256,
    EXPECTED_HOLDOUT_COUNTS,
    EXPECTED_SPLIT_COUNTS,
    PROTOCOL_ID,
    mandatory_pre_outcome_preflight,
)
from psycopg.rows import dict_row

DATE = "2026-10-09"
ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "docs/evaluation/full-coverage-v2-fresh-development-corpus-v1.json"
CROSSWALK_PATH = ROOT / "docs/evaluation/full-coverage-v2-team-identity-crosswalk-v1.json"
CONFIG_PATH = ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-config.json"
PREREG_PATH = (
    ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-preregistration.json"
)
V1_EVIDENCE = ROOT / "docs/evidence/multimodel-challenger-evaluation-v1-2026-10-07.json"
QUALIFICATION_EVIDENCE = (
    ROOT / "docs/evidence/full-coverage-v2-fresh-corpus-qualification-v1-2026-10-08.json"
)
CHAMPION_ARTIFACT = ROOT / "docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json"
V1_SNAPSHOT_ROOT = ROOT / ".local/pitchapi-snapshot-v1/primary"
DEPENDENCY_LOCK = ROOT / "uv.lock"
RESULT_PATH = ROOT / f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-1-{DATE}.json"
REPORT_PATH = ROOT / f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-1-{DATE}.md"
RECEIPT_PATH = (
    ROOT / f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-1-receipt-{DATE}.json"
)

MODEL_INDICES = (0, 2, 3)
BOOTSTRAP_BLOCK_LENGTH = 10
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20260921


@dataclass(frozen=True, slots=True)
class FrozenTarget:
    fixture_id: UUID
    kickoff_at: datetime
    competition_id: UUID
    competition_name: str
    season: str
    home_team_id: UUID
    away_team_id: UUID
    split: str
    target_category: str
    home_promoted: bool | None
    away_promoted: bool | None
    source_provider: str


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    target: FrozenTarget
    snapshot: ForecastInputSnapshot
    home_goals: int
    away_goals: int


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    args = parser.parse_args()
    execute(args.database_url, args.repository_root.resolve())
    return 0


def execute(database_url: str, root: Path = ROOT) -> dict[str, object]:
    config = _json(root / CONFIG_PATH.relative_to(ROOT))
    runtime = build_runtime(config, root)

    def verify_artifacts() -> None:
        expected = {
            key: str(value["artifact_sha256"])
            for key, value in cast(
                dict[str, dict[str, object]], config["candidate_artifacts"]
            ).items()
        }
        actual = runtime["artifact_shas"]
        if actual != expected:
            raise RuntimeError("candidate artifact reproduction mismatch")

    observations, receipt = mandatory_pre_outcome_preflight(
        root=root,
        preregistration_path=root / PREREG_PATH.relative_to(ROOT),
        artifact_verifier=verify_artifacts,
        outcome_loader=lambda: load_observations(database_url, roles={"DEVELOPMENT_HOLDOUT"}),
    )
    result = evaluate_holdout(observations, runtime, config, receipt)
    _write_json(root / RESULT_PATH.relative_to(ROOT), result)
    _write_json(
        root / RECEIPT_PATH.relative_to(ROOT),
        {
            **receipt,
            "contract": "MatchForgeV2ReevaluationExecutionReceiptV1",
            "logical_execution_attempts": 1,
            "outcomes_loaded": True,
            "protocol_id": PROTOCOL_ID,
        },
    )
    (root / REPORT_PATH.relative_to(ROOT)).write_text(_report(result), encoding="utf-8")
    _update_project_status(root, result)
    return result


def load_observations(database_url: str, *, roles: set[str]) -> tuple[EvaluationObservation, ...]:
    corpus = _verified_corpus(CORPUS_PATH)
    targets = tuple(_target(row) for row in cast(list[dict[str, object]], corpus["targets"]))
    selected = tuple(row for row in targets if row.split in roles)
    if not selected:
        raise RuntimeError("requested frozen partition is empty")
    target_ids = {row.fixture_id for row in selected}
    all_team_ids = tuple(
        sorted({team for row in selected for team in (row.home_team_id, row.away_team_id)}, key=str)
    )
    competition_ids = tuple(sorted({row.competition_id for row in selected}, key=str))
    providers_by_competition: dict[UUID, str] = {}
    for target in selected:
        existing_provider = providers_by_competition.setdefault(
            target.competition_id, target.source_provider
        )
        if existing_provider != target.source_provider:
            raise RuntimeError("frozen competition has conflicting outcome providers")
    maximum = max(row.kickoff_at for row in selected)
    minimum = min(row.kickoff_at for row in selected)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        raw = connection.execute(
            """
            SELECT fixture_id, kickoff_at, competition_id, home_team_id, away_team_id,
                   home_goals, away_goals, home_xg, away_xg,
                   source_provider_code, source_snapshot_id
             FROM football.product_team_match_history
             WHERE kickoff_at <= %s
               AND competition_id = ANY(%s::uuid[])
               AND (home_team_id = ANY(%s::uuid[]) OR away_team_id = ANY(%s::uuid[]))
             ORDER BY kickoff_at, fixture_id, source_provider_code, source_snapshot_id
            """,
            (maximum, list(competition_ids), list(all_team_ids), list(all_team_ids)),
        ).fetchall()
    by_fixture: dict[UUID, list[Mapping[str, object]]] = defaultdict(list)
    for row in raw:
        if row["source_provider_code"] != providers_by_competition[row["competition_id"]]:
            continue
        by_fixture[cast(UUID, row["fixture_id"])].append(row)
    target_by_id = {row.fixture_id: row for row in selected}
    history_by_real_fixture: dict[tuple[datetime, UUID, frozenset[UUID]], HistoricalMatch] = {}
    outcomes: dict[UUID, tuple[int, int]] = {}
    for fixture_id, rows in by_fixture.items():
        target = target_by_id.get(fixture_id)
        chosen = next(
            (
                row
                for row in rows
                if target and row["source_provider_code"] == target.source_provider
            ),
            rows[0],
        )
        historical = _historical(chosen)
        real_key = (
            historical.kickoff_at,
            historical.competition_id,
            frozenset((historical.home_team_id, historical.away_team_id)),
        )
        existing = history_by_real_fixture.get(real_key)
        if existing is not None:
            existing_score = {
                existing.home_team_id: existing.home_goals,
                existing.away_team_id: existing.away_goals,
            }
            candidate_score = {
                historical.home_team_id: historical.home_goals,
                historical.away_team_id: historical.away_goals,
            }
            if existing_score != candidate_score:
                raise RuntimeError("retained duplicate real fixture has conflicting outcomes")
            if str(historical.fixture_id) < str(existing.fixture_id):
                history_by_real_fixture[real_key] = historical
        else:
            history_by_real_fixture[real_key] = historical
        if target is not None:
            outcomes[fixture_id] = (historical.home_goals, historical.away_goals)
    missing = target_ids - outcomes.keys()
    if missing:
        raise RuntimeError(f"frozen targets missing retained outcomes: {len(missing)}")
    ordered_history = tuple(
        sorted(
            history_by_real_fixture.values(),
            key=lambda row: (row.kickoff_at, str(row.fixture_id)),
        )
    )
    result: list[EvaluationObservation] = []
    for target in sorted(selected, key=lambda row: (row.kickoff_at, str(row.fixture_id))):
        eligible_history = tuple(
            row for row in ordered_history if row.kickoff_at < target.kickoff_at
        )
        snapshot = build_forecast_snapshot(
            fixture_id=target.fixture_id,
            competition_id=target.competition_id,
            competition_context=CompetitionContext.LEAGUE,
            season_label=target.season,
            kickoff_at=target.kickoff_at,
            home_team_id=target.home_team_id,
            away_team_id=target.away_team_id,
            football_cutoff=target.kickoff_at,
            knowledge_cutoff=target.kickoff_at,
            knowledge_mode="RETROSPECTIVE_SNAPSHOT_POINT_IN_TIME_REPLAY",
            history=eligible_history,
            source_references=(CORPUS_SHA256,),
            home_promoted=target.home_promoted,
            away_promoted=target.away_promoted,
        )
        home_goals, away_goals = outcomes[target.fixture_id]
        result.append(EvaluationObservation(target, snapshot, home_goals, away_goals))
    if roles == {"DEVELOPMENT_HOLDOUT"}:
        if len(result) != EXPECTED_SPLIT_COUNTS["DEVELOPMENT_HOLDOUT"]:
            raise RuntimeError("FAIL_CLOSED_FROZEN_CORPUS_MISMATCH")
        if min(row.target.kickoff_at for row in result) != minimum:
            raise RuntimeError("holdout chronology mismatch")
    return tuple(result)


def build_runtime(config: Mapping[str, object], root: Path = ROOT) -> dict[str, Any]:
    v1_training = tuple(
        row.match
        for row in load_season(
            root / V1_SNAPSHOT_ROOT.relative_to(ROOT),
            DEVELOPMENT_DOMAIN,
            DEVELOPMENT_MANIFEST,
            216,
        ).matches
    )
    evidence = _json(root / V1_EVIDENCE.relative_to(ROOT))
    freeze = cast(dict[str, Any], evidence["development_freeze"])
    model_configs = cast(dict[str, dict[str, object]], freeze["configs"])
    expected_v1 = cast(dict[str, dict[str, object]], freeze["final_artifacts"])
    primary_models = tuple(
        model for index, model in enumerate(default_penaltyblog_models()) if index in MODEL_INDICES
    )
    primary_artifacts = {
        model.model_id: model.fit(v1_training, model_configs[model.model_id])
        for model in primary_models
    }
    for model_id, artifact in primary_artifacts.items():
        if artifact.artifact_sha256 != expected_v1[model_id]["artifact_sha256"]:
            raise RuntimeError(f"V1 artifact reproduction failed: {model_id}")
    champion_model = TransferableRollingGoalsChampion()
    champion_artifact = load_champion_artifact(
        root / CHAMPION_ARTIFACT.relative_to(ROOT), v1_training
    )
    aliases = tuple(
        (str(left), str(right)) for left, right in cast(list[list[str]], config["team_id_aliases"])
    )
    cold = ColdStartConfig(**cast(dict[str, Any], config["selected_cold_start"]))
    source_commit = str(config["source_commit"])
    dependency_sha = hashlib.sha256(
        (root / DEPENDENCY_LOCK.relative_to(ROOT)).read_bytes()
    ).hexdigest()
    v2a_models = tuple(HybridGoalModel.v2a(model, champion_model) for model in primary_models)
    v2b_models = tuple(HybridGoalModel.v2b(model, champion_model, cold) for model in primary_models)
    v2a_artifacts = {
        model.model_id: build_hybrid_artifact(
            model,
            primary_artifacts[model.primary.model_id],
            champion_artifact,
            code_commit_sha=source_commit,
            dependency_lock_sha256=dependency_sha,
            team_id_aliases=aliases,
        )
        for model in v2a_models
    }
    v2b_artifacts = {
        model.model_id: build_hybrid_artifact(
            model,
            primary_artifacts[model.primary.model_id],
            champion_artifact,
            code_commit_sha=source_commit,
            dependency_lock_sha256=dependency_sha,
            team_id_aliases=aliases,
        )
        for model in v2b_models
    }
    ensemble_shas = cast(dict[str, str], config["ensemble_artifact_sha256"])
    artifact_shas = {
        **{key: value.artifact_sha256 for key, value in v2a_artifacts.items()},
        **{key: value.artifact_sha256 for key, value in v2b_artifacts.items()},
        **ensemble_shas,
    }
    return {
        "primary_models": primary_models,
        "primary_artifacts": primary_artifacts,
        "champion_model": champion_model,
        "champion_artifact": champion_artifact,
        "v2a_models": v2a_models,
        "v2a_artifacts": v2a_artifacts,
        "v2b_models": v2b_models,
        "v2b_artifacts": v2b_artifacts,
        "ensemble_shas": ensemble_shas,
        "artifact_shas": artifact_shas,
        "aliases": dict(aliases),
    }


def artifact_manifests(runtime: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    manifests = {
        **{
            key: hybrid_artifact_manifest(value)
            for key, value in cast(dict[str, FittedModelArtifact], runtime["v2a_artifacts"]).items()
        },
        **{
            key: hybrid_artifact_manifest(value)
            for key, value in cast(dict[str, FittedModelArtifact], runtime["v2b_artifacts"]).items()
        },
    }
    for key, value in cast(dict[str, str], runtime["ensemble_shas"]).items():
        manifests[key] = {
            "artifact_sha256": value,
            "contract": "MatchForgeFullCoverageEnsembleArtifactV2",
            "model_id": key,
        }
    return manifests


def evaluate_holdout(
    observations: tuple[EvaluationObservation, ...],
    runtime: Mapping[str, Any],
    config: Mapping[str, object],
    receipt: Mapping[str, object],
) -> dict[str, object]:
    champion_model = cast(TransferableRollingGoalsChampion, runtime["champion_model"])
    champion_artifact = cast(FittedModelArtifact, runtime["champion_artifact"])
    v2a_models = cast(tuple[HybridGoalModel, ...], runtime["v2a_models"])
    v2b_models = cast(tuple[HybridGoalModel, ...], runtime["v2b_models"])
    v2a_artifacts = cast(dict[str, FittedModelArtifact], runtime["v2a_artifacts"])
    v2b_artifacts = cast(dict[str, FittedModelArtifact], runtime["v2b_artifacts"])
    aliases = cast(dict[str, str], runtime["aliases"])
    frozen_weights = EnsembleWeights(
        tuple(
            (str(key), float(value))
            for key, value in cast(dict[str, float], config["ensemble_weights"]).items()
        ),
        (UUID(int=0),),
    )
    predictions: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    coverage: dict[str, list[CoverageObservation]] = defaultdict(list)
    v1_predictions: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    target_by_id = {row.target.fixture_id: row.target for row in observations}
    for item in observations:
        snapshot = item.snapshot
        champion = champion_model.predict(champion_artifact, snapshot)
        _record(predictions, champion, item)
        v2a = tuple(model.predict(v2a_artifacts[model.model_id], snapshot) for model in v2a_models)
        v2b = tuple(model.predict(v2b_artifacts[model.model_id], snapshot) for model in v2b_models)
        for forecast in v2a:
            if (
                forecast.lineage is not None
                and forecast.lineage.champion_fallback_used
                and forecast.score_matrix != champion.score_matrix
            ):
                raise RuntimeError("V2A fallback distribution differs from champion")
        ensemble_a = build_full_coverage_ensemble_forecast(
            model_id="matchforge-ensemble-v2a",
            forecasts=(champion, *v2a),
            champion_forecast=champion,
            weights=frozen_weights,
            model_artifact_sha256=cast(dict[str, str], runtime["ensemble_shas"])[
                "matchforge-ensemble-v2a"
            ],
        )
        ensemble_b = build_full_coverage_ensemble_forecast(
            model_id="matchforge-ensemble-v2b",
            forecasts=(champion, *v2b),
            champion_forecast=champion,
            weights=frozen_weights,
            model_artifact_sha256=cast(dict[str, str], runtime["ensemble_shas"])[
                "matchforge-ensemble-v2b"
            ],
        )
        for forecast in (*v2a, ensemble_a, *v2b, ensemble_b):
            _record(predictions, forecast, item)
            coverage[forecast.model_id].append(
                CoverageObservation(forecast, item.target.competition_name, item.target.season)
            )
        if item.target.target_category == "NATIVE_FITTED":
            aliased = _aliased_snapshot(snapshot, aliases)
            for model in cast(tuple[PenaltyblogGoalModel, ...], runtime["primary_models"]):
                forecast = model.predict(
                    cast(dict[str, FittedModelArtifact], runtime["primary_artifacts"])[
                        model.model_id
                    ],
                    aliased,
                )
                _record(
                    v1_predictions, replace(forecast, input_snapshot_sha256=snapshot.sha256), item
                )

    for rows in coverage.values():
        assert_full_coverage(tuple(rows), eligible_targets=len(observations))
    champion_rows = tuple(predictions[champion_model.model_id])
    coverage_results = {
        model_id: coverage_report(tuple(rows), eligible_targets=len(observations))
        for model_id, rows in coverage.items()
    }
    metric_results = {
        model_id: _metric_payload(tuple(rows)) for model_id, rows in predictions.items()
    }
    paired_overall = {
        model_id: _paired_payload(tuple(rows), champion_rows)
        for model_id, rows in predictions.items()
        if model_id != champion_model.model_id
    }
    cold_start = _cold_start_results(predictions, champion_rows, target_by_id)
    fitted = _fitted_results(predictions, v1_predictions, target_by_id)
    domains = _domain_results(predictions, champion_rows)
    promoted = _promoted_results(predictions, champion_rows, target_by_id)
    decisions = _decisions(coverage_results, cold_start, fitted, paired_overall, domains)
    accepted = [key for key, value in decisions.items() if value == "DEVELOPMENT_ACCEPTED"]
    winner = _winner(accepted, predictions)
    disposition = _overall_disposition(decisions)
    return {
        "authorization": "AUTHORIZE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1",
        "bootstrap": {
            "block_length": BOOTSTRAP_BLOCK_LENGTH,
            "confidence_interval": 0.95,
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "type": "MOVING_BLOCK",
        },
        "candidate_artifacts": config["candidate_artifacts"],
        "contract": "MatchForgeFullCoverageChallengersV2ReevaluationResultV1_1",
        "corpus": {
            "id": CORPUS_ID,
            "sha256": CORPUS_SHA256,
            "split": EXPECTED_SPLIT_COUNTS,
            "holdout": EXPECTED_HOLDOUT_COUNTS,
        },
        "coverage": coverage_results,
        "development_disposition": disposition,
        "development_winner": winner,
        "domain_results": domains,
        "execution": {
            **receipt,
            "logical_execution_attempts": 1,
            "outcomes_loaded": True,
        },
        "fitted_team_vs_v1": fitted,
        "independent_evaluation_available": False,
        "metrics": metric_results,
        "model_decisions": decisions,
        "paired_vs_champion": paired_overall,
        "parent_protocol_id": "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1",
        "production_champion_changed": False,
        "production_promotion_authorized": False,
        "promoted_team_results": promoted,
        "protocol_id": PROTOCOL_ID,
        "selected_hyperparameters": {
            "ensemble_status": config["ensemble_status"],
            "ensemble_weights": config["ensemble_weights"],
            "l2": cast(dict[str, object], config["selected_cold_start"])["l2_regularization"],
            "shrinkage_k": cast(dict[str, object], config["selected_cold_start"])["shrinkage_k"],
            "transfer_weight": config["selected_transfer_weight"],
        },
        "source_commit": config["source_commit"],
        "v2b_cold_start_vs_champion": cold_start,
        "xg_coverage": {"complete": 0, "missing": 1572, "rate": 0.0},
    }


def _cold_start_results(
    predictions: Mapping[str, list[ScoredModelForecast]],
    champion: tuple[ScoredModelForecast, ...],
    targets: Mapping[UUID, FrozenTarget],
) -> dict[str, object]:
    output: dict[str, object] = {}
    fallback_ids = {
        fixture_id
        for fixture_id, target in targets.items()
        if target.target_category != "NATIVE_FITTED"
    }
    champion_by_id = {row.forecast.fixture_id: row for row in champion}
    for model_id, rows in predictions.items():
        if not (model_id.endswith("-transferable-v2b") or model_id == "matchforge-ensemble-v2b"):
            continue
        comparable = tuple(
            row
            for row in rows
            if row.forecast.fixture_id in fallback_ids
            and row.forecast.lineage is not None
            and row.forecast.lineage.cold_start_component_used
            and not row.forecast.lineage.champion_fallback_used
        )
        fallback_count = sum(
            row.forecast.fixture_id in fallback_ids
            and row.forecast.lineage is not None
            and row.forecast.lineage.champion_fallback_used
            for row in rows
        )
        payload: dict[str, object] = {
            "v2a_fallback_target_count": len(fallback_ids),
            "native_cold_start_count": len(comparable),
            "v2b_champion_fallback_count": fallback_count,
        }
        if comparable:
            reference = tuple(champion_by_id[row.forecast.fixture_id] for row in comparable)
            payload.update(_paired_payload(comparable, reference))
        output[model_id] = payload
    return output


def _fitted_results(
    predictions: Mapping[str, list[ScoredModelForecast]],
    v1: Mapping[str, list[ScoredModelForecast]],
    targets: Mapping[UUID, FrozenTarget],
) -> dict[str, object]:
    fitted_ids = {
        fixture_id
        for fixture_id, target in targets.items()
        if target.target_category == "NATIVE_FITTED"
    }
    output: dict[str, object] = {}
    pairs = {
        "pb-dixon-coles-transferable-v2b": "pb-dixon-coles-v1",
        "pb-negative-binomial-transferable-v2b": "pb-negative-binomial-v1",
        "pb-weibull-copula-transferable-v2b": "pb-weibull-copula-v1",
    }
    for model_id, v1_id in pairs.items():
        candidate = tuple(
            row for row in predictions[model_id] if row.forecast.fixture_id in fitted_ids
        )
        reference = tuple(v1[v1_id])
        output[model_id] = _paired_payload(candidate, reference)
    return output


def _domain_results(
    predictions: Mapping[str, list[ScoredModelForecast]],
    champion: tuple[ScoredModelForecast, ...],
) -> dict[str, object]:
    champion_by_id = {row.forecast.fixture_id: row for row in champion}
    result: dict[str, object] = {}
    for model_id, rows in predictions.items():
        if not (model_id.endswith("-transferable-v2b") or model_id == "matchforge-ensemble-v2b"):
            continue
        domains: dict[str, object] = {}
        for domain in sorted({row.competition_id for row in rows}):
            candidate = tuple(row for row in rows if row.competition_id == domain)
            reference = tuple(champion_by_id[row.forecast.fixture_id] for row in candidate)
            domains[domain] = _paired_payload(candidate, reference)
        result[model_id] = domains
    return result


def _promoted_results(
    predictions: Mapping[str, list[ScoredModelForecast]],
    champion: tuple[ScoredModelForecast, ...],
    targets: Mapping[UUID, FrozenTarget],
) -> dict[str, object]:
    promoted_ids = {
        fixture_id
        for fixture_id, target in targets.items()
        if target.home_promoted is True or target.away_promoted is True
    }
    champion_by_id = {row.forecast.fixture_id: row for row in champion}
    output: dict[str, object] = {}
    for model_id, rows in predictions.items():
        if not (model_id.endswith("-transferable-v2b") or model_id == "matchforge-ensemble-v2b"):
            continue
        candidate = tuple(row for row in rows if row.forecast.fixture_id in promoted_ids)
        reference = tuple(champion_by_id[row.forecast.fixture_id] for row in candidate)
        native = sum(
            row.forecast.lineage is not None and row.forecast.lineage.cold_start_component_used
            for row in candidate
        )
        fallback = sum(
            row.forecast.lineage is not None and row.forecast.lineage.champion_fallback_used
            for row in candidate
        )
        output[model_id] = {
            "coverage": len(candidate) / len(promoted_ids),
            "native_cold_start_count": native,
            "champion_fallback_count": fallback,
            **_paired_payload(candidate, reference),
        }
    return output


def _decisions(
    coverage: Mapping[str, object],
    cold: Mapping[str, object],
    fitted: Mapping[str, object],
    overall: Mapping[str, object],
    domains: Mapping[str, object],
) -> dict[str, str]:
    output: dict[str, str] = {}
    for model_id in (
        "pb-dixon-coles-transferable-v2b",
        "pb-negative-binomial-transferable-v2b",
        "pb-weibull-copula-transferable-v2b",
        "matchforge-ensemble-v2b",
    ):
        cov = cast(dict[str, object], coverage[model_id])
        cold_result = cast(dict[str, object], cold[model_id])
        if _number(cov["coverage"]) != 1.0:
            output[model_id] = "DEVELOPMENT_REJECTED"
            continue
        if _number(cold_result["native_cold_start_count"]) == 0:
            output[model_id] = "ROUTING_ONLY_NO_NATIVE_COLD_START"
            continue
        cold_pass = _accept_cold(cold_result)
        overall_pass = _accept_overall(cast(dict[str, object], overall[model_id]))
        fitted_pass = True
        if model_id in fitted:
            fitted_pass = _accept_fitted(cast(dict[str, object], fitted[model_id]))
        domain_pass = _accept_domains(cast(dict[str, object], domains[model_id]))
        output[model_id] = (
            "DEVELOPMENT_ACCEPTED"
            if cold_pass and overall_pass and fitted_pass and domain_pass
            else "DEVELOPMENT_REJECTED"
        )
    return output


def _accept_cold(value: Mapping[str, object]) -> bool:
    metrics = cast(dict[str, dict[str, object]], value["paired_deltas"])
    return (
        _number(metrics["joint_score_log_loss"]["delta"]) <= -0.003
        and float(cast(list[float], metrics["joint_score_log_loss"]["confidence_interval_95"])[1])
        < 0
        and _number(metrics["result_log_loss"]["delta"]) <= 0
        and float(cast(list[float], metrics["result_log_loss"]["confidence_interval_95"])[1]) <= 0
        and float(cast(list[float], metrics["multiclass_brier"]["confidence_interval_95"])[1])
        <= 0.01
        and float(
            cast(list[float], metrics["ranked_probability_score"]["confidence_interval_95"])[1]
        )
        <= 0.01
        and float(cast(list[float], metrics["total_goal_crps"]["confidence_interval_95"])[1])
        <= 0.02
    )


def _accept_overall(value: Mapping[str, object]) -> bool:
    metrics = cast(dict[str, dict[str, object]], value["paired_deltas"])
    return (
        _number(metrics["joint_score_log_loss"]["delta"]) <= -0.003
        and float(cast(list[float], metrics["joint_score_log_loss"]["confidence_interval_95"])[1])
        < 0
        and _number(metrics["result_log_loss"]["delta"]) <= 0
        and float(cast(list[float], metrics["multiclass_brier"]["confidence_interval_95"])[1])
        <= 0.01
        and float(
            cast(list[float], metrics["ranked_probability_score"]["confidence_interval_95"])[1]
        )
        <= 0.01
        and float(cast(list[float], metrics["total_goal_crps"]["confidence_interval_95"])[1])
        <= 0.02
    )


def _accept_fitted(value: Mapping[str, object]) -> bool:
    metrics = cast(dict[str, dict[str, object]], value["paired_deltas"])
    return (
        _number(metrics["joint_score_log_loss"]["delta"]) <= 0.010
        and float(cast(list[float], metrics["result_log_loss"]["confidence_interval_95"])[1])
        <= 0.01
        and float(cast(list[float], metrics["multiclass_brier"]["confidence_interval_95"])[1])
        <= 0.01
        and float(
            cast(list[float], metrics["ranked_probability_score"]["confidence_interval_95"])[1]
        )
        <= 0.01
        and float(cast(list[float], metrics["total_goal_crps"]["confidence_interval_95"])[1])
        <= 0.02
    )


def _accept_domains(value: Mapping[str, object]) -> bool:
    deltas = [
        _number(
            cast(dict[str, dict[str, object]], cast(dict[str, object], row)["paired_deltas"])[
                "joint_score_log_loss"
            ]["delta"]
        )
        for row in value.values()
    ]
    return sum(delta < 0 for delta in deltas) >= 3 and all(delta <= 0.020 for delta in deltas)


def _winner(
    accepted: Sequence[str], predictions: Mapping[str, list[ScoredModelForecast]]
) -> str | None:
    if not accepted:
        return None
    simplicity = {
        "pb-dixon-coles-transferable-v2b": 0,
        "pb-negative-binomial-transferable-v2b": 1,
        "pb-weibull-copula-transferable-v2b": 2,
        "matchforge-ensemble-v2b": 3,
    }
    return min(
        accepted,
        key=lambda model_id: (
            evaluate_model_forecasts(tuple(predictions[model_id])).joint_score_log_loss,
            evaluate_model_forecasts(tuple(predictions[model_id])).result_log_loss,
            evaluate_model_forecasts(tuple(predictions[model_id])).multiclass_brier,
            evaluate_model_forecasts(tuple(predictions[model_id])).ranked_probability_score,
            evaluate_model_forecasts(tuple(predictions[model_id])).total_goal_crps,
            sum(
                row.forecast.lineage is not None and row.forecast.lineage.champion_fallback_used
                for row in predictions[model_id]
            ),
            simplicity[model_id],
            model_id,
        ),
    )


def _overall_disposition(decisions: Mapping[str, str]) -> str:
    if "DEVELOPMENT_ACCEPTED" in decisions.values():
        return "DEVELOPMENT_ACCEPTED_FOR_INDEPENDENT_EVALUATION"
    if all(
        value in {"DEVELOPMENT_REJECTED", "ROUTING_ONLY_NO_NATIVE_COLD_START"}
        for value in decisions.values()
    ):
        return "DEVELOPMENT_REJECTED"
    return "DEVELOPMENT_PARTIAL_SUCCESS"


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError("metric value must be numeric")
    return float(value)


def _metric_payload(rows: tuple[ScoredModelForecast, ...]) -> dict[str, object]:
    metrics = asdict(evaluate_model_forecasts(rows))
    return cast(dict[str, object], _plain(metrics))


def _paired_payload(
    candidate: tuple[ScoredModelForecast, ...], reference: tuple[ScoredModelForecast, ...]
) -> dict[str, object]:
    if not candidate or len(candidate) != len(reference):
        raise RuntimeError("paired comparison target mismatch")
    candidate_by_id = {row.forecast.fixture_id: row for row in candidate}
    reference_by_id = {row.forecast.fixture_id: row for row in reference}
    if candidate_by_id.keys() != reference_by_id.keys():
        raise RuntimeError("paired comparison fixture mismatch")
    ordered = tuple(
        sorted(candidate_by_id, key=lambda key: (candidate_by_id[key].kickoff_at, str(key)))
    )
    names = tuple(ForecastLosses.__dataclass_fields__)
    deltas: dict[str, object] = {}
    for offset, name in enumerate(names):
        values = np.asarray(
            [
                getattr(forecast_losses(candidate_by_id[key]), name)
                - getattr(forecast_losses(reference_by_id[key]), name)
                for key in ordered
            ],
            dtype=float,
        )
        lower, upper = _moving_block_interval(values, seed=BOOTSTRAP_SEED + offset)
        deltas[name] = {
            "confidence_interval_95": [lower, upper],
            "delta": float(values.mean()),
            "target_count": len(values),
        }
    return {
        "candidate_metrics": _metric_payload(candidate),
        "paired_deltas": deltas,
        "reference_metrics": _metric_payload(reference),
        "target_count": len(candidate),
    }


def _moving_block_interval(values: np.ndarray[Any, Any], *, seed: int) -> tuple[float, float]:
    size = len(values)
    length = min(BOOTSTRAP_BLOCK_LENGTH, size)
    starts = np.arange(size - length + 1)
    blocks = math.ceil(size / length)
    rng = np.random.default_rng(seed)
    draws = np.empty(BOOTSTRAP_REPLICATES, dtype=float)
    for index in range(BOOTSTRAP_REPLICATES):
        sampled_starts = rng.choice(starts, size=blocks, replace=True)
        sample = np.concatenate([values[start : start + length] for start in sampled_starts])[:size]
        draws[index] = float(sample.mean())
    lower, upper = np.quantile(draws, (0.025, 0.975))
    return float(lower), float(upper)


def _record(
    output: dict[str, list[ScoredModelForecast]],
    forecast: ModelForecast,
    item: EvaluationObservation,
) -> None:
    output[forecast.model_id].append(
        ScoredModelForecast(
            forecast=forecast,
            kickoff_at=item.target.kickoff_at,
            outcome_known_at=item.target.kickoff_at + timedelta(hours=3),
            home_goals=item.home_goals,
            away_goals=item.away_goals,
            competition_id=item.target.competition_name,
            season_label=item.target.season,
        )
    )


def _aliased_snapshot(
    snapshot: ForecastInputSnapshot, aliases: Mapping[str, str]
) -> ForecastInputSnapshot:
    return replace(
        snapshot,
        home_team_id=UUID(aliases.get(str(snapshot.home_team_id), str(snapshot.home_team_id))),
        away_team_id=UUID(aliases.get(str(snapshot.away_team_id), str(snapshot.away_team_id))),
    )


def _historical(row: Mapping[str, object]) -> HistoricalMatch:
    kickoff = cast(datetime, row["kickoff_at"])
    return HistoricalMatch(
        fixture_id=cast(UUID, row["fixture_id"]),
        competition_id=cast(UUID, row["competition_id"]),
        competition_context=CompetitionContext.LEAGUE,
        kickoff_at=kickoff,
        known_at=kickoff + timedelta(hours=3),
        home_team_id=cast(UUID, row["home_team_id"]),
        away_team_id=cast(UUID, row["away_team_id"]),
        home_goals=int(cast(int, row["home_goals"])),
        away_goals=int(cast(int, row["away_goals"])),
        home_xg=float(cast(float, row["home_xg"])) if row["home_xg"] is not None else None,
        away_xg=float(cast(float, row["away_xg"])) if row["away_xg"] is not None else None,
    )


def _target(row: Mapping[str, object]) -> FrozenTarget:
    def promoted(value: object) -> bool | None:
        if value == "PROMOTED_TEAM":
            return True
        if value == "NOT_PROMOTED":
            return False
        return None

    return FrozenTarget(
        fixture_id=UUID(str(row["fixture_id"])),
        kickoff_at=datetime.fromisoformat(str(row["kickoff_at"])),
        competition_id=UUID(str(row["competition_id"])),
        competition_name=str(row["competition_name"]),
        season=str(row["season"]),
        home_team_id=UUID(str(row["home_team_id"])),
        away_team_id=UUID(str(row["away_team_id"])),
        split=str(row["split"]),
        target_category=str(row["target_category"]),
        home_promoted=promoted(row["home_promotion_state"]),
        away_promoted=promoted(row["away_promotion_state"]),
        source_provider=str(row["source_provider"]),
    )


def _verified_corpus(path: Path) -> dict[str, object]:
    corpus = _json(path)
    if corpus.get("corpus_id") != CORPUS_ID or corpus.get("corpus_sha256") != CORPUS_SHA256:
        raise RuntimeError("FAIL_CLOSED_FROZEN_CORPUS_MISMATCH")
    counts = cast(dict[str, object], corpus["counts"])
    if counts.get("split") != EXPECTED_SPLIT_COUNTS or counts.get("holdout") != {
        **EXPECTED_HOLDOUT_COUNTS,
        "cold_start_power": "ADEQUATE_COLD_START_POWER",
        "total": 315,
    }:
        raise RuntimeError("FAIL_CLOSED_FROZEN_CORPUS_MISMATCH")
    return corpus


def _update_project_status(root: Path, result: Mapping[str, object]) -> None:
    path = root / "docs/project-status.json"
    status = _json(path)
    tracks = cast(list[dict[str, object]], status["evaluation_tracks"])
    tracks.append(
        {
            "development_outcomes_loaded": True,
            "development_winner": result["development_winner"],
            "evidence_ref": RESULT_PATH.relative_to(ROOT).as_posix(),
            "evidence_sha256": _file_sha(root / RESULT_PATH.relative_to(ROOT)),
            "evaluation_protocol_id": PROTOCOL_ID,
            "exact_logical_execution_attempts": 1,
            "execution_commit": cast(dict[str, object], result["execution"])["execution_commit"],
            "independent_evaluation_available": False,
            "model_promoted": False,
            "owner_decision": "CORRECT_FULL_COVERAGE_V2_REEVALUATION_COMMIT_INVARIANT_V1",
            "owner_decision_ref": (
                f"docs/evidence/owner-decision-correct-full-coverage-v2-reevaluation-"
                f"commit-invariant-{DATE}.json"
            ),
            "production_champion_changed": False,
            "provider": "MULTISOURCE_RETAINED_ONLY",
            "report_ref": REPORT_PATH.relative_to(ROOT).as_posix(),
            "result_classification": result["development_disposition"],
            "source_commit": result["source_commit"],
            "status": f"COMPLETE_{result['development_disposition']}",
        }
    )
    decisions = cast(list[str], status["owner_decisions"])
    if "CORRECT_FULL_COVERAGE_V2_REEVALUATION_COMMIT_INVARIANT_V1" not in decisions:
        decisions.append("CORRECT_FULL_COVERAGE_V2_REEVALUATION_COMMIT_INVARIANT_V1")
    status["updated_at"] = f"{DATE}T00:00:00Z"
    _write_json(path, status)


def _report(result: Mapping[str, object]) -> str:
    selected = cast(dict[str, object], result["selected_hyperparameters"])
    return "\n".join(
        (
            "# Full-coverage challenger V2 clean re-evaluation",
            "",
            f"Protocol: `{result['protocol_id']}`",
            f"Disposition: `{result['development_disposition']}`",
            f"Winner: `{result['development_winner']}`",
            "",
            f"Selected shrinkage k: `{selected['shrinkage_k']}`",
            f"Selected L2: `{selected['l2']}`",
            f"Selected transfer weight: `{selected['transfer_weight']}`",
            "",
            (
                "Fresh HOLDOUT outcomes were loaded once after the corrected commit "
                "and hash preflight passed."
            ),
            "Production champion changed: NO.",
            "Independent evaluation available: NO.",
            "",
        )
    )


def _json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(value) + "\n", encoding="utf-8")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (datetime, UUID)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    return value


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
