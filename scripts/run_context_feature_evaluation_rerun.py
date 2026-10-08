"""Execute the authorized Step 5 rerun on the qualified historical context corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from football.context.historical_corpus import canonical_sha256
from football.forecasting.context_research import (
    ContextEvaluationRow,
    RestDevelopmentEvaluation,
    ScoreMetrics,
    evaluate_rest_development,
)
from football.forecasting.contextual_goal import (
    FamilyDisposition,
    FeatureFamily,
    build_contextual_artifact,
)
from football.forecasting.pitchapi_v3 import (
    HistoryObservationV1,
    RollingHistoryV1,
    TransferableForecastContextV1,
    TransferableGoalModelV1,
    TransferableModelError,
    TransferableParametersV1,
)

DATE = "2026-10-08"
RESEARCH_ID = "MATCHFORGE_CONTEXT_FEATURE_EVALUATION_V1"
BASELINE = "transferable-rolling-goals-poisson-v1"
CONTEXT_CORPUS = "MATCHFORGE_HISTORICAL_CONTEXT_CORPUS_V1"
OUTCOME_SOURCE = "openfootball"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repository_root.resolve()
    _verify_source_state(root, args.source_commit)
    inputs = _verify_frozen_inputs(root)
    targets = inputs["targets"]
    snapshots = inputs["snapshots"]
    forbidden_ids = {
        UUID(str(value))
        for value in cast(list[str], inputs["firewall"]["unique_forbidden_target_ids"])
    }
    with psycopg.connect(args.database_url) as connection:
        rows = _replay_baseline(connection, targets, snapshots, forbidden_ids, root)
    evaluation = evaluate_rest_development(rows)
    _write_outputs(root, args.source_commit, rows, evaluation, inputs)
    return 0


def _verify_source_state(root: Path, source_commit: str) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != source_commit:
        raise RuntimeError("source commit does not match HEAD")
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status:
        raise RuntimeError("context evaluation requires a clean worktree")


def _verify_frozen_inputs(root: Path) -> dict[str, Any]:
    evaluation = root / "docs/evaluation"
    manifest_path = evaluation / "matchforge-historical-context-corpus-v1-manifest.json"
    rest_path = evaluation / "matchforge-rest-context-corpus-v1-manifest.json"
    firewall_path = evaluation / "full-coverage-challengers-v2-spent-targets-v1.json"
    target_path = evaluation / "matchforge-historical-context-corpus-v1-targets.jsonl"
    snapshot_path = evaluation / "matchforge-historical-context-snapshots-v1.jsonl"
    manifest = _json(manifest_path)
    rest = _json(rest_path)
    firewall = _json(firewall_path)
    if manifest.get("corpus_id") != CONTEXT_CORPUS or not manifest.get(
        "target_manifest_outcome_blind"
    ):
        raise RuntimeError("historical context corpus contract is not authorized")
    if rest.get("family") != "REST" or rest.get("status") != "QUALIFIED":
        raise RuntimeError("rest context corpus is not qualified")
    _verify_semantic_manifest(manifest)
    _verify_semantic_manifest(rest)
    if _sha256(target_path) != cast(dict[str, str], manifest["target_manifest"])["sha256"]:
        raise RuntimeError("historical target manifest checksum mismatch")
    if (
        _sha256(snapshot_path)
        != cast(dict[str, str], manifest["historical_context_snapshots"])["sha256"]
    ):
        raise RuntimeError("historical context snapshot file checksum mismatch")
    targets, snapshots = _verify_corpus_rows(manifest, rest, firewall, target_path, snapshot_path)
    return {
        "manifest_path": manifest_path,
        "manifest": manifest,
        "rest_path": rest_path,
        "rest": rest,
        "firewall_path": firewall_path,
        "firewall": firewall,
        "target_path": target_path,
        "snapshot_path": snapshot_path,
        "targets": targets,
        "snapshots": snapshots,
    }


def _verify_corpus_rows(
    manifest: dict[str, Any],
    rest: dict[str, Any],
    firewall: dict[str, Any],
    target_path: Path,
    snapshot_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    targets = _jsonl(target_path)
    snapshots = _jsonl(snapshot_path)
    if len(targets) != manifest["target_count"] or len(snapshots) != manifest["target_count"]:
        raise RuntimeError("historical context corpus count mismatch")
    forbidden_fields = {"home_goals", "away_goals", "result", "score", "outcome"}
    if any(forbidden_fields & row.keys() for row in targets):
        raise RuntimeError("phase A target manifest contains outcome fields")
    for snapshot in snapshots:
        semantic = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
        if canonical_sha256(semantic) != snapshot["snapshot_sha256"]:
            raise RuntimeError("historical context snapshot semantic checksum mismatch")
    target_ids = {UUID(str(row["fixture_id"])) for row in targets}
    rest_ids = {UUID(str(value)) for value in cast(list[str], rest["target_ids"])}
    forbidden_ids = {
        UUID(str(value)) for value in cast(list[str], firewall["unique_forbidden_target_ids"])
    }
    if target_ids != rest_ids or target_ids & forbidden_ids:
        raise RuntimeError("rest target set violates the frozen target firewall")
    if (
        canonical_sha256([row["snapshot_sha256"] for row in snapshots])
        != manifest["context_snapshot_sha256"]
    ):
        raise RuntimeError("historical context snapshot aggregate checksum mismatch")
    return targets, snapshots


def _replay_baseline(
    connection: Any,
    targets: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    forbidden_ids: set[UUID],
    root: Path,
) -> tuple[ContextEvaluationRow, ...]:
    target_by_id = {UUID(str(row["fixture_id"])): row for row in targets}
    snapshot_by_id = {UUID(str(row["fixture_id"])): row for row in snapshots}
    team_ids = tuple(
        sorted(
            {UUID(str(row[side])) for row in targets for side in ("home_team", "away_team")},
            key=str,
        )
    )
    maximum_kickoff = max(datetime.fromisoformat(str(row["kickoff"])) for row in targets)
    history = _load_history(connection, team_ids, forbidden_ids, maximum_kickoff)
    artifact_path = root / "docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json"
    artifact = _json(artifact_path)
    if artifact.get("algorithm_version") != BASELINE:
        raise RuntimeError("official production champion artifact mismatch")
    model = TransferableGoalModelV1(
        TransferableParametersV1(**cast(dict[str, float], artifact["parameters"]))
    )
    state = RollingHistoryV1()
    results: list[ContextEvaluationRow] = []
    grouped: dict[datetime, list[HistoryObservationV1]] = defaultdict(list)
    for row in history:
        grouped[row.kickoff_at].append(row)
    for kickoff in sorted(grouped):
        batch = tuple(sorted(grouped[kickoff], key=lambda row: str(row.match_id)))
        for observation in batch:
            target = target_by_id.get(observation.match_id)
            if target is None:
                continue
            _verify_target_history_alignment(target, observation)
            try:
                forecast = model.forecast(
                    TransferableForecastContextV1(
                        observation.match_id,
                        str(target["competition"]),
                        observation.kickoff_at,
                        observation.home_team_id,
                        observation.away_team_id,
                    ),
                    state,
                )
            except TransferableModelError as error:
                if "10 prior appearances" not in str(error):
                    raise
                continue
            results.append(
                ContextEvaluationRow(
                    observation.match_id,
                    observation.kickoff_at,
                    str(target["competition"]),
                    forecast.lambda_home,
                    forecast.lambda_away,
                    observation.home_goals,
                    observation.away_goals,
                    _rest_values(snapshot_by_id[observation.match_id]),
                )
            )
        state.update_batch(batch)
    found = {row.fixture_id for row in results}
    missing_history = set(target_by_id) - {row.match_id for row in history}
    if missing_history:
        raise RuntimeError(f"qualified targets missing retained outcomes: {len(missing_history)}")
    if len(found) != len(results):
        raise RuntimeError("baseline replay emitted duplicate targets")
    return tuple(sorted(results, key=lambda row: (row.kickoff_at, str(row.fixture_id))))


def _load_history(
    connection: Any,
    team_ids: tuple[UUID, ...],
    forbidden_ids: set[UUID],
    maximum_kickoff: datetime,
) -> tuple[HistoryObservationV1, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT fixture_id, kickoff_at, home_team_id, away_team_id,
                   home_goals, away_goals
            FROM football.product_team_match_history
            WHERE source_provider_code = %s
              AND kickoff_at <= %s
              AND (home_team_id = ANY(%s) OR away_team_id = ANY(%s))
              AND NOT (fixture_id = ANY(%s))
            ORDER BY kickoff_at, fixture_id
            """,
            (
                OUTCOME_SOURCE,
                maximum_kickoff,
                list(team_ids),
                list(team_ids),
                list(forbidden_ids),
            ),
        )
        raw = list(cursor.fetchall())
    seen: set[UUID] = set()
    rows: list[HistoryObservationV1] = []
    for fixture_id, kickoff, home, away, home_goals, away_goals in raw:
        if fixture_id in seen:
            raise RuntimeError("retained history contains duplicate source fixture")
        seen.add(fixture_id)
        rows.append(
            HistoryObservationV1(
                fixture_id,
                kickoff,
                home,
                away,
                int(home_goals),
                int(away_goals),
                0.0,
                0.0,
            )
        )
    return tuple(rows)


