from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.base import HttpResponseV1
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource
from football.providers.sources.espn import ESPNSource


def competition(status: str = "STATUS_FULL_TIME") -> dict[str, Any]:
    return {
        "id": "42",
        "date": "2024-08-16T19:00Z",
        "timeValid": True,
        "status": {
            "type": {
                "name": status,
                "state": "pre" if status == "STATUS_SCHEDULED" else "post",
                "completed": status != "STATUS_SCHEDULED",
            },
            "period": 2,
        },
        "competitors": [
            {
                "id": "1",
                "homeAway": "home",
                "team": {"id": "1", "displayName": "Home"},
                "score": "1",
            },
            {
                "id": "2",
                "homeAway": "away",
                "team": {"id": "2", "displayName": "Away"},
                "score": "0",
            },
        ],
    }


def normalize(resource: str, payload: object) -> NormalizationResult:
    raw = json.dumps(payload).encode()
    source = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")
    now = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "espn", None, source, source, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="eng.1/summary?event=42"
        if resource == "summary"
        else "eng.1/scoreboard?dates=20240816",
        fixture_native_id="42" if resource == "summary" else None,
        competition_native_id="700",
        season_label="2024",
    )
    result = normalize_resource(context, resource, raw)
    assert result == normalize_resource(context, resource, raw)
    return result


def test_espn_source_preserves_one_summary_request_and_exact_route() -> None:
    class Transport:
        def get_response(
            self, url: str, *, timeout_seconds: float, max_bytes: int
        ) -> HttpResponseV1:
            calls.append(url)
            return HttpResponseV1(b"{}", 200, "application/json", None, None)

        def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
            raise AssertionError("response metadata must be retained")

    calls: list[str] = []
    guards: list[bool] = []
    source = ESPNSource(
        league_slug="eng.1", transport=Transport(), request_guard=lambda: guards.append(True)
    )
    day = source.fixtures(date(2024, 8, 16))
    summary = source.summary("42")
    assert day.resource_key == "eng.1/scoreboard?dates=20240816"
    assert summary.resource_key == "eng.1/summary?event=42"
    assert calls[1].endswith("/soccer/eng.1/summary?event=42") and len(calls) == len(guards) == 2
    assert day.raw == summary.raw == b"{}"


def test_scoreboard_scheduled_placeholder_scores_and_statistics_stay_out_of_outcomes() -> None:
    comp = competition("STATUS_SCHEDULED")
    comp["competitors"][0]["statistics"] = [{"name": "totalShots", "displayValue": "20"}]
    result = normalize(
        "scoreboard",
        {
            "leagues": [{"id": "700", "slug": "eng.1", "name": "League"}],
            "events": [{"id": "42", "season": {"year": 2024}, "competitions": [comp]}],
        },
    )
    assert not result.findings
    assert any(o.CONTRACT == "FixtureObservationV2" for o in result.observations)
    assert not any(
        o.CONTRACT
        in ("ResultObservationV2", "TeamStatisticObservationV2", "TeamStatisticObservationV3")
        for o in result.observations
    )


def test_summary_named_statistics_and_events_keep_scope_and_ambiguous_people() -> None:
    payload = {
        "header": {
            "id": "42",
            "season": {"year": 2024},
            "league": {"id": "700", "slug": "eng.1", "name": "League"},
            "competitions": [competition()],
        },
        "boxscore": {
            "teams": [
                {
                    "team": {"id": "1", "displayName": "Home"},
                    "statistics": [
                        {"name": "totalShots", "displayValue": "4"},
                        {"name": "shotsOnTarget", "displayValue": "2"},
                        {"name": "totalPasses", "displayValue": "100"},
                        {"name": "accuratePasses", "displayValue": "75"},
                        {"name": "passPct", "displayValue": "0.75"},
                    ],
                }
            ]
        },
        "keyEvents": [
            {
                "id": "10",
                "type": {"type": "goal---volley"},
                "scoringPlay": True,
                "shootout": False,
                "team": {"id": "1"},
                "clock": {"displayValue": "90'+2'"},
                "period": {"number": 2},
                "participants": [{"athlete": {"id": "5"}}, {"athlete": {"id": "6"}}],
                "wallclock": "2024-08-17T06:11:52Z",
            }
        ],
    }
    result = normalize("summary", payload)
    stat = next(
        o.to_dict() for o in result.observations if o.CONTRACT == "TeamStatisticObservationV3"
    )
    assert stat["passes"] == 100 and stat["accurate_passes"] == 75
    event = next(o for o in result.observations if o.CONTRACT == "EventObservationV2")
    assert event.to_dict()["minute"] == 90 and event.to_dict()["added_time"] == 2
    assert event.to_dict()["player"] is None
    assert event.time.event_time is None and event.time.provider_updated_at is None
    assert any(f.rule_code == "MF_NORM_PARTICIPANT_ROLE_UNKNOWN" for f in result.findings)
    assert any(f.evidence.get("source_key") == "passPct" for f in result.findings)


