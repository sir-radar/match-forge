from datetime import UTC, datetime

import pytest
from football.contracts import FoundationHardeningReportV1, FoundationReportError


def test_foundation_report_requires_all_evidence_for_pass() -> None:
    report = _report()

    assert report.status == "PASS"
    assert report.to_dict()["status"] == "PASS"
    assert len(report.sha256) == 64


def test_foundation_report_is_fail_closed_for_missing_or_failed_evidence() -> None:
    assert _report(ci_status="NOT_RUN").status == "NOT_RUN"
    assert _report(provider_platform_status="FAIL").status == "FAIL"
    assert _report(observability_status="PASS_WITH_WARNINGS").status == "PASS_WITH_WARNINGS"


def test_foundation_report_rejects_missing_evidence_refs_and_invalid_policy_identity() -> None:
    with pytest.raises(FoundationReportError, match="evidence references"):
        _report(evidence_refs=())
    with pytest.raises(FoundationReportError, match="dependency lock"):
        _report(dependency_lock_sha256="invalid")


def _report(**overrides: object) -> FoundationHardeningReportV1:
    values: dict[str, object] = {
        "report_id": "foundation-1",
        "policy_version": "foundation-gate-v1",
        "created_at": datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        "provider_platform_status": "PASS",
        "dependency_graph_status": "PASS",
        "rebuild_status": "PASS",
        "ci_status": "PASS",
        "observability_status": "PASS",
        "backup_restore_status": "PASS",
        "integrity_status": "PASS",
        "competition_rules_status": "PASS",
        "code_git_sha": "a" * 40,
        "dependency_lock_sha256": "b" * 64,
        "evidence_refs": ("provider-evidence-1", "integrity-evidence-1"),
    }
    values.update(overrides)
    return FoundationHardeningReportV1(**values)  # type: ignore[arg-type]
