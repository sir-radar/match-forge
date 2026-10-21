"""Count explicit eligible input sets; do not decide identity or qualification here."""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes
from football.providers.resource_capabilities import ResourceScope


class CoverageError(ValueError):
    """Coverage inputs cannot support a consistent measurement."""


@dataclass(frozen=True, slots=True)
class CoverageMetrics:
    expected: int | None
    qualified: int

    def __post_init__(self) -> None:
        if type(self.qualified) is not int or self.qualified < 0:
            raise CoverageError("qualified coverage count must be a nonnegative integer")
        if self.expected is not None and (type(self.expected) is not int or self.expected < 0):
            raise CoverageError("expected coverage count must be nonnegative or unknown")
        if self.expected is not None and self.qualified > self.expected:
            raise CoverageError("qualified count exceeds the expected universe")

    @property
    def coverage_ratio(self) -> float | None:
        return self.qualified / self.expected if self.expected else None

    @property
    def status(self) -> Literal["UNKNOWN", "PARTIAL", "COMPLETE"]:
        if not self.expected:
            return "UNKNOWN"
        return "COMPLETE" if self.qualified == self.expected else "PARTIAL"

    def to_dict(self) -> dict[str, object]:
        return {
            "expected": self.expected,
            "qualified": self.qualified,
            "coverage_ratio": self.coverage_ratio,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalCoverageScope:
    competition_id: UUID
    season_id: UUID
    resource_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.competition_id, UUID) or not isinstance(self.season_id, UUID):
            raise CoverageError("canonical scope requires MatchForge UUIDs")
        if not self.resource_type.strip():
            raise CoverageError("canonical coverage resource is required")

    def to_dict(self) -> dict[str, object]:
        return {
            "competition_id": str(self.competition_id),
            "season_id": str(self.season_id),
            "resource_type": self.resource_type,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderCoverage:
    """Stable native/source-record unit keys supplied by the provider's eligibility owner."""

    scope: ResourceScope
    knowledge_cutoff: datetime
    expected_units: Collection[str] | None
    observed_units: Collection[str]
    qualified_units: Collection[str]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _common(self)
        for name in ("expected_units", "observed_units", "qualified_units"):
            values = getattr(self, name)
            if values is not None:
                values = frozenset(values)
                if any(not isinstance(value, str) or not value.strip() for value in values):
                    raise CoverageError("provider unit keys must be explicit nonblank identifiers")
                object.__setattr__(self, name, values)
        if not set(self.qualified_units) <= set(self.observed_units):
            raise CoverageError("qualified provider units must be observed")
        _expected(self.expected_units, self.qualified_units)

    @property
    def metrics(self) -> CoverageMetrics:
        return CoverageMetrics(
            len(self.expected_units) if self.expected_units is not None else None,
            len(self.qualified_units),
        )

    @property
    def observed(self) -> int:
        return len(self.observed_units)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "ProviderCoverage",
            "contract_version": "1",
            "scope": self.scope.to_dict(),
            "knowledge_cutoff": self.knowledge_cutoff.isoformat(),
            "evidence_refs": list(self.evidence_refs),
            "expected_units": sorted(self.expected_units)
            if self.expected_units is not None
            else None,
            "observed_units": sorted(self.observed_units),
            "qualified_units": sorted(self.qualified_units),
            "metrics": {**self.metrics.to_dict(), "observed": self.observed},
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @property
    def report_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, "matchforge:coverage:ProviderCoverage:" + self.sha256)


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalCoverage:
    """Already-qualified canonical units; coverage does not admit raw observations."""

    scope: CanonicalCoverageScope
    knowledge_cutoff: datetime
    expected_units: Collection[UUID] | None
    qualified_support: Collection[tuple[UUID, str]]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _common(self)
        if self.expected_units is not None:
            expected = frozenset(self.expected_units)
            if any(not isinstance(unit, UUID) for unit in expected):
                raise CoverageError("expected canonical units must be MatchForge UUIDs")
            object.__setattr__(self, "expected_units", expected)
        support = frozenset(self.qualified_support)
        for unit, provider in support:
            if not isinstance(unit, UUID) or not PROVIDER_PATTERN.fullmatch(provider):
                raise CoverageError("canonical support requires a UUID and provider code")
        object.__setattr__(self, "qualified_support", support)
        _expected(self.expected_units, self.qualified_units)

    @property
    def qualified_units(self) -> frozenset[UUID]:
        return frozenset(unit for unit, _ in self.qualified_support)

    @property
    def supporting_providers(self) -> tuple[str, ...]:
        return tuple(sorted({provider for _, provider in self.qualified_support}))

    @property
    def metrics(self) -> CoverageMetrics:
        return CoverageMetrics(
            len(self.expected_units) if self.expected_units is not None else None,
            len(self.qualified_units),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "CanonicalCoverage",
            "contract_version": "1",
            "scope": self.scope.to_dict(),
            "knowledge_cutoff": self.knowledge_cutoff.isoformat(),
            "evidence_refs": list(self.evidence_refs),
            "expected_units": sorted(str(unit) for unit in self.expected_units)
            if self.expected_units is not None
            else None,
            "qualified_support": [
                [str(unit), provider] for unit, provider in sorted(self.qualified_support)
            ],
            "metrics": {
                "expected_canonical_units": self.metrics.expected,
                "qualified_canonical_units": self.metrics.qualified,
                "coverage_ratio": self.metrics.coverage_ratio,
                "status": self.metrics.status,
                "supporting_providers": list(self.supporting_providers),
            },
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @property
    def report_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, "matchforge:coverage:CanonicalCoverage:" + self.sha256)


def _common(report: ProviderCoverage | CanonicalCoverage) -> None:
    if report.knowledge_cutoff.utcoffset() is None:
        raise CoverageError("coverage knowledge cutoff requires a timezone")
    object.__setattr__(report, "knowledge_cutoff", report.knowledge_cutoff.astimezone(UTC))
    refs = tuple(report.evidence_refs)
    if not refs or any(not ref.strip() for ref in refs) or len(refs) != len(set(refs)):
        raise CoverageError("unique coverage input evidence references are required")
    object.__setattr__(report, "evidence_refs", refs)


def _expected[T](expected: Collection[T] | None, qualified: Collection[T]) -> None:
    if expected is not None and not set(qualified) <= set(expected):
        raise CoverageError("qualified units are outside the expected universe")
