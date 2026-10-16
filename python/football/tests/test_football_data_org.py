import json
import urllib.error
from datetime import date
from email.message import Message
from io import BytesIO

import pytest
from football.product.football_data_org import (
    FootballDataOrgClient,
    FootballDataOrgError,
)


def test_finished_matches_uses_versioned_competition_route_and_preserves_raw() -> None:
    calls: list[tuple[str, object]] = []

    def transport(url: str, headers: object) -> bytes:
        calls.append((url, headers))
        return json.dumps({"matches": [{"id": 1, "status": "FINISHED"}]}).encode()

    result = FootballDataOrgClient("secret", transport=transport).finished_matches("PL", 2026)

    assert calls == [
        (
            "https://api.football-data.org/v4/competitions/PL/matches?season=2026&status=FINISHED",
            {"X-Auth-Token": "secret"},
        )
    ]
    assert result.rows == ({"id": 1, "status": "FINISHED"},)
    assert result.provider_code == "football_data_org"


def test_standings_keeps_only_total_table() -> None:
    payload = {
        "standings": [
            {"type": "HOME", "table": [{"position": 1}]},
            {"type": "TOTAL", "table": [{"position": 2}]},
        ]
    }
    client = FootballDataOrgClient(
        "secret", transport=lambda _url, _headers: json.dumps(payload).encode()
    )

    assert client.standings("PL", 2026).rows == ({"position": 2},)


def test_fixture_fallback_is_competition_scoped() -> None:
    calls: list[str] = []

    def transport(url: str, _headers: object) -> bytes:
        calls.append(url)
        return b'{"matches":[]}'

    FootballDataOrgClient("secret", transport=transport).fixtures_for_date(date(2026, 10, 10), "PL")
    assert calls == [
        "https://api.football-data.org/v4/competitions/PL/matches?dateFrom=2026-10-10&dateTo=2026-10-10"
    ]


def test_provider_error_is_explicit() -> None:
    client = FootballDataOrgClient(
        "secret", transport=lambda _url, _headers: b'{"message":"plan restriction"}'
    )
    with pytest.raises(FootballDataOrgError, match="plan restriction"):
        client.finished_matches("PL", 2026)


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_http_failure_preserves_status_without_exposing_credentials(status: int) -> None:
    body = BytesIO(b'{"message":"restricted resource"}')
    calls: list[str] = []

    def transport(url: str, _headers: object) -> bytes:
        calls.append(url)
        raise urllib.error.HTTPError(url, status, "Rejected", Message(), body)

    client = FootballDataOrgClient("private-token", transport=transport)
    with pytest.raises(FootballDataOrgError, match=f"HTTP {status}") as failure:
        client.finished_matches("CL", 2020)

    assert "private-token" not in str(failure.value)
    assert len(calls) == 1
    assert body.closed
