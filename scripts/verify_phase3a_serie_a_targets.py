"""Build a label-free, isolated Serie A qualification target plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
from football.forecasting.dataset import (
    ImmutableWalkForwardTargetPlanStore,
    PointInTimeMatchDatasetProvider,
    WalkForwardDatasetSpecV1,
)

DATASET_ID = UUID("8bfec1dd-5bf7-5162-b56a-7e63f77b0b88")
SNAPSHOT_ID = UUID("01a0c80e-8d2a-7b1b-9516-4a1f82a5e849")
KNOWLEDGE_CUTOFF = datetime(2026, 9, 22, 7, 52, tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_url")
    parser.add_argument("data_root", type=Path)
    parser.add_argument("quality_policy", type=Path)
    args = parser.parse_args()
    if datetime.now(UTC) < KNOWLEDGE_CUTOFF:
        raise ValueError("research knowledge cutoff is in the future")
    quality_sha = hashlib.sha256(args.quality_policy.read_bytes()).hexdigest()
    spec = WalkForwardDatasetSpecV1(
        dataset_version_id=DATASET_ID,
        source_snapshot_id=SNAPSHOT_ID,
        feature_set_version="phase3a-npxg-for-last10-v1",
        knowledge_cutoff=KNOWLEDGE_CUTOFF,
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256=quality_sha,
        minimum_team_history=10,
        minimum_competition_history=100,
    )
    with (
        psycopg.connect(args.database_url) as connection,
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute("SET TRANSACTION READ ONLY")
        rows = cursor.execute(
            """
                SELECT season.competition_id, season.id
                FROM football.season_provider_mappings AS mapping
                JOIN football.providers AS provider ON provider.id = mapping.provider_id
                JOIN football.seasons AS season ON season.id = mapping.season_id
                WHERE provider.code = %s
                  AND mapping.provider_competition_id = %s
                  AND mapping.provider_season_id = %s
                  AND mapping.valid_to IS NULL
                """,
            ("statsbomb_open_data", "12", "27"),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("isolated 12/27 scope does not resolve to one season")
        competition_id, season_id = rows[0]
        provider_reader = PointInTimeMatchDatasetProvider(connection)
        plan = provider_reader.walk_forward_plan(spec, competition_id, season_id)
        team_only = provider_reader.walk_forward_plan(
            replace(spec, minimum_competition_history=1), competition_id, season_id
        )
    if plan.corpus_match_count != 380 or plan.target_set_sha256 != team_only.target_set_sha256:
        raise ValueError("research target plan differs from frozen team-history rule")
    store = ImmutableWalkForwardTargetPlanStore(
        args.data_root / "reports" / "qualification" / "target-plans"
    )
    published = store.publish(plan)
    plan_path = (
        args.data_root / "reports" / "qualification" / "target-plans" / published.relative_path
    )
    print(
        json.dumps(
            {
                "dataset_version_id": str(DATASET_ID),
                "source_snapshot_id": str(SNAPSHOT_ID),
                "competition_id": str(competition_id),
                "season_id": str(season_id),
                "knowledge_cutoff": KNOWLEDGE_CUTOFF.isoformat(),
                "knowledge_mode": spec.knowledge_mode,
                "minimum_team_history": 10,
                "minimum_competition_history": 100,
                "team_only_target_set_equal": True,
                "corpus_match_count": plan.corpus_match_count,
                "excluded_target_count": plan.excluded_target_count,
                "eligible_target_count": plan.target_count,
                "eligible_batch_count": len(plan.batches),
                "target_set_sha256": plan.target_set_sha256,
                "plan_sha256": plan.sha256,
                "plan_path": str(plan_path),
                "plan_status": published.status,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
