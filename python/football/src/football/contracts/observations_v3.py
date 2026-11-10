"""Rich source observations; earlier observation schemas remain immutable.

Named quantities retain provider provenance and reported period. They do not
establish cross-provider or sportsbook settlement equivalence. A missing semantic
version remains unknown and does not qualify an observation for a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Literal

from football.contracts.observations import (
    Amount,
    Count,
    Observation,
    ObservationVersionInfo,
    Probability,
)
from football.contracts.observations_v2 import (
    EntityReferenceV2,
    PlayerStatisticObservationV2,
    ShotObservationV2,
    TeamStatisticObservationV2,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationVersionsV3(ObservationVersionInfo):
    VERSION: ClassVar[str] = "3"
    observation_contract_version: Literal["3"] = "3"
    semantic_version: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamStatisticObservationV3(TeamStatisticObservationV2):
    CONTRACT: ClassVar[str] = "TeamStatisticObservationV3"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV3
    shots_off_target: Count | None = None
    blocked_shots: Count | None = None
    offsides: Count | None = None
    passes: Count | None = None
    accurate_passes: Count | None = None
    accurate_crosses: Count | None = None
    tackles: Count | None = None
    interceptions: Count | None = None
    clearances: Count | None = None
    throw_ins: Count | None = None
    goal_kicks: Count | None = None
    woodwork: Count | None = None
    expected_goals_on_target: Amount | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerStatisticObservationV3(PlayerStatisticObservationV2):
    CONTRACT: ClassVar[str] = "PlayerStatisticObservationV3"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV3
    shots_on_target: Count | None = None
    passes: Count | None = None
    accurate_passes: Count | None = None
    tackles: Count | None = None
    interceptions: Count | None = None
    fouls: Count | None = None
    saves: Count | None = None
    expected_goals: Amount | None = None
    expected_assists: Amount | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ShotObservationV3(ShotObservationV2):
    """Extra categories remain source-reported until semantic qualification."""

    CONTRACT: ClassVar[str] = "ShotObservationV3"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV3
    body_part: str | None = None
    situation: str | None = None
    expected_goals_on_target: Probability | None = None
    assisting_player: EntityReferenceV2 | None = None
    assist_event: EntityReferenceV2 | None = None
    home_goals_before_shot: Count | None = None
    away_goals_before_shot: Count | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PeriodScoreObservationV3(Observation):
    CONTRACT: ClassVar[str] = "PeriodScoreObservationV3"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV3
    fixture: EntityReferenceV2
    period: Literal["FIRST_HALF", "SECOND_HALF", "EXTRA_TIME"]
    score_basis: Literal["REGULATION_90", "EXTRA_TIME", "UNKNOWN"]
    home_goals: Count
    away_goals: Count
    period_complete: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RefereeObservationV3(Observation):
    CONTRACT: ClassVar[str] = "RefereeObservationV3"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV3
    fixture: EntityReferenceV2
    referee: EntityReferenceV2
    name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamRatingObservationV3(Observation):
    """A source calendar date never implies when an intraday rating was available."""

    CONTRACT: ClassVar[str] = "TeamRatingObservationV3"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV3
    team: EntityReferenceV2
    rating_date: date
    rating: float
    rating_system: str


OBSERVATION_V3_TYPES: tuple[type[Observation], ...] = (
    TeamStatisticObservationV3,
    PlayerStatisticObservationV3,
    ShotObservationV3,
    PeriodScoreObservationV3,
    RefereeObservationV3,
    TeamRatingObservationV3,
)
