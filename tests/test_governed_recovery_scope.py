"""VERIFIED_GOVERNED_SCOPE: approved exclusions only, bound to evidence, never full recovery."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import backup_recovery, manual_backup
from scripts.backup_destination import BackupError
from scripts.recovery_scope import (
    EMPTY_SHA256,
    GOVERNED_SCOPE,
    exclude_disposed,
    governed_hash,
    unavailable_hash,
    validate_governed,
)

A, B = "a" * 64, "b" * 64


def _owner(identity: str, digest: str, table: str = "source_snapshots") -> dict[str, Any]:
    return {"table": table, "keys": {"id": identity}, "registered_sha256": digest}


def _record(digest: str, decision: str = "APPLY_RECOVERY_SCOPE_DISPOSITIONS_V1") -> dict[str, str]:
    return {
        "disposition": "SYNTHETIC_TEST_LINEAGE",
        "registered_path": "p",
        "registered_sha256": digest,
        "evidence_reference": "docs/evidence/gaps.json",
        "evidence_sha256": "e" * 64,
        "decision_reference": decision,
        "code_commit_sha": "c" * 40,
    }


SHARED = {
    "root": "data",
    "path": "normalized/second.parquet",
    "sha256": A,
    "size": None,
    "registrations": [
        _owner("one", A, "dataset_files"),
        _owner("two", A, "dataset_files"),
        _owner("three", A, "dataset_files"),
    ],
}
RECORDS = {("dataset_files", key): _record(A) for key in ("one", "two", "three")}


def _plan(excluded: list[dict[str, Any]], records: dict[Any, Any] = RECORDS) -> dict[str, Any]:
    _, disposed = exclude_disposed(
        excluded,
        {key: (value["disposition"], value["registered_sha256"]) for key, value in records.items()},
    )
    return {
        "scope": "RECOVERABLE_ONLY",
        "database": "football",
        "database_oid": "16384",
        "locations": {},
        "unavailable": [],
        "unavailable_sha256": EMPTY_SHA256,
        "excluded": disposed,
        "excluded_sha256": unavailable_hash(disposed),
        "governed_sha256": governed_hash(disposed, records),
    }


def test_shared_path_is_governed_only_when_every_owner_is_disposed() -> None:
    assert len(_plan([SHARED])["excluded"]) == 1
    partial = {key: value for key, value in RECORDS.items() if key[1] != "three"}
    with pytest.raises(ValueError, match="per owner"):
        governed_hash([{**SHARED, "dispositions": ["SYNTHETIC_TEST_LINEAGE"] * 3}], partial)


def test_binding_changes_with_any_approval_or_dependency_detail() -> None:
    plan = _plan([SHARED])
    other_decision = {**RECORDS, ("dataset_files", "two"): _record(A, "SOME_OTHER_DECISION")}
    assert governed_hash(plan["excluded"], other_decision) != plan["governed_sha256"]
    moved = [{**plan["excluded"][0], "path": "normalized/elsewhere.parquet"}]
    assert governed_hash(moved, RECORDS) != plan["governed_sha256"]
    # A disposition bound to another checksum does not govern this registration.
    stale = {**RECORDS, ("dataset_files", "one"): _record(B)}
    with pytest.raises(ValueError, match="per owner"):
        governed_hash(plan["excluded"], stale)


@pytest.mark.parametrize(
    ("change", "message"),
    (
        (
            lambda p: p.update(unavailable=[SHARED], unavailable_sha256=unavailable_hash([SHARED])),
            "zero unavailable",
        ),
        (lambda p: p.update(excluded=[], excluded_sha256=EMPTY_SHA256), "zero unavailable"),
        (lambda p: p.pop("governed_sha256"), "disposition binding"),
        (lambda p: p.update(governed_sha256="not-a-digest"), "disposition binding"),
        (lambda p: p["excluded"][0].update(dispositions=["SYNTHETIC_TEST_LINEAGE"]), "every owner"),
        (lambda p: p.update(excluded_sha256=B), "bindings"),
    ),
)
def test_invalid_governed_plans_fail_closed(change: Any, message: str) -> None:
    plan = copy.deepcopy(_plan([SHARED]))
    validate_governed(plan)
    change(plan)
    with pytest.raises(ValueError, match=message):
        validate_governed(plan)


def _capture(tmp_path: Path, status: str, scope: dict[str, Any] | None) -> Path:
    report: dict[str, Any] = {"version": 1, "status": status}
    if scope is not None:
        report["recovery_scope"] = scope
    (tmp_path / "recovery.json").write_text(json.dumps(report))
    return tmp_path


def _governed_scope() -> dict[str, Any]:
    plan = _plan([SHARED])
    return {
        "scope": GOVERNED_SCOPE,
        "full_recovery": False,
        **{
            key: plan[key]
            for key in (
                "unavailable",
                "unavailable_sha256",
                "excluded",
                "excluded_sha256",
                "governed_sha256",
            )
        },
    }


@pytest.mark.parametrize(
    ("status", "scope", "kwargs", "message"),
    (
        # Strict FULL_RECOVERY never accepts scoped captures.
        ("CAPTURED_GOVERNED", "governed", {}, "unsupported"),
        ("CAPTURED_RECOVERABLE", "recoverable", {"allow_governed": True}, "unsupported"),
        # Status and recorded scope must agree.
        ("CAPTURED_GOVERNED", "recoverable", {"allow_governed": True}, "does not match"),
        ("CAPTURED_GOVERNED", None, {"allow_governed": True}, "does not match"),
        ("CAPTURED", "governed", {}, "does not match"),
        # A governed capture may not claim full recovery or drop its binding.
        ("CAPTURED_GOVERNED", "claims-full", {"allow_governed": True}, "cannot claim full"),
        ("CAPTURED_GOVERNED", "unbound", {"allow_governed": True}, "disposition binding"),
    ),
)
def test_capture_scope_checks(
    tmp_path: Path, status: str, scope: str | None, kwargs: dict[str, bool], message: str
) -> None:
    governed = _governed_scope()
    scopes: dict[str | None, dict[str, Any] | None] = {
        None: None,
        "governed": governed,
        "recoverable": {**governed, "scope": "RECOVERABLE_ONLY"},
        "claims-full": {**governed, "full_recovery": True},
        "unbound": {key: value for key, value in governed.items() if key != "governed_sha256"},
    }
    root = _capture(tmp_path, status, scopes[scope])
    with pytest.raises(ValueError, match=message):
        backup_recovery.verify_capture(root, **kwargs)


def test_governed_restore_rejects_any_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scope = _governed_scope()
    readers = [
        {"artifact_kind": "MODEL_ARTIFACT", "artifact_id": "retired", "status": "MISSING"},
        {"artifact_kind": "DATASET", "artifact_id": "kept", "status": "PASS"},
    ]
    report = {"recovery_scope": scope, "artifact_reader_results": readers}
    restored = {
        "unavailable": [],
        "excluded": scope["excluded"],
        "excluded_sha256": scope["excluded_sha256"],
        "governed_sha256": scope["governed_sha256"],
        "references": [],
    }
    records = {("model_artifacts", "retired"): _record(A)}
    state: dict[str, Any] = {"inventory": restored, "readers": readers, "files": "COMPLETE"}
    monkeypatch.setattr(backup_recovery, "inventory", lambda *_: state["inventory"])
    monkeypatch.setattr(backup_recovery, "capture_files", lambda *_: {"status": state["files"]})
    monkeypatch.setattr(backup_recovery, "artifact_reader_results", lambda *_: state["readers"])
    monkeypatch.setattr(backup_recovery, "disposition_records", lambda _: records)

    def verify() -> dict[str, Any]:
        return backup_recovery.verify_governed_dependencies(None, tmp_path, report, {})  # type: ignore[arg-type]

    result = verify()
    assert result["full_recovery"] is False and result["excluded_dependencies"] == 1
    for change, message in (
        ({"inventory": {**restored, "unavailable": [SHARED]}}, "differs"),
        ({"inventory": {**restored, "governed_sha256": B}}, "differs"),
        ({"inventory": {**restored, "excluded_sha256": B}}, "differs"),
        ({"files": "INCOMPLETE"}, "file verification"),
        ({"readers": readers[:1]}, "reader results differ"),
    ):
        state.update({"inventory": restored, "readers": readers, "files": "COMPLETE"} | change)
        with pytest.raises(ValueError, match=message):
            verify()
    # Only registrations retired as synthetic lineage may fail their reader.
    failing = [readers[0], {**readers[1], "status": "MISSING"}]
    state.update(inventory=restored, files="COMPLETE", readers=failing)
    report["artifact_reader_results"] = failing
    with pytest.raises(ValueError, match="outside the governed exclusions"):
        verify()


def test_admin_policy_keeps_full_recovery_strict_and_governed_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = _plan([SHARED])
    monkeypatch.setattr(manual_backup, "load_plan", lambda _: copy.deepcopy(plan))
    monkeypatch.setenv("MATCHFORGE_BACKUP_RECOVERABLE_INVENTORY", str(tmp_path / "plan.json"))
    monkeypatch.setenv("MATCHFORGE_BACKUP_SCOPE", GOVERNED_SCOPE)
    scope, loaded = manual_backup.admin_policy()
    details = manual_backup.policy_details(scope, loaded)
    assert details["governed_sha256"] == plan["governed_sha256"]
    assert details["excluded_dependencies"] == 1
    monkeypatch.setenv("MATCHFORGE_BACKUP_SCOPE", "FULL_RECOVERY")
    assert manual_backup.policy_details(*manual_backup.admin_policy())["governed_sha256"] is None
    unbound = {key: value for key, value in plan.items() if key != "governed_sha256"}
    monkeypatch.setattr(manual_backup, "load_plan", lambda _: unbound)
    monkeypatch.setenv("MATCHFORGE_BACKUP_SCOPE", GOVERNED_SCOPE)
    with pytest.raises(BackupError, match="inventory is invalid"):
        manual_backup.admin_policy()
