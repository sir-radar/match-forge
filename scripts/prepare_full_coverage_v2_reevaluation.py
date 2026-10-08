#!/usr/bin/env python3
"""Select on frozen TRAIN/VALIDATION and write V2 re-evaluation control artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from football.forecasting.cold_start_fitting import (
    ColdStartDevelopmentObservation,
    select_cold_start_config_from_partitions,
)
from football.forecasting.v2_reevaluation import (
    CORPUS_ID,
    CORPUS_SHA256,
    PARENT_PROTOCOL_ID,
    PROTOCOL_ID,
    scientific_source_files,
    scientific_source_sha256,
)

from scripts.run_full_coverage_v2_reevaluation import (
    CONFIG_PATH,
    CORPUS_PATH,
    CROSSWALK_PATH,
    QUALIFICATION_EVIDENCE,
    ROOT,
    V1_EVIDENCE,
    artifact_manifests,
    build_runtime,
    load_observations,
)

DATE = "2026-10-09"
OWNER_DECISION = ROOT / (
    "docs/evidence/owner-decision-correct-full-coverage-v2-reevaluation-"
    f"commit-invariant-{DATE}.json"
)
PREREGISTRATION = (
    ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-preregistration.json"
)
EXECUTION_STATE = (
    ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-execution-state.json"
)
FIREWALL = ROOT / "docs/evaluation/full-coverage-challengers-v2-spent-targets-v1.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    args = parser.parse_args()
    prepare(args.database_url, args.source_commit, args.repository_root.resolve())
    return 0


def prepare(database_url: str, source_commit: str, root: Path = ROOT) -> dict[str, object]:
    _verify_clean_source(root, source_commit)
    observations = load_observations(database_url, roles={"TRAIN", "VALIDATION"})
    train = tuple(
        ColdStartDevelopmentObservation(row.snapshot, row.home_goals, row.away_goals)
        for row in observations
        if row.target.split == "TRAIN"
    )
    validation = tuple(
        ColdStartDevelopmentObservation(row.snapshot, row.home_goals, row.away_goals)
        for row in observations
        if row.target.split == "VALIDATION"
    )
    if len(train) != 934 or len(validation) != 323:
        raise RuntimeError("FAIL_CLOSED_FROZEN_CORPUS_MISMATCH")
    selection = select_cold_start_config_from_partitions(train, validation)
    aliases = _artifact_aliases(root)
    v1 = _json(root / V1_EVIDENCE.relative_to(ROOT))
    weights = cast(
        dict[str, float], cast(dict[str, Any], v1["development_freeze"])["ensemble_weights"]
    )
    ensemble_shas = {
        model_id: _semantic_sha(
            {
                "model_id": model_id,
                "source_commit": source_commit,
                "weights": weights,
            }
        )
        for model_id in ("matchforge-ensemble-v2a", "matchforge-ensemble-v2b")
    }
    provisional: dict[str, object] = {
        "ensemble_artifact_sha256": ensemble_shas,
        "selected_cold_start": _plain(asdict(selection.config)),
        "source_commit": source_commit,
        "team_id_aliases": [list(item) for item in aliases],
    }
    runtime = build_runtime(provisional, root)
    config = {
        "candidate_artifacts": artifact_manifests(runtime),
        "contract": "MatchForgeFullCoverageV2ReevaluationConfigurationV1_1",
        "ensemble_artifact_sha256": ensemble_shas,
        "ensemble_status": "PREVIOUSLY_VALID_FROZEN_DEVELOPMENT",
        "ensemble_weights": weights,
        "hyperparameter_grids": {
            "l2": [0.01, 0.1, 1.0, 10.0],
            "shrinkage_k": [2, 5, 10, 20, 40],
            "transfer_weight": [0, 0.25, 0.5, 0.75, 1.0],
        },
        "protocol_id": PROTOCOL_ID,
        "selected_cold_start": _plain(asdict(selection.config)),
        "selected_transfer_weight": selection.selected_transfer_weight,
        "source_commit": source_commit,
        "team_id_aliases": [list(item) for item in aliases],
        "transfer_relationship_status": "NO_QUALIFIED_CROSS_COMPETITION_RELATIONSHIP",
        "validation_candidates": [
            {
                "config": _plain(asdict(item.config)),
                "metrics": _plain(asdict(item.metrics)),
                "transfer_weight": item.transfer_weight,
            }
            for item in selection.validation_candidates
        ],
        "validation_winner_metrics": _plain(asdict(selection.validation_metrics)),
    }
    config_path = root / CONFIG_PATH.relative_to(ROOT)
    _write_json(config_path, config)
    decision = {
        "authorized_at": f"{DATE}T00:00:00Z",
        "contract": "MatchForgeOwnerDecisionV1",
        "correction_reason": "IMPOSSIBLE_SELF_REFERENTIAL_COMMIT_INVARIANT",
        "decision_id": "CORRECT_FULL_COVERAGE_V2_REEVALUATION_COMMIT_INVARIANT_V1",
        "execution_commit_policy": {
            "allowed_content": "FROZEN_EXPERIMENT_CONTROL_ONLY",
            "execution_head_parent_equals_source_commit": True,
            "self_referential_commit_sha_forbidden": True,
        },
        "outcomes_loaded_before_decision": 0,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "protocol_id": PROTOCOL_ID,
        "recorded_at": f"{DATE}T00:00:00Z",
        "scope": "GOVERNANCE_EXECUTION_INVARIANT_ONLY",
    }
    decision_path = root / OWNER_DECISION.relative_to(ROOT)
    _write_json(decision_path, decision)
    state_path = root / EXECUTION_STATE.relative_to(ROOT)
    _write_json(
        state_path,
        {
            "logical_execution_attempts": 0,
            "outcomes_loaded": False,
            "protocol_id": PROTOCOL_ID,
        },
    )
    corpus = _json(root / CORPUS_PATH.relative_to(ROOT))
    source_files = scientific_source_files(root)
    allowed = tuple(
        sorted(
            {
                CONFIG_PATH.relative_to(ROOT).as_posix(),
                OWNER_DECISION.relative_to(ROOT).as_posix(),
                PREREGISTRATION.relative_to(ROOT).as_posix(),
                EXECUTION_STATE.relative_to(ROOT).as_posix(),
            }
        )
    )
    preregistration = {
        "acceptance_criteria": {
            "cold_start_joint_ll_delta_max": -0.003,
            "cold_start_joint_ll_ci_upper_max_exclusive": 0,
            "domain_joint_ll_delta_max": 0.020,
            "fitted_joint_ll_delta_max": 0.010,
            "overall_joint_ll_delta_max": -0.003,
            "overall_joint_ll_ci_upper_max_exclusive": 0,
        },
        "bootstrap": {
            "block_length": 10,
            "confidence_interval": 0.95,
            "replicates": 2000,
            "seed": 20260921,
            "type": "MOVING_BLOCK",
        },
        "configuration_ref": CONFIG_PATH.relative_to(ROOT).as_posix(),
        "configuration_sha256": _file_sha(config_path),
        "corpus_file_sha256": _file_sha(root / CORPUS_PATH.relative_to(ROOT)),
        "corpus_id": CORPUS_ID,
        "corpus_ref": CORPUS_PATH.relative_to(ROOT).as_posix(),
        "corpus_sha256": CORPUS_SHA256,
        "execution_commit_allowed_files": list(allowed),
        "execution_commit_policy": "DIRECT_CHILD_CONTROL_ONLY_V1",
        "execution_state_ref": EXECUTION_STATE.relative_to(ROOT).as_posix(),
        "firewall_file_sha256": _file_sha(root / FIREWALL.relative_to(ROOT)),
        "firewall_manifest_sha256": corpus["global_firewall_sha256"],
        "firewall_ref": FIREWALL.relative_to(ROOT).as_posix(),
        "metrics": [
            "Joint Score Log Loss",
            "1X2 Log Loss",
            "Brier",
            "RPS",
            "Total Goal CRPS",
            "calibration",
        ],
        "model_artifact_sha256": {
            key: value["artifact_sha256"]
            for key, value in cast(
                dict[str, dict[str, object]], config["candidate_artifacts"]
            ).items()
        },
        "owner_decision_id": "CORRECT_FULL_COVERAGE_V2_REEVALUATION_COMMIT_INVARIANT_V1",
        "owner_decision_ref": OWNER_DECISION.relative_to(ROOT).as_posix(),
        "owner_decision_sha256": _file_sha(decision_path),
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "preregistration_ref": PREREGISTRATION.relative_to(ROOT).as_posix(),
        "protocol_id": PROTOCOL_ID,
        "qualification_evidence_ref": QUALIFICATION_EVIDENCE.relative_to(ROOT).as_posix(),
        "qualification_evidence_sha256": _file_sha(root / QUALIFICATION_EVIDENCE.relative_to(ROOT)),
        "required_execution_parent": source_commit,
        "scientific_source_files": list(source_files),
        "scientific_source_sha256": scientific_source_sha256(root, source_files),
        "source_commit": source_commit,
        "split_manifest_sha256": corpus["split_manifest_sha256"],
        "target_manifest_sha256": corpus["target_manifest_sha256"],
    }
    prereg_path = root / PREREGISTRATION.relative_to(ROOT)
    _write_json(prereg_path, preregistration)
    return preregistration


def _artifact_aliases(root: Path) -> tuple[tuple[str, str], ...]:
    qualification = _json(root / QUALIFICATION_EVIDENCE.relative_to(ROOT))
    identities = cast(
        list[dict[str, object]],
        cast(dict[str, object], qualification["artifact_identity"])["identities"],
    )
    provider_to_artifact = {
        str(row["provider_team_id"]): str(row["artifact_team_id"]) for row in identities
    }
    crosswalk = _json(root / CROSSWALK_PATH.relative_to(ROOT))
    aliases = {
        str(row["canonical_team_id"]): provider_to_artifact[str(row["source_team_id"])]
        for row in cast(list[dict[str, object]], crosswalk["mappings"])
        if row["source_provider"] == "pitchapi"
        and row["status"] == "VERIFIED"
        and str(row["source_team_id"]) in provider_to_artifact
    }
    if len(aliases) != 18:
        raise RuntimeError(f"frozen artifact alias count mismatch: {len(aliases)}")
    return tuple(sorted(aliases.items()))


def _verify_clean_source(root: Path, source_commit: str) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != source_commit:
        raise RuntimeError("source commit does not equal HEAD")
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    if status:
        raise RuntimeError("TRAIN/VALIDATION preparation requires a clean source commit")


def _json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(value) + "\n", encoding="utf-8")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_sha(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value) if value.__class__.__name__ == "UUID" else value


if __name__ == "__main__":
    raise SystemExit(main())
