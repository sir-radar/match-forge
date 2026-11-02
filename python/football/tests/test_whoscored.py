from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.base import HttpResponseV1, ProviderFetchError
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource
from football.providers.normalization.whoscored import json_bytes
from football.providers.sources.whoscored import WhoScoredSource


def payload() -> dict[str, Any]:
    return {
        "tournaments": [
            {
                "tournamentId": 2,
                "stageId": 3,
                "seasonId": 4,
                "tournamentName": "League",
                "seasonName": "2026/2027",
                "matches": [
                    {
                        "id": 42,
                        "stageId": 3,
                        "status": 6,
                        "elapsed": "FT",
                        "period": 7,
                        "startTimeUtc": "2026-10-31T12:30:00Z",
                        "homeTeamId": 1,
                        "homeTeamName": "Home",
                        "awayTeamId": 2,
                        "awayTeamName": "Away",
                        "homeScore": 1,
                        "awayScore": 0,
                        "homeYellowCards": 0,
                        "awayYellowCards": 2,
                        "homeRedCards": None,
                    }
                ],
            }
        ]
    }


def normalize(
    value: dict[str, Any],
    *,
    resource_key: str = "Regions/252/Tournaments/2/England-Premier-League",
) -> NormalizationResult:
    raw = (
        '<script type="application/json" data-hypernova-key="tournamentfixtures"><!--'
        + json.dumps(value)
        + "--></script>"
    ).encode()
    uid = UUID(int=1)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    ctx = NormalizationContext(
        provenance=ObservationProvenance(
            "whoscored", None, uid, uid, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key=resource_key,
        competition_native_id="2",
        season_label="2026/2027",
    )
    result = normalize_resource(ctx, "fixtures", raw)
    assert result == normalize_resource(ctx, "fixtures", raw)
    return result


def test_public_fixture_cards_keep_missing_zero_and_unqualified_time() -> None:
    result = normalize(payload())
    assert not result.findings
    assert sum(o.CONTRACT == "FixtureObservationV2" for o in result.observations) == 1
    result_row = next(
        o.to_dict() for o in result.observations if o.CONTRACT == "ResultObservationV2"
    )
    assert result_row["score_basis"] == "UNKNOWN"
    stats = [o.to_dict() for o in result.observations if o.CONTRACT == "TeamStatisticObservationV2"]
    assert stats[0]["yellow_cards"] == 0 and stats[0]["red_cards"] is None
    assert all(o.time.event_time is None for o in result.observations)


def test_scheduled_placeholders_never_emit_results_or_cards() -> None:
    value = payload()
    row = value["tournaments"][0]["matches"][0]
    row.update(status=1, elapsed="", period=0)
    result = normalize(value)
    assert not result.findings
    assert not any(
        o.CONTRACT in ("ResultObservationV2", "TeamStatisticObservationV2")
        for o in result.observations
    )


@pytest.mark.parametrize("change", ["status", "teams", "stage", "competition", "season", "time"])
def test_conflicting_scope_or_unknown_status_is_held(change: str) -> None:
    value = payload()
    league = value["tournaments"][0]
    row = league["matches"][0]
    if change == "status":
        row["status"] = 99
    elif change == "teams":
        row["awayTeamId"] = 1
    elif change == "stage":
        row["stageId"] = 999
    elif change == "competition":
        league["tournamentId"] = 9
    elif change == "season":
        league["seasonName"] = "2025/2026"
    else:
        row["startTimeUtc"] = "2026-10-31T12:30:00"
    result = normalize(value)
    assert any(f.severity == "QUARANTINE" for f in result.findings)
    assert not any(o.CONTRACT == "ResultObservationV2" for o in result.observations)


@pytest.mark.parametrize(
    "raw",
    [
        b"<script>doSomething()</script>",
        b'<script data-hypernova-key="tournamentfixtures">{}</script>' * 2,
    ],
)
def test_no_script_execution_or_ambiguous_blocks(raw: bytes) -> None:
    with pytest.raises(ValueError):
        json_bytes(raw)


def test_source_exact_route_guard_and_error_response() -> None:
    calls: list[str] = []
    guards: list[bool] = []

    class Transport:
        status = 200

        def get_response(
            self, url: str, *, timeout_seconds: float, max_bytes: int
        ) -> HttpResponseV1:
            calls.append(url)
            return HttpResponseV1(b"<html></html>", self.status, "text/html", None, None)

        def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
            raise AssertionError("response metadata required")

    transport = Transport()
    source = WhoScoredSource(transport=transport, request_guard=lambda: guards.append(True))
    result = source.league("252", "2")
    assert result.resource_key == "Regions/252/Tournaments/2"
    assert result.raw == b"<html></html>"
    assert calls == ["https://www.whoscored.com/Regions/252/Tournaments/2"] and len(guards) == 1
    with pytest.raises(ValueError):
        source.league("../252", "2")
    assert len(calls) == 1
    transport.status = 403
    with pytest.raises(ProviderFetchError):
        source.league("252", "2")


@pytest.mark.parametrize("stage", ["", "/stages/3/fixtures"])
def test_historical_season_requires_exact_native_season_binding(stage: str) -> None:
    route = f"Regions/252/Tournaments/2/Seasons/4{stage}/england-premier-league"
    accepted = normalize(payload(), resource_key=route)
    assert not accepted.findings
    assert any(o.CONTRACT == "FixtureObservationV2" for o in accepted.observations)
    rejected = normalize(payload(), resource_key=route.replace("/Seasons/4/", "/Seasons/5/"))
    assert not rejected.observations
    assert any(f.rule_code == "MF_NORM_SOURCE_RECORD_INVALID" for f in rejected.findings)
    if stage:
        rejected = normalize(payload(), resource_key=route.replace("/stages/3/", "/stages/5/"))
        assert not rejected.observations


def test_historical_season_source_keeps_observed_route_and_guard() -> None:
    calls: list[str] = []
    guards: list[bool] = []

    class Transport:
        def get_response(
            self, url: str, *, timeout_seconds: float, max_bytes: int
        ) -> HttpResponseV1:
            calls.append(url)
            return HttpResponseV1(b"retained", 200, "text/html", None, None)

        def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
            raise AssertionError("metadata must be retained")

    source = WhoScoredSource(transport=Transport(), request_guard=lambda: guards.append(True))
    result = source.season("252", "2", "5826", "england-premier-league")
    assert result.resource_key == "Regions/252/Tournaments/2/Seasons/5826/england-premier-league"
    assert result.raw == b"retained" and len(calls) == len(guards) == 1
    with pytest.raises(ValueError):
        source.season("252", "2", "5826", "../other")
    assert len(calls) == len(guards) == 1
    fixtures = source.season(
        "252", "2", "5826", "england-premier-league-2015-2016", provider_stage_id="12496"
    )
    assert fixtures.resource_key == (
        "regions/252/tournaments/2/seasons/5826/stages/12496/fixtures/"
        "england-premier-league-2015-2016"
    )
    assert len(calls) == len(guards) == 2
