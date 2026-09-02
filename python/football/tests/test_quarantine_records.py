from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from football.ingestion import QuarantineReasonV1, QuarantineRecordError, QuarantineRecordV1


def test_quarantine_record_preserves_checksums_and_evidence() -> None:
    record = _record()

    assert record.to_dict()["reason_code"] == "IDENTITY_UNRESOLVED"
    assert record.to_dict()["details"] == {"candidates": 2}
    assert len(record.sha256) == 64


def test_quarantine_record_rejects_invalid_reason_checksums_and_time() -> None:
    with pytest.raises(QuarantineRecordError, match="reason"):
        _record(reason_code=cast(QuarantineReasonV1, "NETWORK_FAILURE"))
    with pytest.raises(QuarantineRecordError, match="SHA-256"):
        _record(source_snapshot_sha256="bad")
    with pytest.raises(QuarantineRecordError, match="precedes"):
        _record(last_seen_at=datetime(2025, 1, 1, tzinfo=UTC))


def test_quarantine_record_rejects_negative_attempts() -> None:
    with pytest.raises(QuarantineRecordError, match="attempt count"):
        _record(attempt_count=-1)


def _record(
    *,
    reason_code: QuarantineReasonV1 = "IDENTITY_UNRESOLVED",
    source_snapshot_sha256: str = "a" * 64,
    last_seen_at: datetime = datetime(2026, 1, 2, tzinfo=UTC),
    attempt_count: int = 2,
) -> QuarantineRecordV1:
    return QuarantineRecordV1(
        quarantine_id="quarantine-1",
        provider_id="totalcorner_api",
        resource_identity="match:provider-1",
        source_snapshot_sha256=source_snapshot_sha256,
        source_resource_sha256="b" * 64,
        canonical_candidate_id=None,
        reason_code=reason_code,
        details={"candidates": 2},
        policy_version="resolution-v1",
        first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_seen_at=last_seen_at,
        attempt_count=attempt_count,
        status="NEEDS_REVIEW",
        reviewer=None,
        resolution_ref=None,
    )
