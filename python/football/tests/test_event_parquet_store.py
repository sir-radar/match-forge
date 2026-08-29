from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pytest
from football.normalization.statsbomb_events import EVENT_SCHEMA_SHA256
from football.storage.parquet import (
    EVENT_ARROW_SCHEMA,
    ImmutableEventParquetStore,
    ParquetPublicationError,
)


def _row(index: int) -> dict[str, object]:
    return {
        "canonical_event_id": f"00000000-0000-7000-8000-{index:012d}",
        "canonical_match_id": "11111111-1111-7111-8111-111111111111",
        "provider_event_id": f"aaaaaaaa-aaaa-4aaa-8aaa-{index:012d}",
        "provider_match_id": "3869685",
        "event_index": index,
        "period": 1,
        "timestamp": f"00:00:0{index}.000",
        "minute": 0,
        "second": index,
        "provider_event_type_id": "30",
        "provider_event_type_name": "Pass",
        "canonical_event_type_id": "pass",
        "canonical_team_id": "22222222-2222-7222-8222-222222222222",
        "provider_team_id": "779",
        "canonical_player_id": "33333333-3333-7333-8333-333333333333",
        "provider_player_id": "5503",
        "source_coordinate_system": "statsbomb_120x80",
        "source_x": 60.0,
        "source_y": 40.0,
        "x_norm": 0.5,
        "y_norm": 0.5,
        "location_quality": "valid",
        "provider_payload_json": "{}",
    }


def test_publishes_deterministic_parquet_and_verifies_idempotent_rerun(tmp_path: Path) -> None:
    rows = (_row(1), _row(2))
    relative_path = "normalized/events/schema=v1/dataset=test/events.parquet"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_store = ImmutableEventParquetStore(first_root)

    first = first_store.publish(relative_path, rows)
    modified_at = first.absolute_path.stat().st_mtime_ns
    rerun = first_store.publish(relative_path, rows)
    rebuild = ImmutableEventParquetStore(second_root).publish(relative_path, rows)

    assert first.status == "published"
    assert rerun.status == "verified_published"
    assert first.absolute_path.stat().st_mtime_ns == modified_at
    assert first.physical_sha256 == rerun.physical_sha256 == rebuild.physical_sha256
    assert first.logical_sha256 == rerun.logical_sha256 == rebuild.logical_sha256
    assert first.row_count == rerun.row_count == rebuild.row_count == 2
    assert first_store.read_rows(relative_path) == rows
    assert not list(first_root.rglob("*.part"))


def test_rejects_conflicting_immutable_parquet(tmp_path: Path) -> None:
    store = ImmutableEventParquetStore(tmp_path)
    relative_path = "normalized/events/schema=v1/dataset=test/events.parquet"
    published = store.publish(relative_path, (_row(1),))
    published.absolute_path.write_bytes(b"corrupt")

    with pytest.raises(ParquetPublicationError, match="published Parquet is invalid"):
        store.publish(relative_path, (_row(1),))


def test_arrow_schema_matches_versioned_contract() -> None:
    schema_path = Path(__file__).parents[3] / "schemas/arrow/normalized-events-v1.json"
    payload = schema_path.read_bytes()
    contract = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == EVENT_SCHEMA_SHA256
    assert [
        [
            field.name,
            "float64" if pa.types.is_float64(field.type) else str(field.type),
            field.nullable,
        ]
        for field in EVENT_ARROW_SCHEMA
    ] == contract["fields"]
