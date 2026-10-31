"""No partial comparisons, missing bytes or undocumented exceptions can pass parity."""

from copy import deepcopy

import pytest
from football.product.resolution_parity import REQUIRED_CHECKS, file_evidence, overall_status


def complete():
    return (
        {
            "items": [
                {
                    "case_key": "parity:" + key,
                    "status": "PASS",
                    "required_runtime_scopes_complete": True,
                }
                for key in sorted(REQUIRED_CHECKS)
            ],
            "exceptions": {"generic_elo_conflicts": 0, "insufficient_history_targets": 0},
        },
        {"status": "PASS"},
        {
            "missing_data": {"total": 0},
            "dataset_integrity": {"failed": 0},
            "identity": {"status": "PASS", "mapping_classifications": {}},
        },
    )


@pytest.mark.parametrize("status", ["FAIL", "BLOCKED", "NOT_RUN", "PASS_WITH_WARNINGS"])
def test_incomplete_required_comparison_cannot_pass(status):
    report, retained, current = complete()
    report["items"][0]["status"] = status
    assert overall_status(report, retained, current) != "PASS"


def test_complete_scope_proof_is_required_even_for_exact_bounded_pairs():
    report, retained, current = complete()
    report["items"][0]["required_runtime_scopes_complete"] = False
    assert overall_status(report, retained, current) == "BLOCKED"
    report["items"][0]["required_runtime_scopes_complete"] = True
    assert overall_status(report, retained, current) == "PASS"
    for key in ("generic_elo_conflicts", "insufficient_history_targets"):
        changed = deepcopy(report)
        changed["exceptions"][key] = 1
        assert overall_status(changed, retained, current) == "BLOCKED"
    for scope, field in (("missing_data", "total"), ("dataset_integrity", "failed")):
        changed = deepcopy(current)
        changed[scope][field] = 1
        assert overall_status(report, retained, changed) == "BLOCKED"


def test_retained_evidence_missing_changed_and_path_escape(tmp_path):
    import hashlib

    path = tmp_path / "retained.json"
    path.write_bytes(b"original")
    ref = {"path": "retained.json", "sha256": hashlib.sha256(b"original").hexdigest()}
    assert file_evidence(tmp_path, ref)["status"] == "PASS"
    assert file_evidence(tmp_path, {**ref, "bytes": 999})["status"] == "FAIL"
    path.write_bytes(b"changed")
    assert file_evidence(tmp_path, ref)["status"] == "FAIL"
    path.unlink()
    assert file_evidence(tmp_path, ref)["status"] == "BLOCKED"
    with pytest.raises(ValueError):
        file_evidence(tmp_path, {**ref, "path": "../outside"})


def test_missing_required_checks_cannot_be_ignored():
    report, retained, current = complete()
    report["items"].pop()
    assert overall_status(report, retained, current) == "BLOCKED"
    report["items"] = []
    assert overall_status(report, retained, current) == "BLOCKED"