def summary_payload() -> dict[str, Any]:
    return {
        "header": {
            "id": "42",
            "season": {"year": 2024},
            "timeValid": True,
            "league": {"id": "700", "slug": "eng.1", "name": "League"},
            "competitions": [competition()],
        }
    }


@pytest.mark.parametrize(
    "invalid",
    [
        "fixture",
        "request",
        "season",
        "league",
        "slug",
        "status",
        "roles",
        "same_team",
        "competitor",
        "time",
    ],
)
def test_summary_scope_and_unmapped_status_are_held(invalid: str) -> None:
    payload = summary_payload()
    header = payload["header"]
    comp = header["competitions"][0]
    if invalid == "fixture":
        header["id"] = "43"
    elif invalid == "request":
        comp["id"] = "43"
    elif invalid == "season":
        header["season"]["year"] = 2025
    elif invalid == "league":
        header["league"]["id"] = "701"
    elif invalid == "slug":
        header["league"]["slug"] = "esp.1"
    elif invalid == "status":
        comp["status"]["type"]["name"] = "NEW_STATUS"
    elif invalid == "roles":
        comp["competitors"][1]["homeAway"] = "home"
    elif invalid == "same_team":
        comp["competitors"][1]["team"]["id"] = "1"
    elif invalid == "competitor":
        comp["competitors"][0]["id"] = "999"
    else:
        comp["timeValid"] = False
    result = normalize("summary", payload)
    assert any(f.rule_code == "MF_NORM_RESOURCE_INVALID" for f in result.findings)
    assert not any(o.CONTRACT == "ResultObservationV2" for o in result.observations)


def test_summary_header_time_and_roster_do_not_infer_minutes_or_confirmation() -> None:
    payload = summary_payload()
    del payload["header"]["competitions"][0]["timeValid"]
    payload["rosters"] = [
        {
            "team": {"id": "1", "displayName": "Home"},
            "formation": "4-3-3",
            "roster": [
                {
                    "athlete": {"id": "5", "displayName": "Player"},
                    "starter": False,
                    "active": True,
                    "stats": [{"name": "totalShots", "displayValue": "0"}],
                }
            ],
        }
    ]
    result = normalize("summary", payload)
    assert not result.findings
    stat = next(
        o.to_dict() for o in result.observations if o.CONTRACT == "PlayerStatisticObservationV2"
    )
    assert stat["shots"] == 0 and stat["minutes_played"] is None
    lineup = next(o.to_dict() for o in result.observations if o.CONTRACT == "LineupObservationV2")
    members = lineup["players"]
    assert isinstance(members, list)
    assert lineup["lineup_mode"] == "UNKNOWN" and members[0]["role"] == "BENCH"
    assert not any(o.CONTRACT == "FormationObservationV2" for o in result.observations)


@pytest.mark.parametrize(
    "change,code",
    [
        ("shootout", "EVENT_SHOOTOUT_UNSUPPORTED"),
        ("clock", "SOURCE_RECORD_INVALID"),
        ("team", "SOURCE_RECORD_INVALID"),
        ("unknown", "EVENT_TYPE_UNKNOWN"),
    ],
)
def test_invalid_or_unqualified_event_does_not_become_ordinary_goal(change: str, code: str) -> None:
    payload = summary_payload()
    row: dict[str, Any] = {
        "id": "10",
        "scoringPlay": True,
        "team": {"id": "1"},
        "period": {"number": 2},
        "clock": {"displayValue": "88'"},
        "shootout": False,
    }
    if change == "shootout":
        row["shootout"] = True
    elif change == "clock":
        row["clock"]["displayValue"] = "future format"
    elif change == "team":
        row["team"]["id"] = "9"
    else:
        row["scoringPlay"] = False
        row["type"] = {"type": "unknown"}
    payload["keyEvents"] = [row]
    result = normalize("summary", payload)
    assert any(f.rule_code == "MF_NORM_" + code for f in result.findings)
    assert not any(o.CONTRACT == "EventObservationV2" for o in result.observations)


@pytest.mark.parametrize("slug", ["../eng.1", "eng.1?x=1", "", "https://example.test"])
def test_source_rejects_invalid_routes_before_request(slug: str) -> None:
    with pytest.raises(ValueError):
        ESPNSource(league_slug=slug)
