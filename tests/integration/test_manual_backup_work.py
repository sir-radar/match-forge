import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from psycopg.errors import UniqueViolation

from tests.integration.test_team_identity_correction import isolated_database


def backup_upgrade(url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["goose", "-dir", "infrastructure/migrations", "up-to", "202611100300"],
        env={**os.environ, "GOOSE_DRIVER": "postgres", "GOOSE_DBSTRING": url},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_manual_backup_upgrade_lets_sync_run_reader_finish() -> None:
    with (
        isolated_database("202611100200") as url,
        psycopg.connect(url) as reader,
        psycopg.connect(url, autocommit=True) as observer,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        # Rehearse the historical applied version whose SQL is absent on main.
        observer.execute(
            "INSERT INTO public.goose_db_version(version_id,is_applied) VALUES (202610220100,true)"
        )
        run_id = uuid4()
        observer.execute(
            "INSERT INTO football.product_sync_runs(run_id,sync_type,status) "
            "VALUES (%s,'FOTMOB_SYNC','QUEUED')",
            (run_id,),
        )
        assert reader.execute(
            "SELECT status FROM football.product_sync_runs WHERE run_id=%s", (run_id,)
        ).fetchone() == ("QUEUED",)
        name = "backup_upgrade_" + uuid4().hex
        upgrade = executor.submit(backup_upgrade, make_conninfo(url, application_name=name))
        try:
            deadline = monotonic() + 5
            while monotonic() < deadline and not upgrade.done():
                blocked = observer.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name=%s AND %s=ANY(pg_blocking_pids(pid)))",
                    (name, reader.info.backend_pid),
                ).fetchone()
                if blocked == (True,):
                    break
                sleep(0.01)
            else:
                pytest.fail("migration did not wait for the sync-run reader")
            # The live lock cycle starts when this reader next accesses work_items.
            reader.execute("LOCK TABLE football.work_items IN ACCESS SHARE MODE NOWAIT")
        finally:
            reader.rollback()
        result = upgrade.result(timeout=30)
        assert result.returncode == 0, result.stderr
        assert observer.execute(
            "SELECT is_applied FROM public.goose_db_version WHERE version_id=202610220100"
        ).fetchone() == (True,)
        assert observer.execute(
            "SELECT status FROM football.product_sync_runs WHERE run_id=%s", (run_id,)
        ).fetchone() == ("QUEUED",)


def test_manual_backup_upgrade_rolls_back_when_work_is_busy() -> None:
    with isolated_database("202611100200") as url, psycopg.connect(url) as reader:
        reader.execute("LOCK TABLE football.work_items IN ACCESS SHARE MODE")
        result = backup_upgrade(url)
        assert result.returncode != 0
        assert "SQLSTATE 55P03" in result.stderr
        reader.execute("LOCK TABLE football.product_sync_runs IN ACCESS SHARE MODE NOWAIT")
        assert reader.execute(
            "SELECT count(*) FROM public.goose_db_version "
            "WHERE version_id=202611100300 AND is_applied"
        ).fetchone() == (0,)
        reader.rollback()
        result = backup_upgrade(url)
        assert result.returncode == 0, result.stderr
        assert reader.execute(
            "SELECT count(*) FROM public.goose_db_version "
            "WHERE version_id=202611100300 AND is_applied"
        ).fetchone() == (1,)


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
