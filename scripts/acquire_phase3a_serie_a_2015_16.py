"""Acquire only the owner-approved, commit-pinned Serie A research resources."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from football.contracts.source import SourceResource, sha256_bytes
from football.ingestion.acquisition import SourceAcquirer
from football.providers.statsbomb import StatsBombOpenDataAdapter
from football.storage.raw import ImmutableRawStore

SOURCE_SHA = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"
MATCH_LIST_SHA256 = "613cd3cc70699ba613cb1b3c27b4c8a01b0b5fa28415e09c928d020208905c7a"
MATCH_COUNT = 380


class PreservedResources:
    def __init__(self, adapter: StatsBombOpenDataAdapter, raw: ImmutableRawStore) -> None:
        self.snapshot = adapter.snapshot
        self.raw = raw

    def fetch(self, resource: SourceResource) -> bytes:
        return self.raw.path_for(self.snapshot, resource).read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    args = parser.parse_args()
    adapter = StatsBombOpenDataAdapter(source_git_sha=SOURCE_SHA)
    assert any(
        (scope.competition_id, scope.season_id, scope.resources)
        == ("12", "27", ("fixtures_results", "lineups", "events"))
        for scope in adapter.capability.supported_scopes
    )
    raw = ImmutableRawStore(args.data_root)
    matches = adapter.matches(competition_id=12, season_id=27)
    match_bytes = adapter.fetch(matches)
    if sha256_bytes(match_bytes) != MATCH_LIST_SHA256:
        raise ValueError("pinned Serie A match-list checksum changed")
    raw.publish(adapter.snapshot, matches, match_bytes)
    rows = json.loads(match_bytes)
    match_ids = [row["match_id"] for row in rows]
    if len(match_ids) != MATCH_COUNT or len(set(match_ids)) != MATCH_COUNT:
        raise ValueError("pinned Serie A match list is not 380 unique matches")
    if any(
        row["competition"]["competition_id"] != 12 or row["season"]["season_id"] != 27
        for row in rows
    ):
        raise ValueError("pinned Serie A match list contains another scope")
    resources = tuple(
        resource
        for match_id in match_ids
        for resource in (adapter.events(match_id=match_id), adapter.lineups(match_id=match_id))
    )

    def fetch_and_preserve(resource: SourceResource) -> str:
        raw.publish(adapter.snapshot, resource, adapter.fetch(resource))
        return resource.path

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_and_preserve, resource) for resource in resources]
        for completed, future in enumerate(as_completed(futures), start=1):
            future.result()
            if completed % 40 == 0 or completed == len(resources):
                print(f"preserved {completed}/{len(resources)}", flush=True)

    result = SourceAcquirer(args.data_root).acquire(
        PreservedResources(adapter, raw), (matches, *resources)
    )
    print(f"manifest={result.manifest_path}", flush=True)
    print(f"manifest_sha256={result.manifest_sha256}", flush=True)
    print(f"resources={len(result.manifest.resources)}", flush=True)


if __name__ == "__main__":
    main()
