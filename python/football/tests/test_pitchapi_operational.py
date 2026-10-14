from __future__ import annotations

import json
from datetime import UTC, date, datetime
from email.message import Message
from typing import Any
from urllib.error import HTTPError

import pytest
from football.providers.pitchapi import (
    PitchApiClient,
    PitchApiHttpResponse,
    PitchApiPayloadError,
    UrllibPitchApiTransport,
    normalize_pitchapi_matches,
)


class StubTransport:
    def __init__(self, payload: Any, content_type: str = "application/json") -> None:
        self.payload = json.dumps(payload).encode()
        self.content_type = content_type
        self.calls: list[tuple[str, str, float, float, int]] = []

    def get(
        self,
        url: str,
        *,
        api_key: str,
        connection_timeout_seconds: float,
        request_timeout_seconds: float,
        max_bytes: int,
    ) -> PitchApiHttpResponse:
        self.calls.append(
            (url, api_key, connection_timeout_seconds, request_timeout_seconds, max_bytes)
        )
        return PitchApiHttpResponse(self.payload, self.content_type)


def listing(*, status: str = "live", home_score: int | None = 1) -> dict[str, object]:
    return {
        "data": {
            "league": {"id": "l_0bfbkO", "name": "League"},
            "matches": [
                {
                    "id": "m_B8x2K9",
                    "time_utc": "2026-10-09T20:00:00Z",
                    "status": status,
                    "home_team": {"id": "t_9aB2xQ", "name": "Home"},
                    "away_team": {"id": "t_7YtX4q", "name": "Away"},
                    "score_home": home_score,
                    "score_away": 0 if home_score is not None else None,
                    "minute": 72,
                    "period": "second_half",
                    "updated_at": "2026-10-09T21:31:00Z",
                }
            ],
        }
    }


def test_date_listing_always_requests_all_and_normalizes_live_state() -> None:
    transport = StubTransport(listing())
    response = PitchApiClient("secret", transport=transport).matches_by_date(
        date(2026, 10, 9), status="all"
    )
    rows = normalize_pitchapi_matches(response)
    assert transport.calls[0][0].endswith("/v1/date/2026-10-09?status=all")
    assert transport.calls[0][1] == "secret"
    assert rows[0].status == "LIVE"
    assert rows[0].minute == 72
    assert rows[0].kickoff_at == datetime(2026, 10, 9, 20, tzinfo=UTC)
    assert rows[0].provider_competition_name == "League"


def test_nullable_scores_invalid_content_and_mixed_ids_fail_closed() -> None:
    scheduled = StubTransport(listing(status="upcoming", home_score=None))
    row = normalize_pitchapi_matches(
        PitchApiClient("secret", transport=scheduled).matches_by_date(date(2026, 10, 9))
    )[0]
    assert row.status == "SCHEDULED" and row.home_score is None

    html = StubTransport({"data": {}}, "text/html")
    with pytest.raises(PitchApiPayloadError, match="content type"):
        PitchApiClient("secret", transport=html).matches_by_date(date(2026, 10, 9))

    malformed = listing()
    data = malformed["data"]
    assert isinstance(data, dict)
    matches = data["matches"]
    assert isinstance(matches, list)
    matches[0]["id"] = 123
    with pytest.raises(PitchApiPayloadError, match="identifier"):
        normalize_pitchapi_matches(
            PitchApiClient("secret", transport=StubTransport(malformed)).matches_by_date(
                date(2026, 10, 9)
            )
        )


def test_observed_not_started_status_maps_to_scheduled() -> None:
    row = normalize_pitchapi_matches(
        PitchApiClient(
            "secret", transport=StubTransport(listing(status="not_started", home_score=None))
        ).matches_by_date(date(2026, 10, 9))
    )[0]
    assert row.status == "SCHEDULED"


def test_observed_started_status_maps_to_live() -> None:
    row = normalize_pitchapi_matches(
        PitchApiClient(
            "secret", transport=StubTransport(listing(status="started"))
        ).matches_by_date(date(2026, 10, 9))
    )[0]
    assert row.status == "LIVE"


def test_finished_league_result_has_regulation_score_basis() -> None:
    row = normalize_pitchapi_matches(
        PitchApiClient(
            "secret", transport=StubTransport(listing(status="finished"))
        ).league_matches("l_0bfbkO", season="2025/2026", status="played")
    )[0]
    assert row.result_score_basis == "REGULATION_90"


def test_calendar_year_is_valid_pitchapi_season() -> None:
    transport = StubTransport(listing(status="finished"))
    PitchApiClient("secret", transport=transport).league_matches(
        "l_0bfbkO", season="2026", status="played"
    )
    assert transport.calls[0][0].endswith("/v1/leagues/l_0bfbkO/matches?season=2026&status=played")


def test_match_resources_are_bounded_to_documented_operational_paths() -> None:
    transport = StubTransport({"data": {}})
    client = PitchApiClient("secret", transport=transport)
    client.match_resource("m_B8x2K9", "shots")
    assert transport.calls[0][0].endswith("/v1/matches/m_B8x2K9/shots")
    with pytest.raises(ValueError, match="unsupported"):
        client.match_resource("m_B8x2K9", "private")


def test_transport_retries_rate_limit_and_honors_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    headers["Content-Type"] = "application/json"
    headers["Retry-After"] = "0.25"
    calls = 0

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        payload = json.dumps({"data": {}}).encode()

        def read(self, limit: int) -> bytes:
            result = self.payload[:limit]
            self.payload = self.payload[limit:]
            return result

        @property
        def headers(self) -> Message:
            return headers

    def open_once_limited(*_args: object, **_kwargs: object) -> Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError("https://api.pitchapi.dev", 429, "limited", headers, None)
        return Response()

    delays: list[float] = []
    monkeypatch.setattr("football.providers.pitchapi.open_bounded", open_once_limited)
    transport = UrllibPitchApiTransport(sleep_fn=delays.append)
    result = transport.get(
        "https://api.pitchapi.dev/v1/date/2026-10-09?status=all",
        api_key="secret",
        connection_timeout_seconds=1,
        request_timeout_seconds=2,
        max_bytes=1_000,
    )
    assert result.content_type == "application/json"
    assert calls == 2
    assert delays == [0.25]
