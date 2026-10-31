"""Repeatable read-only parity diagnostics with durable, fenced verification history."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from psycopg import Connection, Error
from psycopg.types.json import Jsonb

from football.integrity import PostgresIntegrityVerifier
from football.product.domain import sha256_json
from football.product.identity_audit import audit_report
from football.product.resolution_data import missing_page
from football.product.resolution_migration import migration_report, verified_document
from football.work.contracts import (
    RetryClassification,
    RetryPolicy,
    WorkClaim,
    WorkRequest,
    WorkType,
)
from football.work.storage import WorkLeaseLost, WorkRegistry

REQUIRED_CHECKS = frozenset(
    {
        "provider_acquisition_and_source_bytes",
        "provider_native_parsing_and_normalization",
        "identity_and_canonical_state",
        "coverage_and_quality",
        "serving_and_read_models",
        "api_and_consumer_contracts",
        "feature_and_forecast_inputs",
        "work_orchestration",
        "history_coverage",
        "performance_external_reports",
        "forecast_artifacts_and_routing",
    }
)


def enqueue_parity(
    connection: Connection[Any], request_id: str, case_key: str, parent: UUID | None = None
) -> UUID | None:
    ready = connection.execute("SELECT to_regclass('football.resolution_parity_work')").fetchone()
    if not ready or not ready[0]:
        return None  # Rolling upgrade: existing identity/recovery work remains usable.
    previous = connection.execute(
        "SELECT work_id FROM football.resolution_parity_work WHERE request_id=%s", (request_id,)
    ).fetchone()
    if previous:
        return UUID(str(previous[0]))
    inputs = {
        "cause_request_id": str(UUID(request_id)),
        "case_key": case_key,
        "scope": "CURRENT_REGISTERED_DATA_AND_EXISTING_ARCHITECTURE_V2_COMPARISONS",
    }
    request = WorkRequest(
        work_type=WorkType.READ_MODEL_PROJECTION,
        semantic_key=f"resolution-parity:{UUID(request_id)}",
        input_hash=sha256_json(inputs),
        priority=0,
        available_at=datetime.now(UTC),
        max_attempts=2**31 - 1,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()),
        dependencies=(parent,) if parent else (),
        parent_work_id=parent,
    )
    WorkRegistry(connection).enqueue(request)
    connection.execute(
        "INSERT INTO football.resolution_parity_work(work_id,request_id,inputs) VALUES (%s,%s,%s)",
        (request.work_id, request_id, Jsonb(inputs)),
    )
    return request.work_id


def file_evidence(repo: Path, reference: dict[str, Any]) -> dict[str, Any]:
    relative = reference.get("path", reference.get("ref"))
    if not isinstance(relative, str):
        raise ValueError("comparison evidence reference must be a relative path")
    path = (repo / relative).resolve()
    path.relative_to(repo.resolve())
    result = {"source_ref": relative, "expected_sha256": reference["sha256"]}
    try:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            size = path.stat().st_size
    except OSError:
        return {**result, "status": "BLOCKED", "reason": "Retained comparison evidence unavailable"}
    return {
        **result,
        "actual_sha256": digest,
        "actual_bytes": size,
        "expected_bytes": reference.get("bytes"),
        "status": "PASS"
        if digest == reference["sha256"] and reference.get("bytes", size) == size
        else "FAIL",
        "reason": "Exact retained evidence checksum",
    }


def retained_comparisons(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    basis = verified_document(repo, report["source_ref"], report["source_sha256"])
    phase34 = next(item for item in basis["evidence_basis"] if "phase-34-2026" in item["ref"])
    comparison = verified_document(repo, phase34["ref"], phase34["sha256"])
    references = list(comparison["evidence_refs"])
    references.extend(
        {"path": path, "sha256": digest}
        for path, digest in comparison["comparisons"]["features"][
            "core_arithmetic_source_sha256"
        ].items()
    )
    checks = [file_evidence(repo, item) for item in references]
    return {
        "scope": "RETAINED_COMPARISON_ARTIFACTS_AND_ORIGINAL_ARITHMETIC; NO_NEW_MODEL_RUN",
        "checks": checks,
        "source_ref": phase34["ref"],
        "source_sha256": phase34["sha256"],
        "status": "FAIL"
        if any(item["status"] == "FAIL" for item in checks)
        else "BLOCKED"
        if any(item["status"] == "BLOCKED" for item in checks)
        else "PASS",
    }


def current_diagnostics(connection: Connection[Any], root: Path) -> dict[str, Any]:
    missing = missing_page(connection, root, {"page_size": 100})
    identity = audit_report(connection, root)
    findings = cast(list[Any], identity.pop("findings"))
    canonical = connection.execute(
        "SELECT disposition,count(*) FROM football.canonical_resource_resolutions "
        "WHERE predecessor_decision_id IS NULL GROUP BY disposition ORDER BY disposition"
    ).fetchall()
    fixtures = connection.execute(
        "SELECT identity_status,count(*) FROM football.product_fixtures "
        "GROUP BY identity_status ORDER BY identity_status"
    ).fetchall()
    datasets = [
        PostgresIntegrityVerifier(connection, root).verify_dataset(row[0]).to_dict()
        for row in connection.execute(
            "SELECT id FROM football.dataset_versions ORDER BY id"
        ).fetchall()
    ]
    database = connection.execute(
        "SELECT current_database(),oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    assert database is not None
    snapshot = connection.execute("SELECT pg_current_snapshot()").fetchone()
    assert snapshot is not None
    return {
        "missing_data": missing,
        "dataset_integrity": {
            "total": len(datasets),
            "failed": sum(item["status"] != "PASS" for item in datasets),
            "results_sha256": sha256_json(datasets),
            "failures": [item for item in datasets if item["status"] != "PASS"][:100],
        },
        "identity": {
            **identity,
            "findings_sha256": sha256_json(findings),
            "finding_count": len(findings),
        },
        "canonical_root_decisions": dict(canonical),
        "fixture_identity_counts": dict(fixtures),
        "database_identity": {"name": database[0], "oid": database[1]},
        "database_snapshot": str(snapshot[0]),
    }


def verify_parity(
    connection: Connection[Any], repo: Path, root: Path, inputs: dict[str, Any]
) -> dict[str, Any]:
    report = migration_report(repo)
    retained = retained_comparisons(repo, report)
    current = current_diagnostics(connection, root)
    from football.product.resolution_retirement import legacy_inventory

    current["legacy_retirement_preparation"] = legacy_inventory(connection, repo)
    checked_at = datetime.now(UTC).isoformat()
    for item in report["items"]:
        item["source_recorded_at"] = item.get("verified_at")
        item["verified_at"] = checked_at
        item["current_diagnostics"] = current
        item["retained_verification"] = retained
        # Re-verifying retained files cannot extend their original comparison universe.
        if retained["status"] == "FAIL":
            item["status"] = "FAIL"
            item["reason"] = "Retained comparison evidence or compared arithmetic changed"
        item["next_action"] = (
            "Resolve listed source/identity blockers and run complete old/new "
            "production scopes under the existing comparison contract."
        )
    status = overall_status(report, retained, current)
    report.update(
        status=status,
        verification_inputs=inputs,
        verified_at=checked_at,
        current_diagnostics=current,
        retained_verification=retained,
        scope="COMPLETE_REQUIRED_PRODUCTION_SCOPES_VERIFIED"
        if status == "PASS"
        else "CURRENT_READ_ONLY_DIAGNOSTICS_AND_RETAINED_COMPARISON_RECHECK; "
        "COMPLETE_PRODUCTION_PARITY_NOT_ESTABLISHED",
    )
    report.pop("stages")  # This report never changes routing or rollback state.
    report.pop("evidence_version")
    return report


def publish_parity(
    connection: Connection[Any], repo: Path, root: Path, claim: WorkClaim
) -> dict[str, Any]:
    registry = WorkRegistry(connection)
    try:
        with connection.transaction():
            row = connection.execute(
                "SELECT inputs FROM football.resolution_parity_work WHERE work_id=%s",
                (claim.work_id,),
            ).fetchone()
            if not row or sha256_json(row[0]) != claim.input_hash:
                raise ValueError("parity work differs from its approved inputs")
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            report = verify_parity(connection, repo, root, row[0])
        outcome = {"report": report, "report_sha256": sha256_json(report)}
        with (
            connection.transaction(),
            registry.publication(claim, result_hash=sha256_json(outcome)),
        ):
            connection.execute(
                "UPDATE football.resolution_parity_work SET outcome=%s WHERE work_id=%s",
                (Jsonb(outcome), claim.work_id),
            )
        return {
            "status": "PROCESSED",
            "work_id": str(claim.work_id),
            "parity_status": report["status"],
            "report_sha256": outcome["report_sha256"],
        }
    except WorkLeaseLost:
        return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
    except (Error, ValueError, OSError, KeyError, TypeError) as error:
        connection.rollback()
        try:
            registry.fail(
                claim,
                RetryClassification.RETRYABLE
                if isinstance(error, Error)
                else RetryClassification.BLOCKED_EXTERNAL,
                error_code="PARITY_VERIFICATION_UNAVAILABLE",
                error_message=type(error).__name__ if isinstance(error, Error) else str(error),
            )
        except WorkLeaseLost:
            return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
        return {
            "status": "RETRY_WAIT" if isinstance(error, Error) else "BLOCKED",
            "work_id": str(claim.work_id),
        }


def overall_status(
    report: dict[str, Any], retained: dict[str, Any], current: dict[str, Any]
) -> str:
    if retained["status"] == "FAIL" or any(item["status"] == "FAIL" for item in report["items"]):
        return "FAIL"
    keys = {item["case_key"].removeprefix("parity:") for item in report["items"]}
    full = keys >= REQUIRED_CHECKS and all(
        item["status"] == "PASS" and item.get("required_runtime_scopes_complete") is True
        for item in report["items"]
    )
    unresolved = sum(
        current["identity"]["mapping_classifications"].get(key, 0)
        for key in ("UNRESOLVED", "CONTRADICTORY", "REVOKED")
    )
    exceptions = report["exceptions"]
    if (
        full
        and retained["status"] == "PASS"
        and current["missing_data"]["total"] == 0
        and current["dataset_integrity"]["failed"] == 0
        and unresolved == 0
        and current["identity"]["status"] == "PASS"
        and exceptions.get("generic_elo_conflicts", 0) == 0
        and exceptions.get("insufficient_history_targets", 0) == 0
    ):
        return "PASS"
    return "BLOCKED"
