from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from football.providers import (
    FootballDataUkAcquisitionEvidenceStoreV1,
    FootballDataUkAcquisitionEvidenceV1,
    FootballDataUkSourceResourceV1,
)


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
