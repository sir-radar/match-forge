from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from football.normalization.statsbomb_events import (
    CanonicalEventReference,
    EventNormalizationError,
    normalize_statsbomb_events,
)

MATCH_ID = UUID("11111111-1111-7111-8111-111111111111")
TEAM_ID = UUID("22222222-2222-7222-8222-222222222222")
PLAYER_ID = UUID("33333333-3333-7333-8333-333333333333")
FIRST_EVENT_ID = UUID("44444444-4444-7444-8444-444444444444")
SECOND_EVENT_ID = UUID("55555555-5555-7555-8555-555555555555")
FIRST_PROVIDER_EVENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SECOND_PROVIDER_EVENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _event(
    provider_event_id: str,
    index: int,
    *,
    event_type_id: int = 30,
    event_type_name: str = "Pass",
    location: list[float] | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "id": provider_event_id,
        "index": index,
        "period": 1,
        "timestamp": f"00:00:0{index}.250",
        "minute": 0,
        "second": index,
        "type": {"id": event_type_id, "name": event_type_name},
        "team": {"id": 779, "name": "Argentina"},
        "player": {"id": 5503, "name": "Lionel Andrés Messi Cuccittini"},
    }
    if location is not None:
        event["location"] = location
    return event


def _reference(event_id: UUID, provider_event_id: str, index: int) -> CanonicalEventReference:
    return CanonicalEventReference(
        canonical_event_id=event_id,
        canonical_match_id=MATCH_ID,
        provider_event_id=provider_event_id,
        event_index=index,
        provider_event_type="Pass",
        period=1,
        event_clock=timedelta(seconds=index, milliseconds=250),
        canonical_team_id=TEAM_ID,
        canonical_player_id=PLAYER_ID,
    )


def test_normalizes_in_source_order_with_canonical_ids_and_coordinates() -> None:
    payload = json.dumps(
        [
            _event(SECOND_PROVIDER_EVENT_ID, 2, location=[130.0, 40.0]),
            _event(FIRST_PROVIDER_EVENT_ID, 1, location=[60.0, 40.0]),
        ]
    ).encode()
    references = {
        FIRST_PROVIDER_EVENT_ID: _reference(FIRST_EVENT_ID, FIRST_PROVIDER_EVENT_ID, 1),
        SECOND_PROVIDER_EVENT_ID: _reference(SECOND_EVENT_ID, SECOND_PROVIDER_EVENT_ID, 2),
    }

    rows = normalize_statsbomb_events(
        payload,
        "3869685",
        references,
        {"779": TEAM_ID},
        {"5503": PLAYER_ID},
    )

    assert [row["event_index"] for row in rows] == [1, 2]
    assert rows[0]["canonical_event_id"] == str(FIRST_EVENT_ID)
    assert rows[0]["canonical_match_id"] == str(MATCH_ID)
    assert rows[0]["canonical_team_id"] == str(TEAM_ID)
    assert rows[0]["canonical_player_id"] == str(PLAYER_ID)
    assert rows[0]["canonical_event_type_id"] == "pass"
    assert rows[0]["source_coordinate_system"] == "statsbomb_120x80"
    assert rows[0]["source_x"] == 60.0
    assert rows[0]["source_y"] == 40.0
    assert rows[0]["x_norm"] == 0.5
    assert rows[0]["y_norm"] == 0.5
    assert rows[0]["location_quality"] == "valid"
    assert rows[1]["source_x"] == 130.0
    assert rows[1]["x_norm"] is None
    assert rows[1]["location_quality"] == "out_of_bounds"
    assert json.loads(str(rows[0]["provider_payload_json"]))["id"] == FIRST_PROVIDER_EVENT_ID


def test_preserves_unknown_provider_type_without_canonical_mapping() -> None:
    event = _event(
        FIRST_PROVIDER_EVENT_ID,
        1,
        event_type_id=999999,
        event_type_name="Unknown Type",
    )
    reference = _reference(FIRST_EVENT_ID, FIRST_PROVIDER_EVENT_ID, 1)
    reference = replace(reference, provider_event_type="Unknown Type")

    rows = normalize_statsbomb_events(
        json.dumps([event]).encode(),
        "3869685",
        {FIRST_PROVIDER_EVENT_ID: reference},
        {"779": TEAM_ID},
        {"5503": PLAYER_ID},
    )

    assert rows[0]["provider_event_type_id"] == "999999"
    assert rows[0]["provider_event_type_name"] == "Unknown Type"
    assert rows[0]["canonical_event_type_id"] is None


def test_rejects_payload_that_conflicts_with_canonical_catalogue() -> None:
    event = _event(FIRST_PROVIDER_EVENT_ID, 2)

    with pytest.raises(EventNormalizationError, match="conflicts with canonical event index"):
        normalize_statsbomb_events(
            json.dumps([event]).encode(),
            "3869685",
            {FIRST_PROVIDER_EVENT_ID: _reference(FIRST_EVENT_ID, FIRST_PROVIDER_EVENT_ID, 1)},
            {"779": TEAM_ID},
            {"5503": PLAYER_ID},
        )
