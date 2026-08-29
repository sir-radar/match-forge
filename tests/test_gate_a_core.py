from __future__ import annotations

import copy
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from experiments.sprint1_roundtrip.core import (
    canonical_json_bytes,
    logical_checksum,
    normalize_events,
    normalized_event_schema,
    stable_uuid,
    write_json_exclusive_or_verify,
)


def event(index: int = 1) -> dict[str, object]:
    return {
        "id": f"event-{index}",
        "index": index,
        "period": 1,
        "timestamp": "00:00:00.000",
        "minute": 0,
        "second": 0,
        "type": {"id": 30, "name": "Pass"},
        "team": {"id": 779, "name": "Argentina"},
        "player": {"id": 5503, "name": "Lionel Andrés Messi Cuccittini"},
        "location": [60.0, 40.0],
    }


def test_stable_uuid_does_not_depend_on_display_name() -> None:
    assert stable_uuid("team", 779) == stable_uuid("team", "779")


def test_normalization_uses_event_index_order_and_preserves_coordinates() -> None:
    result = normalize_events([event(2), event(1)], 3869685)
    assert [row["event_index"] for row in result.rows] == [1, 2]
    assert result.rows[0]["source_x"] == 60.0
    assert result.rows[0]["source_y"] == 40.0
    assert result.rows[0]["x_norm"] == 0.5
    assert result.rows[0]["y_norm"] == 0.5


def test_unknown_provider_type_is_preserved_without_other_mapping() -> None:
    unknown = event()
    unknown["type"] = {"id": 999999, "name": "Prototype Unknown Type"}
    result = normalize_events([unknown], 3869685)
    row = result.rows[0]
    assert row["provider_event_type_id"] == "999999"
    assert row["provider_event_type_name"] == "Prototype Unknown Type"
    assert row["canonical_event_type_id"] is None
    assert result.findings[0].rule_code == "SB_UNKNOWN_EVENT_TYPE"


def test_invalid_coordinate_is_preserved_and_not_normalized() -> None:
    invalid = event()
    invalid["location"] = [130.0, 40.0]
    result = normalize_events([invalid], 3869685)
    assert result.rows[0]["source_x"] == 130.0
    assert result.rows[0]["x_norm"] is None
    assert result.rows[0]["location_quality"] == "out_of_bounds"


def test_duplicate_event_index_quarantines_component() -> None:
    first = event(1)
    second = copy.deepcopy(event(2))
    second["index"] = 1
    result = normalize_events([first, second], 3869685)
    assert not result.rows
    assert result.quarantined_count == 2
    assert result.findings[0].rule_code == "SB_DUPLICATE_EVENT_INDEX"


@given(st.lists(st.integers(), max_size=30))
def test_logical_checksum_is_deterministic(values: list[int]) -> None:
    rows = [{"value": value} for value in values]
    assert logical_checksum(rows) == logical_checksum(rows)


def test_canonical_json_is_key_order_independent() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == canonical_json_bytes({"a": 1, "b": 2})


def test_immutable_json_writer_rejects_conflict(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_json_exclusive_or_verify(path, {"value": 1})
    write_json_exclusive_or_verify(path, {"value": 1})
    try:
        write_json_exclusive_or_verify(path, {"value": 2})
    except RuntimeError as error:
        assert "IMMUTABLE_ARTIFACT_CONFLICT" in str(error) or "conflicting artifact" in str(error)
    else:
        raise AssertionError("conflicting immutable write succeeded")


def test_event_schema_has_no_implicit_nullability_for_identity() -> None:
    schema = normalized_event_schema()
    assert not schema.field("canonical_event_id").nullable
    assert not schema.field("event_index").nullable