def _verify_target_history_alignment(
    target: dict[str, Any], observation: HistoryObservationV1
) -> None:
    expected = (
        datetime.fromisoformat(str(target["kickoff"])),
        UUID(str(target["home_team"])),
        UUID(str(target["away_team"])),
    )
    actual = (observation.kickoff_at, observation.home_team_id, observation.away_team_id)
    if expected != actual:
        raise RuntimeError("retained outcome does not match frozen target identity")


def _rest_values(snapshot: dict[str, Any]) -> dict[str, float | None]:
    context = cast(dict[str, dict[str, float | None]], snapshot["rest_context"])
    home = context["home"]
    away = context["away"]
    values: dict[str, float | None] = {}
    for name in (
        "days_since_last_match",
        "matches_last_3_days",
        "matches_last_7_days",
        "matches_last_14_days",
        "matches_last_30_days",
        "days_to_next_match",
    ):
        home_value = home.get(name)
        away_value = away.get(name)
        values[f"home_{name}"] = home_value
        values[f"away_{name}"] = away_value
        values[f"{name}_difference"] = (
            home_value - away_value if home_value is not None and away_value is not None else None
        )
    return values


def _write_outputs(
    root: Path,
    source_commit: str,
    rows: tuple[ContextEvaluationRow, ...],
    evaluation: RestDevelopmentEvaluation,
    inputs: dict[str, Any],
) -> None:
    evaluation_root = root / "docs/evaluation"
    evidence_root = root / "docs/evidence"
    config_path = evaluation_root / "matchforge-context-feature-evaluation-v1-preregistration.json"
    dataset_path = (
        evaluation_root / "matchforge-context-feature-evaluation-v1-rerun-dataset-manifest.json"
    )
    artifact_path = evaluation_root / "matchforge-contextual-goal-model-v1-rerun-artifact.json"
    evidence_path = evidence_root / f"matchforge-context-feature-evaluation-v1-rerun-{DATE}.json"
    report_path = evidence_root / f"matchforge-context-feature-evaluation-v1-rerun-{DATE}.md"
    configuration_sha = _sha256(config_path)
    dataset_sha = canonical_sha256([_row_payload(row) for row in rows])
    dataset = _dataset_manifest(source_commit, rows, evaluation, inputs, dataset_sha)
    _write_json(dataset_path, dataset)
    family_results = {
        FeatureFamily.AVAILABILITY_LINEUP: FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE,
        FeatureFamily.REST_CONGESTION: evaluation.holdout_result.disposition,
        FeatureFamily.MANAGER: FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE,
        FeatureFamily.TRAVEL: FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE,
    }
    accepted = evaluation.holdout_result.disposition is FamilyDisposition.DEVELOPMENT_ACCEPTED
    fitted = evaluation.coefficients if accepted else ()
    logical = build_contextual_artifact(
        baseline_model=BASELINE,
        family_results=family_results,
        fitted=fitted,
        training_cutoff=evaluation.training_cutoff,
        dataset_sha256=dataset_sha,
        configuration_sha256=configuration_sha,
        source_commit=source_commit,
    )
    artifact = _artifact_payload(logical, evaluation, root)
    _write_json(artifact_path, artifact)
    evidence = _evidence_payload(
        source_commit,
        rows,
        evaluation,
        dataset_path,
        dataset_sha,
        artifact_path,
        config_path,
    )
    _write_json(evidence_path, evidence)
    report_path.write_text(_report(evidence, evaluation), encoding="utf-8")


