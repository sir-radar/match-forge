from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.qualify_statsbomb_tier_a_xg import (
    TierAXGQualificationError,
    qualify,
)

_DATASET_ID = "670662d6-6ed7-5fa1-ba3c-1cfd561e524f"
_COMPETITION_ID = "01a051db-552e-782d-b2ac-b3f0ec58441b"
_SEASON_ID = "01a051db-553a-754a-9560-d79eceeb72b6"


def test_qualifies_complete_statsbomb_xg_coverage(tmp_path: Path) -> None:
    manifest_path = _dataset(tmp_path, xg_values=(0.2, 0.4))

    report = qualify(
        data_root=tmp_path,
        manifest_path=manifest_path,
        expected_dataset_version_id=_DATASET_ID,
    )

    assert report["status"] == "PASS"
    assert report["dataset"]["canonical_competition_id"] == _COMPETITION_ID
    assert report["dataset"]["canonical_season_id"] == _SEASON_ID
    assert report["result"]["coverage"] == {
        "event_count": 2,
        "match_count": 2,
        "matches_with_shots": 2,
        "matches_without_shots": 0,
        "shot_count": 2,
        "shots_with_provider_xg": 2,
        "shots_with_valid_unit_interval_xg": 2,
        "shots_missing_provider_xg": 0,
        "shots_missing_canonical_event_type": 0,
        "shots_missing_canonical_team": 0,
        "shots_missing_canonical_player": 0,
        "shots_missing_source_location": 0,
        "shots_with_out_of_bounds_source_location": 0,
        "malformed_shot_payloads": 0,
    }
    assert report["result"]["semantics"]["xg_sum"] == pytest.approx(0.6)
    assert report["result"]["failures"] == []


def test_reports_invalid_provider_xg_as_failure(tmp_path: Path) -> None:
    manifest_path = _dataset(tmp_path, xg_values=(1.1, 0.4))

    report = qualify(
        data_root=tmp_path,
        manifest_path=manifest_path,
        expected_dataset_version_id=_DATASET_ID,
    )

    assert report["status"] == "FAIL"
    assert report["result"]["coverage"]["shots_with_valid_unit_interval_xg"] == 1
    assert report["result"]["failures"] == ["SHOT_PROVIDER_XG_INVALID"]


def test_rejects_unapproved_dataset_before_reading_files(tmp_path: Path) -> None:
    manifest_path = _dataset(tmp_path, xg_values=(0.2,))

    with pytest.raises(
        TierAXGQualificationError,
        match="dataset identity does not match the allowed dataset",
    ):
        qualify(
            data_root=tmp_path,
            manifest_path=manifest_path,
            expected_dataset_version_id="d62b97d6-f39b-5f14-9773-61f57f7b677b",
        )


def test_rejects_manifest_file_checksum_mismatch(tmp_path: Path) -> None:
    manifest_path = _dataset(tmp_path, xg_values=(0.2,))
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][0]["physical_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(TierAXGQualificationError, match="dataset file checksum mismatch"):
        qualify(
            data_root=tmp_path,
            manifest_path=manifest_path,
            expected_dataset_version_id=_DATASET_ID,
        )


def _dataset(tmp_path: Path, *, xg_values: tuple[float, ...]) -> Path:
    files = []
    for index, xg in enumerate(xg_values, start=1):
        match_id = f"01a08230-a2e8-7bbf-80dd-{index:012d}"
        relative_path = (
            f"normalized/events/schema=v1/dataset={_DATASET_ID}/"
            f"competition_id={_COMPETITION_ID}/season_id={_SEASON_ID}/"
            f"match_id={match_id}/events.parquet"
        )
        event_path = tmp_path / relative_path
        event_path.parent.mkdir(parents=True)
        table = pa.table(
            {
                "provider_event_type_name": ["Shot"],
                "canonical_event_type_id": ["shot"],
                "canonical_team_id": ["01a08230-a2e8-7bbf-80dd-100000000001"],
                "canonical_player_id": ["01a08230-a2e8-7bbf-80dd-200000000001"],
                "period": [1],
                "source_x": [101.0],
                "source_y": [40.0],
                "provider_payload_json": [
                    json.dumps(
                        {
                            "play_pattern": {"name": "Regular Play"},
                            "shot": {
                                "outcome": {"name": "Saved"},
                                "statsbomb_xg": xg,
                                "type": {"name": "Open Play"},
                            },
                        }
                    )
                ],
            }
        )
        pq.write_table(table, event_path)
        raw = event_path.read_bytes()
        files.append(
            {
                "logical_sha256": hashlib.sha256(raw).hexdigest(),
                "physical_sha256": hashlib.sha256(raw).hexdigest(),
                "relative_path": relative_path,
                "row_count": 1,
                "size_bytes": len(raw),
            }
        )
    manifest = {
        "contract": "DatasetManifestV1",
        "dataset_name": "events",
        "dataset_version_id": _DATASET_ID,
        "files": files,
        "normalizer_version": "statsbomb-normalizer-v1",
        "schema_sha256": "a" * 64,
        "schema_version": "v1",
        "source_git_sha": "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb",
    }
    manifest_path = tmp_path / "dataset-manifest-v1.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path
