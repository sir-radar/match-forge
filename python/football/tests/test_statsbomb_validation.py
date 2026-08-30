from __future__ import annotations

import copy
import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from football.validation import (
    EventFileValidationInput,
    MatchValidationContext,
    PositionStintValidationContext,
    QualityPolicy,
    validate_statsbomb_dataset,
)

POLICY_PATH = Path(__file__).parents[3] / "schemas/quality/statsbomb-quality-policy-v1.json"
MATCH_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
HOME_TEAM_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
AWAY_TEAM_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
PLAYER_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
FILE_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
RESOURCE_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")


def _row(
    *,
    event_id: str = "11111111-1111-4111-8111-111111111111",
    event_index: int = 1,
) -> dict[str, object]:
    payload = {
        "id": event_id,
        "index": event_index,
        "period": 1,
        "timestamp": "00:00:05.250",
        "minute": 0,
        "second": 5,
        "type": {"id": 30, "name": "Pass"},
        "team": {"id": 779, "name": "Argentina"},
        "player": {"id": 5503, "name": "Player"},
        "location": [60.0, 40.0],
    }
    return {
        "canonical_event_id": event_id,
        "canonical_match_id": str(MATCH_ID),
        "provider_event_id": event_id,
        "provider_match_id": "3869685",
        "event_index": event_index,
        "period": 1,
        "timestamp": "00:00:05.250",
        "minute": 0,
        "second": 5,
        "provider_event_type_id": "30",
        "provider_event_type_name": "Pass",
        "canonical_event_type_id": "pass",
        "canonical_team_id": str(HOME_TEAM_ID),
        "provider_team_id": "779",
        "canonical_player_id": str(PLAYER_ID),
        "provider_player_id": "5503",
        "source_coordinate_system": "statsbomb_120x80",
        "source_x": 60.0,
        "source_y": 40.0,
        "x_norm": 0.5,
        "y_norm": 0.5,
        "location_quality": "valid",
        "provider_payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":")),
    }


def _context(
    *,
    home_score: int = 0,
    away_score: int = 0,
    lineup_players: dict[UUID, frozenset[UUID]] | None = None,
    position_stints: tuple[PositionStintValidationContext, ...] = (),
) -> MatchValidationContext:
    return MatchValidationContext(
        canonical_match_id=MATCH_ID,
        provider_match_id="3869685",
        home_team_id=HOME_TEAM_ID,
        away_team_id=AWAY_TEAM_ID,
        home_score=home_score,
        away_score=away_score,
        lineup_players=lineup_players
        if lineup_players is not None
        else {HOME_TEAM_ID: frozenset({PLAYER_ID}), AWAY_TEAM_ID: frozenset()},
        position_stints=position_stints,
    )


def _file(
    rows: tuple[dict[str, object], ...],
    *,
    context: MatchValidationContext | None = None,
    file_id: UUID = FILE_ID,
) -> EventFileValidationInput:
    return EventFileValidationInput(
        dataset_file_id=file_id,
        source_resource_id=RESOURCE_ID,
        relative_path=f"match_id={MATCH_ID}/events.parquet",
        match=context or _context(),
        rows=rows,
    )


def _codes(*files: EventFileValidationInput) -> list[str]:
    policy = QualityPolicy.from_path(POLICY_PATH)
    return [finding.rule_code for finding in validate_statsbomb_dataset(files, policy)]


def test_valid_event_dataset_has_no_findings() -> None:
    assert _codes(_file((_row(),))) == []


def test_detects_duplicate_matches_events_and_indexes() -> None:
    duplicate_id = copy.deepcopy(_row(event_index=2))
    duplicate_index = _row(
        event_id="22222222-2222-4222-8222-222222222222",
        event_index=1,
    )
    second_file = _file(
        (_row(event_id="33333333-3333-4333-8333-333333333333"),),
        file_id=UUID("12121212-1212-4212-8212-121212121212"),
    )

    codes = _codes(_file((_row(), duplicate_id, duplicate_index)), second_file)

    assert "SB_DUPLICATE_MATCH" in codes
    assert "SB_DUPLICATE_EVENT" in codes
    assert "SB_DUPLICATE_EVENT_INDEX" in codes


def test_detects_missing_players_and_lineup_inconsistencies() -> None:
    missing_mapping = _row()
    missing_mapping["canonical_player_id"] = None
    absent_from_lineup = _row(
        event_id="22222222-2222-4222-8222-222222222222",
        event_index=2,
    )

    codes = _codes(
        _file(
            (missing_mapping, absent_from_lineup),
            context=_context(lineup_players={HOME_TEAM_ID: frozenset(), AWAY_TEAM_ID: frozenset()}),
        )
    )

    assert "SB_MISSING_PLAYER" in codes
    assert "SB_LINEUP_INCONSISTENCY" in codes


def test_classifies_nonmonotonic_provider_position_stint() -> None:
    position = PositionStintValidationContext(
        canonical_player_id=PLAYER_ID,
        sequence=1,
        period_from=4,
        clock_from=timedelta(minutes=115, seconds=32),
        period_to=1,
        clock_to=timedelta(minutes=28, seconds=11),
    )

    codes = _codes(_file((_row(),), context=_context(position_stints=(position,))))

    assert "SB_NONMONOTONIC_POSITION_STINT" in codes


