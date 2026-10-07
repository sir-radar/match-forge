#!/usr/bin/env python3
"""Run V2A/V2B selection and comparison on the authorized development corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from football.forecasting.champion_adapter import (
    TransferableRollingGoalsChampion,
    load_champion_artifact,
)
from football.forecasting.cold_start_fitting import (
    ColdStartDevelopmentObservation,
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
    HybridGoalModel,
    build_hybrid_artifact,
    hybrid_artifact_manifest,
)
from football.forecasting.model_contracts import (
    CompetitionContext,
    HistoricalMatch,
    ModelForecast,
)
from football.forecasting.multi_model_evaluation import (
    ScoredModelForecast,
    evaluate_model_forecasts,
    forecast_losses,
    paired_bootstrap_delta,
)
from football.forecasting.multimodel_authorized_evaluation import (
    DEVELOPMENT_DOMAIN,
    DEVELOPMENT_MANIFEST,
    load_season,
)
from football.forecasting.penaltyblog_models import default_penaltyblog_models
from football.forecasting.snapshot import build_forecast_snapshot
from football.product.domain import stable_id

from scripts.run_transferable_npxg_dixon_coles_v2_research import (
    CORPUS_SHA256,
    FIREWALL_SHA256,
    MAPPING_SHA256,
    NORMALIZED_MANIFEST_SHA256,
    SNAPSHOT_SHA256,
    load_development,
)

PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_DEVELOPMENT_V1"
V1_EVIDENCE = Path("docs/evidence/multimodel-challenger-evaluation-v1-2026-10-07.json")
DEPENDENCY_LOCK = Path("uv.lock")
COMPETITION_PROVIDER_IDS = {
    "bundesliga_2024_25": "l_1Isor4",
    "bundesliga_2025_26": "l_1Isor4",
    "la_liga_2024_25": "l_0ErfuF",
    "premier_league_2024_25": "l_4WFCIZ",
    "serie_a_2024_25": "l_0ALvwF",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--development-root",
        type=Path,
        default=Path(".local/pitchapi-multi-domain-development-v1-r3/primary"),
    )
    parser.add_argument(
        "--v1-snapshot-root",
        type=Path,
        default=Path(".local/pitchapi-snapshot-v1/primary"),
    )
    parser.add_argument(
        "--champion-artifact",
        type=Path,
        default=Path("docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json"),
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    _verify_source(args.source_commit)
    result = execute(
        development_root=args.development_root,
        v1_snapshot_root=args.v1_snapshot_root,
        champion_artifact_path=args.champion_artifact,
        source_commit=args.source_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_json(result) + "\n", encoding="utf-8")
    args.report.write_text(_markdown(result), encoding="utf-8")


def execute(
    *,
    development_root: Path,
    v1_snapshot_root: Path,
    champion_artifact_path: Path,
    source_commit: str,
) -> dict[str, object]:
    _verify_source(source_commit)
    observations = load_development(development_root)
    targets = _target_ids(development_root)
    development = _development_observations(observations, targets)
    selection = select_cold_start_config(development)
    v1_training = tuple(
        row.match
        for row in load_season(
            v1_snapshot_root, DEVELOPMENT_DOMAIN, DEVELOPMENT_MANIFEST, 216
        ).matches
    )
    v1_evidence = cast(dict[str, Any], json.loads(V1_EVIDENCE.read_text(encoding="utf-8")))
    freeze = cast(dict[str, Any], v1_evidence["development_freeze"])
    configs = cast(dict[str, dict[str, object]], freeze["configs"])
    expected_artifacts = cast(dict[str, dict[str, object]], freeze["final_artifacts"])
    primary_models = tuple(
        model for index, model in enumerate(default_penaltyblog_models()) if index in (0, 2, 3)
    )
    primary_artifacts = {
        model.model_id: model.fit(v1_training, configs[model.model_id]) for model in primary_models
    }
    for model_id, artifact in primary_artifacts.items():
        if artifact.artifact_sha256 != expected_artifacts[model_id]["artifact_sha256"]:
            raise RuntimeError(f"V1 artifact reproduction failed: {model_id}")
    champion_model = TransferableRollingGoalsChampion()
    champion_artifact = load_champion_artifact(champion_artifact_path, v1_training)
    dependency_lock_sha = hashlib.sha256(DEPENDENCY_LOCK.read_bytes()).hexdigest()
    v2a_models = tuple(HybridGoalModel.v2a(model, champion_model) for model in primary_models)
    v2b_models = tuple(
        HybridGoalModel.v2b(model, champion_model, selection.config) for model in primary_models
    )
    v2a_artifacts = {
        model.model_id: build_hybrid_artifact(
            model,
            primary_artifacts[model.primary.model_id],
            champion_artifact,
            code_commit_sha=source_commit,
            dependency_lock_sha256=dependency_lock_sha,
        )
        for model in v2a_models
    }
    v2b_artifacts = {
        model.model_id: build_hybrid_artifact(
            model,
            primary_artifacts[model.primary.model_id],
            champion_artifact,
            code_commit_sha=source_commit,
            dependency_lock_sha256=dependency_lock_sha,
        )
        for model in v2b_models
    }
    holdout = selection.split.development_holdout
    predictions: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    coverage: dict[str, list[CoverageObservation]] = defaultdict(list)
    frozen_weights = EnsembleWeights(
        model_weights=tuple(
            (str(key), float(value))
            for key, value in cast(dict[str, float], freeze["ensemble_weights"]).items()
        ),
        development_fixture_ids=tuple(
            UUID(value)
            for value in cast(
                list[str],
                freeze["selection"]["matchforge-ensemble-v1"].get("development_fixture_ids", []),
            )
        ),
    )
    if not frozen_weights.development_fixture_ids:
        frozen_weights = EnsembleWeights(
            model_weights=frozen_weights.model_weights,
            development_fixture_ids=(UUID(int=0),),
        )
    ensemble_shas = {
        "matchforge-ensemble-v2a": _sha(
            {
                "model_id": "matchforge-ensemble-v2a",
                "weights": frozen_weights.model_weights,
                "source_commit": source_commit,
            }
        ),
        "matchforge-ensemble-v2b": _sha(
            {
                "model_id": "matchforge-ensemble-v2b",
                "weights": frozen_weights.model_weights,
                "source_commit": source_commit,
            }
        ),
    }
    for item in holdout:
        snapshot = item.snapshot
        champion = champion_model.predict(champion_artifact, snapshot)
        _record(predictions, champion, item)
        v2a = tuple(model.predict(v2a_artifacts[model.model_id], snapshot) for model in v2a_models)
        v2b = tuple(model.predict(v2b_artifacts[model.model_id], snapshot) for model in v2b_models)
        ensemble_a = build_full_coverage_ensemble_forecast(
            model_id="matchforge-ensemble-v2a",
            forecasts=(champion, *v2a),
            champion_forecast=champion,
            weights=frozen_weights,
            model_artifact_sha256=ensemble_shas["matchforge-ensemble-v2a"],
        )
        ensemble_b = build_full_coverage_ensemble_forecast(
            model_id="matchforge-ensemble-v2b",
            forecasts=(champion, *v2b),
            champion_forecast=champion,
            weights=frozen_weights,
            model_artifact_sha256=ensemble_shas["matchforge-ensemble-v2b"],
        )
        for forecast in (*v2a, ensemble_a, *v2b, ensemble_b):
            _record(predictions, forecast, item)
            coverage[forecast.model_id].append(
                CoverageObservation(
                    forecast,
                    str(snapshot.competition_id),
                    snapshot.season_label,
                )
            )
    coverage_reports = {
        model_id: coverage_report(tuple(rows), eligible_targets=len(holdout))
        for model_id, rows in coverage.items()
    }
    for rows in coverage.values():
        assert_full_coverage(tuple(rows), eligible_targets=len(holdout))
    metrics = {model_id: _metrics(tuple(rows)) for model_id, rows in predictions.items()}
    champion_rows = tuple(predictions[champion_model.model_id])
    paired = {
        model_id: _paired(tuple(rows), champion_rows)
        for model_id, rows in predictions.items()
        if model_id != champion_model.model_id
    }
    cold_start_comparisons = _cold_start_comparisons(predictions, champion_rows)
    return {
        "contract": "MatchForgeFullCoverageChallengersV2DevelopmentResultV1",
        "protocol_id": PROTOCOL_ID,
        "source_commit": source_commit,
        "datasets": {
            "development_snapshot_sha256": SNAPSHOT_SHA256,
            "development_corpus_sha256": CORPUS_SHA256,
            "development_firewall_sha256": FIREWALL_SHA256,
            "development_normalized_manifest_sha256": NORMALIZED_MANIFEST_SHA256,
            "development_mapping_sha256": MAPPING_SHA256,
            "spent_evaluation_used_for_tuning": False,
        },
        "split": {
            "train_count": len(selection.split.train),
            "validation_count": len(selection.split.validation),
            "development_holdout_count": len(selection.split.development_holdout),
            "train_end": selection.split.train_end.isoformat(),
            "validation_end": selection.split.validation_end.isoformat(),
            "same_kickoff_batches_preserved": True,
        },
        "selected_cold_start": _plain(asdict(selection.config)),
        "selected_transfer_weight": selection.selected_transfer_weight,
        "candidate_count": selection.candidate_count,
        "selection_validation_metrics": asdict(selection.validation_metrics),
        "development_holdout_direct_metrics": asdict(selection.development_holdout_metrics),
        "v1_artifacts_reproduced": {
            key: value.artifact_sha256 for key, value in primary_artifacts.items()
        },
        "v2_artifacts": {
            **{key: hybrid_artifact_manifest(value) for key, value in v2a_artifacts.items()},
            **{key: hybrid_artifact_manifest(value) for key, value in v2b_artifacts.items()},
            **ensemble_shas,
        },
        "old_coverage": _old_coverage(v1_evidence),
        "old_missing_root_cause": _root_cause_breakdown(v1_evidence),
        "coverage": coverage_reports,
        "metrics": metrics,
        "paired_vs_champion": paired,
        "cold_start_subset_vs_champion": cold_start_comparisons,
        "independent_evaluation_available": False,
        "disposition": "DEVELOPMENT_COMPLETE_NEW_EVALUATION_CORPUS_REQUIRED",
        "production_promotion_justified": False,
        "production_conclusion": "PRODUCTION_PROMOTION_NOT_YET_JUSTIFIED",
        "limitations": [
            "WEIBULL_COPULA_V2B_COLD_START_UNAVAILABLE_USES_EXPLICIT_CHAMPION_FALLBACK",
            "PROMOTION_STATUS_UNKNOWN_WITHOUT_QUALIFIED_LOWER_DIVISION_HISTORY",
            "NO_UNSPENT_AUTHORIZED_INDEPENDENT_EVALUATION_CORPUS",
        ],
    }


def _development_observations(
    observations: tuple[Any, ...], targets: frozenset[UUID]
) -> tuple[ColdStartDevelopmentObservation, ...]:
    history: list[HistoricalMatch] = []
    result: list[ColdStartDevelopmentObservation] = []
    position = 0
    while position < len(observations):
        end = position + 1
        while (
            end < len(observations)
            and observations[end].kickoff_at == observations[position].kickoff_at
        ):
            end += 1
        batch = observations[position:end]
        for row in batch:
            if row.match_id not in targets:
                continue
            snapshot = build_forecast_snapshot(
                fixture_id=row.match_id,
                competition_id=_competition_id(row.scope_key),
                competition_context=CompetitionContext.LEAGUE,
                season_label=row.scope_key,
                kickoff_at=row.kickoff_at,
                home_team_id=row.home_team_id,
                away_team_id=row.away_team_id,
                football_cutoff=row.kickoff_at,
                knowledge_cutoff=row.kickoff_at,
                knowledge_mode="RETROSPECTIVE_SNAPSHOT_POINT_IN_TIME_REPLAY",
                history=history,
                source_references=(SNAPSHOT_SHA256,),
            )
            result.append(ColdStartDevelopmentObservation(snapshot, row.home_goals, row.away_goals))
        history.extend(_historical(row) for row in batch)
        position = end
    if len(result) != 1270:
        raise RuntimeError(f"development target count mismatch: {len(result)}")
    return tuple(result)


def _historical(row: Any) -> HistoricalMatch:
    return HistoricalMatch(
        fixture_id=row.match_id,
        competition_id=_competition_id(row.scope_key),
        competition_context=CompetitionContext.LEAGUE,
        kickoff_at=row.kickoff_at,
        known_at=row.kickoff_at + timedelta(hours=3),
        home_team_id=row.home_team_id,
        away_team_id=row.away_team_id,
        home_goals=row.home_goals,
        away_goals=row.away_goals,
        home_xg=row.home_npxg,
        away_xg=row.away_npxg,
    )


def _competition_id(scope_key: str) -> UUID:
    return stable_id("pitchapi-development-competition", COMPETITION_PROVIDER_IDS[scope_key])


def _target_ids(root: Path) -> frozenset[UUID]:
    digest = "9d4e581b1295a61fccdc409f1d5e8386650adb68958699afa1558847235548f6"
    path = root / "manifests" / "sha256" / digest[:2] / f"{digest}.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError("development target manifest checksum mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(UUID(str(row["canonical_fixture_id"])) for row in payload["targets"])


def _record(
    output: dict[str, list[ScoredModelForecast]],
    forecast: ModelForecast,
    item: ColdStartDevelopmentObservation,
) -> None:
    output[forecast.model_id].append(
        ScoredModelForecast(
            forecast=forecast,
            kickoff_at=item.snapshot.kickoff_at,
            outcome_known_at=item.snapshot.kickoff_at + timedelta(hours=3),
            home_goals=item.home_goals,
            away_goals=item.away_goals,
            competition_id=str(item.snapshot.competition_id),
            season_label=item.snapshot.season_label,
        )
    )


def _metrics(rows: tuple[ScoredModelForecast, ...]) -> dict[str, object]:
    overall = asdict(evaluate_model_forecasts(rows))
    by_domain = {
        domain: asdict(
            evaluate_model_forecasts(tuple(row for row in rows if row.season_label == domain))
        )
        for domain in sorted({row.season_label for row in rows})
    }
    by_mode = {}
    for mode in sorted(
        {
            row.forecast.lineage.forecast_mode.value
            for row in rows
            if row.forecast.lineage is not None
        }
    ):
        subset = tuple(
            row
            for row in rows
            if row.forecast.lineage is not None and row.forecast.lineage.forecast_mode.value == mode
        )
        by_mode[mode] = asdict(evaluate_model_forecasts(subset))
    return {"overall": overall, "by_domain": by_domain, "by_forecast_mode": by_mode}


def _paired(
    candidate: tuple[ScoredModelForecast, ...], champion: tuple[ScoredModelForecast, ...]
) -> dict[str, object]:
    return {
        "joint_score_log_loss": asdict(
            paired_bootstrap_delta(candidate=candidate, champion=champion)
        ),
        "result_log_loss": asdict(
            paired_bootstrap_delta(
                candidate=candidate,
                champion=champion,
                metric="result_log_loss",
            )
        ),
        "point_deltas": _point_deltas(candidate, champion),
    }


def _point_deltas(
    candidate: tuple[ScoredModelForecast, ...], champion: tuple[ScoredModelForecast, ...]
) -> dict[str, float]:
    champion_by_id = {row.forecast.fixture_id: row for row in champion}
    values: dict[str, list[float]] = defaultdict(list)
    for row in candidate:
        baseline = champion_by_id[row.forecast.fixture_id]
        left = forecast_losses(row)
        right = forecast_losses(baseline)
        for name in (
            "joint_score_log_loss",
            "result_log_loss",
            "multiclass_brier",
            "ranked_probability_score",
            "total_goal_crps",
        ):
            values[name].append(getattr(left, name) - getattr(right, name))
    return {key: sum(items) / len(items) for key, items in values.items()}


def _cold_start_comparisons(
    predictions: dict[str, list[ScoredModelForecast]],
    champion: tuple[ScoredModelForecast, ...],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for model_id, rows in predictions.items():
        if not model_id.endswith("-transferable-v2b"):
            continue
        subset = tuple(
            row
            for row in rows
            if row.forecast.lineage is not None and row.forecast.lineage.cold_start_component_used
        )
        target_ids = {row.forecast.fixture_id for row in subset}
        champion_subset = tuple(row for row in champion if row.forecast.fixture_id in target_ids)
        if subset:
            output[model_id] = _paired(subset, champion_subset)
    return output


def _old_coverage(evidence: dict[str, Any]) -> dict[str, object]:
    results = cast(dict[str, Any], evidence["results"])
    return {
        model_id: {
            "eligible_targets": 712,
            "successful_forecasts": data["target_count"],
            "coverage": data["coverage"],
        }
        for model_id, data in cast(dict[str, dict[str, Any]], results["models"]).items()
    }


def _root_cause_breakdown(evidence: dict[str, Any]) -> dict[str, object]:
    old = _old_coverage(evidence)
    return {
        "verified_code_path": (
            "PenaltyblogGoalModel.predict rejects fixture IDs absent from "
            "runtime_model.teams; ModelRunner records UNSEEN_TEAM and emits no forecast."
        ),
        "missing_targets_per_classic_challenger": 394,
        "breakdown": {
            "competition_absent_from_fitted_artifact": 280,
            "unseen_team_in_supported_competition": 114,
            "promoted_team_confirmed": 0,
            "promotion_status_unknown": 114,
            "insufficient_history": 0,
            "diagnostic_or_model_failure": 0,
            "other": 0,
        },
        "hierarchical_bayes": {
            "missing_targets": 712,
            "reason": "MODEL_FIT_UNAVAILABLE_BAYESIAN_RHAT",
        },
        "old_coverage": old,
    }


def _verify_source(source_commit: str) -> None:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    if source_commit != head:
        raise RuntimeError("source commit must equal current Git HEAD")
    status = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=no"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError("tracked worktree must be clean before development execution")


def _markdown(result: dict[str, object]) -> str:
    selected = cast(dict[str, object], result["selected_cold_start"])
    return "\n".join(
        (
            "# Full-coverage challenger V2 development result",
            "",
            f"Disposition: `{result['disposition']}`",
            "",
            (
                "V2A uses native fitted challenger distributions only when both teams "
                "exist in the V1 artifact; otherwise it uses the entire champion "
                "distribution with explicit lineage."
            ),
            "",
            (
                "V2B uses hierarchical goals-based cold-start strengths for Dixon-Coles "
                "and Negative Binomial. Weibull-Copula fails closed to the whole champion "
                "distribution because no tested stable parameter-substitution adapter exists."
            ),
            "",
            f"Selected shrinkage k: `{selected['shrinkage_k']}`",
            f"Selected L2: `{selected['l2_regularization']}`",
            (
                f"Selected transfer weight: `{result['selected_transfer_weight']}` "
                "(no qualified cross-competition relationship was available)"
            ),
            "",
            (
                "All V2A/V2B and ensemble development-holdout candidates achieved the "
                "required full coverage through native fitted forecasts, native cold start, "
                "or explicit champion fallback."
            ),
            "",
            (
                "No unspent authorized independent evaluation corpus exists. "
                "Production promotion is not justified."
            ),
            "",
            f"Source commit: `{result['source_commit']}`",
            "",
        )
    )


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _json(value: object) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value


if __name__ == "__main__":
    main()
