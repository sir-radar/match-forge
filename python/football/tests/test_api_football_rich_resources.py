from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource


def normalize(
    resource: str,
    rows: list[object],
    response_fixture: str = "42",
    request_fixture: str | None = "42",
) -> NormalizationResult:
    raw = json.dumps(
        {"response": rows, "errors": [], "parameters": {"fixture": response_fixture}}
    ).encode()
    source = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")
    now = datetime(2026, 10, 16, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "api_football", None, source, source, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="/fixtures/statistics"
        + (f"?fixture={request_fixture}" if request_fixture else ""),
        fixture_native_id="42",
    )
    result = normalize_resource(context, resource, raw)
    assert result == normalize_resource(context, resource, raw)
    return result


@pytest.mark.parametrize("response,request_id", [("43", "42"), ("42", "43"), ("43", None)])
def test_source_and_request_fixture_conflicts_are_quarantined(
    response: str, request_id: str | None
) -> None:
    result = normalize("statistics", [], response, request_id)
    assert not result.observations
    assert result.findings[0].rule_code == "MF_NORM_RESOURCE_INVALID"


def test_response_fixture_evidence_accepts_registered_paths_without_query() -> None:
    assert not normalize("statistics", [], request_fixture=None).findings


@pytest.mark.parametrize(
    "kind,detail,event,own,penalty",
    [
        ("Goal", "Own Goal", "GOAL", True, False),
        ("Goal", "Penalty", "GOAL", False, True),
        ("Card", "Red Card", "RED_CARD", None, None),
        ("Card", "Second Yellow card", "RED_CARD", None, None),
        ("Var", "Goal cancelled", "DISALLOWED_GOAL", None, None),
        ("subst", "Substitution 1", "SUBSTITUTION", None, None),
    ],
)
def test_api_event_categories_are_explicit(
    kind: str, detail: str, event: str, own: bool | None, penalty: bool | None
) -> None:
    result = normalize("events", [{"type": kind, "detail": detail, "time": {}, "team": {"id": 1}}])
    observation = result.observations[0].to_dict()
    assert observation["event_type"] == event
    assert observation["own_goal"] == own and observation["penalty"] == penalty


def test_api_statistics_use_native_vocabulary_without_zero_fill() -> None:
    result = normalize(
        "statistics",
        [
            {
                "team": {"id": 1, "name": "Team"},
                "statistics": [
                    {"type": "Shots on Goal", "value": 0},
                    {"type": "Total Shots", "value": 2},
                    {"type": "Shots off Goal", "value": None},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Total passes", "value": 100},
                    {"type": "Passes accurate", "value": 75},
                    {"type": "Passes %", "value": "75%"},
                    {"type": "expected_goals", "value": "0.4"},
                    {"type": "New statistic", "value": 8},
                ],
            }
        ],
    )
    stat = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "TeamStatisticObservationV3"
    )
    assert stat["shots_on_target"] == stat["corners"] == 0
    assert stat["shots_off_target"] is None
    assert stat["accurate_passes"] == 75
    assert stat["passes"] == 100
    assert not any(f.severity == "QUARANTINE" for f in result.findings)
    assert any(f.evidence.get("source_key") == "New statistic" for f in result.findings)


def test_api_events_preserve_source_position_without_fabricating_ids_or_periods() -> None:
    rows: list[object] = [
        {
            "time": {"elapsed": 45, "extra": 7},
            "team": {"id": 1},
            "player": {"id": None, "name": "Name"},
            "type": "Goal",
            "detail": "Normal Goal",
        },
        {
            "time": {"elapsed": 90},
            "team": {"id": 1},
            "player": None,
            "type": "Card",
            "detail": "Yellow Card",
        },
        {"time": {"elapsed": 90}, "team": {"id": 1}, "type": "Goal", "detail": "Missed Penalty"},
    ]
    result = normalize("events", rows)
    events = [json.loads(o.to_bytes()) for o in result.observations]
    assert len(events) == 2
    assert events[0]["event_type"] == "GOAL" and events[0]["added_time"] == 7
    assert events[0]["player"]["provider_native_id"] is None
    assert events[0]["period"] is None
    assert events[1]["event_type"] == "YELLOW_CARD"
    assert any(f.rule_code == "MF_NORM_EVENT_TYPE_UNKNOWN" for f in result.findings)


def test_api_player_statistics_do_not_infer_pass_accuracy_or_nonappearance() -> None:
    row: dict[str, Any] = {
        "team": {"id": 1, "name": "Team"},
        "players": [
            {
                "player": {"id": 5, "name": "Player"},
                "statistics": [
                    {
                        "games": {"minutes": 0},
                        "shots": {"total": 0, "on": None},
                        "passes": {"total": 12, "accuracy": "9"},
                        "goals": {"assists": 0},
                        "cards": {"yellow": 0, "red": 0},
                    }
                ],
            },
            {"player": {"id": 6, "name": "Unknown appearance"}, "statistics": []},
        ],
    }
    result = normalize("player_statistics", [row])
    stats = [
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "PlayerStatisticObservationV3"
    ]
    assert len(stats) == 1 and stats[0]["minutes_played"] == 0
    assert stats[0]["passes"] == 12 and stats[0]["accurate_passes"] is None
    assert stats[0]["shots"] == 0 and stats[0]["shots_on_target"] is None
    assert any(f.rule_code == "MF_NORM_PLAYER_STATISTIC_SCOPE_UNKNOWN" for f in result.findings)


def test_api_count_failure_is_isolated_to_its_record() -> None:
    result = normalize(
        "statistics",
        [
            {
                "team": {"id": 1},
                "statistics": [
                    {"type": "Corner Kicks", "value": -1},
                    {"type": "Total Shots", "value": 0},
                ],
            }
        ],
    )
    stat = next(
        o.to_dict() for o in result.observations if o.CONTRACT == "TeamStatisticObservationV2"
    )
    assert stat["corners"] is None and stat["total_shots"] == 0
    assert any(f.severity == "QUARANTINE" for f in result.findings)
