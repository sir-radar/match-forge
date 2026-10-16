"""Resource capabilities share transport evidence, never a combined football row."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from football.contracts.source import PROVIDER_PATTERN, SourceContractError


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderPayload:
    provider: str
    resource_key: str
    acquired_at: datetime
    raw: bytes
    media_type: str
    source_revision: str | None = None
    cache_max_age_seconds: int | None = None
    remaining_requests: int | None = None
    minute_remaining: int | None = None

    def __post_init__(self) -> None:
        if not PROVIDER_PATTERN.fullmatch(self.provider):
            raise SourceContractError("source provider must use lowercase snake_case")
        if not self.resource_key or not self.media_type or not isinstance(self.raw, bytes):
            raise SourceContractError("source key, media type and immutable bytes are required")
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise SourceContractError("source acquisition time requires a timezone")
        if self.source_revision is not None and not self.source_revision:
            raise SourceContractError("source revision cannot be empty")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


def numeric_identifier(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise SourceContractError("provider identifier or season must be a positive integer")
    return int(value)


@runtime_checkable
class FixtureSource(Protocol):
    def fixtures(self, day: date) -> ProviderPayload: ...


@runtime_checkable
class ResultSource(Protocol):
    def results(self, provider_competition_id: str, season: str) -> ProviderPayload: ...


@runtime_checkable
class CompetitionSource(Protocol):
    def competitions(self) -> ProviderPayload: ...


@runtime_checkable
class TeamSource(Protocol):
    def team(self, provider_team_id: str) -> ProviderPayload: ...


@runtime_checkable
class PlayerSource(Protocol):
    def player(self, provider_player_id: str) -> ProviderPayload: ...


@runtime_checkable
class CoachSource(Protocol):
    def coaches(self, provider_match_id: str) -> ProviderPayload: ...


@runtime_checkable
class LineupSource(Protocol):
    def lineups(self, provider_match_id: str) -> ProviderPayload: ...


@runtime_checkable
class AvailabilitySource(Protocol):
    def availability(self, provider_match_id: str) -> ProviderPayload: ...


@runtime_checkable
class EventSource(Protocol):
    def events(self, provider_match_id: str) -> ProviderPayload: ...


@runtime_checkable
class ShotSource(Protocol):
    def shots(self, provider_match_id: str) -> ProviderPayload: ...


@runtime_checkable
class ExpectedGoalsSource(Protocol):
    def expected_goals(self, provider_match_id: str) -> ProviderPayload: ...


@runtime_checkable
class StatisticsSource(Protocol):
    def statistics(self, provider_match_id: str) -> ProviderPayload: ...


@runtime_checkable
class StandingSource(Protocol):
    def standings(self, provider_competition_id: str, season: str) -> ProviderPayload: ...


@runtime_checkable
class OddsSource(Protocol):
    def odds(self, provider_competition_id: str, season: str) -> ProviderPayload: ...