def _dataset_manifest(
    source_commit: str,
    rows: tuple[ContextEvaluationRow, ...],
    evaluation: RestDevelopmentEvaluation,
    inputs: dict[str, Any],
    dataset_sha: str,
) -> dict[str, Any]:
    return {
        "authorized_development_corpus": CONTEXT_CORPUS,
        "baseline_eligible_targets": len(rows),
        "baseline_unforecastable_targets": len(inputs["targets"]) - len(rows),
        "context_snapshot_file_sha256": _sha256(inputs["snapshot_path"]),
        "contract": "MatchForgeContextFeatureEvaluationRerunDatasetManifestV1",
        "created_at": f"{DATE}T00:00:00Z",
        "dataset_sha256": dataset_sha,
        "excluded_corpora": [
            "SPENT_PITCHAPI_V5",
            "SPENT_MULTIMODEL_712",
            "OTHER_PROTECTED_OR_SPENT_TARGETS",
        ],
        "firewall_manifest_sha256": _sha256(inputs["firewall_path"]),
        "historical_context_manifest_sha256": _sha256(inputs["manifest_path"]),
        "outcome_source": OUTCOME_SOURCE,
        "partitions": {partition.value: count for partition, count in evaluation.partition_counts},
        "protected_outcomes_loaded": False,
        "qualified_context_targets": len(rows),
        "research_id": RESEARCH_ID,
        "rest_context_manifest_sha256": _sha256(inputs["rest_path"]),
        "source_commit": source_commit,
        "target_manifest_file_sha256": _sha256(inputs["target_path"]),
    }


