from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from football.contracts.source import SourceContractError
from football.product.api_football import ApiFootballClient
from football.product.football_data_org import FootballDataOrgClient
from football.product.openfootball import discover_catalog
from football.providers.base import HttpResponseV1, ProviderConfigurationError
from football.providers.football_data_uk import FootballDataUkSourceResourceV1
from football.providers.football_data_uk_storage import FootballDataUkRawStoreV1
from football.providers.fotmob import FotmobAccessError, FotmobClient
from football.providers.pitchapi import PitchApiClient, PitchApiHttpResponse
from football.providers.sources.contracts import (
    AvailabilitySource,
    CoachSource,
    CompetitionSource,
    EventSource,
    ExpectedGoalsSource,
    FixtureSource,
    LineupSource,
    OddsSource,
    PlayerSource,
    ProviderPayload,
    ResultSource,
    ShotSource,
    StandingSource,
    StatisticsSource,
    TeamSource,
)
from football.providers.sources.files import FootballDataUkSource, OpenFootballSource
from football.providers.sources.http import (
    ApiFootballSource,
    FootballDataOrgSource,
    FotmobSource,
    PitchApiSource,
)
from football.providers.sources.statsbomb import StatsBombSource
from football.providers.statsbomb import StatsBombOpenDataAdapter

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
DAY = date(2026, 10, 16)
RAW = b'{"errors":[],"response":[],"matches":[],"standings":[]}'


class JsonTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        self.calls.append(url)
        return RAW


class PitchTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, **_limits: Any) -> PitchApiHttpResponse:
        self.calls.append(url)
        return PitchApiHttpResponse(b'{"data":{"matches":[]}}', "application/json")


@pytest.mark.parametrize(
    ("invoke", "suffix"),
    [
        (lambda source: source.fixtures(DAY), "matches?date=20261016"),
        (
            lambda source: source.results("337", "2024/2025 - Apertura"),
            "leagues?id=337&season=2024%2F2025+-+Apertura",
        ),
        (lambda source: source.competitions(), "allLeagues"),
        (lambda source: source.team("1"), "teams?id=1"),
        (lambda source: source.player("2"), "playerData?id=2"),
        (lambda source: source.lineups("42"), "matchDetails?matchId=42"),
        (lambda source: source.events("42"), "matchDetails?matchId=42"),
        (lambda source: source.shots("42"), "matchDetails?matchId=42"),
        (lambda source: source.expected_goals("42"), "matchDetails?matchId=42"),
        (lambda source: source.statistics("42"), "matchDetails?matchId=42"),
    ],
)
def test_fotmob_capabilities_retain_original_resource_bytes(
    invoke: Callable[[FotmobSource], ProviderPayload],
    suffix: str,
) -> None:
    transport = JsonTransport()
    source = FotmobSource(FotmobClient(access_approved=True, transport=transport))
    result = invoke(source)
    assert result.provider == "fotmob" and result.raw == RAW
    assert result.resource_key == transport.calls[0]
    assert result.resource_key.endswith(suffix)
    assert result.sha256 == hashlib.sha256(RAW).hexdigest()
    assert len(transport.calls) == 1


def test_sources_do_not_expand_provider_interfaces_or_bypass_access_approval() -> None:
    transport = JsonTransport()
    source = FotmobSource(FotmobClient(transport=transport))
    assert all(
        isinstance(source, capability)
        for capability in (
            FixtureSource,
            ResultSource,
            CompetitionSource,
            TeamSource,
            PlayerSource,
            LineupSource,
            EventSource,
            ShotSource,
            ExpectedGoalsSource,
            StatisticsSource,
        )
    )
    assert not isinstance(source, (AvailabilitySource, CoachSource, OddsSource, StandingSource))
    with pytest.raises(FotmobAccessError):
        source.fixtures(DAY)
    assert transport.calls == []


