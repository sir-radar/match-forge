#!/usr/bin/env python3
"""Execute the frozen V1.2 replacement holdout exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import numpy as np
import psycopg
from football.forecasting.champion_adapter import TransferableRollingGoalsChampion
from football.forecasting.model_contracts import (
    CompetitionContext,
    FittedModelArtifact,
    ForecastInputSnapshot,
    ForecastMode,
    HistoricalMatch,
    ModelForecast,
    ModelStatus,
    derive_markets,
    distributions,
)
from football.forecasting.multi_model_evaluation import (
    ForecastLosses,
    ScoredModelForecast,
    evaluate_model_forecasts,
    forecast_losses,
)
from football.forecasting.replacement_holdout import (
    COMPETITION_PRIOR_K,
    COMPETITION_PRIOR_MODEL_ID,
    REFERENCE_STACK_ID,
    ChampionEligibility,
    CompetitionPriorMatch,
    CompetitionPriorPoissonV1,
)
from football.forecasting.snapshot import build_forecast_snapshot
from psycopg.rows import dict_row

from scripts.prepare_full_coverage_v2_replacement_holdout import (
    CONFIG,
    EXECUTION_STATE,
    OLD_CONFIG,
    OWNER_DECISION,
    PREREGISTRATION,
    PROTOCOL_ID,
    REFERENCE_CONFIG,
    REPLACEMENT_MANIFEST_ID,
    ROOT,
    TARGET_MANIFEST,
    _scientific_source_files,
    _scientific_source_sha,
)
from scripts.run_full_coverage_v2_reevaluation import build_runtime

DATE = "2026-10-09"
RESULT = ROOT / f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-2-{DATE}.json"
REPORT = ROOT / f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-2-{DATE}.md"
RECEIPT = ROOT / (
    f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-2-receipt-{DATE}.json"
)
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
    home_prior_match_count: int
    away_prior_match_count: int
    champion_eligibility: str
    champion_ineligibility_reason: str | None
    home_promoted: bool | None
    away_promoted: bool | None
    expected_route: str
    reference_model_id: str
    reference_mode: str


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    target: FrozenTarget
    snapshot: ForecastInputSnapshot
    competition_history: tuple[CompetitionPriorMatch, ...]
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
    preregistration = _json(root / PREREGISTRATION.relative_to(ROOT))
    config = _json(root / CONFIG.relative_to(ROOT))
    old_config = _json(root / OLD_CONFIG.relative_to(ROOT))
    reference = _json(root / REFERENCE_CONFIG.relative_to(ROOT))
    receipt = _preflight(root, preregistration, config, old_config, reference)
    runtime = build_runtime(old_config, root)
    expected_artifacts = cast(dict[str, str], config["frozen_v2_candidate_artifact_sha256"])
    if runtime["artifact_shas"] != expected_artifacts:
        raise RuntimeError("FAIL_CLOSED_FROZEN_CANDIDATE_MISMATCH")
    _consume(root / EXECUTION_STATE.relative_to(ROOT))
    observations = _load_observations(database_url, root / TARGET_MANIFEST.relative_to(ROOT))
    result = _evaluate(observations, runtime, old_config, reference, receipt)
    _write(root / RESULT.relative_to(ROOT), result)
    _write(
        root / RECEIPT.relative_to(ROOT),
        {
            **receipt,
            "contract": "MatchForgeV2ReplacementExecutionReceiptV1",
            "protocol_id": PROTOCOL_ID,
            "outcomes_loaded": True,
            "logical_executions": 1,
        },
    )
    (root / REPORT.relative_to(ROOT)).write_text(_markdown(result), encoding="utf-8")
    _update_project_status(root, result)
    return result


def _preflight(
    root: Path,
    preregistration: Mapping[str, object],
    config: Mapping[str, object],
    old_config: Mapping[str, object],
    reference: Mapping[str, object],
) -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.check_output(("git", *args), cwd=root, text=True).strip()

    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD^")
    status = git("status", "--porcelain")
    changed = sorted(filter(None, git("diff", "--name-only", "HEAD^", "HEAD").splitlines()))
    if status:
        raise RuntimeError("execution requires a clean worktree")
    if (
        parent != preregistration["source_commit"]
        or parent != preregistration["required_execution_parent"]
    ):
        raise RuntimeError("execution commit parent does not match SOURCE_COMMIT")
    allowed = sorted(cast(list[str], preregistration["execution_commit_allowed_files"]))
    if not changed or any(path not in allowed for path in changed):
        raise RuntimeError("FAIL_CLOSED_EXECUTION_COMMIT_SOURCE_MUTATION")
    source_files = _scientific_source_files(root)
    source_sha = _scientific_source_sha(root, source_files)
    if (
        list(source_files) != preregistration["scientific_source_files"]
        or source_sha != preregistration["scientific_source_sha256"]
    ):
        raise RuntimeError("scientific source hash mismatch")
    _verify_frozen_files(root, preregistration)
    _verify_frozen_manifests(root, preregistration, old_config, reference)
    state = _json(root / str(preregistration["execution_state_ref"]))
    if state != {"logical_executions": 0, "outcomes_loaded": False, "protocol_id": PROTOCOL_ID}:
        raise RuntimeError("replacement holdout already consumed")
    return {
        "source_commit": parent,
        "execution_commit": head,
        "execution_parent_matches_source": True,
        "execution_commit_changed_files": changed,
        "scientific_source_sha256": source_sha,
        "target_manifest_sha256": preregistration["target_manifest_sha256"],
        "firewall_overlap": 0,
        "preflight": "PASS",
    }


def _verify_frozen_files(root: Path, preregistration: Mapping[str, object]) -> None:
    pairs = (
        ("owner_decision_ref", "owner_decision_sha256"),
        ("configuration_ref", "configuration_sha256"),
        ("target_manifest_ref", "target_manifest_file_sha256"),
        ("firewall_ref", "firewall_file_sha256"),
        ("reference_artifact_ref", "reference_artifact_file_sha256"),
        ("frozen_v2_configuration_ref", "frozen_v2_configuration_file_sha256"),
    )
    for ref_key, sha_key in pairs:
        if _file_sha(root / str(preregistration[ref_key])) != preregistration[sha_key]:
            raise RuntimeError(f"{sha_key} mismatch")


def _verify_frozen_manifests(
    root: Path,
    preregistration: Mapping[str, object],
    old_config: Mapping[str, object],
    reference: Mapping[str, object],
) -> None:
    manifest = _json(root / str(preregistration["target_manifest_ref"]))
    targets = cast(list[dict[str, object]], manifest["targets"])
    if (
        manifest.get("manifest_id") != REPLACEMENT_MANIFEST_ID
        or _semantic_sha(targets) != preregistration["target_manifest_sha256"]
    ):
        raise RuntimeError("replacement target manifest mismatch")
    firewall = _json(root / str(preregistration["firewall_ref"]))
    forbidden = set(cast(list[str], firewall["unique_forbidden_target_ids"]))
    if {str(row["fixture_id"]) for row in targets} & forbidden:
        raise RuntimeError("FAIL_CLOSED_SPENT_OR_PROTECTED_INTERSECTION")
    if _semantic_sha(firewall) != preregistration["firewall_sha256"]:
        raise RuntimeError("global firewall mismatch")
    if reference["artifact_sha256"] != preregistration["reference_artifact_sha256"]:
        raise RuntimeError("reference artifact mismatch")
    actual_artifacts = {
        key: value["artifact_sha256"]
        for key, value in cast(
            dict[str, dict[str, object]], old_config["candidate_artifacts"]
        ).items()
    }
    if actual_artifacts != preregistration["frozen_v2_candidate_artifact_sha256"]:
        raise RuntimeError("FAIL_CLOSED_FROZEN_CANDIDATE_MISMATCH")


def _consume(path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {"logical_executions": 1, "outcomes_loaded": True, "protocol_id": PROTOCOL_ID},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    os.replace(temporary, path)


def _load_observations(database_url: str, path: Path) -> tuple[EvaluationObservation, ...]:
    manifest = _json(path)
    targets = tuple(_target(row) for row in cast(list[dict[str, object]], manifest["targets"]))
    target_ids = {row.fixture_id for row in targets}
    competition_ids = sorted({row.competition_id for row in targets}, key=str)
    team_ids = sorted(
        {team for row in targets for team in (row.home_team_id, row.away_team_id)}, key=str
    )
    maximum = max(row.kickoff_at for row in targets)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT fixture_id, kickoff_at, competition_id, home_team_id, away_team_id,
                   home_goals, away_goals, home_xg, away_xg,
                   source_provider_code, source_snapshot_id
              FROM football.product_team_match_history
             WHERE kickoff_at <= %s
               AND (
                    competition_id = ANY(%s::uuid[])
                    OR home_team_id = ANY(%s::uuid[])
                    OR away_team_id = ANY(%s::uuid[])
               )
             ORDER BY kickoff_at, fixture_id
            """,
            (maximum, competition_ids, team_ids, team_ids),
        ).fetchall()
    outcome_by_id = {
        cast(UUID, row["fixture_id"]): row for row in rows if row["fixture_id"] in target_ids
    }
    if outcome_by_id.keys() != target_ids:
        raise RuntimeError("replacement target outcomes are incomplete")
    history = tuple(_historical(row) for row in rows)
    competition_history = tuple(
        CompetitionPriorMatch(
            competition_id=cast(UUID, row["competition_id"]),
            kickoff_at=cast(datetime, row["kickoff_at"]),
            home_goals=int(cast(int, row["home_goals"])),
            away_goals=int(cast(int, row["away_goals"])),
        )
        for row in rows
    )
    output: list[EvaluationObservation] = []
    for target in targets:
        eligible_history = tuple(
            row
            for row in history
            if row.kickoff_at < target.kickoff_at and row.fixture_id not in target_ids
        )
        # Earlier replacement targets are legitimate prior observations; same-kickoff
        # targets remain sealed by the strict comparison.
        eligible_history += tuple(
            row
            for row in history
            if row.kickoff_at < target.kickoff_at and row.fixture_id in target_ids
        )
        eligible_history = tuple(
            sorted(
                {row.fixture_id: row for row in eligible_history}.values(),
                key=lambda row: (row.kickoff_at, str(row.fixture_id)),
            )
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
            knowledge_mode="RETROSPECTIVE_SOURCE_SNAPSHOT",
            history=eligible_history,
            source_references=(f"replacement-target:{target.fixture_id}",),
            home_promoted=target.home_promoted,
            away_promoted=target.away_promoted,
        )
        home_count = sum(
            target.home_team_id in (row.home_team_id, row.away_team_id)
            for row in snapshot.qualified_history
        )
        away_count = sum(
            target.away_team_id in (row.home_team_id, row.away_team_id)
            for row in snapshot.qualified_history
        )
        if (home_count, away_count) != (
            target.home_prior_match_count,
            target.away_prior_match_count,
        ):
            raise RuntimeError("frozen champion eligibility history count mismatch")
        outcome = outcome_by_id[target.fixture_id]
        output.append(
            EvaluationObservation(
                target,
                snapshot,
                competition_history,
                int(cast(int, outcome["home_goals"])),
                int(cast(int, outcome["away_goals"])),
            )
        )
    return tuple(output)


