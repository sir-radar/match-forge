"""Resource observations with references to exact fields when native IDs are absent.

Source references identify evidence inside the observation's source resource. They
are neither provider-assigned IDs nor canonical football identities. Version 1
remains readable with its original schema and serialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from football.contracts.observations import (
    AvailabilityObservationV1,
    CoachObservationV1,
    CompetitionObservationV1,
    EntityReference,
    EventObservationV1,
    ExpectedGoalsObservationV1,
    FixtureObservationV1,
    FormationObservationV1,
    LineupMember,
    LineupObservationV1,
    Observation,
    ObservationError,
    ObservationVersionInfo,
    OddsObservationV1,
    PlayerObservationV1,
    PlayerStatisticObservationV1,
    ResultObservationV1,
    ShotObservationV1,
    StandingObservationV1,
    TeamObservationV1,
    TeamStatisticObservationV1,
)


@dataclass(frozen=True, slots=True)
class EntityReferenceV2(EntityReference):
    source_record_key: str | None = None

    def __post_init__(self) -> None:
        if (
            self.provider_native_id is None
            and self.canonical_id is None
            and not self.source_record_key
        ):
            raise ObservationError("an entity reference requires an ID or source field")


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationVersionsV2(ObservationVersionInfo):
    VERSION: ClassVar[str] = "2"
    observation_contract_version: Literal["2"] = "2"


@dataclass(frozen=True, slots=True, kw_only=True)
class FixtureObservationV2(FixtureObservationV1):
    CONTRACT: ClassVar[str] = "FixtureObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    competition: EntityReferenceV2
    home_team: EntityReferenceV2
    away_team: EntityReferenceV2
    venue: EntityReferenceV2 | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultObservationV2(ResultObservationV1):
    CONTRACT: ClassVar[str] = "ResultObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class CompetitionObservationV2(CompetitionObservationV1):
    CONTRACT: ClassVar[str] = "CompetitionObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    competition: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamObservationV2(TeamObservationV1):
    CONTRACT: ClassVar[str] = "TeamObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    team: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerObservationV2(PlayerObservationV1):
    CONTRACT: ClassVar[str] = "PlayerObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    player: EntityReferenceV2
    team: EntityReferenceV2 | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CoachObservationV2(CoachObservationV1):
    CONTRACT: ClassVar[str] = "CoachObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    coach: EntityReferenceV2
    team: EntityReferenceV2


@dataclass(frozen=True, slots=True)
class LineupMemberV2(LineupMember):
    player: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class LineupObservationV2(LineupObservationV1):
    CONTRACT: ClassVar[str] = "LineupObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    team: EntityReferenceV2
    players: tuple[LineupMemberV2, ...]
    coach: EntityReferenceV2 | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AvailabilityObservationV2(AvailabilityObservationV1):
    CONTRACT: ClassVar[str] = "AvailabilityObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    team: EntityReferenceV2
    player: EntityReferenceV2
    fixture: EntityReferenceV2 | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FormationObservationV2(FormationObservationV1):
    CONTRACT: ClassVar[str] = "FormationObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    team: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class EventObservationV2(EventObservationV1):
    CONTRACT: ClassVar[str] = "EventObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    team: EntityReferenceV2 | None = None
    player: EntityReferenceV2 | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ShotObservationV2(ShotObservationV1):
    CONTRACT: ClassVar[str] = "ShotObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    team: EntityReferenceV2
    player: EntityReferenceV2 | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpectedGoalsObservationV2(ExpectedGoalsObservationV1):
    CONTRACT: ClassVar[str] = "ExpectedGoalsObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    team: EntityReferenceV2
    shot: EntityReferenceV2 | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamStatisticObservationV2(TeamStatisticObservationV1):
    CONTRACT: ClassVar[str] = "TeamStatisticObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    team: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerStatisticObservationV2(PlayerStatisticObservationV1):
    CONTRACT: ClassVar[str] = "PlayerStatisticObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2
    team: EntityReferenceV2
    player: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class StandingObservationV2(StandingObservationV1):
    CONTRACT: ClassVar[str] = "StandingObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    competition: EntityReferenceV2
    team: EntityReferenceV2


@dataclass(frozen=True, slots=True, kw_only=True)
class OddsObservationV2(OddsObservationV1):
    CONTRACT: ClassVar[str] = "OddsObservationV2"
    VERSIONS_TYPE: ClassVar[type[ObservationVersionInfo]] = ObservationVersionsV2
    fixture: EntityReferenceV2


OBSERVATION_V2_TYPES: tuple[type[Observation], ...] = (
    FixtureObservationV2,
    ResultObservationV2,
    CompetitionObservationV2,
    TeamObservationV2,
    PlayerObservationV2,
    CoachObservationV2,
    LineupObservationV2,
    AvailabilityObservationV2,
    FormationObservationV2,
    EventObservationV2,
    ShotObservationV2,
    ExpectedGoalsObservationV2,
    TeamStatisticObservationV2,
    PlayerStatisticObservationV2,
    StandingObservationV2,
    OddsObservationV2,
)