@pytest.mark.parametrize(
    ("invoke", "suffix"),
    [
        (lambda source: source.fixtures(DAY), "/v1/date/2026-10-16?status=all"),
        (
            lambda source: source.results("l_0bfbkO", "2026"),
            "/v1/leagues/l_0bfbkO/matches?season=2026&status=played",
        ),
        (lambda source: source.competitions(), "/v1/leagues"),
        (lambda source: source.lineups("m_B8x2K9"), "/v1/matches/m_B8x2K9/lineups"),
        (lambda source: source.events("m_B8x2K9"), "/v1/matches/m_B8x2K9/events"),
        (lambda source: source.shots("m_B8x2K9"), "/v1/matches/m_B8x2K9/shots"),
        (lambda source: source.expected_goals("m_B8x2K9"), "/v1/matches/m_B8x2K9/shots"),
        (lambda source: source.statistics("m_B8x2K9"), "/v1/matches/m_B8x2K9/stats"),
    ],
)
def test_pitchapi_capabilities_use_existing_native_resource_routes(
    invoke: Callable[[PitchApiSource], ProviderPayload],
    suffix: str,
) -> None:
    transport = PitchTransport()
    source = PitchApiSource(PitchApiClient("test", transport=transport))
    result = invoke(source)
    assert result.provider == "pitchapi"
    assert result.raw == b'{"data":{"matches":[]}}'
    assert result.resource_key.endswith(suffix)
    assert transport.calls[0].endswith(suffix) and len(transport.calls) == 1
    assert not isinstance(source, (TeamSource, PlayerSource, AvailabilitySource, OddsSource))


@pytest.mark.parametrize(
    ("invoke", "key"),
    [
        (lambda source: source.fixtures(DAY), "/fixtures?date=2026-10-16"),
        (lambda source: source.results("39", "2026"), "/fixtures?league=39&season=2026&status=FT"),
        (lambda source: source.competitions(), "/leagues?current=true"),
        (lambda source: source.lineups("42"), "/fixtures/lineups?fixture=42"),
        (lambda source: source.availability("42"), "/injuries?fixture=42"),
        (lambda source: source.standings("39", "2026"), "/standings?league=39&season=2026"),
        (lambda source: source.statistics("42"), "/fixtures/statistics?fixture=42"),
        (lambda source: source.events("42"), "/fixtures/events?fixture=42"),
        (lambda source: source.player_statistics("42"), "/fixtures/players?fixture=42"),
    ],
)
def test_api_football_capabilities_preserve_query_scope_and_quota(
    invoke: Callable[[ApiFootballSource], ProviderPayload],
    key: str,
) -> None:
    calls: list[str] = []

    def transport(url: str, _headers: object) -> HttpResponseV1:
        calls.append(url)
        return HttpResponseV1(
            RAW,
            200,
            "application/json",
            None,
            None,
            headers={
                "x-ratelimit-requests-remaining": "0",
                "X-RateLimit-Remaining": "3",
            },
        )

    result = invoke(ApiFootballSource(ApiFootballClient("test", transport=transport)))
    assert result.raw == RAW and result.provider == "api_football"
    assert result.resource_key == key and calls[0].endswith(key)
    assert result.remaining_requests == 0 and result.minute_remaining == 3


def test_football_data_org_scope_is_explicit_and_checked_before_acquisition() -> None:
    calls: list[str] = []

    def transport(url: str, _headers: object) -> bytes:
        calls.append(url)
        return RAW

    source = FootballDataOrgSource(
        FootballDataOrgClient("test", transport=transport), competition_code="PL"
    )
    assert (
        source.fixtures(DAY).resource_key
        == "/competitions/PL/matches?dateFrom=2026-10-16&dateTo=2026-10-16"
    )
    assert source.results("PL", "2026").resource_key.endswith("?season=2026&status=FINISHED")
    assert source.standings("PL", "2026").resource_key.endswith("?season=2026")
    assert len(calls) == 3
    with pytest.raises(ProviderConfigurationError, match="configured competition"):
        source.results("BL1", "2026")
    assert len(calls) == 3
    assert not isinstance(source, (LineupSource, ShotSource, OddsSource))


