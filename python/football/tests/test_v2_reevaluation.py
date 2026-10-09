from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from football.forecasting.fresh_corpus import semantic_sha256
from football.forecasting.v2_reevaluation import (
    CORPUS_ID,
    CORPUS_SHA256,
    PROTOCOL_ID,
    GitExecutionState,
    ReEvaluationPreflightError,
    mandatory_pre_outcome_preflight,
    scientific_source_files,
    scientific_source_sha256,
)

SOURCE = "a" * 40
EXECUTION = "b" * 40


def test_direct_executor_accepts_config_only_child_commit(tmp_path: Path) -> None:
    preregistration = _frozen_inputs(tmp_path)
    called = False

    def load() -> tuple[str, ...]:
        nonlocal called
        called = True
        return ("loaded",)

    outcomes, receipt = mandatory_pre_outcome_preflight(
        root=tmp_path,
        preregistration_path=preregistration,
        outcome_loader=load,
        git_state=_git_state(),
    )

    assert called
    assert outcomes == ("loaded",)
    assert receipt["execution_parent_matches_source"] is True
    assert _json(tmp_path / "docs/evaluation/state.json")["logical_execution_attempts"] == 1


@pytest.mark.parametrize(
    ("state", "match"),
    (
        (
            GitExecutionState(SOURCE, SOURCE, False, ("docs/evaluation/config.json",)),
            "not committed",
        ),
        (GitExecutionState(EXECUTION, "c" * 40, False, ("docs/evaluation/config.json",)), "parent"),
        (GitExecutionState(EXECUTION, SOURCE, True, ("docs/evaluation/config.json",)), "clean"),
        (
            GitExecutionState(EXECUTION, SOURCE, False, ("python/football/src/x.py",)),
            "SOURCE_MUTATION",
        ),
    ),
)
def test_direct_executor_rejects_invalid_repository_state(
    tmp_path: Path, state: GitExecutionState, match: str
) -> None:
    preregistration = _frozen_inputs(tmp_path)
    called = False

    def load() -> tuple[()]:
        nonlocal called
        called = True
        return ()

    with pytest.raises(ReEvaluationPreflightError, match=match):
        mandatory_pre_outcome_preflight(
            root=tmp_path,
            preregistration_path=preregistration,
            outcome_loader=load,
            git_state=state,
        )
    assert not called


def test_direct_executor_rejects_scientific_source_hash_mismatch(tmp_path: Path) -> None:
    preregistration = _frozen_inputs(tmp_path)
    payload = _json(preregistration)
    payload["scientific_source_sha256"] = "0" * 64
    _write(preregistration, payload)

    with pytest.raises(ReEvaluationPreflightError, match="scientific source hash"):
        mandatory_pre_outcome_preflight(
            root=tmp_path,
            preregistration_path=preregistration,
            outcome_loader=lambda: (),
            git_state=_git_state(),
        )


def test_direct_executor_rejects_manifest_mismatch(tmp_path: Path) -> None:
    preregistration = _frozen_inputs(tmp_path)
    payload = _json(preregistration)
    payload["target_manifest_sha256"] = "0" * 64
    _write(preregistration, payload)

    with pytest.raises(ReEvaluationPreflightError, match="target manifest"):
        mandatory_pre_outcome_preflight(
            root=tmp_path,
            preregistration_path=preregistration,
            outcome_loader=lambda: (),
            git_state=_git_state(),
        )


def test_direct_executor_rejects_second_logical_execution(tmp_path: Path) -> None:
    preregistration = _frozen_inputs(tmp_path)
    _write(
        tmp_path / "docs/evaluation/state.json",
        {
            "logical_execution_attempts": 1,
            "outcomes_loaded": True,
            "protocol_id": PROTOCOL_ID,
        },
    )

    with pytest.raises(ReEvaluationPreflightError, match="second logical execution"):
        mandatory_pre_outcome_preflight(
            root=tmp_path,
            preregistration_path=preregistration,
            outcome_loader=lambda: (),
            git_state=_git_state(),
        )


