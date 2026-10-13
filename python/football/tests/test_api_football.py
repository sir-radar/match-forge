import json
import urllib.error
from datetime import UTC, date, datetime, timedelta
from email.message import Message

import pytest
from football.product.api_football import (
    ApiFootballClient,
    ApiFootballError,
    CapabilityStatus,
    RequestReservation,
    context_capability,
    continent_for_country,
    fixture_status,
    inferred_division,
)
from football.product.sync import _league_seasons
from football.providers.base import HttpResponseV1


@pytest.mark.parametrize(
    "header, expected",
    [
        ("4", 4),
        ("0", 0),
        ("-1", None),
        ("bad", None),
        ("1.5", None),
        ("999999999999999999999", None),
        ("2147483648", None),
        (None, None),
    ],
)
def test_quota_comes_from_documented_headers_not_body(
    header: str | None, expected: int | None
) -> None:
    headers = {} if header is None else {"X-RateLimit-Requests-Remaining": header}
    response = HttpResponseV1(
        payload=b'{"errors":[],"remaining":999,"response":[]}',
        status=200,
        content_type="application/json",
        etag=None,
        last_modified=None,
        headers=headers,
    )
    result = ApiFootballClient("secret", transport=lambda _url, _headers: response).competitions()
    assert result.remaining_day == expected


def test_client_preserves_raw_response_and_encodes_date() -> None:
    calls: list[str] = []

    def transport(url: str, headers: object) -> bytes:
        calls.append(url)
        return json.dumps({"errors": [], "response": [{"fixture": {"id": 1}}]}).encode()

    result = ApiFootballClient("secret", transport=transport).fixtures_for_date(date(2026, 9, 29))
    assert calls == ["https://v3.football.api-sports.io/fixtures?date=2026-09-29"]
    assert result.rows[0]["fixture"] == {"id": 1}
    assert json.loads(result.raw)["response"]


def test_native_transport_retains_quota_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["x-ratelimit-requests-remaining"] = "4"
        headers["X-RateLimit-Remaining"] = "9"

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"errors":[],"response":[]}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    result = ApiFootballClient("secret").competitions()
    assert (result.remaining_day, result.remaining_minute) == (4, 9)


