from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource


def normalize(body: dict[str, Any], family: str, **changes: Any) -> NormalizationResult:
    envelope = {
        "url": "https://www.sofascore.com/api/v1/event/42"
        + ("" if family == "event" else "/" + family),
        "status": 200,
        "fetched_at_utc": "2026-10-01T12:00:00+00:00",
        "trimmed": False,
        "body": body,
    }
    envelope.update(changes)
    raw = json.dumps(envelope).encode()
    now = datetime(2026, 11, 2, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "sofascore", None, UUID(int=1), UUID(int=2), hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="github/pinned/research/" + family + ".json",
        fixture_native_id="42",
    )
    return normalize_resource(context, "retained_" + family, raw)


def test_event_uses_native_ids_epoch_and_unknown_score_basis() -> None:
    body = {
        "event": {
            "id": 42,
            "tournament": {
                "uniqueTournament": {"id": 17, "name": "League"},
                "category": {"sport": {"slug": "football"}},
            },
            "season": {"id": 7, "year": "26/27"},
            "homeTeam": {"id": 1, "name": "Home"},
            "awayTeam": {"id": 2, "name": "Away"},
            "startTimestamp": 1791489600,
            "status": {"type": "finished", "code": 100},
            "homeScore": {"current": 0, "period1": 0},
            "awayScore": {"current": 0, "period1": 0},
        }
    }
    result = normalize(body, "event")
    assert not result.findings
    assert sum(o.CONTRACT == "FixtureObservationV2" for o in result.observations) == 1
    assert (
        next(
            o.to_dict()["score_basis"]
            for o in result.observations
            if o.CONTRACT == "ResultObservationV2"
        )
        == "UNKNOWN"
    )
    assert all(o.time.known_at == datetime(2026, 11, 2, tzinfo=UTC) for o in result.observations)
    body["event"]["id"] = 43
    assert not normalize(body, "event").observations


def test_trimmed_stats_keep_zero_missing_and_scope() -> None:
    body = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": "shotsOnGoal", "home": "0", "away": "3"},
                            {"__trimmed__": 20},
                        ]
                    }
                ],
            }
        ]
    }
    result = normalize(body, "statistics", trimmed=True)
    assert any("TRIMMED" in f.rule_code for f in result.findings)
    rows = [o.to_dict() for o in result.observations if o.CONTRACT == "TeamStatisticObservationV2"]
    assert len(rows) == 2
    assert rows[0]["shots_on_target"] == 0
    assert rows[0]["corners"] is None
    assert not normalize(
        body, "statistics", url="https://www.sofascore.com/api/v1/event/43/statistics"
    ).observations


def test_lineup_minutes_and_partial_members_do_not_become_complete() -> None:
    member = {
        "player": {"id": 9, "name": "Player"},
        "teamId": 1,
        "substitute": False,
        "statistics": {"minutesPlayed": 90, "goals": 0},
    }
    result = normalize(
        {
            "confirmed": True,
            "home": {"players": [member, {"__trimmed__": 10}]},
            "away": {"players": []},
        },
        "lineups",
        trimmed=True,
    )
    assert any(o.CONTRACT == "PlayerStatisticObservationV2" for o in result.observations)
    assert all(
        o.to_dict()["lineup_mode"] == "UNKNOWN"
        for o in result.observations
        if o.CONTRACT == "LineupObservationV2"
    )
    assert not normalize({}, "lineups", status=403).observations


def test_incidents_keep_cards_and_substitution_players() -> None:
    result = normalize(
        {
            "incidents": [
                {"incidentType": "period", "time": 90, "addedTime": 999},
                {
                    "id": 8,
                    "incidentType": "card",
                    "incidentClass": "yellow",
                    "isHome": True,
                    "time": 45,
                    "addedTime": 1,
                    "player": {"id": 9, "name": "Player"},
                },
                {
                    "id": 10,
                    "incidentType": "substitution",
                    "isHome": False,
                    "time": 86,
                    "playerIn": {"id": 11, "name": "Incoming"},
                    "playerOut": {"id": 12, "name": "Outgoing"},
                },
            ]
        },
        "incidents",
    )
    events = [o.to_dict() for o in result.observations if o.CONTRACT == "EventObservationV2"]
    assert len(events) == 2
    assert events[0]["event_type"] == "YELLOW_CARD"
    assert events[0]["added_time"] == 1
    assert events[1]["event_type"] == "SUBSTITUTION"
    assert events[1]["player"] is None


def test_invalid_envelope_and_missing_body_are_rejected() -> None:
    assert not normalize({}, "statistics").observations
    assert not normalize(
        {"statistics": []}, "statistics", fetched_at_utc="2027-01-01T00:00:00Z"
    ).observations
    assert not normalize(
        {"statistics": []}, "statistics", url="https://evil.example/api/v1/event/42/statistics"
    ).observations
    assert not normalize({"statistics": [{"__trimmed__": 10}]}, "statistics").observations


def test_player_team_ids_do_not_establish_match_team_membership() -> None:
    rows = [
        {"player": {"id": 8 + team, "name": "Player"}, "teamId": team, "substitute": False}
        for team in [1, 2]
    ]
    result = normalize({"home": {"players": rows}, "away": {"players": []}}, "lineups")
    assert result.observations
    for observation in result.observations:
        row = observation.to_dict()
        team = row.get("team")
        assert isinstance(team, dict)
        assert team["provider_native_id"] is None
    assert any("PLAYER_TEAM_SCOPE_UNVERIFIED" in finding.rule_code for finding in result.findings)
