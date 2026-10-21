"""Metrics cover direct SQL adapters, rollback, retries and bounded exposition."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from football.work.metrics import render_metrics
from psycopg import Connection
from psycopg.rows import dict_row

from tests.integration.test_work_orchestration import (
    claim,
    enqueue,
    expire,
    finish,
    ownership,
)


def metric(connection: Connection[Any], name: str) -> float:
    return float(
        connection.execute(
            "SELECT value FROM football.work_metrics WHERE name=%s AND work_type='NORMALIZATION'",
            (name,),
        ).fetchone()["value"]
    )


def test_metrics_follow_sql_transitions_and_rollback() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection:
        with connection.transaction(force_rollback=True):
            before = metric(connection, "work_pending")
            item = enqueue(connection)
            assert metric(connection, "work_pending") == before + 1
            leased = claim(connection)
            assert leased and leased["work_id"] == item["work_id"]
            assert metric(connection, "work_claim_latency_count") >= 1
            assert metric(connection, "work_claim_latency_sum") >= 0
            finish(connection, leased)
            assert metric(connection, "work_execution_duration_count") >= 1
            assert metric(connection, "work_execution_duration_sum") > 0
            duration, count = (
                connection.execute(
                    "SELECT sum(duration_seconds) AS duration,sum(observation_count) AS count "
                    "FROM football.work_lock_metrics WHERE backend_pid=pg_backend_pid()"
                )
                .fetchone()
                .values()
            )
            assert duration > 0 and count >= 1
        assert metric(connection, "work_pending") == before


def test_expiry_retry_and_fencing_survive_rejected_transaction() -> None:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection,
        connection.transaction(force_rollback=True),
    ):
        enqueue(connection)
        old = claim(connection, lease=timedelta(milliseconds=5))
        expire(connection, old)
        replacement = claim(connection)
        assert metric(connection, "work_retry_count") >= 1
        assert metric(connection, "work_lease_expirations") >= 1
        before = connection.execute(
            "SELECT value FROM football.work_metrics WHERE name='work_fencing_rejections'"
        ).fetchone()["value"]
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), connection.transaction():
            finish(connection, old)
        after = connection.execute(
            "SELECT value FROM football.work_metrics WHERE name='work_fencing_rejections'"
        ).fetchone()["value"]
        assert after == before + 1
        finish(connection, replacement)


def test_export_is_read_only_and_never_labels_identities() -> None:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection,
        connection.transaction(force_rollback=True),
    ):
        connection.execute("SET TRANSACTION READ ONLY")
        output = render_metrics(connection)
        assert 'work_pending{work_type="NORMALIZATION"}' in output
        assert "work_id" not in output and "fixture_id" not in output
        assert "# TYPE work_execution_duration summary" in output
        for name in ("work_deadlocks", "work_fencing_rejections", "work_lock_wait_duration"):
            assert f"# TYPE {name} " in output


@pytest.mark.parametrize(
    ("classification", "state"),
    [("BLOCKED_EXTERNAL", "blocked"), ("NON_RETRYABLE", "failed"), ("RETRYABLE", "retry_wait")],
)
def test_retry_blocked_failed_gauges(classification: str, state: str) -> None:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection,
        connection.transaction(force_rollback=True),
    ):
        enqueue(connection)
        leased = claim(connection)
        before = metric(connection, f"work_{state}")
        connection.execute(
            "SELECT football.fail_work(%s,%s,%s,%s,%s,%s,%s,NULL,NULL)",
            (*ownership(leased), classification, "TEST", "test failure"),
        )
        assert metric(connection, f"work_{state}") == before + 1


def test_deadlock_counter_survives_victim_rollback() -> None:
    keys = [f"metric-test:{uuid4()}", f"metric-test:{uuid4()}"]
    barrier = Barrier(2)

    def contend(index: int) -> str:
        try:
            with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
                connection.execute("SET LOCAL lock_timeout='5s'")
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (keys[index],)
                )
                barrier.wait(timeout=5)
                connection.execute(
                    "SELECT football.acquire_transaction_lock(50,%s)", (keys[1 - index],)
                )
            return "PASS"
        except psycopg.errors.DeadlockDetected:
            return "40P01"

    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as observer:
        before = observer.execute(
            "SELECT value FROM football.work_metrics WHERE name='work_deadlocks'"
        ).fetchone()[0]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(contend, (0, 1)))
        assert sorted(results) == ["40P01", "PASS"]
        after = observer.execute(
            "SELECT value FROM football.work_metrics WHERE name='work_deadlocks'"
        ).fetchone()[0]
        assert after == before + 1


def test_read_only_coordination_keeps_original_behavior() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SELECT football.acquire_transaction_lock(50,%s)", (str(uuid4()),))


def test_cli_exports_prometheus_without_a_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from football.product import cli

    monkeypatch.delenv("API_FOOTBALL_API_KEY", raising=False)
    assert cli.main(["--database-url", os.environ["TEST_DATABASE_URL"], "work-metrics"]) == 0
    output = capsys.readouterr().out
    assert "# TYPE work_pending gauge" in output
    assert 'work_pending{work_type="NORMALIZATION"}' in output
