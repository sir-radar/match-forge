"""Point-in-time residualized head-to-head context for research models."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

FEATURE_ID = "MATCHFORGE_SECONDARY_MATCHUP_PRIOR_V1"
HALF_LIFE_DAYS = 180.0
MAXIMUM_AGE_DAYS = 730.0
MAXIMUM_MEETINGS = 5
MINIMUM_MEETINGS = 2
RESIDUAL_LIMIT = 1.5


class H2HResidualError(ValueError):
    """Input violates the residualized H2H feature contract."""


class H2HResidualStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_H2H = "INSUFFICIENT_H2H"


@dataclass(frozen=True, slots=True)
class H2HTarget:
    fixture_id: UUID
    competition: str
    season_label: str
    kickoff_at: datetime
    knowledge_cutoff: datetime
    home_team_id: UUID
    away_team_id: UUID

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        _aware(self.knowledge_cutoff, "knowledge_cutoff")
        if self.home_team_id == self.away_team_id:
            raise H2HResidualError("target teams must differ")


@dataclass(frozen=True, slots=True)
class H2HMeeting:
    fixture_id: UUID
    competition: str
    season_label: str
    kickoff_at: datetime
    known_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_npxg: float
    away_npxg: float
    lambda_home: float
    lambda_away: float
    pair_complete: bool = True

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        _aware(self.known_at, "known_at")
        if self.home_team_id == self.away_team_id:
            raise H2HResidualError("meeting teams must differ")
        for name, value in (
            ("home_npxg", self.home_npxg),
            ("away_npxg", self.away_npxg),
            ("lambda_home", self.lambda_home),
            ("lambda_away", self.lambda_away),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise H2HResidualError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class SecondaryMatchupPriorV1:
    secondary_matchup_prior: float
    h2h_usable_meeting_count: int
    h2h_effective_weight: float
    h2h_relevance: float
    h2h_latest_age_days: float | None
    h2h_same_orientation_count: int
    h2h_reversed_orientation_count: int
    status: H2HResidualStatus


@dataclass(frozen=True, slots=True)
class ContextualGoalAdjustmentV1:
    beta_h2h: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.beta_h2h) or not 0.0 <= self.beta_h2h <= 0.25:
            raise H2HResidualError("beta_h2h must be inside [0, 0.25]")

    def adjust(
        self, lambda_home_baseline: float, lambda_away_baseline: float, prior: float
    ) -> tuple[float, float]:
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (lambda_home_baseline, lambda_away_baseline)
        ):
            raise H2HResidualError("baseline goal rates must be finite and positive")
        if not math.isfinite(prior) or not -RESIDUAL_LIMIT <= prior <= RESIDUAL_LIMIT:
            raise H2HResidualError("secondary matchup prior is outside [-1.5, 1.5]")
        shift = self.beta_h2h * prior
        return lambda_home_baseline * math.exp(shift), lambda_away_baseline * math.exp(-shift)


class H2HResidualV1:
    """Build the one predictive H2H scalar and its audit fields."""

    feature_id = FEATURE_ID

    def build(self, target: H2HTarget, meetings: Iterable[H2HMeeting]) -> SecondaryMatchupPriorV1:
        eligible = [meeting for meeting in meetings if _eligible(target, meeting)]
        eligible.sort(key=lambda row: (row.kickoff_at, str(row.fixture_id)), reverse=True)
        selected = eligible[:MAXIMUM_MEETINGS]
        if len(selected) < MINIMUM_MEETINGS:
            return SecondaryMatchupPriorV1(
                0.0,
                len(selected),
                0.0,
                0.0,
                _age_days(target, selected[0]) if selected else None,
                sum(_same_orientation(target, row) for row in selected),
                sum(not _same_orientation(target, row) for row in selected),
                H2HResidualStatus.INSUFFICIENT_H2H,
            )
        weights: list[float] = []
        residuals: list[float] = []
        for index, meeting in enumerate(selected):
            continuity = 1.0
            if index:
                gap_days = (
                    selected[index - 1].kickoff_at - meeting.kickoff_at
                ).total_seconds() / 86_400.0
                continuity = math.exp(-max(0.0, gap_days - 270.0) / 365.0)
            weight = (
                math.pow(2.0, -_age_days(target, meeting) / HALF_LIFE_DAYS)
                * continuity
                * _era_weight(target.season_label, meeting.season_label)
                * (1.0 if _same_orientation(target, meeting) else 0.9)
            )
            weights.append(weight)
            residuals.append(_oriented_residual(target, meeting))
        effective_weight = sum(weights)
        relevance = min(1.0, effective_weight / 1.5)
        value = (
            relevance
            * sum(weight * residual for weight, residual in zip(weights, residuals, strict=True))
            / effective_weight
        )
        return SecondaryMatchupPriorV1(
            max(-RESIDUAL_LIMIT, min(RESIDUAL_LIMIT, value)),
            len(selected),
            effective_weight,
            relevance,
            _age_days(target, selected[0]),
            sum(_same_orientation(target, row) for row in selected),
            sum(not _same_orientation(target, row) for row in selected),
            H2HResidualStatus.AVAILABLE,
        )


def _eligible(target: H2HTarget, meeting: H2HMeeting) -> bool:
    age = _age_days(target, meeting)
    return (
        meeting.kickoff_at < target.kickoff_at
        and meeting.known_at <= target.knowledge_cutoff
        and frozenset((meeting.home_team_id, meeting.away_team_id))
        == frozenset((target.home_team_id, target.away_team_id))
        and meeting.competition == target.competition
        and _era_weight(target.season_label, meeting.season_label) > 0.0
        and 0.0 <= age <= MAXIMUM_AGE_DAYS
        and meeting.pair_complete
    )


def _oriented_residual(target: H2HTarget, meeting: H2HMeeting) -> float:
    if meeting.home_team_id == target.home_team_id:
        target_home_npxg, target_away_npxg = meeting.home_npxg, meeting.away_npxg
        target_home_lambda, target_away_lambda = meeting.lambda_home, meeting.lambda_away
    else:
        target_home_npxg, target_away_npxg = meeting.away_npxg, meeting.home_npxg
        target_home_lambda, target_away_lambda = meeting.lambda_away, meeting.lambda_home
    residual = 0.5 * (
        (target_home_npxg - target_home_lambda) - (target_away_npxg - target_away_lambda)
    )
    return max(-RESIDUAL_LIMIT, min(RESIDUAL_LIMIT, residual))


def _same_orientation(target: H2HTarget, meeting: H2HMeeting) -> bool:
    return meeting.home_team_id == target.home_team_id


def _age_days(target: H2HTarget, meeting: H2HMeeting) -> float:
    return (target.kickoff_at - meeting.kickoff_at).total_seconds() / 86_400.0


def _era_weight(target_season: str, meeting_season: str) -> float:
    target_start = _season_start(target_season)
    meeting_start = _season_start(meeting_season)
    if meeting_start == target_start:
        return 1.0
    if meeting_start == target_start - 1:
        return 0.65
    return 0.0


def _season_start(value: str) -> int:
    normalized = value.replace("_", "/").replace("-", "/")
    first = normalized.split("/", maxsplit=1)[0]
    if len(first) == 2:
        first = f"20{first}"
    try:
        return int(first)
    except ValueError as error:
        raise H2HResidualError(f"invalid season label: {value}") from error


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise H2HResidualError(f"{name} must include a timezone")
