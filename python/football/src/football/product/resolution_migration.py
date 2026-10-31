"""Expose verified migration evidence without upgrading bounded parity to cutover readiness."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

from football.product.domain import sha256_json

STAGES = (
    "Acquisition",
    "Provider-native parsing",
    "Normalization",
    "Work orchestration",
    "Identity",
    "Canonical state",
    "Coverage and quality",
    "Read models",
    "API",
    "Feature platform",
    "Model routing",
    "Forecasting",
    "Remaining background work",
)


def verified_document(repo: Path, reference: str, digest: str) -> dict[str, Any]:
    path = (repo / reference).resolve()
    path.relative_to((repo / "docs").resolve())
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("tracked migration evidence checksum mismatch")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("tracked migration evidence must be an object")
    return cast(dict[str, Any], value)


def migration_report(repo: Path) -> dict[str, Any]:
    payload = (repo / "docs/project-status.json").read_bytes()
    status = json.loads(payload)
    if status.get("contract") != "ProjectStatusV2":
        raise ValueError("project-status contract is unavailable")
    architecture = status["architecture_v2"]
    gate = architecture["phase_35"]
    reference, digest = gate["blocker_resolution_ref"], gate["blocker_resolution_sha256"]
    evidence = verified_document(repo, reference, digest)
    for basis in evidence["evidence_basis"]:
        verified_document(repo, basis["ref"], basis["sha256"])
    comparisons = evidence["phase_35b_parity"]
    items = []
    for key, result in comparisons.items():
        if not isinstance(result, dict):
            continue
        exact_pass = (
            result.get("status") == "PASS"
            and result.get("required_runtime_scopes_complete") is True
        )
        items.append(
            {
                "case_key": "parity:" + key,
                "name": key.replace("_", " "),
                "status": "PASS" if exact_pass else "BLOCKED",
                "reported_status": result.get("status", "NOT_RUN"),
                "expected": "Complete production scopes; disposition every difference",
                "actual": result,
                "reason": result.get("reason", evidence["phase_35b_parity"]["reason"]),
                "source_ref": reference,
                "source_sha256": digest,
                "verified_at": evidence["recorded_at"],
                "next_action": "Resolve blockers, then run the full-scope comparison.",
            }
        )
    controls = evidence["phase_35c_stage_controls"]
    stages = [
        {
            "case_key": f"stage:{index}",
            "order": index,
            "name": name,
            "status": "BLOCKED",
            "current_route": "LEGACY",
            "v2_ready": False,
            "dependencies": [index - 1] if index > 1 else [],
            "switch_config_status": "NOT_IMPLEMENTED",
            "rollback_ready": False,
            "reason": controls["stages"][index - 1]["current_state"],
            "next_action": controls["stages"][index - 1]["rollback_control"],
            "source_ref": reference,
            "source_sha256": digest,
            "rehearsal_status": "NOT_RUN_REQUIRED_PARITY_UNMET",
        }
        for index, name in enumerate(STAGES, 1)
    ]
    result = {
        "status": "BLOCKED",
        "items": items,
        "stages": stages,
        "blockers": evidence["remaining_blockers"],
        "next_actions": evidence["next_required_actions"],
        "production_cutover": gate["runtime_cutover"],
        "phase_36": architecture["phase_36"],
        "source_ref": reference,
        "source_sha256": digest,
        "project_status_sha256": hashlib.sha256(payload).hexdigest(),
        "scope": "VERIFIED_TRACKED_EVIDENCE; recheck verifies evidence, not a new comparison",
        "exceptions": evidence["phase_35b_parity"]["feature_and_forecast_inputs"],
    }
    result["evidence_version"] = sha256_json(result)
    return result


def migration_page(repo: Path, view: str, query: dict[str, Any]) -> dict[str, Any]:
    report = migration_report(repo)
    items = report["stages"] if view == "cutover" else report["items"]
    if query.get("provider") or query.get("kind"):
        raise ValueError("provider and entity filters do not apply to migration evidence")
    items = [
        item
        for item in items
        if (not query.get("status") or item["status"] == query["status"])
        and str(query.get("q", "")).casefold() in str(item).casefold()
    ]
    page, size = query.get("page", 1), query.get("page_size", 20)
    return {
        **report,
        "items": items[(page - 1) * size : page * size],
        "page": page,
        "page_size": size,
        "total": len(items),
        "counts": dict(Counter(item["status"] for item in items)),
        "groups": [],
    }
