"""Verify pinned Serie A raw source integrity and outcome-blind xG coverage."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from acquire_phase3a_serie_a_2015_16 import MATCH_COUNT, MATCH_LIST_SHA256, SOURCE_SHA
from football.contracts.source import ManifestResource, SourceManifest, SourceResource, sha256_bytes
from football.providers.statsbomb import StatsBombOpenDataAdapter
from football.storage.raw import ImmutableRawStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(screen(args.data_root, args.manifest), sort_keys=True))


def screen(data_root: Path, manifest_path: Path) -> dict[str, object]:
    adapter = StatsBombOpenDataAdapter(source_git_sha=SOURCE_SHA)
    raw = ImmutableRawStore(data_root)
    manifest_bytes = manifest_path.read_bytes()
    manifest = SourceManifest.from_bytes(manifest_bytes)
    if manifest.snapshot != adapter.snapshot:
        raise ValueError("source manifest snapshot mismatch")
    match_resource = adapter.matches(competition_id=12, season_id=27)
    resources = {item.path: item for item in manifest.resources}
    match_bytes = _verified_bytes(raw, adapter, resources, match_resource.path)
    if sha256_bytes(match_bytes) != MATCH_LIST_SHA256:
        raise ValueError("match-list checksum mismatch")
    matches = json.loads(match_bytes)
    ids = [match["match_id"] for match in matches]
    if len(ids) != MATCH_COUNT or len(set(ids)) != MATCH_COUNT:
        raise ValueError("match count or match IDs mismatch")
    expected = {match_resource.path}
    for match_id in ids:
        expected.add(adapter.events(match_id=match_id).path)
        expected.add(adapter.lineups(match_id=match_id).path)
    if set(resources) != expected:
        raise ValueError("manifest resource scope does not match Serie A match list")

    counts, invalid_xg = _measure(raw, adapter, resources, ids)
    return {
        "scope": "statsbomb_open_data:12/27",
        "source_git_sha": SOURCE_SHA,
        "match_list_sha256": MATCH_LIST_SHA256,
        "source_manifest_sha256": sha256_bytes(manifest_bytes),
        "resource_count": len(resources),
        "counts": dict(sorted(counts.items())),
        "invalid_retained_shot_xg_count": len(invalid_xg),
        "invalid_retained_shot_xg_sample": invalid_xg[:10],
        "raw_source_coverage_status": "PASS" if not invalid_xg else "FAIL",
        "evaluation_v2_corpus_eligibility": "NOT_DETERMINED",
    }


def _measure(
    raw: ImmutableRawStore,
    adapter: StatsBombOpenDataAdapter,
    resources: dict[str, ManifestResource],
    ids: list[int],
) -> tuple[Counter[str], list[tuple[int, str | None]]]:
    counts: Counter[str] = Counter()
    invalid_xg: list[tuple[int, str | None]] = []
    for match_id in ids:
        lineup_bytes = _verified_bytes(raw, adapter, resources, f"data/lineups/{match_id}.json")
        lineup = json.loads(lineup_bytes)
        if not isinstance(lineup, list) or len(lineup) != 2:
            raise ValueError(f"match {match_id} lacks two lineup teams")
        event_bytes = _verified_bytes(raw, adapter, resources, f"data/events/{match_id}.json")
        events = json.loads(event_bytes)
        if not isinstance(events, list) or not events:
            raise ValueError(f"match {match_id} lacks events")
        counts["events"] += len(events)
        counts["matches"] += 1
        for event in events:
            if event.get("type", {}).get("name") != "Shot":
                continue
            counts["shots"] += 1
            if event.get("period") not in (1, 2):
                counts["excluded_period_shots"] += 1
                continue
            if event.get("shot", {}).get("type", {}).get("name") == "Penalty":
                counts["excluded_penalty_shots"] += 1
                continue
            counts["retained_shots"] += 1
            xg = event.get("shot", {}).get("statsbomb_xg")
            if not _valid_xg(xg):
                invalid_xg.append((match_id, event.get("id")))
    return counts, invalid_xg


def _valid_xg(xg: object) -> bool:
    return (
        not isinstance(xg, bool)
        and isinstance(xg, (int, float))
        and math.isfinite(xg)
        and 0 <= xg <= 1
    )


def _verified_bytes(
    raw: ImmutableRawStore,
    adapter: StatsBombOpenDataAdapter,
    resources: dict[str, ManifestResource],
    resource_path: str,
) -> bytes:
    item = resources[resource_path]
    resource = SourceResource(resource_path)
    if item.raw_path != raw.relative_path(adapter.snapshot, resource):
        raise ValueError(f"raw path mismatch: {resource_path}")
    path = raw.path_for(adapter.snapshot, resource)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"raw resource is not a regular file: {resource_path}")
    payload = path.read_bytes()
    if len(payload) != item.size_bytes or sha256_bytes(payload) != item.sha256:
        raise ValueError(f"raw checksum mismatch: {resource_path}")
    return payload


if __name__ == "__main__":
    main()