def _artifact_payload(
    logical: Any, evaluation: RestDevelopmentEvaluation, root: Path
) -> dict[str, Any]:
    return {
        "algorithm_version": "contextual-goal-adjustment-v1",
        "artifact_schema_version": "MatchForgeContextualGoalArtifactV1",
        "baseline_model": logical.baseline_model,
        "coefficients": [
            {
                "away_coefficient": item.away_coefficient,
                "feature_name": item.feature_name,
                "home_coefficient": item.home_coefficient,
            }
            for item in logical.coefficients
        ],
        "configuration_sha256": logical.configuration_sha256,
        "dataset_sha256": logical.dataset_sha256,
        "dependency_lock_sha256": _sha256(root / "uv.lock"),
        "excluded_feature_families": [item.value for item in logical.excluded_families],
        "family_results": {family.value: result.value for family, result in logical.family_results},
        "included_feature_families": [item.value for item in logical.included_families],
        "logical_model_state_sha256": logical.artifact_sha256,
        "missingness_rule": logical.missingness_rule,
        "model_id": logical.model_id,
        "regularization": {"selected_l2": evaluation.selected_l2, "type": "L2"},
        "runtime_compatibility": "ContextualGoalAdjustmentV1",
        "scaler_parameters": [
            {"feature_name": item.feature_name, "mean": item.mean, "scale": item.scale}
            for item in logical.coefficients
        ],
        "source_commit": logical.source_commit,
        "status": (
            "DEVELOPMENT_ACCEPTED_AWAITING_INDEPENDENT_EVALUATION"
            if logical.included_families
            else "NEUTRAL_NO_ACCEPTED_FAMILIES"
        ),
        "training_cutoff": logical.training_cutoff.isoformat(),
    }


