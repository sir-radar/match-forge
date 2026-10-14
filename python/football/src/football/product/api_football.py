"""API-Football transport and response normalization for MVP ingestion."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, cast

from psycopg import connect

from football.product.history_requests import retry_after_time
from football.providers.base import HttpResponseV1, ProviderFetchError, open_bounded, read_bounded

API_BASE_URL = "https://v3.football.api-sports.io"
Transport = Callable[[str, Mapping[str, str]], bytes | HttpResponseV1]


@dataclass(frozen=True, slots=True)
class RequestReservation:
    window_date: date
    sequence: int
    requested_at: datetime


class RequestBudget(Protocol):
    def before_request(self) -> RequestReservation: ...

    def record_response(
        self, reservation: RequestReservation, remaining: int | None, minute_remaining: int | None
    ) -> None: ...

    def record_rejection(
        self, reservation: RequestReservation, detail: str, retry_after: str | None = None
    ) -> None: ...


class PostgresApiFootballBudget:
    """Persistent daily request circuit; reset is date-based, not a guessed timestamp."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def before_request(self) -> RequestReservation:
        with (
            connect(self.database_url, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """WITH request_clock AS (SELECT clock_timestamp() AS requested_at)
                   INSERT INTO football.provider_request_budgets (
                       provider_code, window_date, requests_used, deferred_until
                   ) SELECT 'api_football', (requested_at AT TIME ZONE 'UTC')::date, 1,
                       (SELECT max(deferred_until) FROM football.provider_request_budgets
                        WHERE provider_code = 'api_football') FROM request_clock
                   WHERE NOT EXISTS (SELECT 1 FROM football.provider_request_budgets
                       WHERE provider_code = 'api_football' AND deferred_until > requested_at)
                   ON CONFLICT (provider_code, window_date) DO UPDATE SET
                       requests_used = football.provider_request_budgets.requests_used + 1,
                       remaining_requests =
                           football.provider_request_budgets.remaining_requests - 1,
                       exhausted = COALESCE(
                           football.provider_request_budgets.remaining_requests = 1, false),
                       minute_remaining = CASE WHEN
                           football.provider_request_budgets.minute_window >
                               (SELECT requested_at FROM request_clock) - interval '1 minute'
                           THEN football.provider_request_budgets.minute_remaining - 1
                           ELSE football.provider_request_budgets.minute_remaining END,
                       deferred_until = GREATEST(
                           football.provider_request_budgets.deferred_until,
                           CASE WHEN football.provider_request_budgets.minute_remaining = 1 AND
                               football.provider_request_budgets.minute_window >
                                   (SELECT requested_at FROM request_clock) - interval '1 minute'
                           THEN (SELECT requested_at FROM request_clock) + interval '1 minute'
                           END),
                       updated_at = clock_timestamp()
                   WHERE NOT football.provider_request_budgets.exhausted
                     AND (football.provider_request_budgets.remaining_requests IS NULL
                          OR football.provider_request_budgets.remaining_requests > 0)
                     AND (football.provider_request_budgets.minute_window IS NULL
                          OR football.provider_request_budgets.minute_window <=
                              (SELECT requested_at FROM request_clock) - interval '1 minute'
                          OR football.provider_request_budgets.minute_remaining IS NULL
                          OR football.provider_request_budgets.minute_remaining > 0)
                     AND (football.provider_request_budgets.deferred_until IS NULL
                          OR football.provider_request_budgets.deferred_until <= clock_timestamp())
                   RETURNING window_date, requests_used, (SELECT requested_at FROM request_clock)"""
            )
            row = cursor.fetchone()
            if row is None:
                raise ApiFootballError("API-Football quota or cooldown active; request suppressed")
            return RequestReservation(*row)

    def record_response(
        self, reservation: RequestReservation, remaining: int | None, minute_remaining: int | None
    ) -> None:
        with (
            connect(self.database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """SELECT remaining_requests, requests_used, exhausted,
                          minute_window, minute_remaining
                   FROM football.provider_request_budgets
                   WHERE provider_code = 'api_football' AND window_date = %s FOR UPDATE""",
                (reservation.window_date,),
            )
            state = cursor.fetchone()
            if state is None:
                raise ApiFootballError("API-Football quota reservation is missing")
            candidate = _monotonic_remaining(state[0], remaining, state[1] - reservation.sequence)
            if state[2]:
                candidate = 0
            minute = reservation.requested_at
            effective_minute = _monotonic_remaining(
                None, minute_remaining, state[1] - reservation.sequence
            )
            minute_window, minute_value = _minute_quota(
                state[3], state[4], minute, effective_minute
            )
            cursor.execute(
                """UPDATE football.provider_request_budgets
                      SET remaining_requests = %s, exhausted = exhausted OR COALESCE(%s = 0, false),
                          minute_window = %s, minute_remaining = %s,
                          deferred_until = GREATEST(deferred_until,
                              CASE WHEN %s::integer = 0
                                   THEN clock_timestamp()+interval '1 minute' END),
                          updated_at = clock_timestamp()
                    WHERE provider_code = 'api_football' AND window_date = %s""",
                (
                    candidate,
                    candidate,
                    minute_window,
                    minute_value,
                    minute_value,
                    reservation.window_date,
                ),
            )

    def record_rejection(
        self, reservation: RequestReservation, detail: str, retry_after: str | None = None
    ) -> None:
        lowered = detail.casefold()
        if not any(
            marker in lowered for marker in ("request limit", "quota", "rate limit", "ratelimit")
        ):
            return
        daily = "daily" in lowered or "for the day" in lowered
        until = retry_after_time(retry_after, datetime.now(UTC)) if not daily else None
        with (
            connect(self.database_url, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """UPDATE football.provider_request_budgets
                      SET remaining_requests = CASE WHEN %s THEN 0 ELSE remaining_requests END,
                          exhausted = exhausted OR %s,
                          deferred_until = GREATEST(deferred_until, %s),
                          last_error = %s, updated_at = clock_timestamp()
                    WHERE provider_code = 'api_football' AND window_date = %s""",
                (daily, daily, until, detail[:1000], reservation.window_date),
            )


def _monotonic_remaining(current: int | None, reported: int | None, later: int = 0) -> int | None:
    if reported is None:
        return current
    candidate = max(0, reported - max(0, later))
    return candidate if current is None else min(current, candidate)


def _minute_quota(
    current_window: datetime | None, current: int | None, window: datetime, reported: int | None
) -> tuple[datetime, int | None]:
    if current_window is not None and abs(window - current_window) < timedelta(minutes=1):
        return current_window, _monotonic_remaining(current, reported)
    if current_window is not None and current_window > window:
        return current_window, current
    return window, reported


class ApiFootballError(RuntimeError):
    """The provider request or response could not be used safely."""

    def __init__(self, message: str, *, capability_status: CapabilityStatus | None = None) -> None:
        super().__init__(message)
        self.capability_status = capability_status


class CapabilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED_BY_COMPETITION = "UNSUPPORTED_BY_COMPETITION"
    PLAN_RESTRICTION = "PLAN_RESTRICTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ApiResponse:
    path: str
    fetched_at: datetime
    raw: bytes
    rows: tuple[Mapping[str, Any], ...]
    remaining_day: int | None
    remaining_minute: int | None = None


class ApiFootballClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: Transport | None = None,
        request_budget: RequestBudget | None = None,
    ) -> None:
        if not api_key:
            raise ApiFootballError("API_FOOTBALL_API_KEY is required")
        self._api_key = api_key
        self._transport = transport or _http_get
        self._request_budget = request_budget

    def competitions(self) -> ApiResponse:
        return self._get("/leagues", {"current": "true"})

    def fixtures_for_date(self, requested_date: date) -> ApiResponse:
        return self._get("/fixtures", {"date": requested_date.isoformat()})

    def finished_fixtures(self, league_id: int, season: int) -> ApiResponse:
        return self._get(
            "/fixtures",
            {"league": str(league_id), "season": str(season), "status": "FT"},
        )

    def standings(self, league_id: int, season: int) -> ApiResponse:
        return self._get("/standings", {"league": str(league_id), "season": str(season)})

    def predictions(self, fixture_id: int) -> ApiResponse:
        return self._get("/predictions", {"fixture": str(fixture_id)})

    def injuries(self, fixture_id: int) -> ApiResponse:
        return self._get("/injuries", {"fixture": str(fixture_id)})

    def lineups(self, fixture_id: int) -> ApiResponse:
        return self._get("/fixtures/lineups", {"fixture": str(fixture_id)})

    def _get(self, path: str, query: Mapping[str, str]) -> ApiResponse:
        reservation = self._request_budget.before_request() if self._request_budget else None
        url = f"{API_BASE_URL}{path}?{urllib.parse.urlencode(sorted(query.items()))}"
        try:
            result = self._transport(url, {"x-apisports-key": self._api_key})
        except urllib.error.HTTPError as error:
            self._record_http_error(reservation, error)
            raise ApiFootballError(f"API-Football request failed for {path}") from error
        except (OSError, urllib.error.URLError, ProviderFetchError) as error:
            raise ApiFootballError(f"API-Football request failed for {path}") from error
        fetched_at = datetime.now(UTC)
        raw = result.payload if isinstance(result, HttpResponseV1) else result
        headers = result.headers if isinstance(result, HttpResponseV1) else {}
        remaining, minute_remaining = self._record_quota(reservation, headers)
        try:
            payload = cast(dict[str, Any], json.loads(raw))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiFootballError("API-Football returned invalid JSON") from error
        provider_errors = payload.get("errors")
        if provider_errors not in ({}, []):
            detail = str(provider_errors)
            if self._request_budget is not None and reservation is not None:
                self._request_budget.record_rejection(reservation, detail)
            lowered = detail.casefold()
            capability_status = (
                CapabilityStatus.PLAN_RESTRICTION
                if any(marker in lowered for marker in ("plan", "subscription", "access"))
                else None
            )
            raise ApiFootballError(
                f"API-Football rejected {path}: {provider_errors}",
                capability_status=capability_status,
            )
        response = payload.get("response")
        if not isinstance(response, list):
            raise ApiFootballError("API-Football response must contain a list")
        return ApiResponse(
            path,
            fetched_at,
            raw,
            tuple(cast(list[Mapping[str, Any]], response)),
            remaining,
            minute_remaining,
        )

    def _record_quota(
        self, reservation: RequestReservation | None, headers: Mapping[str, str]
    ) -> tuple[int | None, int | None]:
        normalized = {key.casefold(): value for key, value in headers.items()}
        remaining = _quota_header(normalized.get("x-ratelimit-requests-remaining"))
        minute = _quota_header(normalized.get("x-ratelimit-remaining"))
        if self._request_budget is not None and reservation is not None:
            self._request_budget.record_response(reservation, remaining, minute)
        return remaining, minute

    def _record_http_error(
        self, reservation: RequestReservation | None, error: urllib.error.HTTPError
    ) -> None:
        try:
            headers = dict(error.headers.items()) if error.headers else {}
            self._record_quota(reservation, headers)
            if error.code == 429 and self._request_budget is not None and reservation is not None:
                retry = next(
                    (value for key, value in headers.items() if key.casefold() == "retry-after"),
                    None,
                )
                self._request_budget.record_rejection(reservation, "HTTP 429 rate limit", retry)
        finally:
            error.close()


def fixture_status(short_status: str) -> str:
    if short_status in {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}:
        return "LIVE"
    if short_status in {"FT", "AET", "PEN"}:
        return "FINISHED"
    if short_status in {"PST"}:
        return "POSTPONED"
    if short_status in {"CANC"}:
        return "CANCELLED"
    if short_status in {"ABD"}:
        return "ABANDONED"
    return "SCHEDULED"


def continent_for_country(country: str) -> str:
    if country in _AFRICA:
        return "Africa"
    if country in _ASIA:
        return "Asia"
    if country in _NORTH_AMERICA:
        return "North/Central America"
    if country in _SOUTH_AMERICA:
        return "South America"
    if country in _OCEANIA:
        return "Oceania"
    if country in _EUROPE:
        return "Europe"
    if country in {"World"}:
        return "World"
    return "Other"


def inferred_division(name: str, competition_type: str) -> int | None:
    if competition_type != "League":
        return None
    value = name.casefold()
    second_markers = (
        "championship",
        "2. bundesliga",
        "segunda",
        "serie b",
        "ligue 2",
        "league two",
        "eerste divisie",
        "division 2",
        "2nd division",
        "second league",
    )
    if any(marker in value for marker in second_markers):
        return 2
    lower_markers = ("3rd", "third", "regional", "reserve", "women", "u19", "u21", "youth")
    if any(marker in value for marker in lower_markers):
        return None
    return 1


def context_capability(competition: Mapping[str, Any], resource: str) -> CapabilityStatus:
    """Return only capability states explicitly supported by provider coverage metadata."""
    coverage = competition.get("coverage")
    if not isinstance(coverage, Mapping):
        return CapabilityStatus.UNKNOWN
    if resource in {"INJURIES", "SUSPENSIONS"}:
        value = coverage.get("injuries")
    elif resource == "LINEUPS":
        fixtures = coverage.get("fixtures")
        value = fixtures.get("lineups") if isinstance(fixtures, Mapping) else None
    else:
        raise ValueError(f"unsupported context resource: {resource}")
    if value is True:
        return CapabilityStatus.SUPPORTED
    if value is False:
        return CapabilityStatus.UNSUPPORTED_BY_COMPETITION
    return CapabilityStatus.UNKNOWN


def _http_get(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
    request = urllib.request.Request(url, headers=dict(headers))
    with open_bounded(request, timeout=30) as response:  # noqa: S310
        return HttpResponseV1(
            payload=read_bounded(response, max_bytes=8 * 1024 * 1024, timeout_seconds=30),
            status=response.status,
            content_type=response.headers.get_content_type(),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            headers={
                key.casefold(): value
                for key, value in response.headers.items()
                if key.casefold()
                in {
                    "x-ratelimit-requests-remaining",
                    "x-ratelimit-remaining",
                    "retry-after",
                    "date",
                }
            },
        )


def _quota_header(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal() or len(value) > 10:
        return None
    parsed = int(value)
    return parsed if parsed <= 2**31 - 1 else None


_AFRICA = frozenset(
    {
        "Algeria",
        "Angola",
        "Benin",
        "Botswana",
        "Burkina-Faso",
        "Burundi",
        "Cameroon",
        "Congo",
        "Congo-DR",
        "Egypt",
        "Eswatini",
        "Ethiopia",
        "Gabon",
        "Gambia",
        "Ghana",
        "Guinea",
        "Ivory-Coast",
        "Kenya",
        "Lesotho",
        "Liberia",
        "Libya",
        "Malawi",
        "Mali",
        "Mauritania",
        "Mauritius",
        "Morocco",
        "Namibia",
        "Nigeria",
        "Rwanda",
        "Senegal",
        "Somalia",
        "South-Africa",
        "Sudan",
        "Tanzania",
        "Togo",
        "Tunisia",
        "Uganda",
        "Zambia",
        "Zimbabwe",
    }
)
_ASIA = frozenset(
    {
        "Bahrain",
        "Bangladesh",
        "Bhutan",
        "Cambodia",
        "China",
        "Chinese-Taipei",
        "Hong-Kong",
        "India",
        "Indonesia",
        "Iran",
        "Iraq",
        "Japan",
        "Jordan",
        "Kuwait",
        "Kyrgyzstan",
        "Laos",
        "Lebanon",
        "Macao",
        "Malaysia",
        "Maldives",
        "Mongolia",
        "Myanmar",
        "Nepal",
        "Oman",
        "Pakistan",
        "Palestine",
        "Philippines",
        "Qatar",
        "Saudi-Arabia",
        "Singapore",
        "South-Korea",
        "Syria",
        "Tajikistan",
        "Thailand",
        "Turkmenistan",
        "United-Arab-Emirates",
        "Uzbekistan",
        "Vietnam",
        "Yemen",
    }
)
_NORTH_AMERICA = frozenset(
    {
        "Antigua-And-Barbuda",
        "Aruba",
        "Barbados",
        "Belize",
        "Bermuda",
        "Canada",
        "Costa-Rica",
        "Cuba",
        "Curacao",
        "Dominican-Republic",
        "El-Salvador",
        "Grenada",
        "Guadeloupe",
        "Guatemala",
        "Haiti",
        "Honduras",
        "Jamaica",
        "Mexico",
        "Nicaragua",
        "Panama",
        "Trinidad-And-Tobago",
        "USA",
    }
)
_SOUTH_AMERICA = frozenset(
    {
        "Argentina",
        "Bolivia",
        "Brazil",
        "Chile",
        "Colombia",
        "Ecuador",
        "Paraguay",
        "Peru",
        "Suriname",
        "Uruguay",
        "Venezuela",
    }
)
_OCEANIA = frozenset({"Australia", "Fiji", "New-Zealand", "Papua-New-Guinea", "Tahiti"})
_EUROPE = frozenset(
    {
        "Albania",
        "Andorra",
        "Armenia",
        "Austria",
        "Azerbaijan",
        "Belarus",
        "Belgium",
        "Bosnia",
        "Bulgaria",
        "Croatia",
        "Cyprus",
        "Czech-Republic",
        "Denmark",
        "England",
        "Estonia",
        "Faroe-Islands",
        "Finland",
        "France",
        "Georgia",
        "Germany",
        "Gibraltar",
        "Greece",
        "Hungary",
        "Iceland",
        "Ireland",
        "Israel",
        "Italy",
        "Kazakhstan",
        "Kosovo",
        "Latvia",
        "Liechtenstein",
        "Lithuania",
        "Luxembourg",
        "Macedonia",
        "Malta",
        "Moldova",
        "Montenegro",
        "Netherlands",
        "Northern-Ireland",
        "Norway",
        "Poland",
        "Portugal",
        "Romania",
        "Russia",
        "San-Marino",
        "Scotland",
        "Serbia",
        "Slovakia",
        "Slovenia",
        "Spain",
        "Sweden",
        "Switzerland",
        "Turkey",
        "Ukraine",
        "Wales",
    }
)
