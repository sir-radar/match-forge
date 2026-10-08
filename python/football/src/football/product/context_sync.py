"""Safe, bounded scheduling for API-Football pre-match context requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class ContextResource(StrEnum):
    INJURIES = "INJURIES"
    LINEUPS = "LINEUPS"


@dataclass(frozen=True, slots=True)
class ContextSyncConfig:
    context_enabled: bool = False
    injury_enabled: bool = False
    lineup_enabled: bool = False
    request_cap: int = 100
    daily_reserve: int = 20

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> ContextSyncConfig:
        return cls(
            _enabled(environ.get("MATCHFORGE_CONTEXT_SYNC_ENABLED", "false")),
            _enabled(environ.get("MATCHFORGE_INJURY_SYNC_ENABLED", "false")),
            _enabled(environ.get("MATCHFORGE_LINEUP_SYNC_ENABLED", "false")),
            _positive_int(environ.get("MATCHFORGE_CONTEXT_REQUEST_CAP", "100")),
            _nonnegative_int(environ.get("MATCHFORGE_API_FOOTBALL_DAILY_RESERVE", "20")),
        )


@dataclass(frozen=True, slots=True)
class FixtureContextTarget:
    provider_fixture_id: str
    kickoff_at: datetime
    injury_capability: str
    lineup_capability: str
    last_injury_fetch_at: datetime | None
    last_lineup_fetch_at: datetime | None
    both_lineups_confirmed: bool


@dataclass(frozen=True, slots=True)
class ContextRequest:
    provider_fixture_id: str
    resource: ContextResource


def plan_context_requests(
    targets: Sequence[FixtureContextTarget],
    now: datetime,
    remaining_day: int | None,
    config: ContextSyncConfig,
) -> tuple[ContextRequest, ...]:
    """Plan deterministic requests without consuming reserve or polling after kickoff."""
    if not config.context_enabled:
        return ()
    available = config.request_cap
    if remaining_day is not None:
        available = min(available, max(0, remaining_day - config.daily_reserve))
    if available == 0:
        return ()
    requests: list[ContextRequest] = []
    for target in sorted(targets, key=lambda item: (item.kickoff_at, item.provider_fixture_id)):
        until_kickoff = target.kickoff_at - now
        if until_kickoff <= timedelta(0):
            continue
        if (
            config.injury_enabled
            and target.injury_capability == "SUPPORTED"
            and until_kickoff <= timedelta(hours=72)
            and _due(target.last_injury_fetch_at, now, timedelta(hours=4))
        ):
            requests.append(ContextRequest(target.provider_fixture_id, ContextResource.INJURIES))
        if (
            config.lineup_enabled
            and target.lineup_capability == "SUPPORTED"
            and not target.both_lineups_confirmed
            and until_kickoff <= timedelta(minutes=90)
            and _due(target.last_lineup_fetch_at, now, timedelta(minutes=10))
        ):
            requests.append(ContextRequest(target.provider_fixture_id, ContextResource.LINEUPS))
        if len(requests) >= available:
            break
    return tuple(requests[:available])


def _due(previous: datetime | None, now: datetime, interval: timedelta) -> bool:
    return previous is None or now - previous >= interval


def _enabled(value: str) -> bool:
    return value.casefold() in {"1", "true", "yes", "on"}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("context request cap must be positive")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError("daily reserve must not be negative")
    return parsed
