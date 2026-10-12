"""API-Football transport and response normalization for MVP ingestion."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Protocol, cast

from psycopg import connect

API_BASE_URL = "https://v3.football.api-sports.io"
Transport = Callable[[str, Mapping[str, str]], bytes]


class RequestBudget(Protocol):
    def before_request(self) -> None: ...

    def record_response(self, remaining: int | None) -> None: ...

    def record_rejection(self, detail: str) -> None: ...


class PostgresApiFootballBudget:
    """Persistent daily request circuit; reset is date-based, not a guessed timestamp."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def before_request(self) -> None:
        today = datetime.now(UTC).date()
        with (
            connect(self.database_url, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """SELECT exhausted FROM football.provider_request_budgets
                    WHERE provider_code = 'api_football' AND window_date = %s""",
                (today,),
            )
            state = cursor.fetchone()
            if state is not None and state[0]:
                raise ApiFootballError("API-Football daily quota is exhausted; request suppressed")
            cursor.execute(
                """INSERT INTO football.provider_request_budgets (
                       provider_code, window_date, requests_used
                   ) VALUES ('api_football', %s, 1)
                   ON CONFLICT (provider_code, window_date) DO UPDATE SET
                       requests_used = football.provider_request_budgets.requests_used + 1,
                       updated_at = clock_timestamp()""",
                (today,),
            )

    def record_response(self, remaining: int | None) -> None:
        if remaining is None:
            return
        with (
            connect(self.database_url, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """UPDATE football.provider_request_budgets
                      SET remaining_requests = %s, exhausted = (%s = 0),
                          last_error = NULL, updated_at = clock_timestamp()
                    WHERE provider_code = 'api_football' AND window_date = %s""",
                (remaining, remaining, datetime.now(UTC).date()),
            )

    def record_rejection(self, detail: str) -> None:
        lowered = detail.casefold()
        if not any(marker in lowered for marker in ("request limit", "quota", "rate limit")):
            return
        with (
            connect(self.database_url, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """UPDATE football.provider_request_budgets
                      SET remaining_requests = 0, exhausted = true,
                          last_error = %s, updated_at = clock_timestamp()
                    WHERE provider_code = 'api_football' AND window_date = %s""",
                (detail[:1000], datetime.now(UTC).date()),
            )


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
        if self._request_budget is not None:
            self._request_budget.before_request()
        url = f"{API_BASE_URL}{path}?{urllib.parse.urlencode(sorted(query.items()))}"
        fetched_at = datetime.now(UTC)
        try:
            raw = self._transport(url, {"x-apisports-key": self._api_key})
        except urllib.error.HTTPError as error:
            if error.code == 429 and self._request_budget is not None:
                self._request_budget.record_rejection("HTTP 429 rate limit")
            raise ApiFootballError(f"API-Football request failed for {path}") from error
        except (OSError, urllib.error.URLError) as error:
            raise ApiFootballError(f"API-Football request failed for {path}") from error
        try:
            payload = cast(dict[str, Any], json.loads(raw))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiFootballError("API-Football returned invalid JSON") from error
        provider_errors = payload.get("errors")
        if provider_errors not in ({}, []):
            detail = str(provider_errors)
            if self._request_budget is not None:
                self._request_budget.record_rejection(detail)
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
        remaining = _remaining_day(payload)
        if self._request_budget is not None:
            self._request_budget.record_response(remaining)
        return ApiResponse(
            path, fetched_at, raw, tuple(cast(list[Mapping[str, Any]], response)), remaining
        )


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


def _http_get(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        value = response.read()
    if not isinstance(value, bytes):
        raise ApiFootballError("API-Football transport returned non-bytes data")
    return value


def _remaining_day(payload: Mapping[str, Any]) -> int | None:
    value = payload.get("remaining")
    if isinstance(value, int):
        return value
    return None


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
