from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from football.providers import (
    FootballDataUkRawStoreV1,
    FootballDataUkSourceResourceError,
    FootballDataUkSourceResourceV1,
)


def test_football_data_raw_store_preserves_content_addressed_bytes_idempotently(
    tmp_path: Path,
) -> None:
    payload = b"Div,Date\nE0,01/01/26\n"
    receipt = _receipt(payload)
    store = FootballDataUkRawStoreV1(tmp_path)

    first = store.publish(receipt, payload)
    second = store.publish(receipt, payload)

    assert first.status == "acquired"
    assert second.status == "verified_existing"
    assert first.relative_path == second.relative_path
    assert "provider=football_data_uk" in first.relative_path
    assert f"sha256={receipt.raw_sha256}" in first.relative_path
    assert first.path.read_bytes() == payload


def test_football_data_raw_store_rejects_payload_that_does_not_match_receipt(
    tmp_path: Path,
) -> None:
    receipt = _receipt(b"original")

    with pytest.raises(FootballDataUkSourceResourceError, match="does not match source receipt"):
        FootballDataUkRawStoreV1(tmp_path).publish(receipt, b"changed")

    assert not list(tmp_path.rglob("*"))


def _receipt(payload: bytes) -> FootballDataUkSourceResourceV1:
    return FootballDataUkSourceResourceV1.from_payload(
        resource_type="historical_league_csv",
        source_path="mmz4281/2526/E0.csv",
        payload=payload,
        observed_by_matchforge_at=datetime(2026, 9, 4, 13, 0, tzinfo=UTC),
        http_status=200,
        content_type="text/csv",
    )