def _evidence_payload(
    source_commit: str,
    rows: tuple[ContextEvaluationRow, ...],
    evaluation: RestDevelopmentEvaluation,
    dataset_path: Path,
    dataset_sha: str,
    artifact_path: Path,
    config_path: Path,
) -> dict[str, Any]:
    baseline_count = len(rows)
    accepted = evaluation.holdout_result.disposition is FamilyDisposition.DEVELOPMENT_ACCEPTED
    unavailable: dict[str, Any] = {
        "calibration": None,
        "context_qualified_targets": 0,
        "coverage": 0.0,
        "domain_results": [],
        "forecasted_targets": baseline_count,
        "metrics": None,
        "missing_context_targets": baseline_count,
        "sample_count": 0,
    }
    metrics = {name: asdict(value) for name, value in evaluation.holdout_result.metrics}
    final_metrics = evaluation.candidate_metrics if accepted else evaluation.baseline_metrics
    return {
        "candidate_artifact_ref": str(artifact_path.relative_to(artifact_path.parents[2])),
        "candidate_artifact_sha256": _sha256(artifact_path),
        "configuration_ref": str(config_path.relative_to(config_path.parents[2])),
        "configuration_sha256": _sha256(config_path),
        "contract": "MatchForgeContextFeatureEvaluationRerunResultV1",
        "dataset_manifest_ref": str(dataset_path.relative_to(dataset_path.parents[2])),
        "dataset_manifest_sha256": _sha256(dataset_path),
        "development_dataset_sha256": dataset_sha,
        "family_results": {
            "availability_lineup": {
                **unavailable,
                "disposition": FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE.value,
                "reason": "No historical availability or lineup observations are qualified.",
            },
            "h2h": _h2h_result(),
            "manager": {
                **unavailable,
                "disposition": FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE.value,
                "reason": (
                    "Zero qualified coach observations; minimum is 300 targets, three "
                    "domains, and 70 percent coverage."
                ),
            },
            "rest_congestion": {
                "baseline_eligible_targets": baseline_count,
                "baseline_metrics": _metrics_payload(evaluation.baseline_metrics),
                "calibration": _calibration_payload(evaluation.candidate_metrics),
                "candidate_metrics": _metrics_payload(evaluation.candidate_metrics),
                "context_qualified_targets": baseline_count,
                "coverage": 1.0,
                "disposition": evaluation.holdout_result.disposition.value,
                "domain_results": [
                    {
                        "baseline": _metrics_payload(item.baseline),
                        "candidate": _metrics_payload(item.candidate),
                        "domain": item.domain,
                        "joint_log_loss_delta": item.joint_log_loss_delta,
                    }
                    for item in evaluation.domain_results
                ],
                "forecasted_targets": baseline_count,
                "metrics": metrics,
                "missing_context_targets": 0,
                "sample_count": evaluation.candidate_metrics.sample_count,
                "selected_l2": evaluation.selected_l2,
                "validation_joint_log_loss": dict(evaluation.validation_joint_log_loss),
            },
            "travel": {
                **unavailable,
                "disposition": FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE.value,
                "reason": (
                    "No qualified venue-coordinate corpus; minimum is 500 targets, three "
                    "domains, and 80 percent coverage."
                ),
            },
        },
        "final_development_metrics": _metrics_payload(final_metrics),
        "final_disposition": (
            "DEVELOPMENT_ACCEPTED_AWAITING_INDEPENDENT_EVALUATION"
            if accepted
            else "DEVELOPMENT_COMPLETE_NO_ACCEPTED_CONTEXT_FAMILIES"
        ),
        "final_included_feature_families": (["REST_CONGESTION"] if accepted else []),
        "implementation_source_commit": source_commit,
        "independent_evaluation_available": False,
        "lineup_predictor": _lineup_report(),
        "production_baseline": BASELINE,
        "production_champion_changed": False,
        "production_promotion_justified": False,
        "protected_outcomes_loaded": False,
        "research_id": RESEARCH_ID,
    }


def _h2h_result() -> dict[str, Any]:
    return {
        "coverage": 0.3771653543307087,
        "disposition": FamilyDisposition.DEVELOPMENT_REJECTED.value,
        "eligible_targets": 479,
        "metrics": {
            "brier_delta": 0.00004335812050469374,
            "crps_delta": 0.00001722140154184461,
            "joint_log_loss_delta": 0.00009958598319782521,
            "joint_log_loss_delta_95_interval": [
                -1.0761151504806502e-7,
                0.00020443573841225147,
            ],
            "one_x_two_log_loss_delta": 0.00007391501922673853,
            "rps_delta": 0.00002292002082695791,
        },
        "report_ref": "docs/evidence/matchforge-h2h-incremental-signal-research-v1-2026-10-07.json",
        "sample_count": 379,
    }


