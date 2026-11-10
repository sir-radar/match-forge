import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import UniqueViolation

from tests.integration.test_team_identity_correction import isolated_database


def test_manual_backup_reuses_shared_work_bulk_exclusion_and_live_independence() -> None:
    with isolated_database() as url, psycopg.connect(url, autocommit=True) as connection:
        identity = uuid4()
        connection.execute(
            "INSERT INTO football.product_sync_runs"
            "(run_id,sync_type,status,worker_id,heartbeat_at) "
            "VALUES (%s,'MANUAL_BACKUP','QUEUED',%s,clock_timestamp())",
            (identity, str(identity)),
        )
        assert connection.execute(
            "SELECT work_type,state FROM football.work_items WHERE work_id=%s",
            (identity,),
        ).fetchone() == ("BACKUP", "PENDING")
        with pytest.raises(UniqueViolation):
            connection.execute(
                "INSERT INTO football.product_sync_runs(run_id,sync_type,status) "
                "VALUES (%s,'MANUAL_BACKUP','QUEUED')",
                (uuid4(),),
            )
        live = uuid4()
        connection.execute(
            "INSERT INTO football.product_sync_runs(run_id,sync_type,status) "
            "VALUES (%s,'FOTMOB_SYNC','QUEUED')",
            (live,),
        )
        connection.execute(
            "UPDATE football.product_sync_runs SET status='RUNNING' WHERE run_id=%s", (identity,)
        )
        connection.execute(
            "UPDATE football.product_sync_runs "
            "SET status='CANCELLED',finished_at=clock_timestamp(),error_message='cancelled' "
            "WHERE run_id=%s",
            (identity,),
        )
        assert (
            connection.execute(
                "SELECT state FROM football.work_items WHERE work_id=%s",
                (identity,),
            ).fetchone()[0]
            == "CANCELLED"
        )
        assert (
            connection.execute(
                "SELECT state FROM football.work_items WHERE work_id=%s",
                (live,),
            ).fetchone()[0]
            == "PENDING"
        )
        run_go_contracts(url)
    with isolated_database("202611100200") as previous:
        run_go_contracts(previous)


def run_go_contracts(url: str) -> None:
    __tracebackhide__ = True  # Keep connection credentials out of pytest argument rendering.
    result = subprocess.run(
        ["go", "test", "./internal/app", "-run", "^TestBackupDatabaseContracts$", "-count=1", "-v"],
        cwd=Path(__file__).resolve().parents[2] / "go/api",
        env={**os.environ, "TEST_DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--- PASS: TestBackupDatabaseContracts" in result.stdout
    assert "SKIP" not in result.stdout