def test_acquisition_time_is_after_full_response_arrives(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clock:
        current = datetime(2026, 10, 13, 12, tzinfo=UTC)

        @classmethod
        def now(cls, _timezone: object) -> datetime:
            return cls.current

    def transport(_url: str, _headers: object) -> bytes:
        Clock.current += timedelta(seconds=10)
        return b'{"errors":[],"response":[]}'

    monkeypatch.setattr("football.product.api_football.datetime", Clock)
    response = ApiFootballClient("secret", transport=transport).competitions()
    assert response.fetched_at == datetime(2026, 10, 13, 12, 0, 10, tzinfo=UTC)


def test_client_rejects_provider_error() -> None:
    client = ApiFootballClient(
        "secret",
        transport=lambda _url, _headers: b'{"errors":{"rateLimit":"reached"},"response":[]}',
    )
    with pytest.raises(ApiFootballError, match="rejected"):
        client.competitions()


def test_client_records_quota_metadata_and_exhaustion() -> None:
    class Budget:
        def __init__(self) -> None:
            self.before = 0
            self.remaining: list[int | None] = []
            self.rejections: list[str] = []

        def before_request(self) -> RequestReservation:
            self.before += 1
            now = datetime.now(UTC)
            return RequestReservation(now.date(), self.before, now)

        def record_response(
            self,
            reservation: RequestReservation,
            remaining: int | None,
            minute_remaining: int | None,
        ) -> None:
            self.remaining.append(remaining)

        def record_rejection(
            self, reservation: RequestReservation, detail: str, retry_after: str | None = None
        ) -> None:
            self.rejections.append(detail)

    budget = Budget()
    success = ApiFootballClient(
        "secret",
        request_budget=budget,
        transport=lambda _url, _headers: HttpResponseV1(
            payload=b'{"errors":[],"response":[]}',
            status=200,
            content_type="application/json",
            etag=None,
            last_modified=None,
            headers={"x-ratelimit-requests-remaining": "4"},
        ),
    )
    success.competitions()
    limited = ApiFootballClient(
        "secret",
        request_budget=budget,
        transport=lambda _url, _headers: (
            b'{"errors":{"requests":"request limit reached"},"response":[]}'
        ),
    )
    with pytest.raises(ApiFootballError, match="rejected"):
        limited.competitions()

    assert budget.before == 2
    assert budget.remaining == [4, None]
    assert budget.rejections == ["{'requests': 'request limit reached'}"]


def test_client_records_http_429_in_persistent_budget() -> None:
    class Budget:
        quota: tuple[int | None, int | None] | None = None

        def before_request(self) -> RequestReservation:
            now = datetime.now(UTC)
            return RequestReservation(now.date(), 1, now)

        def record_response(
            self,
            reservation: RequestReservation,
            remaining: int | None,
            minute_remaining: int | None,
        ) -> None:
            self.quota = (remaining, minute_remaining)

        def record_rejection(
            self, reservation: RequestReservation, detail: str, retry_after: str | None = None
        ) -> None:
            self.detail = detail
            self.retry_after = retry_after

    budget = Budget()

    def rate_limited(_url: str, _headers: object) -> bytes:
        headers = Message()
        headers["x-ratelimit-requests-remaining"] = "50"
        headers["X-RateLimit-Remaining"] = "0"
        headers["Retry-After"] = "120"
        raise urllib.error.HTTPError("https://provider.test", 429, "limited", headers, None)

    client = ApiFootballClient("secret", transport=rate_limited, request_budget=budget)
    with pytest.raises(ApiFootballError, match="request failed"):
        client.competitions()

    assert budget.detail == "HTTP 429 rate limit"
    assert budget.quota == (50, 0)
    assert budget.retry_after == "120"


def test_client_classifies_plan_restriction_without_claiming_unsupported() -> None:
    client = ApiFootballClient(
        "secret",
        transport=lambda _url, _headers: (
            b'{"errors":{"access":"endpoint unavailable on your plan"},"response":[]}'
        ),
    )

    with pytest.raises(ApiFootballError) as caught:
        client.injuries(123)

    assert caught.value.capability_status is CapabilityStatus.PLAN_RESTRICTION


def test_client_reuses_transport_for_fixture_context_resources() -> None:
    calls: list[str] = []

    def transport(url: str, headers: object) -> bytes:
        calls.append(url)
        return b'{"errors":[],"response":[]}'

    client = ApiFootballClient("secret", transport=transport)
    client.injuries(123)
    client.lineups(123)

    assert calls == [
        "https://v3.football.api-sports.io/injuries?fixture=123",
        "https://v3.football.api-sports.io/fixtures/lineups?fixture=123",
    ]


def test_context_capability_distinguishes_explicit_unsupported_from_unknown() -> None:
    supported = {"coverage": {"injuries": True, "fixtures": {"lineups": True}}}
    unsupported = {"coverage": {"injuries": False, "fixtures": {"lineups": False}}}

    assert context_capability(supported, "INJURIES") is CapabilityStatus.SUPPORTED
    assert context_capability(unsupported, "LINEUPS") is CapabilityStatus.UNSUPPORTED_BY_COMPETITION
    assert context_capability({}, "INJURIES") is CapabilityStatus.UNKNOWN


@pytest.mark.parametrize(
    ("provider_status", "expected"),
    [("NS", "SCHEDULED"), ("1H", "LIVE"), ("FT", "FINISHED"), ("PST", "POSTPONED")],
)
def test_fixture_status_mapping(provider_status: str, expected: str) -> None:
    assert fixture_status(provider_status) == expected


def test_coverage_classification() -> None:
    assert continent_for_country("Nigeria") == "Africa"
    assert continent_for_country("Japan") == "Asia"
    assert continent_for_country("Bangladesh") == "Asia"
    assert continent_for_country("Benin") == "Africa"
    assert continent_for_country("Aruba") == "North/Central America"
    assert continent_for_country("England") == "Europe"
    assert continent_for_country("New provider territory") == "Other"
    assert inferred_division("Championship", "League") == 2
    assert inferred_division("Premier League", "League") == 1
    assert inferred_division("FA Cup", "Cup") is None


def test_fixture_leagues_do_not_require_absent_standings_metadata() -> None:
    rows = [
        {"league": {"id": 39, "season": 2026}},
        {"league": {"id": 999, "season": 2026}},
    ]
    assert _league_seasons(rows) == [(39, 2026), (999, 2026)]
