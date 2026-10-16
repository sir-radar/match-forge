"""Offline contracts for the optional FotMob integration; never call a live provider."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
from football.providers.base import HttpResponseV1
from football.providers.fotmob import (
    FotmobAccessError,
    FotmobClient,
    FotmobPayloadError,
    FotmobResponse,
    normalize_daily_matches,
)


class StubTransport:
    def __init__(self, payload: Any) -> None:
        self.raw = json.dumps(payload).encode("utf-8")
        self.calls: list[tuple[str, float, int]] = []

    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        self.calls.append((url, timeout_seconds, max_bytes))
        return self.raw


def test_league_score_string_is_preserved_and_conflicts_rejected() -> None:
    row = match(home_score=None, away_score=None)
    row["status"].update(finished=True, scoreStr="2 - 1", reason={"short": "FT"})
    result = normalize_daily_matches(response([row]))[0]
    assert (result.home_score, result.away_score, result.result_score_basis) == (
        2,
        1,
        "REGULATION_90",
    )
    row["home"]["score"] = 3
    with pytest.raises(FotmobPayloadError, match="contradict"):
        normalize_daily_matches(response([row]))


class ResponseTransport(StubTransport):
    def __init__(self, payload: Any, *, content_type: str = "application/json") -> None:
        super().__init__(payload)
        self.content_type = content_type

    def get_response(self, url: str, *, timeout_seconds: float, max_bytes: int) -> HttpResponseV1:
        self.calls.append((url, timeout_seconds, max_bytes))
        return HttpResponseV1(
            payload=self.raw,
            status=200,
            content_type=self.content_type,
            etag=None,
            last_modified=None,
            cache_control="public, max-age=10",
        )


def match(
    match_id: int = 5795427,
    *,
    status: dict[str, Any] | None = None,
    home_score: int | None = 2,
    away_score: int | None = 1,
) -> dict[str, Any]:
    return {
        "id": match_id,
        "home": {"id": 8455, "name": "Chelsea", "score": home_score},
        "away": {"id": 10204, "name": "Brighton", "score": away_score},
        "status": status
        or {
            "utcTime": "2026-10-09T20:00:00.000Z",
            "started": True,
            "finished": False,
            "cancelled": False,
            "liveTime": {"short": "72'"},
        },
    }


def response(matches: list[dict[str, Any]]) -> FotmobResponse:
    return FotmobResponse(
        resource_url="https://www.fotmob.com/api/data/matches?date=20261009",
        fetched_at=datetime(2026, 10, 9, 20, 42, tzinfo=UTC),
        sha256="a" * 64,
        raw=b"{}",
        data={"leagues": [{"id": 47, "name": "Premier League", "matches": matches}]},
    )


def test_access_is_disabled_and_never_calls_transport() -> None:
    stub = StubTransport({"leagues": []})
    client = FotmobClient(transport=stub)
    with pytest.raises(FotmobAccessError, match="development provider"):
        client.matches_by_date(date(2026, 10, 9))
    assert stub.calls == []


@pytest.mark.parametrize("stage", ["Apertura", "Clausura"])
def test_league_transport_preserves_native_split_season(stage: str) -> None:
    season = f"2024/2025 - {stage}"
    stub = StubTransport({"details": {"id": 337, "selectedSeason": season}})
    client = FotmobClient(transport=stub, access_approved=True)

    result = client.league("337", season)

    assert result.data == {"details": {"id": 337, "selectedSeason": season}}
    assert stub.calls == [
        (
            f"https://www.fotmob.com/api/data/leagues?id=337&season=2024%2F2025+-+{stage}",
            10.0,
            4_000_000,
        )
    ]


def test_league_transport_rejects_unknown_stage_before_request() -> None:
    stub = StubTransport({})
    client = FotmobClient(transport=stub, access_approved=True)
    with pytest.raises(ValueError, match="invalid FotMob season"):
        client.league("337", "2024/2025 - Final")
    assert stub.calls == []


def test_fetch_preserves_auditable_source_and_uses_fixed_endpoints() -> None:
    stub = StubTransport({"leagues": []})
    client = FotmobClient(transport=stub, access_approved=True)
    result = client.matches_by_date(date(2026, 10, 9))
    assert result.sha256 == hashlib.sha256(stub.raw).hexdigest()
    assert result.raw == stub.raw
    assert result.fetched_at.utcoffset() is not None
    assert stub.calls == [
        ("https://www.fotmob.com/api/data/matches?date=20261009", 10.0, 4_000_000)
    ]
    client.match_details("5795427")
    client.fixtures(47)
    client.league(47, "2025/2026")
    client.table(47)
    client.search("Chelsea & Brighton")
    assert stub.calls[1][0].endswith("matchDetails?matchId=5795427")
    assert stub.calls[2][0].endswith("fixtures?id=47")
    assert stub.calls[3][0].endswith("leagues?id=47&season=2025%2F2026")
    assert stub.calls[4][0].endswith("tltable?leagueId=47")
    assert stub.calls[5][0].endswith("search/suggest?term=Chelsea+%26+Brighton")


def test_live_snapshot_keeps_provider_ids_and_utc_kickoff() -> None:
    rows = normalize_daily_matches(response([match()]))
    assert len(rows) == 1
    row = rows[0]
    assert (row.provider_match_id, row.provider_competition_id) == ("5795427", "47")
    assert (row.provider_home_team_id, row.provider_away_team_id) == ("8455", "10204")
    assert row.status == "LIVE"
    assert row.clock == "72'"
    assert row.minute == 72
    assert row.added_time is None
    assert row.kickoff_at == datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
    assert row.to_dict()["kickoff_at"] == "2026-10-09T20:00:00+00:00"
    assert row.to_dict()["source_updated_at"] is None
    assert row.home_score == 2 and row.away_score == 1
    assert row.provider_competition_name == "Premier League"


@pytest.mark.parametrize(
    ("flags", "reason", "expected"),
    [
        ((False, False, False), None, "SCHEDULED"),
        ((True, False, False), None, "LIVE"),
        ((True, True, False), "FT", "FINISHED"),
        ((False, False, True), "PST", "POSTPONED"),
        ((True, False, False), "ABD", "ABANDONED"),
        ((False, False, True), "CANC", "CANCELLED"),
    ],
)
def test_fixture_statuses(
    flags: tuple[bool, bool, bool], reason: str | None, expected: str
) -> None:
    status: dict[str, Any] = {
        "utcTime": "2026-10-09T20:00:00Z",
        "started": flags[0],
        "finished": flags[1],
        "cancelled": flags[2],
    }
    if reason:
        status["reason"] = {"short": reason}
    assert normalize_daily_matches(response([match(status=status)]))[0].status == expected


def test_fail_closed_on_ambiguous_kickoff_or_duplicate_ids() -> None:
    unzoned = match()
    unzoned["status"]["utcTime"] = "2026-10-09T20:00:00"
    with pytest.raises(FotmobPayloadError, match="timezone"):
        normalize_daily_matches(response([unzoned]))
    with pytest.raises(FotmobPayloadError, match="duplicate"):
        normalize_daily_matches(response([match(), match()]))


def test_missing_flags_bad_identifiers_and_scores_rejected() -> None:
    bad = match()
    del bad["status"]["finished"]
    with pytest.raises(FotmobPayloadError, match="boolean finished"):
        normalize_daily_matches(response([bad]))
    with pytest.raises(FotmobPayloadError, match="numeric identifier"):
        normalize_daily_matches(response([match(match_id=True)]))
    with pytest.raises(FotmobPayloadError, match="invalid match score"):
        normalize_daily_matches(response([match(home_score=-1)]))


def test_provider_does_not_accept_unvalidated_params_or_broken_json() -> None:
    client = FotmobClient(transport=StubTransport({}), access_approved=True)
    with pytest.raises(ValueError, match="season"):
        client.league(47, "../../bad")
    with pytest.raises(ValueError, match="transfers page"):
        client.transfers(0)
    with pytest.raises(ValueError, match="search term"):
        client.search("\n")
    with pytest.raises(FotmobPayloadError, match="numeric identifier"):
        client.match_details("7&evil=true")
    stub = StubTransport({})
    stub.raw = b"<html>not JSON</html>"
    with pytest.raises(FotmobPayloadError, match="not JSON"):
        FotmobClient(transport=stub, access_approved=True).matches_by_date(date(2026, 10, 9))


def test_byte_limit_checked_even_for_injected_transport() -> None:
    stub = StubTransport({"leagues": []})
    with pytest.raises(FotmobPayloadError, match="byte limit"):
        FotmobClient(transport=stub, access_approved=True, max_bytes=2).matches_by_date(
            date(2026, 10, 9)
        )


def test_cache_control_and_content_type_are_validated() -> None:
    response_transport = ResponseTransport({"leagues": []})
    result = FotmobClient(transport=response_transport, access_approved=True).matches_by_date(
        date(2026, 10, 9)
    )
    assert result.cache_max_age_seconds == 10

    html = ResponseTransport({"leagues": []}, content_type="text/html")
    with pytest.raises(FotmobPayloadError, match="content type"):
        FotmobClient(transport=html, access_approved=True).matches_by_date(date(2026, 10, 9))


def test_half_time_suspended_and_added_time_are_preserved() -> None:
    status = {
        "utcTime": "2026-10-09T20:00:00Z",
        "started": True,
        "finished": False,
        "cancelled": False,
        "reason": {"short": "HT"},
        "liveTime": {"short": "45+3'"},
    }
    row = normalize_daily_matches(response([match(status=status)]))[0]
    assert (row.status, row.minute, row.added_time, row.period) == ("HALF_TIME", 45, 3, "HT")


def test_phase_label_uses_reported_long_clock_without_inventing_elapsed_time() -> None:
    status = {
        "utcTime": "2026-10-09T20:00:00Z",
        "started": True,
        "finished": False,
        "cancelled": False,
        "reason": {"short": "HT"},
        "liveTime": {"short": "HT", "long": "45:00 + 3:52"},
    }
    row = normalize_daily_matches(response([match(status=status)]))[0]
    assert (row.clock, row.minute, row.added_time, row.period) == ("HT", 45, 3, "HT")


def test_phase_label_without_numeric_provider_clock_keeps_minute_missing() -> None:
    status = {
        "utcTime": "2026-10-09T20:00:00Z",
        "started": True,
        "finished": False,
        "cancelled": False,
        "reason": {"short": "HT"},
        "liveTime": {"short": "HT", "long": "Half time"},
    }
    row = normalize_daily_matches(response([match(status=status)]))[0]
    assert (row.clock, row.minute, row.added_time, row.period) == ("HT", None, None, "HT")


def test_finished_score_basis_is_explicit_only_when_provider_proves_it() -> None:
    status = {
        "utcTime": "2026-10-09T20:00:00Z",
        "started": True,
        "finished": True,
        "cancelled": False,
        "reason": {"short": "FT"},
    }
    row = normalize_daily_matches(response([match(status=status)]))[0]
    assert row.result_score_basis == "REGULATION_90"


def test_daily_group_uses_explicit_primary_competition_id() -> None:
    original = response([match()])
    assert isinstance(original.data, dict)
    data: dict[str, Any] = {
        "leagues": [{**original.data["leagues"][0], "id": 943230, "primaryId": 42}]
    }
    raw = json.dumps(data).encode()
    grouped = FotmobResponse(
        "daily", original.fetched_at, hashlib.sha256(raw).hexdigest(), raw, data
    )
    assert normalize_daily_matches(grouped)[0].provider_competition_id == "42"
    assert data["leagues"][0]["id"] == 943230
    data["leagues"][0]["primaryId"] = True
    with pytest.raises(FotmobPayloadError):
        normalize_daily_matches(grouped)
