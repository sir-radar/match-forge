from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from football.providers.resource_capabilities import (
    CapabilityAvailability,
    CapabilityError,
    ResourceCapability,
    ResourceScope,
    acquisition_plan,
)

SCOPE = ResourceScope(
    provider="api_football", resource_type="lineups", competition="39", season="2025"
)


def capability(availability: CapabilityAvailability = "SUPPORTED") -> ResourceCapability:
    return ResourceCapability(
        availability=availability,
        adapter_version="api-v1",
        normalizer_version="lineup-v2",
        historical_start=date(2025, 1, 1),
        historical_end=date(2026, 1, 1),
        freshness_seconds=60,
        expected_completeness=0.9,
        entitlement="reviewed-account",
        rate_limit_per_minute=10,
        retention_status="reviewed-retention",
        timestamp_precision="minute",
        identity_quality="provider-native-ids",
    )


@pytest.mark.parametrize(
    "availability",
    [
        "SUPPORTED",
        "UNSUPPORTED",
        "PARTIAL",
        "UNKNOWN",
        "PLAN_RESTRICTED",
        "AUTHORIZATION_REQUIRED",
        "TEMPORARILY_UNAVAILABLE",
    ],
)
def test_only_registered_available_states_allow_acquisition(
    availability: CapabilityAvailability,
) -> None:
    plan = acquisition_plan(
        SCOPE, capability(availability), adapter_version="api-v1", normalizer_version="lineup-v2"
    )
    assert plan.allowed == (availability in ("SUPPORTED", "PARTIAL"))
    assert plan.availability == availability


def test_unknown_scope_never_infers_support_from_a_method_or_static_declaration() -> None:
    plan = acquisition_plan(SCOPE, None, adapter_version="api-v1", normalizer_version="lineup-v2")
    assert not plan.allowed and plan.availability == "UNKNOWN"


@pytest.mark.parametrize("change", [{"adapter_version": "other"}, {"normalizer_version": "other"}])
def test_processing_version_drift_blocks_an_old_capability(change: dict[str, str]) -> None:
    versions = {"adapter_version": "api-v1", "normalizer_version": "lineup-v2", **change}
    assert not acquisition_plan(
        SCOPE,
        capability(),
        adapter_version=versions["adapter_version"],
        normalizer_version=versions["normalizer_version"],
    ).allowed


@pytest.mark.parametrize("day", [date(2024, 12, 31), date(2026, 1, 2)])
def test_known_historical_boundaries_block_impossible_requests(day: date) -> None:
    assert not acquisition_plan(
        SCOPE,
        capability(),
        adapter_version="api-v1",
        normalizer_version="lineup-v2",
        football_date=day,
    ).allowed


@pytest.mark.parametrize(
    "change",
    [
        {"freshness_seconds": 0},
        {"rate_limit_per_minute": True},
        {"expected_completeness": float("nan")},
        {"expected_completeness": 1.1},
        {"historical_end": date(2024, 1, 1)},
        {"adapter_version": " "},
        {"retention_status": ""},
    ],
)
def test_invalid_scoped_metadata_is_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(CapabilityError):
        replace(capability(), **change)


def test_native_scope_is_exact_and_catalog_nulls_are_not_wildcards() -> None:
    catalog = ResourceScope(
        provider="api_football", resource_type="competitions", competition=None, season=None
    )
    assert catalog.sha256 != SCOPE.sha256
    assert SCOPE.sha256 != replace(SCOPE, season="2024").sha256
    assert SCOPE.sha256 != replace(SCOPE, provider="fotmob").sha256
    assert SCOPE.subject_id != catalog.subject_id


@pytest.mark.parametrize("day", [date(2025, 1, 1), date(2026, 1, 1)])
def test_registered_historical_date_bounds_are_inclusive(day: date) -> None:
    assert acquisition_plan(
        SCOPE,
        capability(),
        adapter_version="api-v1",
        normalizer_version="lineup-v2",
        football_date=day,
    ).allowed
