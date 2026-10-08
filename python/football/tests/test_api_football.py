import json
from datetime import date

import pytest
from football.product.api_football import (
    ApiFootballClient,
    ApiFootballError,
    CapabilityStatus,
    context_capability,
    continent_for_country,
    fixture_status,
    inferred_division,
)
from football.product.sync import _league_seasons


def test_client_preserves_raw_response_and_encodes_date() -> None:
    calls: list[str] = []

    def transport(url: str, headers: object) -> bytes:
        calls.append(url)
        return json.dumps({"errors": [], "response": [{"fixture": {"id": 1}}]}).encode()

    result = ApiFootballClient("secret", transport=transport).fixtures_for_date(date(2026, 9, 29))
    assert calls == ["https://v3.football.api-sports.io/fixtures?date=2026-09-29"]
    assert result.rows[0]["fixture"] == {"id": 1}
    assert json.loads(result.raw)["response"]


def test_client_rejects_provider_error() -> None:
    client = ApiFootballClient(
        "secret",
        transport=lambda _url, _headers: b'{"errors":{"rateLimit":"reached"},"response":[]}',
    )
    with pytest.raises(ApiFootballError, match="rejected"):
        client.competitions()


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
