"""Shared state, counters and pure helpers for the operational provider sync layers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import UUID

from psycopg import Connection

from football.product.domain import (
    normalize_team_name,
    sha256_json,
)
from football.providers.fotmob import (
    FotmobLiveScore,
    FotmobResponse,
    normalize_daily_matches,
)
from football.providers.pitchapi import (
    PitchApiFixture,
    PitchApiResponse,
)

FixtureObservation = FotmobLiveScore | PitchApiFixture


@dataclass(slots=True)
class SyncCounts:
    failure_reasons: dict[str, int] = field(default_factory=dict)
    attempted_requests: int = 0
    successful_requests: int = 0
    fetched: int = 0
    matched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    unmatched: int = 0
    failed: int = 0
    resources: int = 0
    canonical_fixtures_created: int = 0
    history_inserted: int = 0
    stored_observations_reconciled: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "attempted_requests": self.attempted_requests,
            "successful_requests": self.successful_requests,
            "fetched": self.fetched,
            "matched": self.matched,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "unmatched": self.unmatched,
            "failed": self.failed,
            "failure_reasons": self.failure_reasons,
            "resources": self.resources,
            "canonical_fixtures_created": self.canonical_fixtures_created,
            "history_inserted": self.history_inserted,
            "stored_observations_reconciled": self.stored_observations_reconciled,
        }

    def add(self, other: SyncCounts) -> None:
        for name, value in other.to_dict().items():
            if name != "failure_reasons":
                setattr(self, name, getattr(self, name) + value)
        for reason, count in other.failure_reasons.items():
            self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + count


@dataclass(frozen=True, slots=True)
class DetailCounts:
    attempted_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    resources: int = 0
    fresh_until: datetime | None = None


class RequestPacer:
    def __init__(self, minimum_interval_seconds: float) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("provider minimum interval must be non-negative")
        self._interval = minimum_interval_seconds
        self._last: float | None = None

    def wait(self) -> None:
        now = monotonic()
        if self._last is not None:
            remaining = self._interval - (now - self._last)
            if remaining > 0:
                sleep(remaining)
        self._last = monotonic()


def _fotmob_season_rows(
    response: FotmobResponse, league_id: str, season: str
) -> tuple[FotmobLiveScore, ...]:
    if not isinstance(response.data, Mapping):
        raise ValueError("FotMob league response must be an object")
    details = response.data.get("details", {})
    fixtures = response.data.get("fixtures", {})
    if not isinstance(details, Mapping) or not isinstance(fixtures, Mapping):
        raise ValueError("FotMob league metadata or fixtures missing")
    from football.product.provider_history_scopes import normalize_seasons

    selected = details.get("selectedSeason", response.data.get("selectedSeason"))
    if str(details.get("id")) != league_id:
        raise ValueError("FotMob fixture competition ID mismatch")
    if normalize_seasons([selected]) != normalize_seasons([season]):
        raise ValueError("FotMob selected season does not match requested season")
    if not isinstance(fixtures.get("allMatches"), list):
        raise ValueError("FotMob league fixture list missing")
    return normalize_daily_matches(
        replace(
            response,
            data={
                "leagues": [
                    {
                        "id": league_id,
                        "name": details.get("name"),
                        "matches": fixtures["allMatches"],
                    }
                ]
            },
        )
    )


def _fotmob_resources(payload: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"MATCH_DETAILS": payload}
    content = payload.get("content")
    source = content if isinstance(content, Mapping) else payload
    aliases = {
        "matchFacts": "MATCH_DETAILS",
        "events": "EVENTS",
        "stats": "STATISTICS",
        "shotmap": "SHOTS",
        "momentum": "MOMENTUM",
        "lineup": "LINEUPS",
        "playerStats": "PLAYER_RATINGS",
        "h2h": "H2H",
    }
    resources = {
        resource_type: source[key]
        for key, resource_type in aliases.items()
        if key in source and isinstance(source[key], (Mapping, list))
    }
    if "MATCH_DETAILS" not in resources:
        resources["MATCH_DETAILS"] = payload
    match_facts = source.get("matchFacts")
    if isinstance(match_facts, Mapping):
        events = match_facts.get("events")
        if isinstance(events, (Mapping, list)):
            resources["EVENTS"] = events
    return resources


def _valid_transition(current: str, incoming: str) -> bool:
    terminal = {"FINISHED", "CANCELLED", "ABANDONED", "AWARDED"}
    if current in terminal:
        return current == incoming
    allowed = {
        "SCHEDULED": {"SCHEDULED", "LIVE", "HALF_TIME", "POSTPONED", *terminal},
        "POSTPONED": {"POSTPONED", "SCHEDULED", "LIVE", *terminal},
        "LIVE": {"LIVE", "HALF_TIME", "SUSPENDED", "INTERRUPTED", *terminal},
        "HALF_TIME": {"HALF_TIME", "LIVE", "SUSPENDED", "INTERRUPTED", *terminal},
        "SUSPENDED": {"SUSPENDED", "INTERRUPTED", "LIVE", "HALF_TIME", *terminal},
        "INTERRUPTED": {"INTERRUPTED", "SUSPENDED", "LIVE", "HALF_TIME", *terminal},
    }
    return incoming in allowed.get(current, set())


def _cache_fresh_until(response: FotmobResponse | PitchApiResponse) -> datetime | None:
    if isinstance(response, FotmobResponse) and response.cache_max_age_seconds is not None:
        return response.fetched_at + timedelta(seconds=response.cache_max_age_seconds)
    return None


def _newer_calendar_row(
    row: FixtureObservation, selected: Mapping[str, tuple[FixtureObservation, UUID | None]]
) -> bool:
    previous = selected.get(row.provider_match_id)
    if previous is None:
        return True
    # Retain the current-day observation when the older calendar cannot prove
    # newer source information. Both immutable listing snapshots are retained.
    return (
        row.source_updated_at is not None
        and previous[0].source_updated_at is not None
        and row.source_updated_at > previous[0].source_updated_at
    )


def _detail_priority(item: FixtureObservation, fixture_id: UUID | None) -> tuple[int, float, str]:
    mapped = fixture_id is not None
    if item.status == "LIVE":
        rank = 0 if mapped else 1
    elif item.status in {"HALF_TIME", "INTERRUPTED", "SUSPENDED"}:
        rank = 2 if mapped else 5
    elif item.status == "FINISHED" and mapped:
        rank = 3
    elif item.status == "SCHEDULED" and mapped:
        rank = 4
    else:
        rank = 5
    return rank, abs((item.kickoff_at - item.observed_at).total_seconds()), item.provider_match_id


def _normalize_competition_name(value: str) -> str:
    normalized = normalize_team_name(value)
    normalized = re.sub(r"\blaliga\b", "la liga", normalized)
    normalized = re.sub(r"\bj league 2\b", "j2 league", normalized)
    normalized = re.sub(r"\bj league\b", "j1 league", normalized)
    normalized = re.sub(r"\bliga nacional apertura\b", "liga nacional", normalized)
    return normalized


def _fixture_observation_sha256(
    provider_code: str, row: FixtureObservation, fixture_id: UUID | None
) -> str:
    return sha256_json(
        {
            "provider": provider_code,
            "match_id": row.provider_match_id,
            "canonical_fixture_id": str(fixture_id) if fixture_id else None,
            "status": row.status,
            "provider_status": row.provider_status or None,
            "scores": [row.home_score, row.away_score],
            "result_score_basis": row.result_score_basis,
            "clock": [row.minute, row.added_time, row.period],
            "source_updated_at": (
                row.source_updated_at.isoformat() if row.source_updated_at else None
            ),
        }
    )


class OperationalProviderSyncBase:
    def __init__(
        self,
        connection: Connection[Any],
        data_root: Path,
        *,
        provider_code: str,
        stale_after_seconds: int = 180,
        minimum_interval_seconds: float = 1.0,
        kickoff_tolerance_minutes: int = 30,
    ) -> None:
        if stale_after_seconds <= 0 or not 0 <= kickoff_tolerance_minutes <= 60:
            raise ValueError("invalid operational provider sync limits")
        self.connection = connection
        self.data_root = data_root
        self.provider_code = provider_code
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.kickoff_tolerance = timedelta(minutes=kickoff_tolerance_minutes)
        self.pacer = RequestPacer(minimum_interval_seconds)
        self._geographic_scopes: dict[str, str | None] | None = None
