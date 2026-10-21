from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from football.contracts.source import canonical_json_bytes
from football.providers import (
    FootballDataUkAcquisitionEvidenceStoreV1,
    FootballDataUkAcquisitionEvidenceV1,
    FootballDataUkSourceResourceV1,
)
from football.providers.football_data_uk_evidence import FootballDataUkAcquisitionEvidenceError


def test_acquisition_evidence_immutably_bundles_the_frozen_source_receipts(tmp_path: Path) -> None:
    evidence = FootballDataUkAcquisitionEvidenceV1(receipts=_receipts())
    store = FootballDataUkAcquisitionEvidenceStoreV1(tmp_path)

    write = store.publish(evidence)
    retry = store.publish(evidence)

    assert write.status == "acquired"
    assert retry.status == "verified_existing"
    assert write.path.read_bytes() == evidence.to_bytes()
    receipts = evidence.to_dict()["receipts"]
    assert isinstance(receipts, list)
    overlap_receipt = receipts[2]
    assert isinstance(overlap_receipt, dict)
    assert overlap_receipt["source_path"] == "mmz4281/1516/E0.csv"
    assert len(evidence.sha256) == 64


def test_acquisition_evidence_reader_preserves_published_bytes_and_logical_digest() -> None:
    evidence = FootballDataUkAcquisitionEvidenceV1(receipts=_receipts())
    restored = FootballDataUkAcquisitionEvidenceV1.from_bytes(evidence.to_bytes())
    assert restored == evidence
    assert restored.to_bytes() == evidence.to_bytes()
    assert restored.sha256 == evidence.sha256


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract", "unsupported"),
        ("provider_id", "another_provider"),
        ("provider_competition_code", "wrong"),
        ("adapter_version", "changed"),
        ("raw_byte_size", True),
        ("http_status", "200"),
        ("request_started_at", "2026-09-04T16:21:00+00:00"),
        ("observed_by_matchforge_at", "2026-09-04T16:20:00"),
        ("http_etag", 5),
        ("source_path", "../E0.csv"),
        ("extra", "unknown"),
    ],
)
def test_acquisition_evidence_reader_rejects_changed_receipt_metadata(
    field: str, value: object
) -> None:
    evidence = FootballDataUkAcquisitionEvidenceV1(receipts=_receipts()).to_dict()
    receipts = evidence["receipts"]
    assert isinstance(receipts, list)
    receipts[0][field] = value
    with pytest.raises(FootballDataUkAcquisitionEvidenceError):
        FootballDataUkAcquisitionEvidenceV1.from_bytes(canonical_json_bytes(evidence) + b"\n")


@pytest.mark.parametrize("payload", [b"null", b"[]", b"{}", b'{"receipts":[null]}', b"\xff"])
def test_acquisition_evidence_reader_rejects_invalid_structure(payload: bytes) -> None:
    with pytest.raises(FootballDataUkAcquisitionEvidenceError):
        FootballDataUkAcquisitionEvidenceV1.from_bytes(payload)


@pytest.mark.parametrize("change", ["newline", "duplicate", "version", "order"])
def test_acquisition_evidence_reader_rejects_noncanonical_bundles(change: str) -> None:
    evidence = FootballDataUkAcquisitionEvidenceV1(receipts=_receipts())
    payload = evidence.to_bytes()
    if change == "newline":
        payload = payload.rstrip(b"\n")
    elif change == "duplicate":
        payload = payload.replace(b'{"contract":', b'{"contract":"duplicate","contract":', 1)
    elif change == "version":
        payload = payload.replace(b"AcquisitionEvidenceV1", b"AcquisitionEvidenceV2", 1)
    else:
        payload = (
            canonical_json_bytes(
                {
                    "contract": evidence.contract,
                    "receipts": [r.to_dict() for r in reversed(_receipts())],
                }
            )
            + b"\n"
        )
    with pytest.raises(FootballDataUkAcquisitionEvidenceError):
        FootballDataUkAcquisitionEvidenceV1.from_bytes(payload)


def _receipts() -> tuple[FootballDataUkSourceResourceV1, ...]:
    observed_at = datetime(2026, 9, 4, 16, 20, tzinfo=UTC)
    return (
        FootballDataUkSourceResourceV1.from_payload(
            resource_type="schema_semantics_and_attribution",
            source_path="notes.txt",
            payload=b"terms",
            observed_by_matchforge_at=observed_at,
            http_status=200,
            content_type="text/plain",
        ),
        FootballDataUkSourceResourceV1.from_payload(
            resource_type="historical_league_csv",
            source_path="mmz4281/2526/E0.csv",
            payload=b"current",
            observed_by_matchforge_at=observed_at,
            http_status=200,
            content_type="text/csv",
        ),
        FootballDataUkSourceResourceV1.from_payload(
            resource_type="historical_league_csv",
            source_path="mmz4281/1516/E0.csv",
            payload=b"overlap",
            observed_by_matchforge_at=observed_at,
            http_status=200,
            content_type="text/csv",
        ),
    )
