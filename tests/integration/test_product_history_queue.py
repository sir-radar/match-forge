from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from football.product.api_football import ApiFootballError
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.provider_history_scopes import run_scopes
from football.product.sync import HISTORY_JOB_LEASE, ProductSync

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def test_history_queue_deduplicates_recovers_and_claims_once() -> None:
    first = 990_001
    second = 990_002
    candidates = [(first, 2099), (first, 2099), (second, 2099)]

    try:
        with psycopg.connect(DATABASE_URL) as connection:
            sync = ProductSync(connection, cast(Any, object()), Path("data"), Path("artifact"))
            sync._enqueue_history_jobs(candidates)
            connection.commit()
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(*)
                    FROM football.product_history_sync_queue
                    WHERE provider_competition_id = ANY(%s)
                    """,
                    ([str(first), str(second)],),
                )
                assert cursor.fetchone() == (2,)
                cursor.execute(
                    """
                    UPDATE football.product_history_sync_queue
                    SET job_status = 'RUNNING', claimed_at = clock_timestamp() - %s
                    WHERE provider_competition_id = %s
                    """,
                    (HISTORY_JOB_LEASE + timedelta(seconds=1), str(first)),
                )
            connection.commit()

            sync._recover_abandoned_history_jobs()
            connection.commit()

        with (
            psycopg.connect(DATABASE_URL) as first_connection,
            psycopg.connect(DATABASE_URL) as second_connection,
        ):
            first_sync = ProductSync(
                first_connection, cast(Any, object()), Path("data"), Path("artifact")
            )
            second_sync = ProductSync(
                second_connection, cast(Any, object()), Path("data"), Path("artifact")
            )
            batch_started_at = datetime.now(UTC)
            first_job = first_sync._claim_history_job(batch_started_at)
            second_job = second_sync._claim_history_job(batch_started_at)
            assert first_job is not None
            assert second_job is not None
            assert first_job[0] != second_job[0]
            assert first_sync._claim_history_job(batch_started_at) is None

            first_sync._retry_history_job(
                first_job[0], first_job[3], ApiFootballError("temporary provider failure")
            )
            second_sync._complete_history_job(second_job[0])

        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_status, next_attempt_at > clock_timestamp(), last_error
                FROM football.product_history_sync_queue
                WHERE job_id = %s
                """,
                (first_job[0],),
            )
            assert cursor.fetchone() == ("PENDING", True, "temporary provider failure")
            cursor.execute(
                "SELECT job_status FROM football.product_history_sync_queue WHERE job_id = %s",
                (second_job[0],),
            )
            assert cursor.fetchone() == ("SUCCEEDED",)
    finally:
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM football.product_history_sync_queue
                WHERE provider_competition_id = ANY(%s)
                """,
                ([str(first), str(second)],),
            )


@pytest.mark.parametrize("operation", ["enqueue", "recover", "attach"])
def test_history_queue_locks_all_existing_keys_in_order(operation: str) -> None:
    first, second, third = 991_101, 991_102, 991_103
    backlog = operation == "attach"
    run_id = uuid4()
    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
        psycopg.connect(DATABASE_URL, autocommit=True) as observer,
    ):
        owner.execute(
            """INSERT INTO football.product_sync_runs (run_id,sync_type,status)
            VALUES (%s,'FOTMOB_SYNC','RUNNING')""",
            (run_id,),
        )
        for league in (first, second, third):
            owner.execute(
                """INSERT INTO football.product_history_sync_queue
                (provider_competition_id,season,job_status)
                VALUES (%s,2099,%s)""",
                (str(league), "SUCCEEDED" if league == third else "PENDING"),
            )
        if operation == "recover":
            owner.execute(
                """UPDATE football.product_history_sync_queue SET job_status='RUNNING',
                claimed_at=clock_timestamp()-interval '2 hours'
                WHERE provider_competition_id=ANY(%s)""",
                ([str(first), str(second)],),
            )
        sync = ProductSync(
            worker,
            cast(Any, object()),
            Path("data"),
            Path("artifact"),
            sync_run_id=run_id if backlog else None,
        )
        worker.execute("SET statement_timeout='5s'")

        def enqueue() -> None:
            with worker.transaction():
                if operation == "recover":
                    sync._recover_abandoned_history_jobs()
                    return
                sync._enqueue_history_jobs(
                    [(third, 2099)] if backlog else [(second, 2099), (first, 2099)]
                )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                with owner.transaction():
                    owner.execute(
                        "SELECT job_id FROM football.product_history_sync_queue "
                        "WHERE provider_competition_id=%s FOR UPDATE",
                        (str(second),),
                    )
                    future = pool.submit(enqueue)
                    deadline = monotonic() + 3
                    while monotonic() < deadline:
                        if observer.execute(
                            "SELECT pg_blocking_pids(%s)", (worker.info.backend_pid,)
                        ).fetchone()[0]:
                            break
                        sleep(0.01)
                    else:
                        future.result(timeout=1)
                        pytest.fail("enqueue did not reach the controlled queue lock")
                    if backlog:
                        with observer.transaction():
                            observer.execute(
                                "SELECT job_id FROM football.product_history_sync_queue "
                                "WHERE provider_competition_id=%s FOR UPDATE NOWAIT",
                                (str(third),),
                            )
                    else:
                        with pytest.raises(psycopg.errors.LockNotAvailable), observer.transaction():
                            observer.execute(
                                "SELECT job_id FROM football.product_history_sync_queue "
                                "WHERE provider_competition_id=%s FOR UPDATE NOWAIT",
                                (str(first),),
                            )
                future.result(timeout=5)
        finally:
            owner.execute(
                "DELETE FROM football.product_history_sync_queue "
                "WHERE provider_competition_id=ANY(%s)",
                ([str(first), str(second), str(third)],),
            )
            owner.execute("DELETE FROM football.product_sync_runs WHERE run_id=%s", (run_id,))


def test_history_enqueue_keeps_requested_priority_and_pending_retry_state() -> None:
    first, second = 991_201, 991_202
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        sync = ProductSync(connection, cast(Any, object()), Path("data"), Path("artifact"))
        try:
            with connection.transaction():
                sync._enqueue_history_jobs([(second, 2099), (first, 2099), (second, 2099)])
            assert connection.execute(
                """SELECT provider_competition_id FROM football.product_history_sync_queue
                WHERE provider_competition_id=ANY(%s) ORDER BY queued_at,job_id""",
                ([str(first), str(second)],),
            ).fetchall() == [(str(second),), (str(first),)]
            connection.execute(
                """UPDATE football.product_history_sync_queue SET attempt_count=2,
                next_attempt_at=clock_timestamp()+interval '1 hour',last_error='retry me'
                WHERE provider_competition_id=%s""",
                (str(first),),
            )
            before = connection.execute(
                """SELECT queued_at,attempt_count,next_attempt_at,last_error
                FROM football.product_history_sync_queue WHERE provider_competition_id=%s""",
                (str(first),),
            ).fetchone()
            with connection.transaction():
                sync._enqueue_history_jobs([(first, 2099)])
            assert (
                connection.execute(
                    """SELECT queued_at,attempt_count,next_attempt_at,last_error
                FROM football.product_history_sync_queue WHERE provider_competition_id=%s""",
                    (str(first),),
                ).fetchone()
                == before
            )
        finally:
            connection.execute(
                "DELETE FROM football.product_history_sync_queue "
                "WHERE provider_competition_id=ANY(%s)",
                ([str(first), str(second)],),
            )


def test_scope_refresh_locks_eligible_rows_in_key_order(tmp_path: Path) -> None:
    league = f"lock-order-{uuid4()}"
    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
        psycopg.connect(DATABASE_URL, autocommit=True) as observer,
    ):
        for season in ("2098", "2097"):
            owner.execute(
                """INSERT INTO football.product_provider_history_scopes
                (provider_code,provider_competition_id,season_label,status)
                VALUES ('pitchapi',%s,%s,'FAILED')""",
                (league, season),
            )
        worker.execute("SET enable_indexscan=off")
        worker.execute("SET enable_bitmapscan=off")
        worker.execute("SET statement_timeout='5s'")
        sync = OperationalProviderSync(worker, tmp_path, provider_code="pitchapi")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                with owner.transaction():
                    owner.execute(
                        """SELECT 1 FROM football.product_provider_history_scopes
                        WHERE provider_code='pitchapi' AND provider_competition_id=%s
                        AND season_label='2098' FOR UPDATE""",
                        (league,),
                    )
                    future = pool.submit(
                        run_scopes,
                        sync,
                        cast(Any, object()),
                        budget=0,
                        competition=league,
                        refresh=True,
                    )
                    deadline = monotonic() + 3
                    while monotonic() < deadline:
                        if observer.execute(
                            "SELECT pg_blocking_pids(%s)", (worker.info.backend_pid,)
                        ).fetchone()[0]:
                            break
                        sleep(0.01)
                    else:
                        future.result(timeout=1)
                        pytest.fail("refresh did not reach the controlled scope lock")
                    with pytest.raises(psycopg.errors.LockNotAvailable), observer.transaction():
                        observer.execute(
                            """SELECT 1 FROM football.product_provider_history_scopes
                            WHERE provider_code='pitchapi' AND provider_competition_id=%s
                            AND season_label='2097' FOR UPDATE NOWAIT""",
                            (league,),
                        )
                assert future.result(timeout=5) == []
        finally:
            owner.execute(
                "DELETE FROM football.product_provider_history_scopes "
                "WHERE provider_code='pitchapi' AND provider_competition_id=%s",
                (league,),
            )


def test_history_enqueue_rejects_reversed_batches_within_one_transaction() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        sync = ProductSync(connection, cast(Any, object()), Path("data"), Path("artifact"))
        with connection.transaction(force_rollback=True):
            sync._enqueue_history_jobs([(991_302, 2099)])
            with pytest.raises(psycopg.Error) as failure, connection.transaction():
                sync._enqueue_history_jobs([(991_301, 2099)])
            assert failure.value.sqlstate == "MFL01"
