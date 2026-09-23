"""Check isolated Italy kickoff claims against pinned match-list local times."""

from __future__ import annotations

import argparse
import json
from datetime import date, time
from pathlib import Path

import psycopg
from acquire_phase3a_serie_a_2015_16 import MATCH_LIST_SHA256, SOURCE_SHA
from football.contracts.source import sha256_bytes
from football.forecasting.kickoff import TZDATA_VERSION, resolve_local_kickoff

DATASET_ID = "8bfec1dd-5bf7-5162-b56a-7e63f77b0b88"
SNAPSHOT_ID = "01a0c80e-8d2a-7b1b-9516-4a1f82a5e849"
CLAIM_VERSION = "statsbomb-italy-local-kickoff-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_url")
    parser.add_argument("data_root", type=Path)
    args = parser.parse_args()
    match_path = (
        args.data_root
        / f"raw/provider=statsbomb_open_data/snapshot={SOURCE_SHA}/data/matches/12/27.json"
    )
    payload = match_path.read_bytes()
    if sha256_bytes(payload) != MATCH_LIST_SHA256:
        raise ValueError("pinned match-list checksum mismatch")
    source = {str(row["match_id"]): row for row in json.loads(payload)}
    with psycopg.connect(args.database_url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        rows = connection.execute(
            """
            SELECT observation.provider_match_id, observation.match_date,
                   observation.kick_off_local, kickoff.kickoff_at,
                   kickoff.claim_version, kickoff.timezone_name, kickoff.tzdata_version
            FROM football.match_kickoff_claims AS kickoff
            JOIN football.match_lifecycle_claims AS lifecycle
              ON lifecycle.id = kickoff.lifecycle_claim_id
            JOIN football.match_observations AS observation
              ON observation.id = kickoff.match_observation_id
            WHERE lifecycle.dataset_version_id = %s
              AND lifecycle.source_snapshot_id = %s
            """,
            (DATASET_ID, SNAPSHOT_ID),
        ).fetchall()
    if len(rows) != 380 or len({row[0] for row in rows}) != 380:
        raise ValueError("isolated kickoff claims do not cover 380 unique matches")
    kickoffs = set()
    for provider_match_id, match_date, local_time, kickoff_at, version, timezone, tzdata in rows:
        item = source[provider_match_id]
        expected_date = date.fromisoformat(item["match_date"])
        expected_time = time.fromisoformat(item["kick_off"])
        if (match_date, local_time) != (expected_date, expected_time):
            raise ValueError("preserved local kickoff differs from pinned match list")
        if (version, timezone, tzdata) != (CLAIM_VERSION, "Europe/Rome", TZDATA_VERSION):
            raise ValueError("kickoff claim policy differs from approved Italy rule")
        if kickoff_at != resolve_local_kickoff(match_date, local_time, timezone_name=timezone):
            raise ValueError("persisted UTC kickoff differs from pinned tzdata resolution")
        kickoffs.add(kickoff_at)
    print(
        json.dumps(
            {
                "verified_claims": len(rows),
                "distinct_kickoff_batches": len(kickoffs),
                "claim_version": CLAIM_VERSION,
                "timezone": "Europe/Rome",
                "tzdata_version": TZDATA_VERSION,
                "match_list_sha256": MATCH_LIST_SHA256,
                "local_source_identity": "PASS",
                "utc_resolution": "PASS",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
