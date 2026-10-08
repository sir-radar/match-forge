from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from football.forecasting.fresh_corpus import semantic_sha256

PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1_1"
PARENT_PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1"
CORPUS_ID = "MATCHFORGE_FULL_COVERAGE_V2_FRESH_DEVELOPMENT_CORPUS_V1"
CORPUS_SHA256 = "0234d64bb21d4340e8499e6178b03f3342dd480e94dd2357253523d5f62a0835"
EXPECTED_SPLIT_COUNTS = {"TRAIN": 934, "VALIDATION": 323, "DEVELOPMENT_HOLDOUT": 315}
EXPECTED_HOLDOUT_COUNTS = {"cold_start": 251, "native_fitted": 64, "promoted": 117}


class ReEvaluationPreflightError(RuntimeError):
    """Fail-closed error raised before development-holdout outcome access."""


@dataclass(frozen=True, slots=True)
class GitExecutionState:
    head: str
    parent: str
    dirty: bool
    changed_files: tuple[str, ...]


def scientific_source_files(root: Path) -> tuple[str, ...]:
    forecasting = root / "python/football/src/football/forecasting"
    files = {
        path.relative_to(root).as_posix() for path in forecasting.rglob("*.py") if path.is_file()
    }
    files.update(
        {
            "scripts/prepare_full_coverage_v2_reevaluation.py",
            "scripts/run_full_coverage_v2_reevaluation.py",
        }
    )
    missing = sorted(path for path in files if not (root / path).is_file())
    if missing:
        raise ReEvaluationPreflightError(f"scientific source file missing: {missing}")
    return tuple(sorted(files))


