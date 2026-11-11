"""Shared state, constants and pure helpers for the product sync layers."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

from psycopg import Connection

from football.product.api_football import (
    ApiFootballClient,
)
from football.product.context_sync import (
    ContextSyncConfig,
)
from football.product.domain import (
    FinishedMatch,
    ProductForecast,
)
from football.product.football_data_org import (
    FootballDataOrgClient,
)
from football.product.identity_crosswalks import FOOTBALL_DATA_COMPETITIONS

PROVIDER_CODE = "api_football"


FALLBACK_PROVIDER_CODE = "football_data_org"


PRODUCT_FORECAST_ALGORITHM_VERSION = "transferable-rolling-goals-poisson-v1-rolling10-v2"


LOGGER = logging.getLogger(__name__)


HISTORY_JOB_LEASE = timedelta(minutes=30)


if TYPE_CHECKING:
    from football.product.history_worker import HistorySyncWorker


class HistoryWorkerFactory(Protocol):
    def __call__(self) -> AbstractContextManager[HistorySyncWorker]: ...


def _empty_standing() -> dict[str, int]:
    return {
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "goals_for": 0,
        "goals_against": 0,
        "points": 0,
    }


def _history_sync_candidates(
    league_seasons: set[tuple[int, int]],
    last_attempts: Mapping[tuple[int, int], datetime],
) -> list[tuple[int, int]]:
    return sorted(
        league_seasons,
        key=lambda item: (
            item in last_attempts,
            last_attempts.get(item, datetime.min.replace(tzinfo=UTC)),
            item[0] not in FOOTBALL_DATA_COMPETITIONS,
            item,
        ),
    )


def _season_date_bounds(
    start_value: object,
    end_value: object,
    provider_competition_id: str,
    season: int,
    snapshot_id: UUID,
) -> tuple[date | None, date | None]:
    try:
        start_date = date.fromisoformat(str(start_value)) if start_value is not None else None
    except ValueError:
        start_date = None
    try:
        end_date = date.fromisoformat(str(end_value)) if end_value is not None else None
    except ValueError:
        end_date = None

    invalid_value = (start_value is not None and start_date is None) or (
        end_value is not None and end_date is None
    )
    invalid_range = start_date is not None and end_date is not None and end_date < start_date
    if invalid_value or invalid_range:
        LOGGER.warning(
            "API-Football returned invalid season bounds for league %s season %s "
            "(start=%r end=%r snapshot=%s)",
            provider_competition_id,
            season,
            start_value,
            end_value,
            snapshot_id,
        )
    if invalid_range:
        return None, None
    return start_date, end_date


@dataclass(frozen=True)
class _PreparedForecast:
    fixture_id: UUID
    home_id: UUID
    away_id: UUID
    kickoff_at: datetime
    window: tuple[FinishedMatch, ...] | None
    forecast: ProductForecast | None
    blocked: bool


def _fixture_sync_dates(
    requested_date: date, fixture_from_date: date | None = None
) -> tuple[date, ...]:
    if fixture_from_date is not None and fixture_from_date > requested_date:
        raise ValueError("fixture backfill start date must not be after requested date")
    live_window_start = requested_date - timedelta(days=1)
    start = max(fixture_from_date or live_window_start, live_window_start)
    return tuple(
        start + timedelta(days=offset) for offset in range((requested_date - start).days + 1)
    )


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    found = value.get(key)
    if not isinstance(found, Mapping):
        raise ValueError(f"provider field {key} must be an object")
    return cast(Mapping[str, Any], found)


def _integer(value: Mapping[str, Any], key: str) -> int:
    found = value.get(key)
    if isinstance(found, bool) or not isinstance(found, int):
        raise ValueError(f"provider field {key} must be an integer")
    return found


def _league_seasons(fixtures: Iterable[Mapping[str, Any]]) -> list[tuple[int, int]]:
    values = {
        (_integer(_mapping(row, "league"), "id"), int(_mapping(row, "league")["season"]))
        for row in fixtures
    }
    return sorted(values, key=lambda item: (item[0] not in FOOTBALL_DATA_COMPETITIONS, item))


def _football_data_fixture_season(row: Mapping[str, Any]) -> int:
    season = _mapping(row, "season")
    start = season.get("startDate")
    if not isinstance(start, str):
        raise ValueError("football-data.org fixture season startDate is required")
    try:
        parsed = date.fromisoformat(start)
        if parsed.isoformat() != start:
            raise ValueError("season startDate must use YYYY-MM-DD")
        return parsed.year
    except ValueError as error:
        raise ValueError("football-data.org fixture season startDate is invalid") from error


def _football_data_status(value: str) -> str:
    if value in {"IN_PLAY", "PAUSED", "EXTRA_TIME", "PENALTY_SHOOTOUT"}:
        return "LIVE"
    if value in {"FINISHED", "AWARDED"}:
        return "FINISHED"
    if value == "POSTPONED":
        return "POSTPONED"
    if value == "CANCELLED":
        return "CANCELLED"
    if value == "SUSPENDED":
        return "ABANDONED"
    return "SCHEDULED"


def _api_football_score_basis(short_status: str) -> str:
    return {
        "FT": "REGULATION_90",
        "AET": "EXTRA_TIME",
        "PEN": "PENALTY_SHOOTOUT",
    }.get(short_status, "UNKNOWN")


def _football_data_score_basis(row: Mapping[str, Any]) -> str:
    score = row.get("score")
    duration = score.get("duration") if isinstance(score, Mapping) else None
    if not isinstance(duration, str):
        return "UNKNOWN"
    return {
        "REGULAR": "REGULATION_90",
        "EXTRA_TIME": "EXTRA_TIME",
        "PENALTY_SHOOTOUT": "PENALTY_SHOOTOUT",
    }.get(duration, "UNKNOWN")


class ProductSyncBase:
    def __init__(
        self,
        connection: Connection[Any],
        client: ApiFootballClient,
        data_root: Path,
        artifact_path: Path,
        history_fallback: FootballDataOrgClient | None = None,
        api_football_max_history_season: int | None = None,
        history_worker_factory: HistoryWorkerFactory | None = None,
        sync_run_id: UUID | None = None,
        context_config: ContextSyncConfig | None = None,
    ) -> None:
        if api_football_max_history_season is not None and api_football_max_history_season <= 0:
            raise ValueError("api_football_max_history_season must be positive")
        self.connection = connection
        self.client = client
        self.data_root = data_root
        self.artifact_path = artifact_path
        self.history_fallback = history_fallback
        self.api_football_max_history_season = api_football_max_history_season
        self.history_worker_factory = history_worker_factory
        self.sync_run_id = sync_run_id
        self.context_config = context_config or ContextSyncConfig.from_environ(os.environ)
        # Same-team, same-kickoff history collisions handed to identity review.
        self.history_identity_conflicts = 0

    def _database_now(self) -> datetime:
        row = self.connection.execute("SELECT clock_timestamp()").fetchone()
        assert row is not None
        return cast(datetime, row[0])