def test_detects_timestamp_coordinate_type_and_payload_quality() -> None:
    timestamp = _row()
    timestamp["timestamp"] = "00:99:05.250"
    out_of_bounds = _row(
        event_id="22222222-2222-4222-8222-222222222222",
        event_index=2,
    )
    out_of_bounds.update(
        source_x=130.0,
        source_y=40.0,
        x_norm=None,
        y_norm=None,
        location_quality="out_of_bounds",
    )
    out_of_bounds_payload = json.loads(str(out_of_bounds["provider_payload_json"]))
    out_of_bounds_payload["location"] = [130.0, 40.0]
    out_of_bounds["provider_payload_json"] = json.dumps(out_of_bounds_payload)
    unknown = _row(
        event_id="33333333-3333-4333-8333-333333333333",
        event_index=3,
    )
    unknown["canonical_event_type_id"] = None
    unknown["provider_event_type_id"] = "999999"
    unknown["provider_event_type_name"] = "Unknown Test Event"
    unknown_payload = json.loads(str(unknown["provider_payload_json"]))
    unknown_payload["type"] = {"id": 999999, "name": "Unknown Test Event"}
    unknown["provider_payload_json"] = json.dumps(unknown_payload)
    malformed = _row(
        event_id="44444444-4444-4444-8444-444444444444",
        event_index=4,
    )
    malformed["provider_payload_json"] = "{"

    codes = _codes(_file((timestamp, out_of_bounds, unknown, malformed)))

    assert "SB_IMPOSSIBLE_EVENT_TIMESTAMP" in codes
    assert "SB_EVENT_LOCATION_OUT_OF_BOUNDS" in codes
    assert "SB_UNKNOWN_EVENT_TYPE" in codes
    assert "SB_MALFORMED_EVENTS_JSON" in codes

    policy = QualityPolicy.from_path(POLICY_PATH)
    findings = validate_statsbomb_dataset((_file((timestamp,)),), policy)
    timestamp_finding = next(
        finding for finding in findings if finding.rule_code == "SB_IMPOSSIBLE_EVENT_TIMESTAMP"
    )
    assert timestamp_finding.severity == "WARNING"
    assert timestamp_finding.action == "USE_EVENT_INDEX_AND_EXCLUDE_TEMPORAL_FEATURES"


def test_detects_score_inconsistency_and_ignores_shootout_goals() -> None:
    normal_time_goal = _row()
    normal_payload = json.loads(str(normal_time_goal["provider_payload_json"]))
    normal_payload["type"] = {"id": 16, "name": "Shot"}
    normal_payload["shot"] = {"outcome": {"id": 97, "name": "Goal"}}
    normal_time_goal.update(
        provider_event_type_id="16",
        provider_event_type_name="Shot",
        canonical_event_type_id="shot",
        provider_payload_json=json.dumps(normal_payload),
    )
    shootout_goal = _row(
        event_id="22222222-2222-4222-8222-222222222222",
        event_index=2,
    )
    shootout_payload = json.loads(str(shootout_goal["provider_payload_json"]))
    shootout_payload.update(period=5, type={"id": 16, "name": "Shot"})
    shootout_payload["shot"] = {"outcome": {"id": 97, "name": "Goal"}}
    shootout_goal.update(
        period=5,
        provider_event_type_id="16",
        provider_event_type_name="Shot",
        canonical_event_type_id="shot",
        provider_payload_json=json.dumps(shootout_payload),
    )

    assert "SB_SCORE_INCONSISTENCY" not in _codes(
        _file((normal_time_goal, shootout_goal), context=_context(home_score=1, away_score=0))
    )
    assert "SB_SCORE_INCONSISTENCY" in _codes(
        _file((normal_time_goal, shootout_goal), context=_context(home_score=2, away_score=0))
    )


def test_counts_paired_own_goal_events_once() -> None:
    own_goal_for = _row()
    for_payload = json.loads(str(own_goal_for["provider_payload_json"]))
    for_payload["type"] = {"id": 25, "name": "Own Goal For"}
    own_goal_for.update(
        provider_event_type_id="25",
        provider_event_type_name="Own Goal For",
        canonical_team_id=str(HOME_TEAM_ID),
        provider_payload_json=json.dumps(for_payload),
    )
    own_goal_against = _row(
        event_id="22222222-2222-4222-8222-222222222222",
        event_index=2,
    )
    against_payload = json.loads(str(own_goal_against["provider_payload_json"]))
    against_payload.update(
        type={"id": 20, "name": "Own Goal Against"},
        team={"id": 780, "name": "Away"},
    )
    own_goal_against.update(
        provider_event_type_id="20",
        provider_event_type_name="Own Goal Against",
        canonical_team_id=str(AWAY_TEAM_ID),
        provider_team_id="780",
        provider_payload_json=json.dumps(against_payload),
    )

    assert "SB_SCORE_INCONSISTENCY" not in _codes(
        _file(
            (own_goal_for, own_goal_against),
            context=_context(home_score=1, away_score=0),
        )
    )


def test_findings_are_deterministic() -> None:
    row = _row()
    row["canonical_event_type_id"] = None
    file = _file((row,))
    policy = QualityPolicy.from_path(POLICY_PATH)

    assert validate_statsbomb_dataset((file,), policy) == validate_statsbomb_dataset(
        (file,), policy
    )
