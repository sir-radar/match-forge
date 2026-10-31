"""Expose verified migration evidence without upgrading bounded parity to cutover readiness."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

from psycopg import Connection

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
    items: list[dict[str, Any]] = []
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
                "status": "PASS"
                if exact_pass
                else (
                    result.get("status")
                    if result.get("status") in {"FAIL", "NOT_RUN"}
                    else "BLOCKED"
                ),
                "required_runtime_scopes_complete": exact_pass,
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
    for key, label in (
        ("history_coverage", "Fixture and historical coverage"),
        ("performance_external_reports", "Performance and external comparison reports"),
        ("forecast_artifacts_and_routing", "Forecast artifacts and model routing"),
    ):
        if any(item["case_key"] == "parity:" + key for item in items):
            continue
        items.append(
            {
                "case_key": "parity:" + key,
                "name": label,
                "status": "NOT_RUN",
                "expected": "Complete production scopes with exact source and artifact lineage",
                "actual": "No complete old/new production-scope comparison registered",
                "required_runtime_scopes_complete": False,
                "reason": "Complete required scopes exceed the existing bounded comparisons",
                "next_action": "Run all required scopes; preserve cutoffs and known discrepancies",
                "dependencies": ["identity_and_canonical_state", "coverage_and_quality"],
                "source_ref": reference,
                "source_sha256": digest,
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


def parity_report(connection: Connection[Any], repo: Path) -> dict[str, Any]:
    report = migration_report(repo)
    ready = connection.execute("SELECT to_regclass('football.resolution_parity_work')").fetchone()
    if not ready or not ready[0]:
        return report
    rows = connection.execute(
        """SELECT b.work_id,b.outcome,w.state,w.requested_at,e.actor,e.reason
           FROM football.resolution_parity_work b JOIN football.work_items w USING(work_id)
           JOIN football.resolution_review_events e USING(request_id)
           ORDER BY w.requested_at DESC,w.work_id DESC LIMIT 20"""
    ).fetchall()
    latest = connection.execute(
        "SELECT outcome FROM football.resolution_parity_work b "
        "JOIN football.work_items w USING(work_id) "
        "WHERE outcome IS NOT NULL ORDER BY w.finished_at DESC,w.work_id DESC LIMIT 1"
    ).fetchone()
    completed = [row for row in rows if row[1] is not None]
    for row in completed:
        if sha256_json(row[1]["report"]) != row[1]["report_sha256"]:
            raise ValueError("parity verification receipt checksum mismatch")
    if latest:
        if sha256_json(latest[0]["report"]) != latest[0]["report_sha256"]:
            raise ValueError("parity verification receipt checksum mismatch")
        database = connection.execute(
            "SELECT current_database(),oid FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        assert database is not None
        bound = latest[0]["report"].get("current_diagnostics", {}).get("database_identity")
        fresh = latest[0]["report"]["source_sha256"] == report["source_sha256"] and bound == {
            "name": database[0],
            "oid": database[1],
        }
        report.update(latest[0]["report"])
        report["fresh_for_tracked_evidence"] = fresh
        if not fresh:
            report["status"] = "BLOCKED"
            report["blockers"] = [
                *report["blockers"],
                "Verification is for different evidence or database; recheck parity",
            ]
    for item in report["items"]:
        item["verification_history"] = [
            {
                "work_id": str(row[0]),
                "state": row[2],
                "requested_at": str(row[3]),
                "actor": row[4],
                "reason": row[5],
                "report_sha256": row[1]["report_sha256"] if row[1] else None,
                "verified_at": row[1]["report"]["verified_at"] if row[1] else None,
                "check": historical_check(row[1], item["case_key"]),
            }
            for row in rows
        ]
    report["evidence_version"] = sha256_json(report)
    return report


def historical_check(outcome: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if outcome is None:
        return None
    check = next((item for item in outcome["report"]["items"] if item["case_key"] == key), None)
    return (
        {
            k: v
            for k, v in check.items()
            if k not in {"current_diagnostics", "retained_verification"}
        }
        if check
        else None
    )


def migration_page(
    repo: Path, view: str, query: dict[str, Any], connection: Connection[Any] | None = None
) -> dict[str, Any]:
    report = parity_report(connection, repo) if connection is not None else migration_report(repo)
    if view == "cutover" and connection is not None:
        from football.product.resolution_stages import stage_controls

        report["stages"] = stage_controls(connection, report["stages"])
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


def migration_detail(connection: Connection[Any], repo: Path, key: str) -> dict[str, Any]:
    if key.startswith("stage:"):
        from football.product.resolution_stages import projection_digest, stage_controls

        stages = stage_controls(connection, migration_report(repo)["stages"])
        result = next((stage for stage in stages if stage["case_key"] == key), {})
        if not result:
            raise ValueError("unknown migration stage")
        if result["order"] == 8:
            result["current_projection"] = projection_digest(connection, "product_serving_fixtures")
        return result
    report = parity_report(connection, repo)
    result = next((item.copy() for item in report["items"] if item["case_key"] == key), {})
    if not result:
        raise ValueError("unknown required parity check")
    result.update(overall_status=report["status"], exceptions=report["exceptions"])
    return result
