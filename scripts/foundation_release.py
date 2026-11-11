"""Read-only P00 release diagnostics; never migrate or start domain work."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
QUERIES = {
    "snapshot": "SELECT transaction_timestamp() AS observed_at, current_database() AS database, "
    "current_setting('server_version') AS version, "
    "current_setting('transaction_read_only') AS read_only, "
    "pg_current_snapshot()::text AS snapshot",
    "migrations": "SELECT version_id FROM (SELECT DISTINCT ON (version_id) "
    "version_id,is_applied FROM public.goose_db_version ORDER BY version_id,id DESC) latest "
    "WHERE is_applied ORDER BY version_id",
    "extensions": "SELECT extname,extversion FROM pg_extension ORDER BY extname",
    "schemas": "SELECT nspname,pg_get_userbyid(nspowner) AS owner FROM pg_namespace "
    "WHERE nspname IN ('public','football') ORDER BY nspname",
    "models": "SELECT registration_sha256,registered_at FROM football.runtime_model_registrations "
    "ORDER BY registered_at",
    "forecast_artifacts": "SELECT model_algorithm_version,model_artifact_sha256,count(*) AS count "
    "FROM football.product_forecasts GROUP BY 1,2 ORDER BY 1,2",
    "routes": "SELECT stage,route FROM football.resolution_stage_settings ORDER BY stage",
    "work": "SELECT work_type,state,count(*) AS count,min(requested_at) AS oldest_requested_at, "
    "count(*) FILTER (WHERE state='RUNNING' AND lease_until<transaction_timestamp()) AS expired "
    "FROM football.work_items GROUP BY 1,2 ORDER BY 1,2",
    "leases": "SELECT work_type,lease_owner,lease_until,heartbeat_at,generation "
    "FROM football.work_items WHERE state='RUNNING' ORDER BY work_type,work_id",
    "sync": "SELECT sync_type,status,count(*) AS count FROM football.product_sync_runs "
    "WHERE status IN ('QUEUED','RUNNING') GROUP BY 1,2 ORDER BY 1,2",
}


def migration_truth(repository: dict[int, str], applied: list[int]) -> dict[str, Any]:
    versions = set(applied) - {0}
    return {
        "repository_checksums": repository,
        "applied": sorted(versions),
        "pending": sorted(repository.keys() - versions),
        "unknown_applied": sorted(versions - repository.keys()),
        "applied_checksums_verified": False,
        "checksum_limitation": "Goose records versions, not historical applied SQL checksums.",
    }


def release_truth(version: dict[str, Any], repository_sha: str) -> str:
    commit = version.get("code_commit_sha")
    if not isinstance(commit, str) or len(commit) != 40:
        return "UNKNOWN"
    if commit != repository_sha:
        return "DIFFERENT_RELEASE"
    if version.get("worktree_state") != "clean":
        return "BUILD_STATE_UNVERIFIED"
    return "MATCHING_CLEAN_BUILD"


def capture() -> dict[str, Any]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    migrations = {
        int(path.name.split("_", 1)[0]): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "infrastructure/migrations").glob("*.sql"))
    }
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
        options=(
            "-c default_transaction_read_only=on -c statement_timeout=20000 -c lock_timeout=1000"
        ),
        application_name="matchforge-foundation-release-readonly",
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        database = {name: connection.execute(query).fetchall() for name, query in QUERIES.items()}
        connection.rollback()
    api: dict[str, Any] = {}
    for path in ("/version", "/healthz", "/readyz", "/v1/admin/sync-runs"):
        request = urllib.request.Request(
            "http://127.0.0.1:8080" + path, headers={"Origin": "http://127.0.0.1:3000"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.load(response)
            api[path] = (
                {"provider_configuration": value.get("provider_configuration")}
                if path.endswith("sync-runs")
                else value
            )
        except (OSError, ValueError):
            api[path] = {"status": "UNAVAILABLE"}
    return {
        "repository_sha": commit,
        "database": database,
        "migration_truth": migration_truth(
            migrations, [r["version_id"] for r in database["migrations"]]
        ),
        "api": api,
        "running_release": release_truth(api["/version"], commit),
        "approved_champion_sha256": hashlib.sha256(
            (
                ROOT / "docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json"
            ).read_bytes()
        ).hexdigest(),
        "operating_mutations": 0,
        "http_consistency": "Separately timed GET observations, outside the database snapshot.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = capture()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    print(json.dumps({"running_release": report["running_release"], "operating_mutations": 0}))


if __name__ == "__main__":
    main()
