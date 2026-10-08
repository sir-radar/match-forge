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


def _sha256(relative_path: str) -> str:
    return hashlib.sha256((REPOSITORY_ROOT / relative_path).read_bytes()).hexdigest()


def test_context_evaluation_stops_before_protected_outcomes() -> None:
    evidence = _load("docs/evidence/matchforge-context-feature-evaluation-v1-2026-10-08.json")

    assert evidence["final_disposition"] == "INSUFFICIENT_QUALIFIED_COVERAGE"
    assert evidence["protected_outcomes_loaded"] is False
    assert evidence["final_included_feature_families"] == []
    assert evidence["production_champion_changed"] is False
    assert evidence["production_promotion_justified"] is False
    assert evidence["lineup_predictor"]["sample_count"] == 0


def test_neutral_context_artifact_contains_no_unaccepted_feature() -> None:
    artifact = _load("docs/evaluation/matchforge-contextual-goal-model-v1-artifact.json")

    assert artifact["status"] == "NEUTRAL_NO_ACCEPTED_FAMILIES"
    assert artifact["included_feature_families"] == []
    assert artifact["coefficients"] == []
    assert artifact["scaler_parameters"] == []


def test_context_evidence_references_exact_immutable_inputs() -> None:
    evidence = _load("docs/evidence/matchforge-context-feature-evaluation-v1-2026-10-08.json")

    assert evidence["configuration_sha256"] == _sha256(evidence["configuration_ref"])
    assert evidence["dataset_manifest_sha256"] == _sha256(evidence["dataset_manifest_ref"])
    assert evidence["candidate_artifact_sha256"] == _sha256(evidence["candidate_artifact_ref"])