def _lineup_report() -> dict[str, Any]:
    return {
        "coverage_by_confidence": {"HIGH": 0, "LOW": 0, "MEDIUM": 0},
        "exact_position_replacement_accuracy": None,
        "exact_xi_rate": None,
        "formation_accuracy": None,
        "injury_replacement_accuracy": None,
        "mean_correct_starters": None,
        "median_correct_starters": None,
        "naive_mean_correct_starters": None,
        "naive_replacement_accuracy": None,
        "prediction_coverage": 0.0,
        "sample_count": 0,
        "status": FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE.value,
        "suspension_replacement_accuracy": None,
    }


def _metrics_payload(metrics: ScoreMetrics) -> dict[str, Any]:
    return {
        "brier": metrics.brier,
        "calibration": _calibration_payload(metrics),
        "crps": metrics.crps,
        "joint_log_loss": metrics.joint_log_loss,
        "one_x_two_log_loss": metrics.one_x_two_log_loss,
        "rps": metrics.rps,
        "sample_count": metrics.sample_count,
    }


def _calibration_payload(metrics: ScoreMetrics) -> list[dict[str, Any]]:
    return [
        {"intercept": intercept, "outcome": outcome, "slope": slope}
        for outcome, intercept, slope in metrics.calibration
    ]


def _report(evidence: dict[str, Any], evaluation: RestDevelopmentEvaluation) -> str:
    rest = cast(dict[str, Any], cast(dict[str, Any], evidence["family_results"])["rest_congestion"])
    included = cast(list[str], evidence["final_included_feature_families"])
    coverage = evaluation.holdout_result.coverage.baseline_eligible_targets
    joint = dict(evaluation.holdout_result.metrics)["joint_log_loss"]
    lines = [
        "# MatchForge governed context feature evaluation V1 rerun",
        "",
        f"Status: `{evidence['final_disposition']}`",
        "",
        f"Production baseline: `{BASELINE}`. Production champion changed: **NO**.",
        "The qualified rest corpus was evaluated under the frozen 60/20/20 protocol.",
        "Protected and spent target outcomes were not loaded.",
        "",
        "## Family results",
        "",
        "- H2H: `DEVELOPMENT_REJECTED` (reused immutable Step 3 result).",
        "- Availability/lineup: `INSUFFICIENT_QUALIFIED_COVERAGE`.",
        f"- Rest/congestion: `{rest['disposition']}`.",
        "- Manager: `INSUFFICIENT_QUALIFIED_COVERAGE`.",
        "- Travel: `INSUFFICIENT_QUALIFIED_COVERAGE`.",
        "",
        "## Rest development result",
        "",
        f"- Baseline-eligible and context-qualified targets: `{coverage}`",
        f"- TRAIN / VALIDATION / HOLDOUT: `{dict(evaluation.partition_counts)}`",
        f"- Selected L2: `{evaluation.selected_l2}`",
        f"- Joint LL delta: `{joint.point}`",
        f"- Joint LL paired 95% interval: `{joint.confidence_interval_95}`",
        f"- Included feature families: `{included}`",
        "",
        "No independent authorized evaluation corpus exists. Production promotion is not",
        "justified. Accepted development context, if any, remains inactive in production",
        "`predictive_input_snapshot_sha256` until separately authorized.",
    ]
    return "\n".join(lines) + "\n"


def _row_payload(row: ContextEvaluationRow) -> dict[str, Any]:
    return {
        "away_goals": row.away_goals,
        "baseline_away_rate": row.baseline_away_rate,
        "baseline_home_rate": row.baseline_home_rate,
        "competition": row.competition,
        "fixture_id": str(row.fixture_id),
        "home_goals": row.home_goals,
        "kickoff_at": row.kickoff_at.isoformat(),
        "values": row.values,
    }


def _verify_semantic_manifest(payload: dict[str, Any]) -> None:
    expected = payload.get("manifest_sha256")
    actual = canonical_sha256(
        {key: value for key, value in payload.items() if not key.endswith("sha256")}
    )
    if expected != actual:
        raise RuntimeError("semantic manifest checksum mismatch")


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if any(not isinstance(value, dict) for value in values):
        raise RuntimeError(f"{path} must contain JSON objects")
    return cast(list[dict[str, Any]], values)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
