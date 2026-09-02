from datetime import UTC, datetime
from typing import Any, cast

import pytest
from football.providers import ProviderObservabilityError, ProviderObservabilitySnapshotV1


def test_observability_snapshot_is_machine_readable_and_hashable() -> None:
    snapshot = _snapshot()

    payload = snapshot.to_dict()
    assert payload["contract"] == "ProviderObservabilitySnapshotV1"
    assert payload["freshness_status"] == "FRESH"
    assert payload["alert_conditions"] == ["QUARANTINE_ITEMS_PRESENT"]
    assert len(snapshot.sha256) == 64


def test_observability_surfaces_staleness_and_open_circuit() -> None:
    snapshot = _snapshot(
        observed_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        last_successful_sync_at=datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
        circuit_state="OPEN",
        quarantine_count=0,
    )

    assert snapshot.freshness_status == "STALE"
    assert snapshot.alert_conditions == ("PROVIDER_OR_RESOURCE_STALE", "PROVIDER_CIRCUIT_OPEN")


def test_observability_rejects_invalid_counts_and_timestamps() -> None:
    with pytest.raises(ProviderObservabilityError, match="cannot exceed"):
        _snapshot(resolution_attempt_count=1, resolution_success_count=2)
    with pytest.raises(ProviderObservabilityError, match="must include a timezone"):
        _snapshot(observed_at=datetime(2026, 9, 2, 12, 0))


def _snapshot(**overrides: object) -> ProviderObservabilitySnapshotV1:
    values: dict[str, object] = {
        "provider_id": "statsbomb_open_data",
        "resource_id": "events:competition=43:season=106",
        "observed_at": datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        "last_successful_sync_at": datetime(2026, 9, 2, 11, 59, tzinfo=UTC),
        "last_successful_acquisition_at": datetime(2026, 9, 2, 11, 59, tzinfo=UTC),
        "last_successful_publication_at": datetime(2026, 9, 2, 11, 59, tzinfo=UTC),
        "freshness_target_seconds": 3600,
        "discovered_count": 3,
        "fetched_count": 2,
        "unchanged_count": 1,
        "bytes_acquired": 1024,
        "validation_failure_count": 0,
        "resolution_attempt_count": 3,
        "resolution_success_count": 3,
        "quarantine_count": 1,
        "unresolved_conflict_count": 0,
        "retry_count": 0,
        "rate_limit_response_count": 0,
        "processing_latency_ms": 250,
        "publication_failure_count": 0,
        "reconciliation_failure_count": 0,
        "change_set_emission_count": 1,
        "cursor_lag_seconds": 0,
        "circuit_state": "CLOSED",
    }
    values.update(overrides)
    return ProviderObservabilitySnapshotV1(**cast(dict[str, Any], values))
