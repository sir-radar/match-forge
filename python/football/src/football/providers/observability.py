from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

FreshnessStatusV1 = Literal["FRESH", "STALE", "NEVER_SUCCEEDED"]
CircuitStateV1 = Literal["CLOSED", "OPEN", "HALF_OPEN"]
_CIRCUIT_STATES = frozenset(("CLOSED", "OPEN", "HALF_OPEN"))


class ProviderObservabilityError(ValueError):
    """A provider observability snapshot violates its versioned contract."""


@dataclass(frozen=True, slots=True)
class ProviderObservabilitySnapshotV1:
    """Machine-readable metrics for one provider resource at one observation time."""

    provider_id: str
    resource_id: str
    observed_at: datetime
    last_successful_sync_at: datetime | None
    last_successful_acquisition_at: datetime | None
    last_successful_publication_at: datetime | None
    freshness_target_seconds: int
    discovered_count: int
    fetched_count: int
    unchanged_count: int
    bytes_acquired: int
    validation_failure_count: int
    resolution_attempt_count: int
    resolution_success_count: int
    quarantine_count: int
    unresolved_conflict_count: int
    retry_count: int
    rate_limit_response_count: int
    processing_latency_ms: int
    publication_failure_count: int
    reconciliation_failure_count: int
    change_set_emission_count: int
    cursor_lag_seconds: int | None
    circuit_state: CircuitStateV1
    contract: str = "ProviderObservabilitySnapshotV1"
    schema_compatibility_failure_count: int = 0
    quota_exhaustion_count: int = 0
    resolution_review_backlog_count: int = 0
    dataset_rebuild_queue_count: int = 0
    stale_dependency_count: int = 0
    last_cursor_advanced_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_identity(self)
        _validate_timestamps(self)
        _validate_counts(self)

    @property
    def freshness_status(self) -> FreshnessStatusV1:
        if self.last_successful_sync_at is None:
            return "NEVER_SUCCEEDED"
        age_seconds = (self.observed_at - self.last_successful_sync_at).total_seconds()
        return "FRESH" if age_seconds <= self.freshness_target_seconds else "STALE"

    @property
    def alert_conditions(self) -> tuple[str, ...]:
        alerts = _freshness_alerts(self)
        alerts.extend(_failure_alerts(self))
        return tuple(alerts)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "resource_id": self.resource_id,
            "observed_at": self.observed_at.isoformat(),
            "last_successful_sync_at": _iso(self.last_successful_sync_at),
            "last_successful_acquisition_at": _iso(self.last_successful_acquisition_at),
            "last_successful_publication_at": _iso(self.last_successful_publication_at),
            "freshness_target_seconds": self.freshness_target_seconds,
            "freshness_status": self.freshness_status,
            "discovered_count": self.discovered_count,
            "fetched_count": self.fetched_count,
            "unchanged_count": self.unchanged_count,
            "bytes_acquired": self.bytes_acquired,
            "validation_failure_count": self.validation_failure_count,
            "resolution_attempt_count": self.resolution_attempt_count,
            "resolution_success_count": self.resolution_success_count,
            "quarantine_count": self.quarantine_count,
            "unresolved_conflict_count": self.unresolved_conflict_count,
            "retry_count": self.retry_count,
            "rate_limit_response_count": self.rate_limit_response_count,
            "processing_latency_ms": self.processing_latency_ms,
            "publication_failure_count": self.publication_failure_count,
            "reconciliation_failure_count": self.reconciliation_failure_count,
            "change_set_emission_count": self.change_set_emission_count,
            "cursor_lag_seconds": self.cursor_lag_seconds,
            "circuit_state": self.circuit_state,
            "schema_compatibility_failure_count": self.schema_compatibility_failure_count,
            "quota_exhaustion_count": self.quota_exhaustion_count,
            "resolution_review_backlog_count": self.resolution_review_backlog_count,
            "dataset_rebuild_queue_count": self.dataset_rebuild_queue_count,
            "stale_dependency_count": self.stale_dependency_count,
            "last_cursor_advanced_at": _iso(self.last_cursor_advanced_at),
            "alert_conditions": list(self.alert_conditions),
        }


