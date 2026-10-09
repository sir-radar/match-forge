"""Outcome-blind eligibility and reference models for V2 replacement evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from scipy.stats import poisson

CHAMPION_MODEL_ID = "transferable-rolling-goals-poisson-v1"
COMPETITION_PRIOR_MODEL_ID = "competition-prior-poisson-v1"
REFERENCE_STACK_ID = "MATCHFORGE_REFERENCE_STACK_V1"
CHAMPION_MINIMUM_HISTORY = 10
COMPETITION_PRIOR_K = 20
SCORE_TAIL_START = 10


class ChampionEligibility(StrEnum):
    ELIGIBLE = "CHAMPION_ELIGIBLE"
    INELIGIBLE = "CHAMPION_INELIGIBLE"


class ChampionIneligibilityReason(StrEnum):
    HOME_INSUFFICIENT_HISTORY = "HOME_INSUFFICIENT_HISTORY"
    AWAY_INSUFFICIENT_HISTORY = "AWAY_INSUFFICIENT_HISTORY"
    BOTH_INSUFFICIENT_HISTORY = "BOTH_INSUFFICIENT_HISTORY"
    HOME_IDENTITY_UNRESOLVED = "HOME_IDENTITY_UNRESOLVED"
    AWAY_IDENTITY_UNRESOLVED = "AWAY_IDENTITY_UNRESOLVED"
    COMPETITION_CONTEXT_UNAVAILABLE = "COMPETITION_CONTEXT_UNAVAILABLE"
    REQUIRED_FEATURE_UNAVAILABLE = "REQUIRED_FEATURE_UNAVAILABLE"
    OTHER_CHAMPION_PRECONDITION_FAILED = "OTHER_CHAMPION_PRECONDITION_FAILED"


class ReferenceMode(StrEnum):
    CHAMPION = "CHAMPION"
    COMPETITION_PRIOR = "COMPETITION_PRIOR"


@dataclass(frozen=True, slots=True)
class ChampionEligibilityInput:
    """Pre-outcome facts needed by the production champion."""

    fixture_identity_resolved: bool
    home_identity_resolved: bool
    away_identity_resolved: bool
    competition_context_available: bool
    required_features_available: bool
    home_prior_match_count: int
    away_prior_match_count: int
    other_preconditions_satisfied: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("home_prior_match_count", self.home_prior_match_count),
            ("away_prior_match_count", self.away_prior_match_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ChampionEligibilityResult:
    status: ChampionEligibility
    reason: ChampionIneligibilityReason | None
    home_prior_match_count: int
    away_prior_match_count: int


def champion_eligibility(value: ChampionEligibilityInput) -> ChampionEligibilityResult:
    reason: ChampionIneligibilityReason | None = None
    if not value.fixture_identity_resolved:
        reason = ChampionIneligibilityReason.OTHER_CHAMPION_PRECONDITION_FAILED
    elif not value.home_identity_resolved:
        reason = ChampionIneligibilityReason.HOME_IDENTITY_UNRESOLVED
    elif not value.away_identity_resolved:
        reason = ChampionIneligibilityReason.AWAY_IDENTITY_UNRESOLVED
    elif not value.competition_context_available:
        reason = ChampionIneligibilityReason.COMPETITION_CONTEXT_UNAVAILABLE
    elif not value.required_features_available:
        reason = ChampionIneligibilityReason.REQUIRED_FEATURE_UNAVAILABLE
    elif not value.other_preconditions_satisfied:
        reason = ChampionIneligibilityReason.OTHER_CHAMPION_PRECONDITION_FAILED
    else:
        home_low = value.home_prior_match_count < CHAMPION_MINIMUM_HISTORY
        away_low = value.away_prior_match_count < CHAMPION_MINIMUM_HISTORY
        if home_low and away_low:
            reason = ChampionIneligibilityReason.BOTH_INSUFFICIENT_HISTORY
        elif home_low:
            reason = ChampionIneligibilityReason.HOME_INSUFFICIENT_HISTORY
        elif away_low:
            reason = ChampionIneligibilityReason.AWAY_INSUFFICIENT_HISTORY
    return ChampionEligibilityResult(
        ChampionEligibility.INELIGIBLE if reason else ChampionEligibility.ELIGIBLE,
        reason,
        value.home_prior_match_count,
        value.away_prior_match_count,
    )


@dataclass(frozen=True, slots=True)
class CompetitionPriorMatch:
    competition_id: UUID
    kickoff_at: datetime
    home_goals: int
    away_goals: int

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        for name, value in (("home_goals", self.home_goals), ("away_goals", self.away_goals)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class CompetitionPriorRates:
    lambda_home: float
    lambda_away: float
    prior_match_count: int


class CompetitionPriorPoissonV1:
    """Independent Poisson reference with competition-level history only."""

    model_id = COMPETITION_PRIOR_MODEL_ID

    def __init__(self, global_home_rate: float, global_away_rate: float) -> None:
        for name, value in (
            ("global_home_rate", global_home_rate),
            ("global_away_rate", global_away_rate),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        self.global_home_rate = global_home_rate
        self.global_away_rate = global_away_rate

    def rates(
        self,
        *,
        competition_id: UUID,
        kickoff_at: datetime,
        history: Sequence[CompetitionPriorMatch],
    ) -> CompetitionPriorRates:
        _aware(kickoff_at, "kickoff_at")
        prior = tuple(
            row
            for row in history
            if row.competition_id == competition_id and row.kickoff_at < kickoff_at
        )
        count = len(prior)
        if count == 0:
            return CompetitionPriorRates(self.global_home_rate, self.global_away_rate, 0)
        weight = count / (count + COMPETITION_PRIOR_K)
        raw_home = sum(row.home_goals for row in prior) / count
        raw_away = sum(row.away_goals for row in prior) / count
        return CompetitionPriorRates(
            weight * raw_home + (1 - weight) * self.global_home_rate,
            weight * raw_away + (1 - weight) * self.global_away_rate,
            count,
        )

    def distribution(
        self,
        *,
        competition_id: UUID,
        kickoff_at: datetime,
        history: Sequence[CompetitionPriorMatch],
    ) -> tuple[tuple[float, ...], ...]:
        rates = self.rates(
            competition_id=competition_id,
            kickoff_at=kickoff_at,
            history=history,
        )
        home = _poisson_distribution(rates.lambda_home)
        away = _poisson_distribution(rates.lambda_away)
        matrix = tuple(tuple(left * right for right in away) for left in home)
        cells = tuple(value for row in matrix for value in row)
        if any(not math.isfinite(value) or value < 0 for value in cells) or not math.isclose(
            sum(cells), 1.0, abs_tol=1e-12
        ):
            raise ValueError("competition-prior score distribution is invalid")
        return matrix


@dataclass(frozen=True, slots=True)
class ReferenceSelection:
    model_id: str
    mode: ReferenceMode


class ReferenceStackV1:
    stack_id = REFERENCE_STACK_ID

    def select(self, eligibility: ChampionEligibilityResult) -> ReferenceSelection:
        if eligibility.status is ChampionEligibility.ELIGIBLE:
            return ReferenceSelection(CHAMPION_MODEL_ID, ReferenceMode.CHAMPION)
        return ReferenceSelection(COMPETITION_PRIOR_MODEL_ID, ReferenceMode.COMPETITION_PRIOR)


def _poisson_distribution(rate: float) -> tuple[float, ...]:
    exact = [float(poisson.pmf(value, rate)) for value in range(SCORE_TAIL_START)]
    tail = 1.0 - sum(exact)
    if tail < -1e-12:
        raise ValueError("Poisson tail is negative")
    return tuple((*exact, max(0.0, tail)))


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