def _frozen_inputs(root: Path) -> Path:
    source_root = root / "python/football/src/football/forecasting"
    source_root.mkdir(parents=True)
    (source_root / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "prepare_full_coverage_v2_reevaluation.py").write_text("# prepare\n")
    (scripts / "run_full_coverage_v2_reevaluation.py").write_text("# run\n")
    evaluation = root / "docs/evaluation"
    evidence = root / "docs/evidence"
    evaluation.mkdir(parents=True)
    evidence.mkdir(parents=True)
    targets = [
        {
            "fixture_id": f"fixture-{index}",
            "split": "TRAIN"
            if index < 934
            else "VALIDATION"
            if index < 1257
            else "DEVELOPMENT_HOLDOUT",
        }
        for index in range(1572)
    ]
    corpus = {
        "contract": "test",
        "corpus_id": CORPUS_ID,
        "corpus_sha256": CORPUS_SHA256,
        "global_firewall_sha256": "f" * 64,
        "split_manifest_sha256": semantic_sha256(
            [{"fixture_id": row["fixture_id"], "split": row["split"]} for row in targets]
        ),
        "target_manifest_sha256": semantic_sha256(targets),
        "targets": targets,
    }
    config = {
        "candidate_artifacts": {
            "candidate": {"artifact_sha256": "1" * 64},
        }
    }
    firewall: dict[str, object] = {"unique_forbidden_target_ids": []}
    owner = {"decision_id": "CORRECT_FULL_COVERAGE_V2_REEVALUATION_COMMIT_INVARIANT_V1"}
    qualification = {"final_disposition": "FRESH_DEVELOPMENT_CORPUS_QUALIFIED"}
    paths = {
        "corpus": evaluation / "corpus.json",
        "config": evaluation / "config.json",
        "firewall": evaluation / "firewall.json",
        "owner": evidence / "owner.json",
        "qualification": evidence / "qualification.json",
        "state": evaluation / "state.json",
        "prereg": evaluation / "prereg.json",
    }
    _write(paths["corpus"], corpus)
    _write(paths["config"], config)
    _write(paths["firewall"], firewall)
    _write(paths["owner"], owner)
    _write(paths["qualification"], qualification)
    _write(
        paths["state"],
        {
            "logical_execution_attempts": 0,
            "outcomes_loaded": False,
            "protocol_id": PROTOCOL_ID,
        },
    )
    files = scientific_source_files(root)
    preregistration = {
        "configuration_ref": "docs/evaluation/config.json",
        "configuration_sha256": _sha(paths["config"]),
        "corpus_file_sha256": _sha(paths["corpus"]),
        "corpus_ref": "docs/evaluation/corpus.json",
        "execution_commit_allowed_files": [
            "docs/evaluation/config.json",
            "docs/evaluation/prereg.json",
        ],
        "execution_state_ref": "docs/evaluation/state.json",
        "firewall_file_sha256": _sha(paths["firewall"]),
        "firewall_manifest_sha256": "f" * 64,
        "firewall_ref": "docs/evaluation/firewall.json",
        "model_artifact_sha256": {"candidate": "1" * 64},
        "owner_decision_ref": "docs/evidence/owner.json",
        "owner_decision_sha256": _sha(paths["owner"]),
        "preregistration_ref": "docs/evaluation/prereg.json",
        "protocol_id": PROTOCOL_ID,
        "qualification_evidence_ref": "docs/evidence/qualification.json",
        "qualification_evidence_sha256": _sha(paths["qualification"]),
        "required_execution_parent": SOURCE,
        "scientific_source_files": list(files),
        "scientific_source_sha256": scientific_source_sha256(root, files),
        "source_commit": SOURCE,
        "split_manifest_sha256": corpus["split_manifest_sha256"],
        "target_manifest_sha256": corpus["target_manifest_sha256"],
    }
    _write(paths["prereg"], preregistration)
    return paths["prereg"]


def _git_state() -> GitExecutionState:
    return GitExecutionState(
        EXECUTION,
        SOURCE,
        False,
        ("docs/evaluation/config.json", "docs/evaluation/prereg.json"),
    )


def _json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
