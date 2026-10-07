from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _load(relative_path: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")),
    )


def _target_digest(target_ids: list[str]) -> str:
    payload = "".join(f"{target_id}\n" for target_id in sorted(target_ids))
    return hashlib.sha256(payload.encode()).hexdigest()


def test_spent_target_manifest_records_exposed_v2_holdout() -> None:
    manifest = _load("docs/evaluation/full-coverage-challengers-v2-spent-targets-v1.json")
    groups = {group["group_id"]: group for group in manifest["groups"]}
    exposed = groups["MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_DEVELOPMENT_V1_EXPOSED_HOLDOUT"]

    assert exposed["disposition"] == "SPENT_FOR_V2_DEVELOPMENT"
    assert exposed["target_count"] == 300
    assert len(set(exposed["target_ids"])) == 300
    assert _target_digest(exposed["target_ids"]) == exposed["target_ids_sha256"]


def test_spent_target_manifest_union_is_complete_and_stable() -> None:
    manifest = _load("docs/evaluation/full-coverage-challengers-v2-spent-targets-v1.json")
    target_ids = manifest["unique_forbidden_target_ids"]

    assert manifest["unique_forbidden_target_count"] == 2198
    assert len(set(target_ids)) == 2198
    assert _target_digest(target_ids) == manifest["unique_forbidden_target_ids_sha256"]


def test_reevaluation_stopped_before_fresh_outcome_loading() -> None:
    evidence = _load("docs/evidence/full-coverage-challengers-v2-reevaluation-v1-2026-10-07.json")
    previous = _load("docs/evidence/full-coverage-challengers-v2-development-2026-10-07.json")

    assert evidence["stop_code"] == "FRESH_DEVELOPMENT_CORPUS_REQUIRED"
    assert evidence["development_disposition"] == "DEFER_INSUFFICIENT_FRESH_DATA"
    assert evidence["new_development_outcomes_loaded"] is False
    assert evidence["logical_execution_attempts"] == 0
    assert previous["overall_result"] == "FAIL_CLOSED_PROTOCOL_VIOLATION"
