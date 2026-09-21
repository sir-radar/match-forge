#!/usr/bin/env python3
"""Measure StatsBomb shot/xG coverage for one exact normalized event dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

_EVENT_COLUMNS = (
    "provider_event_type_name",
    "canonical_event_type_id",
    "canonical_team_id",
    "canonical_player_id",
    "period",
    "source_x",
    "source_y",
    "provider_payload_json",
)


class TierAXGQualificationError(RuntimeError):
    """The requested dataset cannot be qualified safely."""


def main() -> int:
    arguments = _arguments()
    report = qualify(
        data_root=arguments.data_root.resolve(),
        manifest_path=arguments.manifest.resolve(),
        expected_dataset_version_id=arguments.expected_dataset_version_id,
    )
    payload = _canonical_json_bytes(report) + b"\n"
    output_path = arguments.output.resolve()
    if output_path.exists() and output_path.read_bytes() != payload:
        raise TierAXGQualificationError("output already exists with different bytes")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists():
        output_path.write_bytes(payload)
    print(json.dumps({"output": str(output_path), "sha256": _sha256(payload)}, sort_keys=True))
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-dataset-version-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def qualify(
    *, data_root: Path, manifest_path: Path, expected_dataset_version_id: str
) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = _mapping(json.loads(manifest_bytes), "dataset manifest")
    _validate_manifest_identity(manifest, expected_dataset_version_id)
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise TierAXGQualificationError("dataset manifest has no files")

    measurements = _measure_dataset(data_root, raw_files)
    totals = measurements["totals"]
    match_ids = measurements["match_ids"]
    matches_with_shots = measurements["matches_with_shots"]
    failures = measurements["failures"]
    xg_values = measurements["xg_values"]

    coverage = {
        "event_count": totals["events"],
        "match_count": len(match_ids),
        "matches_with_shots": len(matches_with_shots),
        "matches_without_shots": len(match_ids - matches_with_shots),
        "shot_count": totals["shots"],
        "shots_with_provider_xg": totals["shots_with_provider_xg"],
        "shots_with_valid_unit_interval_xg": totals["shots_with_valid_xg"],
        "shots_missing_provider_xg": totals["shots"] - totals["shots_with_provider_xg"],
        "shots_missing_canonical_event_type": totals["shots_missing_canonical_event_type"],
        "shots_missing_canonical_team": totals["shots_missing_canonical_team"],
        "shots_missing_canonical_player": totals["shots_missing_canonical_player"],
        "shots_missing_source_location": totals["shots_missing_source_location"],
        "shots_with_out_of_bounds_source_location": totals["shots_out_of_bounds"],
        "malformed_shot_payloads": totals["malformed_shot_payloads"],
    }
    result = {
        "coverage": coverage,
        "failures": sorted(failures),
        "semantics": {
            "provider_event_type": "Shot",
            "provider_xg_field": "shot.statsbomb_xg",
            "allowed_xg_interval": [0.0, 1.0],
            "shot_outcomes": dict(sorted(measurements["shot_outcomes"].items())),
            "shot_periods": dict(sorted(measurements["shot_periods"].items())),
            "shot_play_patterns": dict(sorted(measurements["play_patterns"].items())),
            "shot_types": dict(sorted(measurements["shot_types"].items())),
            "xg_max": max(xg_values) if xg_values else None,
            "xg_min": min(xg_values) if xg_values else None,
            "xg_sum": math.fsum(xg_values),
        },
    }
    return {
        "contract": "Phase1CStatsBombXGCoverageV1",
        "status": "PASS" if not failures else "FAIL",
        "dataset": {
            "canonical_competition_id": measurements["canonical_competition_id"],
            "canonical_season_id": measurements["canonical_season_id"],
            "dataset_manifest_sha256": _sha256(manifest_bytes),
            "dataset_name": _string(manifest, "dataset_name"),
            "dataset_version_id": expected_dataset_version_id,
            "file_count": len(raw_files),
            "normalizer_version": _string(manifest, "normalizer_version"),
            "schema_sha256": _string(manifest, "schema_sha256"),
            "schema_version": _string(manifest, "schema_version"),
            "source_git_sha": _string(manifest, "source_git_sha"),
        },
        "result": result,
        "reproducibility": {
            "code_git_sha": _git_sha(),
            "python_version": sys.version.split()[0],
            "script_sha256": _sha256(Path(__file__).read_bytes()),
        },
    }


def _measure_dataset(data_root: Path, raw_files: list[object]) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = {
        "totals": Counter(),
        "shot_types": Counter(),
        "shot_outcomes": Counter(),
        "shot_periods": Counter(),
        "play_patterns": Counter(),
    }
    match_ids: set[str] = set()
    matches_with_shots: set[str] = set()
    competition_ids: set[str] = set()
    season_ids: set[str] = set()
    xg_values: list[float] = []
    failures: set[str] = set()
    for raw_file in raw_files:
        _measure_dataset_file(
            data_root=data_root,
            raw_file=raw_file,
            counters=counters,
            match_ids=match_ids,
            matches_with_shots=matches_with_shots,
            competition_ids=competition_ids,
            season_ids=season_ids,
            xg_values=xg_values,
            failures=failures,
        )
    if len(competition_ids) != 1 or len(season_ids) != 1:
        raise TierAXGQualificationError("dataset manifest spans multiple canonical scopes")
    if len(match_ids) != len(raw_files):
        raise TierAXGQualificationError("dataset manifest does not contain one file per match")
    if len(matches_with_shots) != len(match_ids):
        failures.add("MATCH_WITHOUT_SHOT")
    if counters["totals"]["shots"] == 0:
        failures.add("NO_SHOTS")
    return {
        **counters,
        "canonical_competition_id": next(iter(competition_ids)),
        "canonical_season_id": next(iter(season_ids)),
        "failures": failures,
        "match_ids": match_ids,
        "matches_with_shots": matches_with_shots,
        "xg_values": xg_values,
    }


def _measure_dataset_file(
    *,
    data_root: Path,
    raw_file: object,
    counters: Mapping[str, Counter[str]],
    match_ids: set[str],
    matches_with_shots: set[str],
    competition_ids: set[str],
    season_ids: set[str],
    xg_values: list[float],
    failures: set[str],
) -> None:
    file_entry = _mapping(raw_file, "dataset file")
    relative_path = _string(file_entry, "relative_path")
    event_path = _safe_dataset_path(data_root, relative_path)
    if _sha256(event_path.read_bytes()) != _string(file_entry, "physical_sha256"):
        raise TierAXGQualificationError(f"dataset file checksum mismatch: {relative_path}")
    table = pq.read_table(event_path, columns=list(_EVENT_COLUMNS))
    if table.num_rows != _integer(file_entry, "row_count"):
        raise TierAXGQualificationError(f"dataset file row-count mismatch: {relative_path}")
    match_id, competition_id, season_id = _path_scope(relative_path)
    if match_id in match_ids:
        raise TierAXGQualificationError(f"duplicate match file: {match_id}")
    match_ids.add(match_id)
    competition_ids.add(competition_id)
    season_ids.add(season_id)
    counters["totals"]["events"] += table.num_rows
    for row in table.to_pylist():
        if row["provider_event_type_name"] == "Shot":
            _measure_shot(
                row=row,
                match_id=match_id,
                matches_with_shots=matches_with_shots,
                totals=counters["totals"],
                shot_types=counters["shot_types"],
                shot_outcomes=counters["shot_outcomes"],
                shot_periods=counters["shot_periods"],
                play_patterns=counters["play_patterns"],
                xg_values=xg_values,
                failures=failures,
            )


def _validate_manifest_identity(
    manifest: Mapping[str, object], expected_dataset_version_id: str
) -> None:
    if manifest.get("contract") != "DatasetManifestV1":
        raise TierAXGQualificationError("unsupported dataset manifest contract")
    if manifest.get("dataset_name") != "events":
        raise TierAXGQualificationError("qualification requires an events dataset")
    actual_dataset_version_id = _string(manifest, "dataset_version_id")
    if actual_dataset_version_id != expected_dataset_version_id:
        raise TierAXGQualificationError("dataset identity does not match the allowed dataset")


def _measure_shot(
    *,
    row: Mapping[str, Any],
    match_id: str,
    matches_with_shots: set[str],
    totals: Counter[str],
    shot_types: Counter[str],
    shot_outcomes: Counter[str],
    shot_periods: Counter[str],
    play_patterns: Counter[str],
    xg_values: list[float],
    failures: set[str],
) -> None:
    totals["shots"] += 1
    matches_with_shots.add(match_id)
    shot_periods[str(row["period"])] += 1
    if row["period"] not in (1, 2):
        failures.add("SHOT_OUTSIDE_REGULATION_PERIOD")
    if row["canonical_event_type_id"] != "shot":
        totals["shots_missing_canonical_event_type"] += 1
        failures.add("SHOT_CANONICAL_EVENT_TYPE_MISSING")
    if row["canonical_team_id"] is None:
        totals["shots_missing_canonical_team"] += 1
        failures.add("SHOT_CANONICAL_TEAM_MISSING")
    if row["canonical_player_id"] is None:
        totals["shots_missing_canonical_player"] += 1
        failures.add("SHOT_CANONICAL_PLAYER_MISSING")
    source_x, source_y = row["source_x"], row["source_y"]
    if source_x is None or source_y is None:
        totals["shots_missing_source_location"] += 1
        failures.add("SHOT_SOURCE_LOCATION_MISSING")
    elif not (0.0 <= source_x <= 120.0 and 0.0 <= source_y <= 80.0):
        totals["shots_out_of_bounds"] += 1
        failures.add("SHOT_SOURCE_LOCATION_OUT_OF_BOUNDS")
    try:
        payload = _mapping(json.loads(row["provider_payload_json"]), "provider shot payload")
        shot = _mapping(payload.get("shot"), "provider shot")
    except (json.JSONDecodeError, TypeError, TierAXGQualificationError):
        totals["malformed_shot_payloads"] += 1
        failures.add("SHOT_PAYLOAD_MALFORMED")
        return
    shot_types[_nested_name(shot, "type")] += 1
    shot_outcomes[_nested_name(shot, "outcome")] += 1
    play_patterns[_nested_name(payload, "play_pattern")] += 1
    if "statsbomb_xg" not in shot:
        failures.add("SHOT_PROVIDER_XG_MISSING")
        return
    totals["shots_with_provider_xg"] += 1
    xg = shot["statsbomb_xg"]
    if (
        isinstance(xg, bool)
        or not isinstance(xg, (int, float))
        or not math.isfinite(xg)
        or not 0.0 <= xg <= 1.0
    ):
        failures.add("SHOT_PROVIDER_XG_INVALID")
        return
    totals["shots_with_valid_xg"] += 1
    xg_values.append(float(xg))


def _safe_dataset_path(data_root: Path, relative_path: str) -> Path:
    candidate = (data_root / relative_path).resolve()
    try:
        candidate.relative_to(data_root.resolve())
    except ValueError as error:
        raise TierAXGQualificationError("dataset file escapes the data root") from error
    if not candidate.is_file():
        raise TierAXGQualificationError(f"dataset file is missing: {relative_path}")
    return candidate


def _path_scope(relative_path: str) -> tuple[str, str, str]:
    values: dict[str, str] = {}
    for part in Path(relative_path).parts:
        if "=" in part:
            key, value = part.split("=", 1)
            values[key] = value
    try:
        return values["match_id"], values["competition_id"], values["season_id"]
    except KeyError as error:
        raise TierAXGQualificationError("dataset file path has incomplete scope") from error


def _nested_name(value: Mapping[str, object], field: str) -> str:
    nested = _mapping(value.get(field), field)
    return _string(nested, "name")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TierAXGQualificationError(f"{field} must be an object")
    return value


def _string(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise TierAXGQualificationError(f"{field} must be a non-empty string")
    return item


def _integer(value: Mapping[str, object], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise TierAXGQualificationError(f"{field} must be a non-negative integer")
    return item


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_sha() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
