"""Stage the verified pinned Serie A source in a separate research data root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acquire_phase3a_serie_a_2015_16 import MATCH_COUNT, MATCH_LIST_SHA256, SOURCE_SHA
from football.contracts.source import SourceManifest, SourceResource, sha256_bytes
from football.ingestion.acquisition import SourceAcquirer
from football.providers.statsbomb import StatsBombOpenDataAdapter
from football.storage.raw import ImmutableRawStore


class VerifiedLocalProvider:
    def __init__(
        self,
        adapter: StatsBombOpenDataAdapter,
        source_root: Path,
        expected_sha256: dict[str, str],
    ) -> None:
        self.snapshot = adapter.snapshot
        self._raw = ImmutableRawStore(source_root)
        self._expected_sha256 = expected_sha256

    def fetch(self, resource: SourceResource) -> bytes:
        expected = self._expected_sha256.get(resource.path)
        if expected is None:
            raise ValueError(f"resource outside approved Serie A staging scope: {resource.path}")
        path = self._raw.path_for(self.snapshot, resource)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"source is not a regular file: {resource.path}")
        payload = path.read_bytes()
        if sha256_bytes(payload) != expected:
            raise ValueError(f"source checksum mismatch: {resource.path}")
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("isolated_root", type=Path)
    parser.add_argument("detail_manifest", type=Path)
    parser.add_argument("catalog_manifest", type=Path)
    args = parser.parse_args()
    if args.source_root.resolve() == args.isolated_root.resolve():
        raise ValueError("isolated root must differ from source root")
    adapter = StatsBombOpenDataAdapter(source_git_sha=SOURCE_SHA)
    details = SourceManifest.from_bytes(args.detail_manifest.read_bytes())
    catalog = SourceManifest.from_bytes(args.catalog_manifest.read_bytes())
    if details.snapshot != adapter.snapshot or catalog.snapshot != adapter.snapshot:
        raise ValueError("source snapshot is not the pinned revision")
    if [item.path for item in catalog.resources] != [adapter.competitions().path]:
        raise ValueError("catalog manifest is not a single competitions resource")
    match_resource = adapter.matches(competition_id=12, season_id=27)
    raw = ImmutableRawStore(args.source_root)
    match_bytes = raw.path_for(adapter.snapshot, match_resource).read_bytes()
    if sha256_bytes(match_bytes) != MATCH_LIST_SHA256:
        raise ValueError("Serie A match list checksum mismatch")
    match_ids = [row["match_id"] for row in json.loads(match_bytes)]
    if len(match_ids) != MATCH_COUNT or len(set(match_ids)) != MATCH_COUNT:
        raise ValueError("Serie A match list is not 380 unique matches")
    detail_resources = tuple(
        resource
        for match_id in match_ids
        for resource in (adapter.events(match_id=match_id), adapter.lineups(match_id=match_id))
    )
    expected_paths = {match_resource.path, *(item.path for item in detail_resources)}
    if {item.path for item in details.resources} != expected_paths:
        raise ValueError("detail manifest includes missing or outside-scope resources")
    expected_sha256 = {item.path: item.sha256 for item in (*catalog.resources, *details.resources)}
    provider = VerifiedLocalProvider(adapter, args.source_root, expected_sha256)
    acquirer = SourceAcquirer(args.isolated_root)
    for label, resources in (
        ("catalog", (adapter.competitions(),)),
        ("matches", (match_resource,)),
        ("details", detail_resources),
    ):
        result = acquirer.acquire(provider, resources)
        print(
            f"{label}: resources={len(result.manifest.resources)} "
            f"manifest_sha256={result.manifest_sha256} path={result.manifest_path}",
            flush=True,
        )


if __name__ == "__main__":
    main()
