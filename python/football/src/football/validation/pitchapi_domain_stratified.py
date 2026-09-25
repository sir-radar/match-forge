"""Pure policy helpers for the proposed PitchAPI domain-stratified evaluation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2 = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2"

_EXPECTED_TARGETS = MappingProxyType(
    {
        "bundesliga_2022_23": 216,
        "bundesliga_2023_24": 216,
        "ligue1_2022_23": 280,
    }
)


class PitchApiDomainPolicyError(ValueError):
    """The proposed domain-stratified policy input is malformed."""


class XgTreatment(StrEnum):
    RAW = "RAW"
    LOGISTIC_RECALIBRATION = "LOGISTIC_RECALIBRATION"


@dataclass(frozen=True, slots=True)
class PairedScoreComparisonV1:
    """Transformed-minus-raw proper-score comparison from development data."""

    point_delta: float
    interval_lower: float
    interval_upper: float

    def __post_init__(self) -> None:
        values = (self.point_delta, self.interval_lower, self.interval_upper)
        if any(not math.isfinite(value) for value in values):
            raise PitchApiDomainPolicyError("score comparison must be finite")
        if not self.interval_lower <= self.interval_upper:
            raise PitchApiDomainPolicyError("score interval is reversed")


def select_development_xg_treatment(
    *,
    log_loss: PairedScoreComparisonV1,
    brier_score: PairedScoreComparisonV1,
) -> XgTreatment:
    """Select recalibration only when both proper scores support no degradation."""

    if (
        log_loss.point_delta < 0
        and log_loss.interval_upper < 0
        and brier_score.point_delta <= 0
        and brier_score.interval_upper <= 0
    ):
        return XgTreatment.LOGISTIC_RECALIBRATION
    return XgTreatment.RAW


@dataclass(frozen=True, slots=True)
class DomainMetricV1:
    """One domain's metric and fixed target count."""

    value: float
    targets: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise PitchApiDomainPolicyError("domain metric must be finite")
        if isinstance(self.targets, bool) or self.targets <= 0:
            raise PitchApiDomainPolicyError("domain target count must be positive")


@dataclass(frozen=True, slots=True)
class DomainAggregateV1:
    macro_average: float
    target_weighted_average: float
    total_targets: int


@dataclass(frozen=True, slots=True)
class CanonicalFixtureKeyV1:
    """Provider-neutral fixture key after governed alias resolution."""

    competition_id: str
    season_id: str
    kickoff_at: str
    home_team_id: str
    away_team_id: str

    def __post_init__(self) -> None:
        values = (
            self.competition_id,
            self.season_id,
            self.kickoff_at,
            self.home_team_id,
            self.away_team_id,
        )
        if any(not value for value in values):
            raise PitchApiDomainPolicyError("resolved fixture key fields must be non-empty")
        if self.home_team_id == self.away_team_id:
            raise PitchApiDomainPolicyError("fixture teams must differ")


def aggregate_domain_metric(metrics: Mapping[str, DomainMetricV1]) -> DomainAggregateV1:
    """Return the pre-registered equal-domain and target-weighted summaries."""

    if set(metrics) != set(_EXPECTED_TARGETS):
        raise PitchApiDomainPolicyError("metrics must contain exactly the three V2 domains")
    for scope, expected_targets in _EXPECTED_TARGETS.items():
        if metrics[scope].targets != expected_targets:
            raise PitchApiDomainPolicyError(f"unexpected target count for {scope}")
    ordered = [metrics[scope] for scope in _EXPECTED_TARGETS]
    total_targets = sum(metric.targets for metric in ordered)
    return DomainAggregateV1(
        macro_average=sum(metric.value for metric in ordered) / len(ordered),
        target_weighted_average=(
            sum(metric.value * metric.targets for metric in ordered) / total_targets
        ),
        total_targets=total_targets,
    )


def validate_exact_target_plan(targets: Mapping[str, frozenset[str]]) -> int:
    """Validate exact group counts and zero fixture intersection."""

    if set(targets) != set(_EXPECTED_TARGETS):
        raise PitchApiDomainPolicyError("target plan has the wrong domain membership")
    seen: set[str] = set()
    for scope, expected_count in _EXPECTED_TARGETS.items():
        domain_targets = targets[scope]
        if len(domain_targets) != expected_count:
            raise PitchApiDomainPolicyError(f"unexpected target count for {scope}")
        overlap = seen.intersection(domain_targets)
        if overlap:
            raise PitchApiDomainPolicyError("evaluation domains contain duplicate targets")
        seen.update(domain_targets)
    if len(seen) < 500:
        raise PitchApiDomainPolicyError("fewer than 500 exact evaluation targets")
    return len(seen)


def validate_cross_provider_fixture_roles(
    *,
    protected: frozenset[CanonicalFixtureKeyV1],
    development: frozenset[CanonicalFixtureKeyV1],
    evaluation: frozenset[CanonicalFixtureKeyV1],
    unresolved_fixture_count: int,
) -> None:
    """Fail unless resolved provider-neutral fixtures are disjoint by role."""

    if isinstance(unresolved_fixture_count, bool) or unresolved_fixture_count < 0:
        raise PitchApiDomainPolicyError("unresolved fixture count is invalid")
    if unresolved_fixture_count:
        raise PitchApiDomainPolicyError("cross-provider fixture aliases are unresolved")
    if protected & (development | evaluation):
        raise PitchApiDomainPolicyError("protected fixture overlap")
    if development & evaluation:
        raise PitchApiDomainPolicyError("development/evaluation fixture overlap")
