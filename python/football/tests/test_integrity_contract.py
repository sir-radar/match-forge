from datetime import UTC, datetime

import pytest
from football.contracts import IntegrityContractError, IntegrityVerificationReportV1


def test_integrity_report_requires_restore_and_all_checks_for_pass() -> None:
    report = _report()

    assert report.status == "PASS"
    assert report.to_dict()["status"] == "PASS"
    assert len(report.sha256) == 64


def test_integrity_report_does_not_treat_backup_without_restore_as_pass() -> None:
    report = _report(postgres_restore="NOT_RUN")

    assert report.status == "NOT_RUN"


def test_integrity_report_fails_closed_on_any_failed_check() -> None:
    report = _report(model_artifact_integrity="FAIL")

    assert report.status == "FAIL"
    with pytest.raises(IntegrityContractError, match="status"):
        _report(forecast_evaluation_integrity="UNKNOWN")


def _report(**overrides: object) -> IntegrityVerificationReportV1:
    values: dict[str, object] = {
        "report_id": "integrity-1",
        "policy_version": "foundation-integrity-v1",
        "created_at": datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        "postgres_backup": "PASS",
        "postgres_restore": "PASS",
        "raw_object_integrity": "PASS",
        "dataset_manifest_integrity": "PASS",
        "model_artifact_integrity": "PASS",
        "forecast_evaluation_integrity": "PASS",
        "code_git_sha": "a" * 40,
        "dependency_lock_sha256": "b" * 64,
    }
    values.update(overrides)
    return IntegrityVerificationReportV1(**values)  # type: ignore[arg-type]