def test_statsbomb_resource_stays_commit_pinned() -> None:
    transport = JsonTransport()
    source = StatsBombSource(
        StatsBombOpenDataAdapter(source_git_sha="a" * 40, transport=transport), clock=lambda: NOW
    )
    resources = [
        source.competitions(),
        source.results("2", "27"),
        source.lineups("42"),
        source.events("42"),
    ]
    assert [item.resource_key for item in resources] == [
        "data/competitions.json",
        "data/matches/2/27.json",
        "data/lineups/42.json",
        "data/events/42.json",
    ]
    assert all(
        item.raw == RAW and item.acquired_at == NOW and item.source_revision == "a" * 40
        for item in resources
    )
    assert all("/" + "a" * 40 + "/data/" in url for url in transport.calls)
    assert not isinstance(source, (FixtureSource, AvailabilitySource, OddsSource))


def test_retained_csv_checks_scope_and_original_checksum(tmp_path: Path) -> None:
    raw = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/01/2016,A,B,1,0\n"
    receipt = FootballDataUkSourceResourceV1.from_payload(
        resource_type="historical_league_csv",
        source_path="mmz4281/1516/E0.csv",
        payload=raw,
        observed_by_matchforge_at=NOW,
        http_status=200,
        content_type="text/csv",
    )
    write = FootballDataUkRawStoreV1(tmp_path).publish(receipt, raw)
    source = FootballDataUkSource(tmp_path, receipt)
    assert isinstance(source, ResultSource) and not isinstance(source, (FixtureSource, OddsSource))
    result = source.results("E0", "1516")
    assert result.raw == raw and result.acquired_at == NOW
    with pytest.raises(ProviderConfigurationError, match="registered CSV scope"):
        source.results("D1", "1516")
    write.path.write_bytes(b"changed")
    with pytest.raises(ProviderConfigurationError, match="immutable receipt"):
        source.results("E0", "1516")


def test_openfootball_uses_pinned_git_bytes_not_mutable_working_file(tmp_path: Path) -> None:
    season = tmp_path / "2026"
    season.mkdir()
    path = season / "en.1.json"
    raw = json.dumps({"matches": []}).encode()
    path.write_bytes(raw)
    commands = [
        ["init", "-q"],
        ["add", "2026/en.1.json"],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ]
    for command in commands:
        subprocess.run(["git", "-C", str(tmp_path), *command], check=True, capture_output=True)
    revision = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    entries = discover_catalog(tmp_path, revision)
    path.write_bytes(b"changed")
    source = OpenFootballSource(entries, acquired_at=NOW)
    result = source.results("en.1", "2026")
    assert result.raw == raw and result.source_revision == revision
    with pytest.raises(ProviderConfigurationError, match="exactly one"):
        source.results("en.1", "2025")


def test_payload_requires_real_provider_time_and_bytes() -> None:
    with pytest.raises(SourceContractError, match="timezone"):
        ProviderPayload(
            provider="fotmob",
            resource_key="matches",
            acquired_at=NOW.replace(tzinfo=None),
            raw=RAW,
            media_type="application/json",
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "Bad Provider"},
        {"resource_key": ""},
        {"raw": bytearray(RAW)},
        {"media_type": ""},
        {"source_revision": ""},
    ],
)
def test_payload_rejects_invalid_transport_evidence(changes: dict[str, Any]) -> None:
    values: dict[str, Any] = dict(
        provider="fotmob",
        resource_key="matches",
        acquired_at=NOW,
        raw=RAW,
        media_type="application/json",
    )
    values.update(changes)
    with pytest.raises(SourceContractError):
        ProviderPayload(**values)


def test_invalid_numeric_scope_is_rejected_before_api_calls() -> None:
    calls: list[str] = []

    def transport(url: str, _headers: object) -> bytes:
        calls.append(url)
        return RAW

    source = ApiFootballSource(ApiFootballClient("test", transport=transport))
    with pytest.raises(SourceContractError, match="positive integer"):
        source.results("39", "2025/2026")
    assert calls == []


def test_fotmob_cache_zero_remains_an_observed_zero() -> None:
    class CachedTransport(JsonTransport):
        def get_response(
            self, url: str, *, timeout_seconds: float, max_bytes: int
        ) -> HttpResponseV1:
            return HttpResponseV1(
                self.get(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes),
                200,
                "application/json",
                None,
                None,
                cache_control="max-age=0",
            )

    source = FotmobSource(FotmobClient(access_approved=True, transport=CachedTransport()))
    assert source.fixtures(DAY).cache_max_age_seconds == 0
