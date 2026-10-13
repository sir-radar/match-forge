from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from football.product import identity_admission, identity_audit
from football.product.domain import stable_id


class _Result:
    def fetchone(self) -> tuple[str]:
        return ("England",)


class _Connection:
    def execute(self, *_args: object) -> _Result:
        return _Result()


@pytest.fixture(autouse=True)
def no_admissions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_audit, "_admission_states", lambda _connection: {})
    monkeypatch.setattr(identity_audit, "_legacy_manifest_counts", lambda _connection: {})


def test_identity_audit_classifies_origin_and_crosswalk_using_shared_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = stable_id("team", "api_football", "42")
    rows = [
        (uuid4(), canonical, "api_football", "42", "deterministic", 1, "England", uuid4()),
        (uuid4(), canonical, "fotmob", "9825", "explicit_crosswalk", 1, "England", uuid4()),
    ]
    monkeypatch.setattr(
        identity_audit, "mapping_rows", lambda _connection, kind: rows if kind == "team" else []
    )
    monkeypatch.setattr(
        identity_admission,
        "verify_source_identifier",
        lambda *_args: {
            "source_resource_id": "verified",
            "acquired_at": "2026-10-01T00:00:00+00:00",
        },
    )
    connection: Any = _Connection()
    report = identity_audit.audit_report(connection, Path("unused"))
    assert report["contract"] == "ProviderIdentityAuditV2"
    assert report["status"] == "PASS"
    assert report["verified_shared_identity_count"] == 1
    assert report["mapping_classifications"] == {"CROSSWALK": 1, "ORIGIN_ANCHOR": 1}
    assert report["findings"] == []

    rows[1] = (*rows[1][:4], "deterministic", *rows[1][5:])
    report = identity_audit.audit_report(connection, Path("unused"))
    assert report["status"] == "FAIL"
    assert report["unsafe_shared_identity_count"] == 1
    assert report["mapping_classifications"] == {"ORIGIN_ANCHOR": 1, "UNRESOLVED": 1}
    findings: Any = report["findings"]
    assert findings[0]["classification"] == "UNRESOLVED"


def test_identity_audit_retains_contradictory_and_missing_source_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = stable_id("team", "api_football", "42")
    rows = [
        (uuid4(), canonical, "api_football", "40", "deterministic", 1, "England", uuid4()),
        (uuid4(), canonical, "fotmob", "9825", "explicit_crosswalk", 1, "England", uuid4()),
    ]
    monkeypatch.setattr(
        identity_audit, "mapping_rows", lambda _connection, kind: rows if kind == "team" else []
    )
    monkeypatch.setattr(
        identity_admission,
        "verify_source_identifier",
        lambda *_args: {
            "source_resource_id": "verified",
            "acquired_at": "2026-10-01T00:00:00+00:00",
        },
    )
    connection: Any = _Connection()
    report = identity_audit.audit_report(connection)
    findings: Any = report["findings"]
    assert findings[0]["classification"] == "CONTRADICTORY"
    assert report["mapping_classifications"] == {"CONTRADICTORY": 1, "CROSSWALK": 1}
    monkeypatch.setattr(identity_admission, "verify_source_identifier", lambda *_args: None)
    report = identity_audit.audit_report(connection)
    assert report["mapping_classifications"] == {"UNRESOLVED": 2}
    assert report["unsafe_shared_identity_count"] == 1
