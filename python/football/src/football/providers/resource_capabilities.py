"""Scoped runtime evidence; static adapter declarations do not establish availability."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, fields
from datetime import date
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

CapabilityAvailability = Literal[
    "SUPPORTED",
    "UNSUPPORTED",
    "PARTIAL",
    "UNKNOWN",
    "PLAN_RESTRICTED",
    "AUTHORIZATION_REQUIRED",
    "TEMPORARILY_UNAVAILABLE",
]
AVAILABILITIES = frozenset(
    (
        "SUPPORTED",
        "UNSUPPORTED",
        "PARTIAL",
        "UNKNOWN",
        "PLAN_RESTRICTED",
        "AUTHORIZATION_REQUIRED",
        "TEMPORARILY_UNAVAILABLE",
    )
)


class CapabilityError(ValueError):
    """Runtime capability evidence or its acquisition scope is invalid."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceScope:
    provider: str
    resource_type: str
    competition: str | None
    season: str | None

    def __post_init__(self) -> None:
        if not PROVIDER_PATTERN.fullmatch(self.provider):
            raise CapabilityError("provider must use lowercase snake_case")
        if not self.resource_type.strip():
            raise CapabilityError("resource_type is required")
        if any(
            value is not None and not value.strip() for value in (self.competition, self.season)
        ):
            raise CapabilityError("native scope identifiers must be nonblank or explicit null")
        if self.competition is None and self.season is not None:
            raise CapabilityError("a season requires its native competition scope")

    def to_dict(self) -> dict[str, object]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    @property
    def subject_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, "matchforge:provider-resource-scope:" + self.sha256)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceCapability:
    availability: CapabilityAvailability
    adapter_version: str
    normalizer_version: str
    historical_start: date | None = None
    historical_end: date | None = None
    freshness_seconds: int | None = None
    expected_completeness: float | None = None
    entitlement: str | None = None
    rate_limit_per_minute: int | None = None
    retention_status: str | None = None
    timestamp_precision: str | None = None
    identity_quality: str | None = None

    def __post_init__(self) -> None:
        if self.availability not in AVAILABILITIES:
            raise CapabilityError("unsupported capability availability")
        _validate_history(self)
        for value in (self.freshness_seconds, self.rate_limit_per_minute):
            if value is not None and (type(value) is not int or value <= 0):
                raise CapabilityError(
                    "freshness and rate limits must be positive integers or unknown"
                )
        completeness = self.expected_completeness
        if completeness is not None and (
            isinstance(completeness, bool)
            or not math.isfinite(completeness)
            or not 0 <= completeness <= 1
        ):
            raise CapabilityError("expected completeness must be a finite fraction or unknown")
        _validate_descriptions(self)

    def to_dict(self) -> dict[str, object]:
        return {
            item.name: value.isoformat()
            if isinstance(value := getattr(self, item.name), date)
            else value
            for item in fields(self)
        }


def _validate_history(capability: ResourceCapability) -> None:
    for value in (capability.historical_start, capability.historical_end):
        if value is not None and type(value) is not date:
            raise CapabilityError("historical coverage boundaries must be dates")
    if (
        capability.historical_start is not None
        and capability.historical_end is not None
        and capability.historical_end < capability.historical_start
    ):
        raise CapabilityError("historical coverage range is reversed")


def _validate_descriptions(capability: ResourceCapability) -> None:
    if not capability.adapter_version.strip() or not capability.normalizer_version.strip():
        raise CapabilityError("adapter and normalizer versions are required")
    values = (
        capability.entitlement,
        capability.retention_status,
        capability.timestamp_precision,
        capability.identity_quality,
    )
    if any(value is not None and not value.strip() for value in values):
        raise CapabilityError("capability descriptions must be nonblank or unknown")


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    scope: ResourceScope
    capability: ResourceCapability | None
    allowed: bool
    reason: str
    decision_id: UUID | None = None

    @property
    def availability(self) -> CapabilityAvailability:
        return self.capability.availability if self.capability else "UNKNOWN"


def acquisition_plan(
    scope: ResourceScope,
    capability: ResourceCapability | None,
    *,
    adapter_version: str,
    normalizer_version: str,
    football_date: date | None = None,
) -> AcquisitionPlan:
    """Use registered scope evidence without inventing support, dates or retries."""
    if capability is None or capability.availability not in ("SUPPORTED", "PARTIAL"):
        return AcquisitionPlan(scope, capability, False, "Scope is unknown or unavailable")
    if (adapter_version, normalizer_version) != (
        capability.adapter_version,
        capability.normalizer_version,
    ):
        return AcquisitionPlan(scope, capability, False, "Registered processing versions differ")
    if football_date is not None and (
        (capability.historical_start is not None and football_date < capability.historical_start)
        or (capability.historical_end is not None and football_date > capability.historical_end)
    ):
        return AcquisitionPlan(
            scope, capability, False, "Requested date is outside registered coverage"
        )
    return AcquisitionPlan(scope, capability, True, "Registered scope permits acquisition")