def _validate_timestamp(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProviderObservabilityError(f"{field} must include a timezone")


def _validate_identity(snapshot: ProviderObservabilitySnapshotV1) -> None:
    if snapshot.contract != "ProviderObservabilitySnapshotV1":
        raise ProviderObservabilityError("unsupported provider observability contract")
    if not PROVIDER_PATTERN.fullmatch(snapshot.provider_id):
        raise ProviderObservabilityError("provider_id must use lowercase snake_case")
    if not snapshot.resource_id:
        raise ProviderObservabilityError("resource_id must not be empty")
    if snapshot.freshness_target_seconds <= 0:
        raise ProviderObservabilityError("freshness target must be positive")
    if snapshot.circuit_state not in _CIRCUIT_STATES:
        raise ProviderObservabilityError("circuit state is unsupported")


def _validate_timestamps(snapshot: ProviderObservabilitySnapshotV1) -> None:
    _validate_timestamp(snapshot.observed_at, "observed_at")
    for name, value in (
        ("last_successful_sync_at", snapshot.last_successful_sync_at),
        ("last_successful_acquisition_at", snapshot.last_successful_acquisition_at),
        ("last_successful_publication_at", snapshot.last_successful_publication_at),
        ("last_cursor_advanced_at", snapshot.last_cursor_advanced_at),
    ):
        if value is not None:
            _validate_timestamp(value, name)
            if value > snapshot.observed_at:
                raise ProviderObservabilityError(f"{name} must not be in the future")


def _validate_counts(snapshot: ProviderObservabilitySnapshotV1) -> None:
    count_fields = (
        "discovered_count",
        "fetched_count",
        "unchanged_count",
        "bytes_acquired",
        "validation_failure_count",
        "resolution_attempt_count",
        "resolution_success_count",
        "quarantine_count",
        "unresolved_conflict_count",
        "retry_count",
        "rate_limit_response_count",
        "processing_latency_ms",
        "publication_failure_count",
        "reconciliation_failure_count",
        "change_set_emission_count",
        "schema_compatibility_failure_count",
        "quota_exhaustion_count",
        "resolution_review_backlog_count",
        "dataset_rebuild_queue_count",
        "stale_dependency_count",
    )
    if any(getattr(snapshot, name) < 0 for name in count_fields):
        raise ProviderObservabilityError("observability counts must not be negative")
    if snapshot.resolution_success_count > snapshot.resolution_attempt_count:
        raise ProviderObservabilityError("resolution successes cannot exceed attempts")
    if snapshot.cursor_lag_seconds is not None and snapshot.cursor_lag_seconds < 0:
        raise ProviderObservabilityError("cursor lag must not be negative")


def _freshness_alerts(snapshot: ProviderObservabilitySnapshotV1) -> list[str]:
    alerts: list[str] = []
    if snapshot.freshness_status == "NEVER_SUCCEEDED":
        alerts.append("PROVIDER_NEVER_SUCCEEDED")
    elif snapshot.freshness_status == "STALE":
        alerts.append("PROVIDER_OR_RESOURCE_STALE")
    if snapshot.circuit_state == "OPEN":
        alerts.append("PROVIDER_CIRCUIT_OPEN")
    return alerts


def _failure_alerts(snapshot: ProviderObservabilitySnapshotV1) -> list[str]:
    checks = (
        (snapshot.validation_failure_count, "VALIDATION_FAILURES_PRESENT"),
        (snapshot.quarantine_count, "QUARANTINE_ITEMS_PRESENT"),
        (snapshot.unresolved_conflict_count, "UNRESOLVED_CONFLICTS_PRESENT"),
        (snapshot.publication_failure_count, "PUBLICATION_FAILURES_PRESENT"),
        (snapshot.reconciliation_failure_count, "RECONCILIATION_FAILURES_PRESENT"),
        (snapshot.schema_compatibility_failure_count, "SCHEMA_COMPATIBILITY_FAILURES_PRESENT"),
        (snapshot.quota_exhaustion_count, "QUOTA_EXHAUSTION_PRESENT"),
        (snapshot.resolution_review_backlog_count, "RESOLUTION_REVIEW_BACKLOG_PRESENT"),
        (snapshot.dataset_rebuild_queue_count, "DATASET_REBUILD_QUEUE_NON_EMPTY"),
        (snapshot.stale_dependency_count, "STALE_DEPENDENCIES_PRESENT"),
    )
    return [code for count, code in checks if count]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
