"""Compare Serie A provider match IDs with protected and development scopes only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("isolated_database_url")
    parser.add_argument("normal_database_url")
    parser.add_argument("target_plan", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.target_plan.read_bytes())
    if plan["contract"] != "WalkForwardTargetPlanV1" or plan["target_count"] != 280:
        raise ValueError("target plan is not the expected isolated Serie A research plan")
    target_ids = {
        target["context"]["match_id"] for batch in plan["batches"] for target in batch["targets"]
    }
    with psycopg.connect(args.isolated_database_url) as isolated:
        isolated.execute("SET TRANSACTION READ ONLY")
        candidate = _provider_match_ids(isolated, "12")
    with psycopg.connect(args.normal_database_url) as normal:
        normal.execute("SET TRANSACTION READ ONLY")
        protected = _provider_match_ids(normal, "2")
        development = _provider_match_ids(normal, "11")
    if len(candidate) != 380 or len(protected) != 380 or len(development) != 380:
        raise ValueError("one comparison scope lacks exact 380-match identity coverage")
    if not target_ids <= set(candidate) or len(target_ids) != 280:
        raise ValueError("target plan does not map to 280 Serie A provider matches")
    candidate_ids = set(candidate.values())
    target_provider_ids = {candidate[match_id] for match_id in target_ids}
    protected_ids = set(protected.values())
    development_ids = set(development.values())
    if (
        candidate_ids & protected_ids
        or candidate_ids & development_ids
        or target_provider_ids & protected_ids
        or target_provider_ids & development_ids
    ):
        raise ValueError("Serie A source intersects protected or development identity scope")
    print(
        json.dumps(
            {
                "candidate_all_matches": len(candidate_ids),
                "candidate_targets": len(target_provider_ids),
                "protected_all_matches": len(protected),
                "development_all_matches": len(development),
                "all_match_protected_intersection": len(candidate_ids & protected_ids),
                "all_match_development_intersection": len(candidate_ids & development_ids),
                "target_protected_intersection": len(target_provider_ids & protected_ids),
                "target_development_intersection": len(target_provider_ids & development_ids),
                "identity_key": "statsbomb_open_data provider_match_id",
                "comparison_reads": "match identifiers only; no admissions, scores, or outcomes",
            },
            sort_keys=True,
        )
    )


def _provider_match_ids(connection: psycopg.Connection[Any], competition_id: str) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT DISTINCT match.id::text, observation.provider_match_id
        FROM football.match_observations AS observation
        JOIN football.matches AS match ON match.id = observation.match_id
        JOIN football.season_provider_mappings AS mapping
          ON mapping.season_id = match.season_id
         AND mapping.provider_id = observation.provider_id
        JOIN football.providers AS provider ON provider.id = observation.provider_id
        WHERE provider.code = %s
          AND mapping.provider_competition_id = %s
          AND mapping.provider_season_id = %s
          AND mapping.valid_to IS NULL
        """,
        ("statsbomb_open_data", competition_id, "27"),
    ).fetchall()
    result = {match_id: provider_match_id for match_id, provider_match_id in rows}
    if len(result) != len(rows) or len(set(result.values())) != len(result):
        raise ValueError("match identity mapping is not one-to-one")
    return result


if __name__ == "__main__":
    main()