def _evaluate(
    observations: tuple[EvaluationObservation, ...],
    runtime: Mapping[str, Any],
    old_config: Mapping[str, object],
    reference_artifact: Mapping[str, object],
    receipt: Mapping[str, object],
) -> dict[str, object]:
    champion_model = cast(TransferableRollingGoalsChampion, runtime["champion_model"])
    champion_artifact = cast(FittedModelArtifact, runtime["champion_artifact"])
    v2a_models = runtime["v2a_models"]
    v2b_models = runtime["v2b_models"]
    v2a_artifacts = runtime["v2a_artifacts"]
    v2b_artifacts = runtime["v2b_artifacts"]
    prior_model = CompetitionPriorPoissonV1(
        _number(reference_artifact["global_home_rate"]),
        _number(reference_artifact["global_away_rate"]),
    )
    predictions, references, champion_rows, v2a_predictions, routes = _forecast_all(
        observations,
        champion_model,
        champion_artifact,
        v2a_models,
        v2a_artifacts,
        v2b_models,
        v2b_artifacts,
        prior_model,
        reference_artifact,
    )
    reference_rows = tuple(references)
    reference_by_id = {row.forecast.fixture_id: row for row in reference_rows}
    champion_by_id = {row.forecast.fixture_id: row for row in champion_rows}
    eligible_ids = frozenset(champion_by_id)
    ineligible_ids = frozenset(reference_by_id) - eligible_ids
    targets = {item.target.fixture_id: item.target for item in observations}

    strata_a: dict[str, object] = {}
    strata_b: dict[str, object] = {}
    overall: dict[str, object] = {}
    domains: dict[str, object] = {}
    low_history: dict[str, object] = {}
    promoted: dict[str, object] = {}
    decisions: dict[str, str] = {}
    for model_id, rows in predictions.items():
        candidate = tuple(rows)
        if len(candidate) != len(observations):
            raise RuntimeError("IMPLEMENTATION_FAILURE: V2B target silently dropped")
        by_id = {row.forecast.fixture_id: row for row in candidate}
        a = tuple(by_id[key] for key in eligible_ids)
        b = tuple(by_id[key] for key in ineligible_ids)
        a_ref = tuple(champion_by_id[key] for key in eligible_ids)
        b_ref = tuple(reference_by_id[key] for key in ineligible_ids)
        strata_a[model_id] = _paired_payload(a, a_ref)
        strata_b[model_id] = _paired_payload(b, b_ref)
        overall[model_id] = _paired_payload(candidate, reference_rows)
        domains[model_id] = _group_results(
            candidate, reference_by_id, lambda target: target.competition_name, targets
        )
        low_history[model_id] = _group_results(candidate, reference_by_id, _history_bucket, targets)
        promoted_ids = {
            key for key, target in targets.items() if target.home_promoted or target.away_promoted
        }
        promoted[model_id] = (
            _paired_payload(
                tuple(by_id[key] for key in promoted_ids),
                tuple(reference_by_id[key] for key in promoted_ids),
            )
            if promoted_ids
            else {"target_count": 0, "status": "DESCRIPTIVE_ONLY"}
        )
        decisions[model_id] = _candidate_decision(
            cast(dict[str, object], strata_a[model_id]),
            cast(dict[str, object], strata_b[model_id]),
            cast(dict[str, object], overall[model_id]),
            cast(dict[str, object], domains[model_id]),
            routes[model_id],
            len(candidate),
            len(observations),
            len(ineligible_ids) >= 50,
        )

    accepted = [
        model_id
        for model_id, decision in decisions.items()
        if decision == "DEVELOPMENT_ACCEPTED_FOR_INDEPENDENT_EVALUATION"
    ]
    winner = min(
        accepted,
        key=lambda model_id: cast(dict[str, Any], overall[model_id])["candidate_metrics"][
            "joint_score_log_loss"
        ],
        default=None,
    )
    if accepted:
        disposition = "DEVELOPMENT_ACCEPTED_FOR_INDEPENDENT_EVALUATION"
    elif any(value == "DEVELOPMENT_PARTIAL_SUCCESS" for value in decisions.values()):
        disposition = "DEVELOPMENT_PARTIAL_SUCCESS"
    else:
        disposition = "DEVELOPMENT_REJECTED"

    v2a_report = {
        model_id: _v2a_report(tuple(rows), tuple(champion_rows))
        for model_id, rows in v2a_predictions.items()
    }
    reason_counts = Counter(
        target.champion_ineligibility_reason
        for target in targets.values()
        if target.champion_ineligibility_reason
    )
    history_counts = Counter(_history_bucket(target) for target in targets.values())
    return {
        "contract": "MatchForgeFullCoverageChallengersV2ReplacementResultV1",
        "protocol_id": PROTOCOL_ID,
        "authorization": "AUTHORIZE_FULL_COVERAGE_V2_REPLACEMENT_HOLDOUT_V1",
        "parent_protocol_id": "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1_1",
        "replacement_manifest_id": REPLACEMENT_MANIFEST_ID,
        "execution": {**receipt, "outcomes_loaded": True, "logical_executions": 1},
        "frozen_v2": {
            "candidate_artifact_sha256": runtime["artifact_shas"],
            "selected_shrinkage_k": cast(dict[str, object], old_config["selected_cold_start"])[
                "shrinkage_k"
            ],
            "selected_l2": cast(dict[str, object], old_config["selected_cold_start"])[
                "l2_regularization"
            ],
            "selected_transfer_weight": old_config["selected_transfer_weight"],
            "ensemble_status": "PREVIOUSLY_VALID_FROZEN_DEVELOPMENT",
        },
        "reference_stack": {
            "id": REFERENCE_STACK_ID,
            "competition_prior_model_id": COMPETITION_PRIOR_MODEL_ID,
            "competition_prior_artifact_sha256": reference_artifact["artifact_sha256"],
            "k_prior": COMPETITION_PRIOR_K,
        },
        "target_count": len(observations),
        "competition_counts": dict(
            sorted(Counter(target.competition_name for target in targets.values()).items())
        ),
        "season_counts": dict(
            sorted(Counter(target.season for target in targets.values()).items())
        ),
        "champion_eligible_count": len(eligible_ids),
        "champion_ineligible_count": len(ineligible_ids),
        "champion_ineligibility_reason_counts": dict(sorted(reason_counts.items())),
        "low_history_counts": dict(sorted(history_counts.items())),
        "v2b_routing_counts": {
            key: dict(sorted(value.items())) for key, value in sorted(routes.items())
        },
        "v2a_stratum_a": v2a_report,
        "stratum_a_v2b_vs_champion": strata_a,
        "stratum_b_v2b_vs_competition_prior": strata_b,
        "overall_v2b_vs_reference_stack": overall,
        "low_history_results": low_history,
        "promoted_team_results": promoted,
        "domain_results": domains,
        "candidate_decisions": decisions,
        "development_winner": winner,
        "final_disposition": disposition,
        "coverage": {
            model_id: len(rows) / len(observations) for model_id, rows in predictions.items()
        },
        "independent_evaluation_available": False,
        "production_promotion_justified": False,
        "production_champion_changed": False,
    }


