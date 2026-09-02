from datetime import UTC, datetime

import pytest
from football.contracts import ProviderAcceptanceError, ProviderPlatformAcceptanceReportV1


def test_provider_acceptance_requires_two_end_to_end_namespaces_for_pass() -> None:
    report = _report(approved_provider_refs=("statsbomb_open_data", "provider_b"))

    assert report.status == "PASS"
    assert report.to_dict()["status"] == "PASS"
    assert len(report.sha256) == 64


def test_provider_acceptance_fails_when_only_one_provider_is_exercised() -> None:
    assert _report(approved_provider_refs=("statsbomb_open_data",)).status == "FAIL"
    assert _report(approved_provider_refs=(), end_to_end_status="NOT_RUN").status == "NOT_RUN"


def test_provider_acceptance_preserves_warnings_and_rejects_duplicate_refs() -> None:
    assert (
        _report(
            approved_provider_refs=("statsbomb_open_data", "provider_b"),
            runtime_safety_status="PASS_WITH_WARNINGS",
        ).status
        == "PASS_WITH_WARNINGS"
    )
    with pytest.raises(ProviderAcceptanceError, match="must be unique"):
        _report(evidence_refs=("evidence-1", "evidence-1"))


def _report(**overrides: object) -> ProviderPlatformAcceptanceReportV1:
    values: dict[str, object] = {
        "report_id": "provider-acceptance-1",
        "policy_version": "provider-platform-gate-v1",
        "created_at": datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        "approved_provider_refs": ("statsbomb_open_data", "provider_b"),
        "end_to_end_status": "PASS",
        "schema_contract_status": "PASS",
        "runtime_safety_status": "PASS",
        "secret_boundary_status": "PASS",
        "resolution_ledger_status": "PASS",
        "quarantine_reprocessing_status": "PASS",
        "conflict_reconciliation_status": "PASS",
        "change_set_publication_status": "PASS",
        "evidence_refs": ("sync-evidence-1", "resolution-evidence-1"),
    }
    values.update(overrides)
    return ProviderPlatformAcceptanceReportV1(**values)  # type: ignore[arg-type]
