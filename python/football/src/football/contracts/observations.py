"""Versioned provider-neutral resource observations, before canonical resolution.

An absent resource produces no observation. Within an observed resource, ``None``
means unreported/unknown, never zero. Native identifiers remain scoped to the
provenance provider. Optional canonical identifiers require independent identity
evidence; their presence does not itself admit an observation to model history.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, ClassVar, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

Count = Annotated[int, "nonnegative"]
Amount = Annotated[float, "nonnegative"]
Probability = Annotated[float, "probability"]
Percentage = Annotated[float, "percentage"]
DecimalOdds = Annotated[float, "decimal_odds"]

FixtureStatus = Literal[
    "SCHEDULED",
    "LIVE",
    "HALF_TIME",
    "FINISHED",
    "POSTPONED",
    "CANCELLED",
    "ABANDONED",
    "AWARDED",
    "INTERRUPTED",
    "SUSPENDED",
    "UNKNOWN",
]
ScoreBasis = Literal["REGULATION_90", "EXTRA_TIME", "PENALTY_SHOOTOUT", "UNKNOWN"]


class ObservationError(ValueError):
    """A resource observation violates its declared wire or semantic contract."""


@dataclass(frozen=True, slots=True)
class EntityReference:
    """One native entity ID, plus an independently resolved MatchForge ID if known."""

    provider_native_id: str | None
    canonical_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ObservationProvenance:
    provider: Annotated[str, "provider"]
    provider_native_id: str | None
    source_snapshot_id: UUID
    source_resource_id: UUID
    source_sha256: Annotated[str, "sha256"]
    source_record_key: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationVersions:
    adapter_version: str
    normalizer_version: str
    provider_schema_version: str | None = None
    observation_contract_version: Literal["1"] = "1"
    resolution_version: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationTime:
    """Football validity, provider clocks and MatchForge knowledge stay separate."""

    observed_at: datetime
    acquired_at: datetime
    known_at: datetime
    event_time: datetime | None = None
    provider_updated_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Observation:
    provenance: ObservationProvenance
    time: ObservationTime
    versions: ObservationVersions
    CONTRACT: ClassVar[str]

    def __post_init__(self) -> None:
        from football.contracts.observation_codec import validate_observation

        validate_observation(self)

    def to_dict(self) -> dict[str, object]:
        from football.contracts.observation_codec import observation_payload

        return observation_payload(self)

    def to_bytes(self) -> bytes:
        from football.contracts.observation_codec import observation_bytes

        return observation_bytes(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @property
    def observation_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"matchforge:observation:{self.CONTRACT}:{self.sha256}")


@dataclass(frozen=True, slots=True, kw_only=True)
class FixtureObservationV1(Observation):
    """Scheduling and participants only; results are structurally separate."""

    CONTRACT: ClassVar[str] = "FixtureObservationV1"
    fixture: EntityReference
    competition: EntityReference
    home_team: EntityReference
    away_team: EntityReference
    kickoff_at: datetime
    status: FixtureStatus
    kickoff_precision: Literal["EXACT", "DATE_ONLY"]
    season_label: str | None = None
    round: str | None = None
    venue: EntityReference | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultObservationV1(Observation):
    """An observed score with explicit status/basis, never implied eligibility."""

    CONTRACT: ClassVar[str] = "ResultObservationV1"
    fixture: EntityReference
    status: FixtureStatus
    score_basis: ScoreBasis
    home_goals: Count | None = None
    away_goals: Count | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CompetitionObservationV1(Observation):
    CONTRACT: ClassVar[str] = "CompetitionObservationV1"
    competition: EntityReference
    name: str
    country: str | None = None
    competition_type: str | None = None
    season_label: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamObservationV1(Observation):
    CONTRACT: ClassVar[str] = "TeamObservationV1"
    team: EntityReference
    name: str
    country: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerObservationV1(Observation):
    CONTRACT: ClassVar[str] = "PlayerObservationV1"
    player: EntityReference
    name: str
    team: EntityReference | None = None
    position: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CoachObservationV1(Observation):
    CONTRACT: ClassVar[str] = "CoachObservationV1"
    coach: EntityReference
    team: EntityReference
    name: str | None = None


@dataclass(frozen=True, slots=True)
class LineupMember:
    player: EntityReference
    role: Literal["STARTER", "BENCH"]
    position: str | None = None
    grid_position: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LineupObservationV1(Observation):
    CONTRACT: ClassVar[str] = "LineupObservationV1"
    fixture: EntityReference
    team: EntityReference
    lineup_mode: Literal["CONFIRMED", "PREDICTED_REPEAT_XI", "UNKNOWN"]
    players: tuple[LineupMember, ...]
    coach: EntityReference | None = None
    formation: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AvailabilityObservationV1(Observation):
    CONTRACT: ClassVar[str] = "AvailabilityObservationV1"
    team: EntityReference
    player: EntityReference
    availability_type: Literal["INJURY", "SUSPENSION", "OTHER"]
    availability_state: Literal[
        "AVAILABLE_CONFIRMED",
        "UNAVAILABLE_INJURY",
        "UNAVAILABLE_SUSPENSION",
        "UNAVAILABLE_OTHER",
        "ASSUMED_AVAILABLE_NO_REPORTED_ISSUE",
        "AVAILABILITY_UNVERIFIED",
        "UNKNOWN",
    ]
    fixture: EntityReference | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FormationObservationV1(Observation):
    CONTRACT: ClassVar[str] = "FormationObservationV1"
    fixture: EntityReference
    team: EntityReference
    formation: str
    mode: Literal["CONFIRMED", "PREDICTED_REPEAT_XI"]


@dataclass(frozen=True, slots=True, kw_only=True)
class EventObservationV1(Observation):
    CONTRACT: ClassVar[str] = "EventObservationV1"
    fixture: EntityReference
    event_type: Literal[
        "GOAL",
        "DISALLOWED_GOAL",
        "YELLOW_CARD",
        "RED_CARD",
        "SUBSTITUTION",
        "CORNER",
    ]
    team: EntityReference | None = None
    player: EntityReference | None = None
    minute: Count | None = None
    added_time: Count | None = None
    period: str | None = None
    own_goal: bool | None = None
    penalty: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ShotObservationV1(Observation):
    """Normalized coordinates use 0..1; missing coordinates remain missing."""

    CONTRACT: ClassVar[str] = "ShotObservationV1"
    fixture: EntityReference
    team: EntityReference
    player: EntityReference | None = None
    minute: Count | None = None
    second: Count | None = None
    period: str | None = None
    x_norm: Probability | None = None
    y_norm: Probability | None = None
    expected_goals: Probability | None = None
    is_penalty: bool | None = None
    is_own_goal: bool | None = None
    outcome: Literal["GOAL", "SAVED", "BLOCKED", "OFF_TARGET", "POST"] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpectedGoalsObservationV1(Observation):
    CONTRACT: ClassVar[str] = "ExpectedGoalsObservationV1"
    fixture: EntityReference
    team: EntityReference
    expected_goals: Amount
    scope: Literal["MATCH_TOTAL", "SHOT"]
    shot: EntityReference | None = None
    model_version: str | None = None
    includes_penalties: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamStatisticObservationV1(Observation):
    """Named statistics, with no EAV metric-name/value escape hatch."""

    CONTRACT: ClassVar[str] = "TeamStatisticObservationV1"
    fixture: EntityReference
    team: EntityReference
    period: str
    possession: Percentage | None = None
    total_shots: Count | None = None
    shots_on_target: Count | None = None
    corners: Count | None = None
    fouls: Count | None = None
    yellow_cards: Count | None = None
    red_cards: Count | None = None
    big_chances: Count | None = None
    saves: Count | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerStatisticObservationV1(Observation):
    CONTRACT: ClassVar[str] = "PlayerStatisticObservationV1"
    fixture: EntityReference
    team: EntityReference
    player: EntityReference
    minutes_played: Amount | None = None
    shots: Count | None = None
    goals: Count | None = None
    assists: Count | None = None
    yellow_cards: Count | None = None
    red_cards: Count | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StandingObservationV1(Observation):
    CONTRACT: ClassVar[str] = "StandingObservationV1"
    competition: EntityReference
    team: EntityReference
    season_label: str
    rank: Annotated[int, "positive"]
    played: Count
    won: Count
    drawn: Count
    lost: Count
    goals_for: Count
    goals_against: Count
    points: int


@dataclass(frozen=True, slots=True, kw_only=True)
class OddsObservationV1(Observation):
    """Three-way decimal prices; market data is not a baseline model feature."""

    CONTRACT: ClassVar[str] = "OddsObservationV1"
    fixture: EntityReference
    bookmaker: str
    market: Literal["1X2"]
    home_decimal: DecimalOdds
    draw_decimal: DecimalOdds
    away_decimal: DecimalOdds


OBSERVATION_TYPES: tuple[type[Observation], ...] = (
    FixtureObservationV1,
    ResultObservationV1,
    CompetitionObservationV1,
    TeamObservationV1,
    PlayerObservationV1,
    CoachObservationV1,
    LineupObservationV1,
    AvailabilityObservationV1,
    FormationObservationV1,
    EventObservationV1,
    ShotObservationV1,
    ExpectedGoalsObservationV1,
    TeamStatisticObservationV1,
    PlayerStatisticObservationV1,
    StandingObservationV1,
    OddsObservationV1,
)


def observation_from_bytes(payload: bytes) -> Observation:
    from football.contracts.observation_codec import decode_observation

    return decode_observation(payload)