def _forecast_all(
    observations: Sequence[EvaluationObservation],
    champion_model: Any,
    champion_artifact: FittedModelArtifact,
    v2a_models: Sequence[Any],
    v2a_artifacts: Mapping[str, FittedModelArtifact],
    v2b_models: Sequence[Any],
    v2b_artifacts: Mapping[str, FittedModelArtifact],
    prior_model: CompetitionPriorPoissonV1,
    reference_artifact: Mapping[str, object],
) -> tuple[
    dict[str, list[ScoredModelForecast]],
    list[ScoredModelForecast],
    list[ScoredModelForecast],
    dict[str, list[ScoredModelForecast]],
    dict[str, Counter[str]],
]:
    predictions: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    references: list[ScoredModelForecast] = []
    champions: list[ScoredModelForecast] = []
    v2a_predictions: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    routes: dict[str, Counter[str]] = defaultdict(Counter)
    for item in observations:
        if item.target.champion_eligibility == ChampionEligibility.ELIGIBLE.value:
            champion = champion_model.predict(champion_artifact, item.snapshot)
            scored_champion = _scored(champion, item)
            champions.append(scored_champion)
            references.append(scored_champion)
            for model in v2a_models:
                forecast = model.predict(v2a_artifacts[model.model_id], item.snapshot)
                v2a_predictions[model.model_id].append(_scored(forecast, item))
        else:
            reference = _competition_prior_forecast(prior_model, reference_artifact, item)
            references.append(_scored(reference, item))
        for model in v2b_models:
            try:
                forecast = model.predict(v2b_artifacts[model.model_id], item.snapshot)
            except Exception as error:
                raise RuntimeError(
                    f"IMPLEMENTATION_FAILURE: {item.target.fixture_id}:{model.model_id}:{error}"
                ) from error
            predictions[model.model_id].append(_scored(forecast, item))
            mode = (
                forecast.lineage.forecast_mode.value
                if forecast.lineage
                else "OTHER_EXPLICIT_FALLBACK"
            )
            routes[model.model_id][mode] += 1
    return predictions, references, champions, v2a_predictions, routes