def scientific_source_sha256(root: Path, files: Sequence[str] | None = None) -> str:
    selected = tuple(files) if files is not None else scientific_source_files(root)
    digest = hashlib.sha256()
    for relative in selected:
        path = root / relative
        if not path.is_file():
            raise ReEvaluationPreflightError(f"scientific source file missing: {relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def repository_execution_state(root: Path) -> GitExecutionState:
    def git(*args: str) -> str:
        return subprocess.run(
            ("git", *args),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD^")
    status = git("status", "--porcelain")
    changed = tuple(line for line in git("diff", "--name-only", "HEAD^", "HEAD").splitlines())
    return GitExecutionState(head, parent, bool(status), changed)


def mandatory_pre_outcome_preflight[T](
    *,
    root: Path,
    preregistration_path: Path,
    outcome_loader: Callable[[], T],
    artifact_verifier: Callable[[], None] | None = None,
    git_state: GitExecutionState | None = None,
) -> tuple[T, dict[str, object]]:
    """Verify every frozen input, persist consumption, then and only then load outcomes."""
    preregistration = _json(preregistration_path)
    state = git_state or repository_execution_state(root)
    receipt = _verify_preflight(root, preregistration, state)
    if artifact_verifier is not None:
        artifact_verifier()
    execution_state_path = root / str(preregistration["execution_state_ref"])
    _consume_execution(execution_state_path)
    outcomes = outcome_loader()
    return outcomes, receipt


def _verify_preflight(
    root: Path, preregistration: Mapping[str, object], state: GitExecutionState
) -> dict[str, object]:
    if preregistration.get("protocol_id") != PROTOCOL_ID:
        raise ReEvaluationPreflightError("preregistration protocol identity mismatch")
    if state.dirty:
        raise ReEvaluationPreflightError("development execution requires a clean worktree")
    source_commit = str(preregistration.get("source_commit", ""))
    required_parent = str(preregistration.get("required_execution_parent", ""))
    if state.parent != source_commit or state.parent != required_parent:
        raise ReEvaluationPreflightError("execution HEAD parent does not match source commit")
    if state.head == source_commit:
        raise ReEvaluationPreflightError("preregistration is not committed in a child commit")
    allowed = frozenset(cast(list[str], preregistration["execution_commit_allowed_files"]))
    changed = frozenset(state.changed_files)
    if not changed or not changed.issubset(allowed):
        forbidden = sorted(changed - allowed)
        raise ReEvaluationPreflightError(
            f"FAIL_CLOSED_EXECUTION_COMMIT_SOURCE_MUTATION: {forbidden}"
        )
    if any(path.endswith((".py", ".go", ".rs", ".ts", ".tsx", ".js", ".jsx")) for path in changed):
        raise ReEvaluationPreflightError("FAIL_CLOSED_EXECUTION_COMMIT_SOURCE_MUTATION")

    expected_files = tuple(cast(list[str], preregistration["scientific_source_files"]))
    actual_files = scientific_source_files(root)
    if expected_files != actual_files:
        raise ReEvaluationPreflightError("scientific source file set mismatch")
    actual_source_sha = scientific_source_sha256(root, actual_files)
    if actual_source_sha != preregistration.get("scientific_source_sha256"):
        raise ReEvaluationPreflightError("scientific source hash mismatch")

    _verify_file_hash(root, preregistration, "owner_decision_ref", "owner_decision_sha256")
    _verify_file_hash(root, preregistration, "configuration_ref", "configuration_sha256")
    _verify_file_hash(root, preregistration, "corpus_ref", "corpus_file_sha256")
    _verify_file_hash(root, preregistration, "firewall_ref", "firewall_file_sha256")
    _verify_file_hash(
        root,
        preregistration,
        "qualification_evidence_ref",
        "qualification_evidence_sha256",
    )
    _verify_corpus(root, preregistration)
    _verify_artifacts(root, preregistration)
    _verify_execution_state(root, preregistration)
    return {
        "execution_commit": state.head,
        "execution_parent": state.parent,
        "execution_parent_matches_source": True,
        "execution_commit_changed_files": sorted(changed),
        "scientific_source_sha256_expected": preregistration["scientific_source_sha256"],
        "scientific_source_sha256_actual": actual_source_sha,
        "preregistration_sha256": _sha256(root / str(preregistration["preregistration_ref"])),
    }


def _verify_file_hash(
    root: Path, preregistration: Mapping[str, object], ref_key: str, hash_key: str
) -> None:
    path = root / str(preregistration[ref_key])
    if _sha256(path) != preregistration.get(hash_key):
        raise ReEvaluationPreflightError(f"{hash_key} mismatch")


def _verify_corpus(root: Path, preregistration: Mapping[str, object]) -> None:
    corpus = _json(root / str(preregistration["corpus_ref"]))
    if corpus.get("corpus_id") != CORPUS_ID or corpus.get("corpus_sha256") != CORPUS_SHA256:
        raise ReEvaluationPreflightError("FAIL_CLOSED_FROZEN_CORPUS_MISMATCH")
    targets = cast(list[dict[str, object]], corpus.get("targets"))
    target_sha = semantic_sha256(targets)
    split_sha = semantic_sha256(
        [{"fixture_id": row["fixture_id"], "split": row["split"]} for row in targets]
    )
    if target_sha != preregistration.get("target_manifest_sha256"):
        raise ReEvaluationPreflightError("target manifest mismatch")
    if split_sha != preregistration.get("split_manifest_sha256"):
        raise ReEvaluationPreflightError("split manifest mismatch")
    split_counts = {
        role: sum(row["split"] == role for row in targets) for role in EXPECTED_SPLIT_COUNTS
    }
    if split_counts != EXPECTED_SPLIT_COUNTS:
        raise ReEvaluationPreflightError("FAIL_CLOSED_FROZEN_CORPUS_MISMATCH")
    firewall = _json(root / str(preregistration["firewall_ref"]))
    forbidden = frozenset(cast(list[str], firewall["unique_forbidden_target_ids"]))
    target_ids = {str(row["fixture_id"]) for row in targets}
    if target_ids & forbidden:
        raise ReEvaluationPreflightError("FAIL_CLOSED_SPENT_OR_PROTECTED_INTERSECTION")
    if corpus.get("global_firewall_sha256") != preregistration.get("firewall_manifest_sha256"):
        raise ReEvaluationPreflightError("firewall manifest mismatch")


def _verify_artifacts(root: Path, preregistration: Mapping[str, object]) -> None:
    configuration = _json(root / str(preregistration["configuration_ref"]))
    actual = {
        str(model_id): str(manifest["artifact_sha256"])
        for model_id, manifest in cast(
            dict[str, dict[str, object]], configuration["candidate_artifacts"]
        ).items()
    }
    expected = {
        str(key): str(value)
        for key, value in cast(dict[str, str], preregistration["model_artifact_sha256"]).items()
    }
    if actual != expected:
        raise ReEvaluationPreflightError("candidate artifact hash mismatch")


def _verify_execution_state(root: Path, preregistration: Mapping[str, object]) -> None:
    state = _json(root / str(preregistration["execution_state_ref"]))
    if state != {
        "logical_execution_attempts": 0,
        "outcomes_loaded": False,
        "protocol_id": PROTOCOL_ID,
    }:
        raise ReEvaluationPreflightError("second logical execution is not authorized")


def _consume_execution(path: Path) -> None:
    payload = {
        "logical_execution_attempts": 1,
        "outcomes_loaded": True,
        "protocol_id": PROTOCOL_ID,
    }
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReEvaluationPreflightError(f"cannot read frozen input: {path}") from error
    if not isinstance(value, dict):
        raise ReEvaluationPreflightError(f"frozen input must be an object: {path}")
    return cast(dict[str, object], value)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ReEvaluationPreflightError(f"cannot hash frozen input: {path}") from error


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
