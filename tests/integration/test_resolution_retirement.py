"""Legacy preparation preserves active shared work and old in-flight compatibility rows."""

from pathlib import Path
from uuid import uuid4

import psycopg
from football.product.resolution_cases import case_detail
from football.product.resolution_retirement import legacy_inventory
from football.work.contracts import WorkState
from football.work.storage import WorkRegistry

from tests.integration.test_product_identity_upgrade import _migrate
from tests.integration.test_team_identity_correction import isolated_database, retained, seed


def test_readonly_retirement_inventory_preserves_domain_and_never_authorizes_removal(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        before = retained(c)
        c.commit()
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        report = legacy_inventory(c, Path.cwd())
        assert report["status"] == report["live_retirement"] == "BLOCKED"
        assert not report["phase_35_runtime_cutover"]
        assert not report["code_removal_authorized"]
        assert "NOT_VERIFIED" in report["deployed_scheduler_inventory"]
        assert all(len(item["sha256"]) == 64 for item in report["source_bindings"])
        assert retained(c) == before
        detail = case_detail(c, tmp_path, "stage:13")
        assert detail["legacy_retirement_preparation"]["scope"].startswith("READ_ONLY")


def test_pending_and_running_operator_work_still_has_the_same_shared_owner(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        key = uuid4()
        c.execute(
            "INSERT INTO football.product_sync_runs "
            "(run_id,sync_type,status,worker_id,heartbeat_at,log_path) "
            "VALUES (%s,'FOTMOB_SYNC','QUEUED',%s,clock_timestamp(),'retained.log')",
            (key, str(key)),
        )
        c.commit()
        report = legacy_inventory(c, Path.cwd())
        assert report["domain_queues"]["operator_runs"]["outstanding"] == 1
        assert report["domain_queues"]["operator_runs"]["compatibility_unbound"] == 0
        c.execute("UPDATE football.product_sync_runs SET status='RUNNING' WHERE run_id=%s", (key,))
        c.commit()
        report = legacy_inventory(c, Path.cwd())
        assert report["shared_ownership"]["active_leases"] == 1
        assert report["domain_queues"]["operator_runs"]["running"] == 1
        c.commit()
        assert WorkRegistry(c).state(key) == WorkState.RUNNING
        assert WorkRegistry(c).cancel(key) == WorkState.CANCELLED


def test_upgrade_inventory_retains_unbound_inflight_legacy_runs(tmp_path):
    with isolated_database("202610181900") as url:
        key = uuid4()
        with psycopg.connect(url) as c:
            c.execute(
                "INSERT INTO football.product_sync_runs "
                "(run_id,sync_type,status,worker_id,heartbeat_at,log_path) "
                "VALUES (%s,'FOTMOB_SYNC','RUNNING',%s,clock_timestamp(),'legacy.log')",
                (key, str(key)),
            )
        _migrate(url, "up")
        with psycopg.connect(url) as c:
            report = legacy_inventory(c, Path.cwd())
            assert report["domain_queues"]["operator_runs"]["compatibility_unbound_running"] == 1
            assert report["live_retirement"] == "BLOCKED"
            assert c.execute(
                "SELECT status,log_path FROM football.product_sync_runs WHERE run_id=%s", (key,)
            ).fetchone() == ("RUNNING", "legacy.log")
            assert c.execute(
                "SELECT count(*) FROM football.work_items WHERE work_id=%s", (key,)
            ).fetchone() == (0,)
