"""football-data.org v4 transport normalized for MVP fallback ingestion."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

API_BASE_URL = "https://api.football-data.org/v4"
Transport = Callable[[str, Mapping[str, str]], bytes]


class FootballDataOrgError(RuntimeError):
    """The provider request or response could not be used safely."""


@dataclass(frozen=True, slots=True)
class FootballDataResponse:
    path: str
    fetched_at: datetime
    raw: bytes
    rows: tuple[Mapping[str, Any], ...]
    provider_code: str = "football_data_org"


class FootballDataOrgClient:
    def __init__(self, token: str, *, transport: Transport | None = None) -> None:
        if not token:
            raise FootballDataOrgError("FOOTBALL_DATA_DOT_ORG_API_TOKEN is required")
        self._token = token
        self._transport = transport or _http_get

    def finished_matches(self, competition_code: str, season: int) -> FootballDataResponse:
        return self._get(
            f"/competitions/{competition_code}/matches",
            {"season": str(season), "status": "FINISHED"},
            "matches",
        )

    def standings(self, competition_code: str, season: int) -> FootballDataResponse:
        response = self._get(
            f"/competitions/{competition_code}/standings", {"season": str(season)}, "standings"
        )
        tables: list[Mapping[str, Any]] = []
        for standing in response.rows:
            if standing.get("type") == "TOTAL":
                tables.extend(cast(list[Mapping[str, Any]], standing.get("table", [])))
        return FootballDataResponse(response.path, response.fetched_at, response.raw, tuple(tables))

    def fixtures_for_date(
        self, requested_date: date, competition_code: str = "PL"
    ) -> FootballDataResponse:
        return self._get(
            f"/competitions/{competition_code}/matches",
            {"dateFrom": requested_date.isoformat(), "dateTo": requested_date.isoformat()},
            "matches",
        )

    def _get(
        self, path: str, query: Mapping[str, str], collection_key: str
    ) -> FootballDataResponse:
        url = f"{API_BASE_URL}{path}?{urllib.parse.urlencode(sorted(query.items()))}"
        fetched_at = datetime.now(UTC)
        try:
            raw = self._transport(url, {"X-Auth-Token": self._token})
        except (OSError, urllib.error.URLError) as error:
            raise FootballDataOrgError(f"football-data.org request failed for {path}") from error
        try:
            payload = cast(dict[str, Any], json.loads(raw))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FootballDataOrgError("football-data.org returned invalid JSON") from error
        rows = payload.get(collection_key)
        if not isinstance(rows, list):
            message = payload.get("message")
            raise FootballDataOrgError(
                f"football-data.org rejected {path}: {message or 'missing collection'}"
            )
        return FootballDataResponse(
            path, fetched_at, raw, tuple(cast(list[Mapping[str, Any]], rows))
        )


def _http_get(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        value = response.read()
    if not isinstance(value, bytes):
        raise FootballDataOrgError("football-data.org transport returned non-bytes data")
    return value
