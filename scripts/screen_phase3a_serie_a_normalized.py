"""Verify retained-shot xG and mappings in the isolated Serie A dataset."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from acquire_phase3a_serie_a_2015_16 import SOURCE_SHA
from football.contracts.source import sha256_bytes

DATASET_ID = "8bfec1dd-5bf7-5162-b56a-7e63f77b0b88"
MANIFEST_SHA256 = "760592efe5c8d6ce698105003b336f2c2849c00c74b3d6948fbec7c75eb7106d"
COLUMNS = (
    "provider_event_type_name",
    "canonical_event_type_id",
    "canonical_team_id",
    "canonical_player_id",
    "period",
    "source_x",
    "source_y",
    "provider_payload_json",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    args = parser.parse_args()
    root = args.data_root.resolve()
    manifest_path = root / f"manifests/datasets/dataset={DATASET_ID}/dataset-manifest-v1.json"
    payload = manifest_path.read_bytes()
    manifest = json.loads(payload)
    if sha256_bytes(payload) != MANIFEST_SHA256:
        raise ValueError("isolated Serie A dataset manifest hash mismatch")
    if manifest["dataset_version_id"] != DATASET_ID or manifest["source_git_sha"] != SOURCE_SHA:
        raise ValueError("isolated Serie A dataset identity mismatch")
    files = manifest["files"]
    if len(files) != 380:
        raise ValueError("isolated Serie A dataset is not 380 match files")
    counts: Counter[str] = Counter()
    for item in files:
        path = root / item["relative_path"]
        if (
            not path.is_file()
            or path.is_symlink()
            or sha256_bytes(path.read_bytes()) != item["physical_sha256"]
        ):
            raise ValueError(f"dataset file integrity mismatch: {item['relative_path']}")
        table = pq.read_table(path, columns=list(COLUMNS))
        if table.num_rows != item["row_count"]:
            raise ValueError(f"dataset row count mismatch: {item['relative_path']}")
        counts["events"] += table.num_rows
        counts["matches"] += 1
        for row in table.to_pylist():
            if row["provider_event_type_name"] == "Shot":
                _measure_shot(row, counts)
    print(json.dumps(dict(sorted(counts.items())), sort_keys=True))


def _measure_shot(row: dict[str, object], counts: Counter[str]) -> None:
    counts["shots"] += 1
    shot = json.loads(str(row["provider_payload_json"]))["shot"]
    if row["period"] not in (1, 2):
        counts["outside_period_shots"] += 1
        return
    if shot.get("type", {}).get("name") == "Penalty":
        counts["excluded_penalty_shots"] += 1
        return
    counts["retained_shots"] += 1
    xg = shot.get("statsbomb_xg")
    if (
        isinstance(xg, bool)
        or not isinstance(xg, (int, float))
        or not math.isfinite(xg)
        or not 0 <= xg <= 1
    ):
        counts["invalid_retained_xg"] += 1
    if row["canonical_event_type_id"] != "shot":
        counts["missing_shot_mapping"] += 1
    if row["canonical_team_id"] is None:
        counts["missing_team_mapping"] += 1
    if row["canonical_player_id"] is None:
        counts["missing_player_mapping"] += 1
    x, y = row["source_x"], row["source_y"]
    if (
        not isinstance(x, (int, float))
        or not isinstance(y, (int, float))
        or not (0 <= x <= 120 and 0 <= y <= 80)
    ):
        counts["missing_or_invalid_shot_location"] += 1


if __name__ == "__main__":
    main()
