from __future__ import annotations

import json
from uuid import UUID

import pytest
from football.forecasting.corner_labels import (
    CornerLabelError,
    extract_statsbomb_corner_counts,
)

MATCH_ID = UUID("11111111-1111-4111-8111-111111111111")
HOME_TEAM_ID = UUID("22222222-2222-4222-8222-222222222222")
AWAY_TEAM_ID = UUID("33333333-3333-4333-8333-333333333333")


def _row(
    *,
    event_id: str,
    team_id: UUID | None,
    event_type_id: str = "30",
    event_type_name: str = "Pass",
    payload: object | None = None,
) -> dict[str, object]:
    return {
        "canonical_event_id": event_id,
        "canonical_match_id": str(MATCH_ID),
        "canonical_team_id": str(team_id) if team_id is not None else None,
        "provider_event_type_id": event_type_id,
        "provider_event_type_name": event_type_name,
        "provider_payload_json": json.dumps(payload or {}),
    }


def test_extracts_exact_statsbomb_corner_labels_by_canonical_team() -> None:
    rows = (
        _row(
            event_id="a",
            team_id=HOME_TEAM_ID,
            payload={"pass": {"type": {"id": 61, "name": "Corner"}}},
        ),
        _row(
            event_id="b",
            team_id=HOME_TEAM_ID,
            payload={"pass": {"type": {"id": 61, "name": "Corner"}}},
        ),
        _row(
            event_id="c",
            team_id=AWAY_TEAM_ID,
            payload={"pass": {"type": {"id": 61, "name": "Corner"}}},
        ),
        _row(
            event_id="d",
            team_id=AWAY_TEAM_ID,
            event_type_id="42",
            event_type_name="Ball Receipt*",
            payload={"play_pattern": {"id": 2, "name": "From Corner"}},
        ),
    )

    counts = extract_statsbomb_corner_counts(rows, MATCH_ID, HOME_TEAM_ID, AWAY_TEAM_ID)

    assert (counts.home_corners, counts.away_corners, counts.total_events) == (2, 1, 3)
    assert counts.event_ids == ("a", "b", "c")


@pytest.mark.parametrize(
    "row",
    (
        _row(
            event_id="a",
            team_id=HOME_TEAM_ID,
            payload={"pass": {"type": {"id": 999, "name": "Corner"}}},
        ),
        _row(
            event_id="a",
            team_id=HOME_TEAM_ID,
            payload={"pass": {"type": {"id": 61, "name": "Not Corner"}}},
        ),
    ),
)
def test_rejects_conflicting_statsbomb_corner_vocabulary(row: dict[str, object]) -> None:
    with pytest.raises(CornerLabelError, match="corner vocabulary conflicts"):
        extract_statsbomb_corner_counts((row,), MATCH_ID, HOME_TEAM_ID, AWAY_TEAM_ID)


def test_rejects_corner_without_match_team_attribution() -> None:
    foreign_team = UUID("44444444-4444-4444-8444-444444444444")
    row = _row(
        event_id="a",
        team_id=foreign_team,
        payload={"pass": {"type": {"id": 61, "name": "Corner"}}},
    )

    with pytest.raises(CornerLabelError, match="not a match participant"):
        extract_statsbomb_corner_counts((row,), MATCH_ID, HOME_TEAM_ID, AWAY_TEAM_ID)


def test_rejects_malformed_provider_payload() -> None:
    row = _row(event_id="a", team_id=HOME_TEAM_ID)
    row["provider_payload_json"] = "{"

    with pytest.raises(CornerLabelError, match="malformed provider payload"):
        extract_statsbomb_corner_counts((row,), MATCH_ID, HOME_TEAM_ID, AWAY_TEAM_ID)