def _competition_prior_forecast(
    model: CompetitionPriorPoissonV1,
    artifact: Mapping[str, object],
    item: EvaluationObservation,
) -> ModelForecast:
    target = item.target
    history = tuple(
        row
        for row in item.competition_history
        if row.competition_id == target.competition_id and row.kickoff_at < target.kickoff_at
    )
    matrix = model.distribution(
        competition_id=target.competition_id,
        kickoff_at=target.kickoff_at,
        history=history,
    )
    home, away, total = distributions(matrix)
    markets = derive_markets(matrix)
    return ModelForecast(
        fixture_id=target.fixture_id,
        model_id=COMPETITION_PRIOR_MODEL_ID,
        model_family="COMPETITION_PRIOR_INDEPENDENT_POISSON",
        model_version=COMPETITION_PRIOR_MODEL_ID,
        model_artifact_sha256=str(artifact["artifact_sha256"]),
        football_cutoff=target.kickoff_at,
        knowledge_cutoff=target.kickoff_at,
        created_at=datetime.now(UTC),
        expected_home_goals=sum(index * value for index, value in enumerate(home)),
        expected_away_goals=sum(index * value for index, value in enumerate(away)),
        score_labels=tuple(str(index) for index in range(10)) + ("10+",),
        score_matrix=matrix,
        home_goal_distribution=home,
        away_goal_distribution=away,
        total_goal_distribution=total,
        status=ModelStatus.SUCCESS,
        warnings=(),
        input_snapshot_sha256=item.snapshot.sha256,
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


def _candidate_decision(
    stratum_a: Mapping[str, object],
    stratum_b: Mapping[str, object],
    overall: Mapping[str, object],
    domains: Mapping[str, object],
    routes: Counter[str],
    coverage_count: int,
    target_count: int,
    stratum_b_sufficient: bool,
) -> str:
    coverage_pass = coverage_count == target_count
    native_cold = sum(
        routes[mode.value]
        for mode in (
            ForecastMode.COLD_START_HOME,
            ForecastMode.COLD_START_AWAY,
            ForecastMode.COLD_START_BOTH,
        )
    )
    if not coverage_pass or native_cold < 50:
        return "DEVELOPMENT_REJECTED"
    a_pass = _gate(stratum_a, require_result_ci=True)
    b_pass = _gate(stratum_b, require_result_ci=False) if stratum_b_sufficient else True
    overall_pass = _gate(overall, require_result_ci=False)
    deltas = [
        float(cast(dict[str, Any], value)["paired_deltas"]["joint_score_log_loss"]["delta"])
        for value in domains.values()
    ]
    domain_pass = (
        all(delta <= 0.020 for delta in deltas) and sum(delta < 0 for delta in deltas) >= 2
    )
    if a_pass and b_pass and overall_pass and domain_pass:
        return (
            "DEVELOPMENT_ACCEPTED_FOR_INDEPENDENT_EVALUATION"
            if stratum_b_sufficient
            else "DEVELOPMENT_PARTIAL_SUCCESS"
        )
    return "DEVELOPMENT_REJECTED"


def _gate(value: Mapping[str, object], *, require_result_ci: bool) -> bool:
    metrics = cast(dict[str, dict[str, object]], value["paired_deltas"])
    result_ci = cast(list[float], metrics["result_log_loss"]["confidence_interval_95"])[1]
    return (
        _number(metrics["joint_score_log_loss"]["delta"]) <= -0.003
        and cast(list[float], metrics["joint_score_log_loss"]["confidence_interval_95"])[1] < 0
        and _number(metrics["result_log_loss"]["delta"]) <= 0
        and (not require_result_ci or result_ci <= 0)
        and cast(list[float], metrics["multiclass_brier"]["confidence_interval_95"])[1] <= 0.01
        and cast(list[float], metrics["ranked_probability_score"]["confidence_interval_95"])[1]
        <= 0.01
        and cast(list[float], metrics["total_goal_crps"]["confidence_interval_95"])[1] <= 0.02
    )


def _group_results(
    candidate: Sequence[ScoredModelForecast],
    references: Mapping[UUID, ScoredModelForecast],
    key: Any,
    targets: Mapping[UUID, FrozenTarget],
) -> dict[str, object]:
    groups: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    for row in candidate:
        groups[str(key(targets[row.forecast.fixture_id]))].append(row)
    return {
        name: _paired_payload(
            tuple(rows), tuple(references[row.forecast.fixture_id] for row in rows)
        )
        for name, rows in sorted(groups.items())
    }


def _history_bucket(target: FrozenTarget) -> str:
    value = min(target.home_prior_match_count, target.away_prior_match_count)
    if value == 0:
        return "0"
    if value <= 4:
        return "1-4"
    if value <= 9:
        return "5-9"
    return ">=10"


def _v2a_report(
    candidate: tuple[ScoredModelForecast, ...], reference: tuple[ScoredModelForecast, ...]
) -> dict[str, object]:
    native = tuple(
        row
        for row in candidate
        if row.forecast.lineage and not row.forecast.lineage.champion_fallback_used
    )
    fallback = tuple(
        row
        for row in candidate
        if row.forecast.lineage and row.forecast.lineage.champion_fallback_used
    )
    reference_by_id = {row.forecast.fixture_id: row for row in reference}
    return {
        "applicability": "STRATUM_A_ONLY",
        "coverage": len(candidate) / len(reference) if reference else 0.0,
        "native_challenger_count": len(native),
        "champion_fallback_count": len(fallback),
        "overall": _paired_payload(candidate, reference),
        "native_only": _paired_payload(
            native, tuple(reference_by_id[row.forecast.fixture_id] for row in native)
        )
        if native
        else {"target_count": 0},
        "fallback_only": _paired_payload(
            fallback, tuple(reference_by_id[row.forecast.fixture_id] for row in fallback)
        )
        if fallback
        else {"target_count": 0},
    }


def _paired_payload(
    candidate: tuple[ScoredModelForecast, ...], reference: tuple[ScoredModelForecast, ...]
) -> dict[str, object]:
    if not candidate or len(candidate) != len(reference):
        raise RuntimeError("paired comparison target mismatch")
    left = {row.forecast.fixture_id: row for row in candidate}
    right = {row.forecast.fixture_id: row for row in reference}
    if left.keys() != right.keys():
        raise RuntimeError("paired comparison fixture mismatch")
    ordered = tuple(sorted(left, key=lambda item: (left[item].kickoff_at, str(item))))
    deltas: dict[str, object] = {}
    for offset, name in enumerate(ForecastLosses.__dataclass_fields__):
        values = np.asarray(
            [
                getattr(forecast_losses(left[item]), name)
                - getattr(forecast_losses(right[item]), name)
                for item in ordered
            ]
        )
        lower, upper = _moving_block_interval(values, BOOTSTRAP_SEED + offset)
        deltas[name] = {
            "delta": float(values.mean()),
            "confidence_interval_95": [lower, upper],
            "target_count": len(values),
        }
    return {
        "target_count": len(candidate),
        "candidate_metrics": asdict(evaluate_model_forecasts(candidate)),
        "reference_metrics": asdict(evaluate_model_forecasts(reference)),
        "paired_deltas": deltas,
    }


def _moving_block_interval(values: np.ndarray[Any, Any], seed: int) -> tuple[float, float]:
    length = min(BOOTSTRAP_BLOCK_LENGTH, len(values))
    starts = np.arange(len(values) - length + 1)
    blocks = math.ceil(len(values) / length)
    random = np.random.default_rng(seed)
    draws = np.empty(BOOTSTRAP_REPLICATES)
    for index in range(BOOTSTRAP_REPLICATES):
        selected = random.choice(starts, size=blocks, replace=True)
        sample = np.concatenate([values[start : start + length] for start in selected])[
            : len(values)
        ]
        draws[index] = sample.mean()
    lower, upper = np.quantile(draws, (0.025, 0.975))
    return float(lower), float(upper)


def _scored(forecast: ModelForecast, item: EvaluationObservation) -> ScoredModelForecast:
    return ScoredModelForecast(
        forecast=forecast,
        kickoff_at=item.target.kickoff_at,
        outcome_known_at=item.target.kickoff_at + timedelta(hours=3),
        home_goals=item.home_goals,
        away_goals=item.away_goals,
        competition_id=item.target.competition_name,
        season_label=item.target.season,
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
        return True if value == "PROMOTED_TEAM" else False if value == "NOT_PROMOTED" else None

    return FrozenTarget(
        fixture_id=UUID(str(row["fixture_id"])),
        kickoff_at=datetime.fromisoformat(str(row["kickoff"])),
        competition_id=UUID(str(row["competition_id"])),
        competition_name=str(row["competition"]),
        season=str(row["season"]),
        home_team_id=UUID(str(row["home_team"])),
        away_team_id=UUID(str(row["away_team"])),
        home_prior_match_count=int(cast(int, row["home_prior_match_count"])),
        away_prior_match_count=int(cast(int, row["away_prior_match_count"])),
        champion_eligibility=str(row["champion_eligibility"]),
        champion_ineligibility_reason=(
            str(row["champion_ineligibility_reason"])
            if row["champion_ineligibility_reason"] is not None
            else None
        ),
        home_promoted=promoted(row["home_promotion_state"]),
        away_promoted=promoted(row["away_promotion_state"]),
        expected_route=str(row["V2B_expected_route"]),
        reference_model_id=str(row["reference_model_id"]),
        reference_mode=str(row["reference_mode"]),
    )


def _update_project_status(root: Path, result: Mapping[str, object]) -> None:
    path = root / "docs/project-status.json"
    status = _json(path)
    decisions = cast(list[str], status["owner_decisions"])
    decision = "AUTHORIZE_FULL_COVERAGE_V2_REPLACEMENT_HOLDOUT_V1"
    if decision not in decisions:
        decisions.append(decision)
    tracks = cast(list[dict[str, object]], status["evaluation_tracks"])
    tracks.append(
        {
            "evaluation_protocol_id": PROTOCOL_ID,
            "provider": "MULTISOURCE_RETAINED_ONLY",
            "status": f"COMPLETE_{result['final_disposition']}",
            "owner_decision": decision,
            "owner_decision_ref": OWNER_DECISION.relative_to(ROOT).as_posix(),
            "source_commit": cast(dict[str, object], result["execution"])["source_commit"],
            "execution_commit": cast(dict[str, object], result["execution"])["execution_commit"],
            "replacement_holdout_target_count": result["target_count"],
            "development_outcomes_loaded": True,
            "logical_executions": 1,
            "result_classification": result["final_disposition"],
            "development_winner": result["development_winner"],
            "evidence_ref": RESULT.relative_to(ROOT).as_posix(),
            "report_ref": REPORT.relative_to(ROOT).as_posix(),
            "execution_receipt_ref": RECEIPT.relative_to(ROOT).as_posix(),
            "independent_evaluation_available": False,
            "model_promoted": False,
            "production_promotion_justified": False,
            "production_champion_changed": False,
            "next_action": "OWNER_HANDOFF_REPLACEMENT_DEVELOPMENT_HOLDOUT_COMPLETE",
        }
    )
    status["updated_at"] = f"{DATE}T00:00:00Z"
    _write_pretty(path, status)


def _markdown(result: Mapping[str, object]) -> str:
    return "\n".join(
        (
            "# Full-coverage V2 replacement holdout",
            "",
            f"Protocol: `{result['protocol_id']}`",
            f"Targets: `{result['target_count']}`",
            f"Champion eligible: `{result['champion_eligible_count']}`",
            f"Champion ineligible: `{result['champion_ineligible_count']}`",
            f"Disposition: `{result['final_disposition']}`",
            f"Development winner: `{result['development_winner']}`",
            "",
            "Outcomes loaded exactly once after preflight: YES.",
            "Independent evaluation available: NO.",
            "Production promotion justified: NO.",
            "Production champion changed: NO.",
            "",
        )
    )


def _semantic_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError("metric value must be numeric")
    return float(value)


def _json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _write(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _write_pretty(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
