from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from football.ingestion import (
    QuarantineReprocessError,
    QuarantineReprocessRequestV1,
    ReprocessTriggerV1,
)


def test_reprocess_request_is_append_only_and_canonical() -> None:
    request = _request()

    assert request.to_dict()["source_quarantine_id"] == "quarantine-1"
    assert len(request.sha256) == 64


def test_reprocess_request_requires_supported_trigger_and_timezone() -> None:
    with pytest.raises(QuarantineReprocessError, match="trigger"):
        _request(trigger=cast(ReprocessTriggerV1, "NETWORK_RETRY"))
    with pytest.raises(QuarantineReprocessError, match="timezone-aware"):
        _request(scheduled_at=datetime(2026, 1, 1))


def _request(
    *,
    trigger: ReprocessTriggerV1 = "MAPPING_REVIEWED",
    scheduled_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> QuarantineReprocessRequestV1:
    return QuarantineReprocessRequestV1(
        request_id="reprocess-1",
        source_quarantine_id="quarantine-1",
        trigger=trigger,
        trigger_ref="decision-1",
        policy_version="resolution-v2",
        scheduled_at=scheduled_at,
    )
