"""Operational PitchAPI client kept separate from immutable research acquisitions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from time import sleep
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from football.providers.base import ProviderFetchError

_BASE_URL = "https://api.pitchapi.dev"
_ID = re.compile(r"^[mltp]_[A-Za-z0-9]{6}$")
_RETRYABLE = frozenset((408, 429, 500, 502, 503, 504))


class PitchApiPayloadError(ValueError):
    """PitchAPI payload violates the operational provider contract."""


@dataclass(frozen=True, slots=True)
class PitchApiHttpResponse:
    payload: bytes
    content_type: str
    retry_after: str | None = None


class PitchApiTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        api_key: str,
        connection_timeout_seconds: float,
        request_timeout_seconds: float,
        max_bytes: int,
    ) -> PitchApiHttpResponse: ...


class UrllibPitchApiTransport:
    def __init__(
        self,
        *,
        max_attempts: int = 4,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        if not 1 <= max_attempts <= 8:
            raise ValueError("PitchAPI max attempts must be between 1 and 8")
        self._max_attempts = max_attempts
        self._sleep = sleep_fn

    def get(
        self,
        url: str,
        *,
        api_key: str,
        connection_timeout_seconds: float,
        request_timeout_seconds: float,
        max_bytes: int,
    ) -> PitchApiHttpResponse:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MatchForge/0.1 operational-provider-adapter",
                "X-API-KEY": api_key,
            },
        )
        timeout = min(connection_timeout_seconds, request_timeout_seconds)
        for attempt in range(1, self._max_attempts + 1):
            try:
                with urlopen(request, timeout=timeout) as response:
                    payload = cast(bytes, response.read(max_bytes + 1))
                    if len(payload) > max_bytes:
                        raise ProviderFetchError(f"PitchAPI response exceeds {max_bytes} bytes")
                    return PitchApiHttpResponse(
                        payload=payload,
                        content_type=response.headers.get_content_type(),
                        retry_after=response.headers.get("Retry-After"),
                    )
            except HTTPError as error:
                retry = error.headers.get("Retry-After") if error.headers is not None else None
                if error.code not in _RETRYABLE or attempt == self._max_attempts:
                    suffix = f"; retry_after={retry}" if error.code == 429 and retry else ""
                    raise ProviderFetchError(f"PitchAPI HTTP {error.code}{suffix}") from error
                self._sleep(_retry_delay(retry, attempt))
            except (URLError, OSError) as error:
                if attempt == self._max_attempts:
                    raise ProviderFetchError("PitchAPI transport failed") from error
                self._sleep(_retry_delay(None, attempt))
        raise AssertionError("unreachable PitchAPI retry state")


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after is not None:
        try:
            return min(max(float(retry_after), 0.0), 30.0)
        except ValueError:
            pass
    return min(2.0 ** (attempt - 1), 8.0)


@dataclass(frozen=True, slots=True)
class PitchApiResponse:
    path: str
    fetched_at: datetime
    sha256: str
    raw: bytes
    data: Mapping[str, Any] | list[Any]


@dataclass(frozen=True, slots=True)
class PitchApiFixture:
    provider_match_id: str
    provider_competition_id: str
    provider_home_team_id: str
    provider_away_team_id: str
    home_team_name: str
    away_team_name: str
    kickoff_at: datetime
    status: str
    provider_status: str
    home_score: int | None
    away_score: int | None
    minute: int | None
    added_time: int | None
    period: str | None
    source_updated_at: datetime | None
    observed_at: datetime
    provider_competition_name: str | None = None
    result_score_basis: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("kickoff_at", "source_updated_at", "observed_at"):
            value = payload[key]
            payload[key] = value.isoformat() if isinstance(value, datetime) else None
        return payload


class PitchApiClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: PitchApiTransport | None = None,
        connection_timeout_seconds: float = 5.0,
        request_timeout_seconds: float = 20.0,
        max_bytes: int = 8_000_000,
    ) -> None:
        if not api_key:
            raise ValueError("PITCH_API_TOKEN is required")
        if min(connection_timeout_seconds, request_timeout_seconds, max_bytes) <= 0:
            raise ValueError("PitchAPI transport limits must be positive")
        self._api_key = api_key
        self._transport = transport or UrllibPitchApiTransport()
        self._connection_timeout = connection_timeout_seconds
        self._request_timeout = request_timeout_seconds
        self._max_bytes = max_bytes

    def matches_by_date(self, day: date, *, status: str = "all") -> PitchApiResponse:
        if status not in {"all", "upcoming", "played", "live"}:
            raise ValueError("invalid PitchAPI status")
        return self._get(f"/v1/date/{day.isoformat()}", {"status": status})

    def league_matches(
        self, league_id: str, *, season: str | None = None, status: str = "all"
    ) -> PitchApiResponse:
        _resource_id(league_id, "l")
        params = {"status": status}
        if season is not None:
            if not re.fullmatch(r"\d{4}(?:/\d{4})?", season):
                raise ValueError("PitchAPI season must use YYYY or YYYY/YYYY")
            params["season"] = season
        return self._get(f"/v1/leagues/{quote(league_id)}" + "/matches", params)

    def leagues(self) -> PitchApiResponse:
        """Retrieve the documented catalogue, including available seasons."""
        return self._get("/v1/leagues", {})

    def match(self, match_id: str) -> PitchApiResponse:
        return self._match_resource(match_id, "")

    def match_resource(self, match_id: str, resource: str) -> PitchApiResponse:
        if resource not in {
            "shots",
            "events",
            "lineups",
            "momentum",
            "stats",
            "players",
            "h2h",
            "advanced",
        }:
            raise ValueError("unsupported PitchAPI match resource")
        return self._match_resource(match_id, f"/{resource}")

    def _match_resource(self, match_id: str, suffix: str) -> PitchApiResponse:
        _resource_id(match_id, "m")
        return self._get(f"/v1/matches/{quote(match_id)}{suffix}", {})

    def _get(self, path: str, params: Mapping[str, str]) -> PitchApiResponse:
        url = _BASE_URL + path
        if params:
            url += "?" + urlencode(sorted(params.items()))
        result = self._transport.get(
            url,
            api_key=self._api_key,
            connection_timeout_seconds=self._connection_timeout,
            request_timeout_seconds=self._request_timeout,
            max_bytes=self._max_bytes,
        )
        if result.content_type not in {"application/json", "text/json"} and not (
            result.content_type.endswith("+json")
        ):
            raise PitchApiPayloadError(
                f"PitchAPI response content type was not JSON: {result.content_type}"
            )
        try:
            envelope = json.loads(result.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PitchApiPayloadError("PitchAPI response was not JSON") from error
        if not isinstance(envelope, Mapping) or "data" not in envelope or "error" in envelope:
            raise PitchApiPayloadError("PitchAPI response envelope is invalid")
        data = envelope["data"]
        if not isinstance(data, (Mapping, list)):
            raise PitchApiPayloadError("PitchAPI data must be an object or array")
        return PitchApiResponse(
            path=path + (("?" + urlencode(sorted(params.items()))) if params else ""),
            fetched_at=datetime.now(UTC),
            sha256=hashlib.sha256(result.payload).hexdigest(),
            raw=result.payload,
            data=cast(Mapping[str, Any] | list[Any], data),
        )


def normalize_pitchapi_matches(response: PitchApiResponse) -> tuple[PitchApiFixture, ...]:
    data = response.data
    if not isinstance(data, Mapping):
        raise PitchApiPayloadError("PitchAPI match listing must be an object")
    rows = data.get("matches")
    if not isinstance(rows, list):
        raise PitchApiPayloadError("PitchAPI match listing is missing matches")
    league = data.get("league")
    default_league = league.get("id") if isinstance(league, Mapping) else None
    default_league_name = league.get("name") if isinstance(league, Mapping) else None
    result: list[PitchApiFixture] = []
    seen: set[str] = set()
    for value in rows:
        if not isinstance(value, Mapping):
            raise PitchApiPayloadError("PitchAPI match row must be an object")
        match_id = _resource_id(value.get("id"), "m")
        if match_id in seen:
            raise PitchApiPayloadError("duplicate PitchAPI match ID")
        seen.add(match_id)
        row_league = value.get("league")
        league_id = row_league.get("id") if isinstance(row_league, Mapping) else default_league
        league_name = (
            row_league.get("name") if isinstance(row_league, Mapping) else default_league_name
        )
        home = _mapping(value.get("home_team"), "home_team")
        away = _mapping(value.get("away_team"), "away_team")
        kickoff = _timestamp(value.get("time_utc"), "time_utc")
        provider_status = _text(value.get("status"), "status").casefold()
        home_score = _score(value.get("score_home"))
        away_score = _score(value.get("score_away"))
        if (home_score is None) != (away_score is None):
            raise PitchApiPayloadError("PitchAPI scores must be both present or both absent")
        result.append(
            PitchApiFixture(
                provider_match_id=match_id,
                provider_competition_id=_resource_id(league_id, "l"),
                provider_home_team_id=_resource_id(home.get("id"), "t"),
                provider_away_team_id=_resource_id(away.get("id"), "t"),
                home_team_name=_text(home.get("name"), "home team name"),
                away_team_name=_text(away.get("name"), "away team name"),
                kickoff_at=kickoff,
                status=_status(provider_status),
                provider_status=provider_status,
                home_score=home_score,
                away_score=away_score,
                minute=_optional_int(value.get("minute"), 180),
                added_time=_optional_int(value.get("added_time"), 30),
                period=_optional_text(value.get("period"), 40),
                source_updated_at=_optional_timestamp(value.get("updated_at")),
                observed_at=response.fetched_at,
                provider_competition_name=(
                    league_name.strip()
                    if isinstance(league_name, str) and league_name.strip()
                    else None
                ),
                result_score_basis=(
                    "REGULATION_90"
                    if provider_status == "finished" and response.path.startswith("/v1/leagues/")
                    else "UNKNOWN"
                ),
            )
        )
    return tuple(result)


def _status(value: str) -> str:
    values = {
        "scheduled": "SCHEDULED",
        "upcoming": "SCHEDULED",
        "not_started": "SCHEDULED",
        "live": "LIVE",
        "started": "LIVE",
        "half_time": "HALF_TIME",
        "halftime": "HALF_TIME",
        "finished": "FINISHED",
        "postponed": "POSTPONED",
        "cancelled": "CANCELLED",
        "abandoned": "ABANDONED",
        "suspended": "SUSPENDED",
        "interrupted": "INTERRUPTED",
        "awarded": "AWARDED",
    }
    try:
        return values[value]
    except KeyError as error:
        raise PitchApiPayloadError(f"unsupported PitchAPI match status: {value}") from error


def _resource_id(value: Any, prefix: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or not value.startswith(prefix + "_"):
        raise PitchApiPayloadError(f"invalid PitchAPI {prefix} identifier")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PitchApiPayloadError(f"PitchAPI {label} must be an object")
    return cast(Mapping[str, Any], value)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PitchApiPayloadError(f"PitchAPI {label} is required")
    return value.strip()


def _score(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise PitchApiPayloadError("invalid PitchAPI score")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise PitchApiPayloadError(f"PitchAPI {label} is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PitchApiPayloadError(f"invalid PitchAPI {label}") from error
    if result.tzinfo is None:
        raise PitchApiPayloadError(f"PitchAPI {label} must include timezone")
    return result.astimezone(UTC)


def _optional_timestamp(value: Any) -> datetime | None:
    return _timestamp(value, "updated_at") if value is not None else None


def _optional_int(value: Any, maximum: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        raise PitchApiPayloadError("invalid PitchAPI match clock")
    return value


def _optional_text(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PitchApiPayloadError("invalid PitchAPI period")
    return value
