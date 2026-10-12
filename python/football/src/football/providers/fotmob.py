"""Optional, backend-only FotMob adapter for ordinary accessible JSON endpoints.

This module supports the operational sync while preserving provider IDs and timestamps
for the existing resolution layer. Detailed observations remain development-only.
The upstream MIT project and operational limits are documented in
docs/MVP-OPERATIONAL-PROVIDERS.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

from football.providers.base import (
    HttpResponseTransport,
    HttpTransport,
    ProviderFetchError,
    UrllibHttpTransport,
)

_BASE_URL = "https://www.fotmob.com/api/data"
_ID_PATTERN = re.compile(r"^[0-9]{1,20}$")


class FotmobAccessError(RuntimeError):
    """FotMob access has not been explicitly enabled for this installation."""


class FotmobPayloadError(ValueError):
    """A provider payload is missing required match identity or timing data."""


@dataclass(frozen=True, slots=True)
class FotmobResponse:
    resource_url: str
    fetched_at: datetime
    sha256: str
    raw: bytes
    data: Mapping[str, Any] | list[Any]
    cache_max_age_seconds: int | None = None
    content_type: str = "application/json"


@dataclass(frozen=True, slots=True)
class FotmobLiveScore:
    """Provider-only observation; NOT a verified MatchForge canonical fixture."""

    provider_match_id: str
    provider_competition_id: str
    provider_home_team_id: str
    provider_away_team_id: str
    home_team_name: str
    away_team_name: str
    kickoff_at: datetime
    status: str
    provider_status: str | None
    home_score: int | None
    away_score: int | None
    clock: str | None
    minute: int | None
    added_time: int | None
    period: str | None
    source_updated_at: datetime | None
    cache_expires_at: datetime | None
    observed_at: datetime
    provider_competition_name: str | None = None
    result_score_basis: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in (
            "kickoff_at",
            "source_updated_at",
            "cache_expires_at",
            "observed_at",
        ):
            value = result[key]
            result[key] = value.isoformat() if isinstance(value, datetime) else None
        return result


class FotmobClient:
    """Subset of the upstream read-only API with controlled backend acquisition.

    No method performs network I/O unless ``access_approved`` is True. This
    flag is an explicit deployment opt-in.
    No browser headers, signing, anti-bot workarounds, or fallback hosts exist.
    """

    def __init__(
        self,
        *,
        access_approved: bool = False,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 10.0,
        max_bytes: int = 4_000_000,
    ) -> None:
        if timeout_seconds <= 0 or max_bytes <= 0:
            raise ValueError("FotMob transport limits must be positive")
        self._access_approved = access_approved
        self._transport = transport or UrllibHttpTransport(
            user_agent="MatchForge/0.1 approved-provider-adapter",
            accept="application/json",
        )
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes

    def matches_by_date(self, day: date) -> FotmobResponse:
        return self._get("matches", {"date": day.strftime("%Y%m%d")})

    def match_details(self, match_id: int | str) -> FotmobResponse:
        return self._get("matchDetails", {"matchId": _provider_id(match_id)})

    def league_data_for_match(self, match_id: int | str, league_id: int | str) -> FotmobResponse:
        return self._get(
            "leagueDataForMatch",
            {"matchId": _provider_id(match_id), "leagueId": _provider_id(league_id)},
        )

    def league(self, league_id: int | str, season: str | None = None) -> FotmobResponse:
        params = {"id": _provider_id(league_id)}
        if season is not None:
            if not re.fullmatch(r"\d{4}(?:/\d{4})?", season):
                raise ValueError("invalid FotMob season")
            params["season"] = season
        return self._get("leagues", params)

    def league_seasons(self, league_id: int | str) -> FotmobResponse:
        return self._get("leagueseasondeepstats", {"id": _provider_id(league_id)})

    def table(self, league_id: int | str) -> FotmobResponse:
        return self._get("tltable", {"leagueId": _provider_id(league_id)})

    def fixtures(self, league_id: int | str) -> FotmobResponse:
        return self._get("fixtures", {"id": _provider_id(league_id)})

    def team(self, team_id: int | str) -> FotmobResponse:
        return self._get("teams", {"id": _provider_id(team_id)})

    def player(self, player_id: int | str) -> FotmobResponse:
        return self._get("playerData", {"id": _provider_id(player_id)})

    def all_leagues(self) -> FotmobResponse:
        return self._get("allLeagues", {})

    def search(self, term: str) -> FotmobResponse:
        if not term.strip() or len(term) > 100 or any(ord(c) < 32 for c in term):
            raise ValueError("search term must be 1–100 printable characters")
        return self._get("search/suggest", {"term": term})

    def transfers(self, page: int = 1) -> FotmobResponse:
        if type(page) is not int or page < 1 or page > 1000:
            raise ValueError("invalid FotMob transfers page")
        return self._get("transfers", {"page": str(page)})

    def _get(self, path: str, params: Mapping[str, str]) -> FotmobResponse:
        if not self._access_approved:
            raise FotmobAccessError("FotMob access disabled: enable the development provider")
        url = f"{_BASE_URL}/{path}"
        if params:
            url += "?" + urlencode(sorted(params.items()))
        try:
            raw, content_type, cache_control = self._fetch_transport(url)
        except ProviderFetchError:
            raise
        except FotmobPayloadError:
            raise
        except (OSError, ValueError) as error:
            raise ProviderFetchError("FotMob transport failed") from error
        if len(raw) > self._max_bytes:
            raise FotmobPayloadError("FotMob payload exceeded configured byte limit")
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FotmobPayloadError("FotMob response was not JSON") from error
        if not isinstance(data, (dict, list)):
            raise FotmobPayloadError("FotMob response must be an object or array")
        return FotmobResponse(
            resource_url=url,
            fetched_at=datetime.now(UTC),
            sha256=hashlib.sha256(raw).hexdigest(),
            raw=raw,
            data=cast(Mapping[str, Any] | list[Any], data),
            cache_max_age_seconds=_cache_max_age(cache_control),
            content_type=content_type,
        )

    def _fetch_transport(self, url: str) -> tuple[bytes, str, str | None]:
        if not hasattr(self._transport, "get_response"):
            raw = self._transport.get(
                url, timeout_seconds=self._timeout_seconds, max_bytes=self._max_bytes
            )
            return raw, "application/json", None
        result = cast(HttpResponseTransport, self._transport).get_response(
            url, timeout_seconds=self._timeout_seconds, max_bytes=self._max_bytes
        )
        if not _json_content_type(result.content_type):
            raise FotmobPayloadError(
                f"FotMob response content type was not JSON: {result.content_type}"
            )
        return result.payload, result.content_type, result.cache_control


def normalize_daily_matches(response: FotmobResponse) -> tuple[FotmobLiveScore, ...]:
    """Fail closed on malformed rows; do not guess canonical team or fixture IDs."""
    if not isinstance(response.data, Mapping):
        raise FotmobPayloadError("daily match response must be an object")
    leagues = response.data.get("leagues")
    if not isinstance(leagues, list):
        raise FotmobPayloadError("daily match response is missing leagues")
    observations: list[FotmobLiveScore] = []
    seen: set[str] = set()
    for league in leagues:
        if not isinstance(league, Mapping) or not isinstance(league.get("matches"), list):
            raise FotmobPayloadError("invalid league match list")
        league_id = _provider_id(league.get("id"))
        league_name = league.get("name")
        if not isinstance(league_name, str) or not league_name.strip():
            league_name = None
        for row in league["matches"]:
            if not isinstance(row, Mapping):
                raise FotmobPayloadError("invalid match row")
            observation = _normalize_match(
                row,
                league_id,
                response.fetched_at,
                response.cache_max_age_seconds,
                league_name,
            )
            if observation.provider_match_id in seen:
                raise FotmobPayloadError("duplicate FotMob match ID")
            seen.add(observation.provider_match_id)
            observations.append(observation)
    return tuple(observations)


def _normalize_match(
    row: Mapping[str, Any],
    league_id: str,
    observed_at: datetime,
    cache_max_age_seconds: int | None,
    league_name: str | None,
) -> FotmobLiveScore:
    home = _object(row.get("home"), "home team")
    away = _object(row.get("away"), "away team")
    status = _object(row.get("status"), "status")
    utc_time = status.get("utcTime")
    if not isinstance(utc_time, str):
        raise FotmobPayloadError("match kickoff must include a UTC timestamp")
    try:
        kickoff = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
    except ValueError as error:
        raise FotmobPayloadError("invalid match kickoff timestamp") from error
    if kickoff.tzinfo is None or kickoff.utcoffset() is None:
        raise FotmobPayloadError("match kickoff timezone is required")
    live_time = status.get("liveTime")
    provider_clock, minute, added_time = _live_clock(live_time)
    reason = status.get("reason")
    provider_status = reason.get("short") if isinstance(reason, Mapping) else None
    if not isinstance(provider_status, str):
        provider_status = provider_clock if isinstance(provider_clock, str) else None
    if isinstance(provider_clock, str) and len(provider_clock) > 20:
        provider_clock = None
    source_updated_at = _optional_datetime(status.get("updatedAt"))
    home_score, away_score = _match_scores(home, away, status)
    return FotmobLiveScore(
        provider_match_id=_provider_id(row.get("id")),
        provider_competition_id=league_id,
        provider_home_team_id=_provider_id(home.get("id")),
        provider_away_team_id=_provider_id(away.get("id")),
        home_team_name=_team_name(home),
        away_team_name=_team_name(away),
        kickoff_at=kickoff.astimezone(UTC),
        status=_match_status(status),
        provider_status=provider_status,
        home_score=home_score,
        away_score=away_score,
        clock=provider_clock if isinstance(provider_clock, str) else None,
        minute=minute,
        added_time=added_time,
        period=_period(status, provider_status),
        source_updated_at=source_updated_at,
        cache_expires_at=(
            observed_at + timedelta(seconds=cache_max_age_seconds)
            if cache_max_age_seconds is not None
            else None
        ),
        observed_at=observed_at,
        provider_competition_name=league_name,
        result_score_basis=_result_score_basis(provider_status, status),
    )


def _match_scores(
    home: Mapping[str, Any], away: Mapping[str, Any], status: Mapping[str, Any]
) -> tuple[int | None, int | None]:
    """League fixtures carry scoreStr; daily listings also carry team score fields."""
    scores = (_score(home.get("score")), _score(away.get("score")))
    text = status.get("scoreStr")
    parsed = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", text) if isinstance(text, str) else None
    if parsed is None:
        return scores
    aggregate = (int(parsed[1]), int(parsed[2]))
    if any(
        score is not None and score != value for score, value in zip(scores, aggregate, strict=True)
    ):
        raise FotmobPayloadError("FotMob score fields contradict scoreStr")
    return aggregate


def _result_score_basis(provider_status: str | None, status: Mapping[str, Any]) -> str:
    if not status.get("finished"):
        return "UNKNOWN"
    label = (provider_status or "").upper()
    if label in {"AET", "AFTER EXTRA TIME"}:
        return "EXTRA_TIME"
    if label in {"AP", "PEN", "PENS", "AFTER PENALTIES"}:
        return "PENALTY_SHOOTOUT"
    if label in {"FT", "FULL TIME", "FULL-TIME"}:
        return "REGULATION_90"
    return "UNKNOWN"


def _match_status(status: Mapping[str, Any]) -> str:
    for key in ("started", "finished", "cancelled"):
        if not isinstance(status.get(key), bool):
            raise FotmobPayloadError(f"FotMob match status missing boolean {key}")
    reason = status.get("reason")
    label = str(reason.get("short", "")).upper() if isinstance(reason, Mapping) else ""
    mapped = {
        "HT": "HALF_TIME",
        "HALF TIME": "HALF_TIME",
        "HALF-TIME": "HALF_TIME",
        "SUSP": "SUSPENDED",
        "SUSPENDED": "SUSPENDED",
        "INT": "INTERRUPTED",
        "INTERRUPTED": "INTERRUPTED",
        "PST": "POSTPONED",
        "POSTPONED": "POSTPONED",
        "ABD": "ABANDONED",
        "ABANDONED": "ABANDONED",
        "AWD": "AWARDED",
        "AW": "AWARDED",
        "AWARDED": "AWARDED",
    }.get(label)
    if mapped is not None:
        return mapped
    if status["cancelled"]:
        return "CANCELLED"
    if status["finished"]:
        return "FINISHED"
    if status["started"]:
        return "LIVE"
    return "SCHEDULED"


def _clock_parts(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    match = re.fullmatch(r"\s*(\d{1,3})(?:\s*\+\s*(\d{1,2}))?'?\s*", value)
    if match is None:
        return None, None
    minute = int(match.group(1))
    added = int(match.group(2)) if match.group(2) is not None else None
    if minute > 180 or (added is not None and added > 30):
        return None, None
    return minute, added


def _live_clock(value: Any) -> tuple[str | None, int | None, int | None]:
    if not isinstance(value, Mapping):
        return None, None, None
    short = value.get("short")
    provider_clock = short if isinstance(short, str) and len(short) <= 20 else None
    minute, added_time = _clock_parts(provider_clock)
    if minute is not None:
        return provider_clock, minute, added_time

    # FotMob may put a phase label such as HT in ``short`` while retaining the
    # numeric provider clock in ``long``. Use only that reported clock; never
    # infer a minute from kickoff time or local elapsed time.
    long_clock = value.get("long")
    if not isinstance(long_clock, str):
        return provider_clock, None, None
    match = re.fullmatch(
        r"\s*(\d{1,3})(?::\d{1,2})?(?:\s*\+\s*(\d{1,2})(?::\d{1,2})?)?'?\s*",
        long_clock,
    )
    if match is None:
        return provider_clock, None, None
    minute = int(match.group(1))
    added_time = int(match.group(2)) if match.group(2) is not None else None
    if minute > 180 or (added_time is not None and added_time > 30):
        return provider_clock, None, None
    return provider_clock, minute, added_time


def _period(status: Mapping[str, Any], provider_status: str | None) -> str | None:
    for key in ("period", "currentPeriod"):
        value = status.get(key)
        if isinstance(value, str) and value.strip():
            return value[:40]
    if provider_status in {"HT", "FT"}:
        return provider_status
    return None


def _optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _cache_max_age(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"(?:^|,)\s*(?:s-maxage|max-age)=(\d+)", value, re.IGNORECASE)
    if match is None:
        return None
    return min(int(match.group(1)), 86_400)


def _json_content_type(value: str) -> bool:
    return value in {"application/json", "text/json"} or value.endswith("+json")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FotmobPayloadError(f"missing {label} object")
    return cast(Mapping[str, Any], value)


def _provider_id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise FotmobPayloadError("invalid FotMob numeric identifier")
    text = str(value)
    if not _ID_PATTERN.fullmatch(text):
        raise FotmobPayloadError("invalid FotMob numeric identifier")
    return text


def _team_name(team: Mapping[str, Any]) -> str:
    value = team.get("name")
    if not isinstance(value, str) or not value.strip():
        raise FotmobPayloadError("team name is missing")
    return value


def _score(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise FotmobPayloadError("invalid match score")
    return value
