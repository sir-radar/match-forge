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
from football.product.history_worker import HistorySyncWorker
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.provider_history_scopes import run_scopes
from football.product.sync import HISTORY_JOB_LEASE, ProductSync

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def test_history_queue_deduplicates_recovers_and_claims_once(tmp_path: Path) -> None:
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
            psycopg.connect(DATABASE_URL) as observer,
        ):
            first_sync = HistorySyncWorker(
                first_connection, cast(Any, object()), tmp_path / "first", Path("artifact")
            )
            second_sync = HistorySyncWorker(
                second_connection, cast(Any, object()), tmp_path / "second", Path("artifact")
            )
            batch_started_at = datetime.now(UTC)
            first_job = first_sync._claim_history_job(batch_started_at)
            second_job = second_sync._claim_history_job(batch_started_at)
            assert first_job is not None
            assert second_job is not None
            assert first_job[0] != second_job[0]
            assert (
                HistorySyncWorker(
                    observer, cast(Any, object()), tmp_path / "observer", Path("artifact")
                )._claim_history_job(batch_started_at)
                is None
            )

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


@pytest.mark.parametrize("attempts", [0, 2, 1000])
def test_history_request_registration_preserves_detail_and_cooldown(attempts: int) -> None:
    from football.product.history_work import register_history_request

    league = str(uuid4().int % 2_000_000_000)
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue
            (provider_competition_id,season,attempt_count,next_attempt_at,last_error)
            VALUES (%s,2099,%s,clock_timestamp()+interval '1 hour','existing retry')
            RETURNING job_id,to_jsonb(product_history_sync_queue)""",
            (league, attempts),
        ).fetchone()
        assert job is not None
        identity = None
        try:
            identity = register_history_request(connection, job[0])
            assert identity is not None
            assert register_history_request(connection, job[0]) == identity
            work = connection.execute(
                """SELECT work_type,state,attempt_count,max_attempts,available_at,
                retry_base_seconds,retry_cap_seconds,lease_retry_delay_seconds
                FROM football.work_items WHERE work_id=%s""",
                (identity,),
            ).fetchone()
            assert work is not None
            due = connection.execute(
                "SELECT next_attempt_at FROM football.product_history_sync_queue WHERE job_id=%s",
                (job[0],),
            ).fetchone()[0]
            assert work == (
                "HISTORICAL_ACQUISITION",
                "PENDING",
                0,
                2**31 - 1 - attempts,
                due,
                min(60 * 2 ** min(attempts, 12), 3600),
                3600,
                0,
            )
            assert connection.execute(
                "SELECT to_jsonb(q) FROM football.product_history_sync_queue q WHERE job_id=%s",
                (job[0],),
            ).fetchone() == (job[1],)
            assert connection.execute(
                "SELECT attempt_offset FROM football.product_history_work WHERE work_id=%s",
                (identity,),
            ).fetchone() == (attempts,)
        finally:
            if identity is not None:
                from football.work.storage import WorkRegistry

                WorkRegistry(connection).cancel(identity)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job[0],)
            )


@pytest.mark.parametrize("status", ["RUNNING", "SUCCEEDED", "FAILED"])
def test_history_registration_does_not_adopt_legacy_ownership_or_terminal_jobs(status: str) -> None:
    from football.product.history_work import register_history_request

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue
            (provider_competition_id,season,job_status,claimed_at)
            VALUES (%s,2099,%s,clock_timestamp()) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000), status),
        ).fetchone()[0]
        before = connection.execute("SELECT count(*) FROM football.work_items").fetchone()
        try:
            assert register_history_request(connection, job) is None
            assert (
                connection.execute("SELECT count(*) FROM football.work_items").fetchone() == before
            )
        finally:
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_history_registration_rolls_back_new_work_if_the_queue_row_is_busy() -> None:
    from football.product.history_work import register_history_request

    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
    ):
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        before = worker.execute("SELECT count(*) FROM football.work_items").fetchone()
        try:
            with owner.transaction():
                owner.execute(
                    "SELECT 1 FROM football.product_history_sync_queue WHERE job_id=%s FOR UPDATE",
                    (job,),
                )
                assert register_history_request(worker, job) is None
            assert worker.execute("SELECT count(*) FROM football.work_items").fetchone() == before
            assert worker.execute(
                "SELECT count(*) FROM football.product_history_work WHERE job_id=%s", (job,)
            ).fetchone() == (0,)
        finally:
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


def test_concurrent_history_registration_retains_one_immutable_request() -> None:
    from football.product.history_work import register_history_request
    from football.work.storage import WorkRegistry

    with psycopg.connect(DATABASE_URL, autocommit=True) as owner:
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]

        def register() -> Any:
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                connection.execute("SET statement_timeout='5s'")
                return register_history_request(connection, job)

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = [
                    future.result(timeout=10)
                    for future in [pool.submit(register), pool.submit(register)]
                ]
            assert results[0] is not None and results[0] == results[1]
            assert owner.execute(
                "SELECT count(*) FROM football.product_history_work WHERE job_id=%s", (job,)
            ).fetchone() == (1,)
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), owner.transaction():
                owner.execute(
                    "UPDATE football.product_history_work SET attempt_offset=1 WHERE job_id=%s",
                    (job,),
                )
            WorkRegistry(owner).cancel(results[0])
        finally:
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


def test_changed_history_request_rolls_back_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football.product.history_work import register_history_request
    from football.work.storage import WorkRegistry

    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
    ):
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        original = WorkRegistry.enqueue

        def change_after_enqueue(self: Any, request: Any) -> Any:
            result = original(self, request)
            owner.execute(
                """UPDATE football.product_history_sync_queue
                SET next_attempt_at=clock_timestamp()+interval '2 hours' WHERE job_id=%s""",
                (job,),
            )
            return result

        monkeypatch.setattr(WorkRegistry, "enqueue", change_after_enqueue)
        before = worker.execute("SELECT count(*) FROM football.work_items").fetchone()
        try:
            assert register_history_request(worker, job) is None
            assert worker.execute("SELECT count(*) FROM football.work_items").fetchone() == before
            assert worker.execute(
                "SELECT count(*) FROM football.product_history_work WHERE job_id=%s", (job,)
            ).fetchone() == (0,)
        finally:
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


def test_registered_history_request_does_not_reclaim_active_legacy_ownership() -> None:
    from football.product.history_work import register_history_request
    from football.work.storage import WorkRegistry

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        identity = None
        try:
            identity = register_history_request(connection, job)
            assert identity is not None
            connection.execute(
                """UPDATE football.product_history_sync_queue SET job_status='RUNNING',
                claimed_at=clock_timestamp() WHERE job_id=%s""",
                (job,),
            )
            assert register_history_request(connection, job) is None
        finally:
            if identity is not None:
                WorkRegistry(connection).cancel(identity)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_competition_id", "changed-competition"),
        ("season", 2100),
        ("attempt_count", 7),
    ],
)
def test_history_registration_rejects_changed_inputs_for_the_same_request(
    field: str, value: Any
) -> None:
    from football.product.history_work import register_history_request
    from football.work.storage import WorkConflict, WorkRegistry
    from psycopg import sql

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        identity = None
        try:
            identity = register_history_request(connection, job)
            assert identity is not None
            connection.execute(
                sql.SQL(
                    "UPDATE football.product_history_sync_queue SET {}=%s WHERE job_id=%s"
                ).format(sql.Identifier(field)),
                (value, job),
            )
            with pytest.raises(WorkConflict, match="history request"):
                register_history_request(connection, job)
        finally:
            if identity is not None:
                WorkRegistry(connection).cancel(identity)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_requeued_history_request_keeps_its_previous_work_identity_immutable() -> None:
    from football.product.history_work import register_history_request
    from football.work.storage import WorkRegistry

    league = uuid4().int % 2_000_000_000
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(league),),
        ).fetchone()[0]
        old = new = None
        try:
            old = register_history_request(connection, job)
            assert old is not None
            WorkRegistry(connection).cancel(old)
            connection.execute(
                "UPDATE football.product_history_sync_queue "
                "SET job_status='SUCCEEDED' WHERE job_id=%s",
                (job,),
            )
            sync = ProductSync(connection, cast(Any, object()), Path("data"), Path("artifact"))
            with connection.transaction():
                sync._enqueue_history_jobs([(league, 2099)])
            new = register_history_request(connection, job)
            assert new is not None and new != old
            assert connection.execute(
                "SELECT count(*) FROM football.product_history_work WHERE job_id=%s", (job,)
            ).fetchone() == (2,)
            assert connection.execute(
                "SELECT state FROM football.work_items WHERE work_id=%s", (old,)
            ).fetchone() == ("CANCELLED",)
        finally:
            if new is not None:
                WorkRegistry(connection).cancel(new)
            if old is not None:
                WorkRegistry(connection).cancel(old)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_history_registration_rejects_exhausted_integer_attempt_capacity() -> None:
    from football.product.history_work import register_history_request
    from football.work.contracts import WorkContractError

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue
            (provider_competition_id,season,attempt_count)
            VALUES (%s,2099,2147483647) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        before = connection.execute("SELECT count(*) FROM football.work_items").fetchone()
        try:
            with pytest.raises(WorkContractError, match="integer capacity"):
                register_history_request(connection, job)
            assert (
                connection.execute("SELECT count(*) FROM football.work_items").fetchone() == before
            )
        finally:
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_history_registration_rejects_work_claimed_before_association(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football.product.history_work import register_history_request
    from football.work.contracts import WorkType
    from football.work.storage import WorkConflict, WorkRegistry

    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
    ):
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        original = WorkRegistry.enqueue
        identities = []

        def claim_before_binding(self: Any, request: Any) -> Any:
            identity = original(WorkRegistry(owner), request)
            identities.append(identity)
            assert (
                WorkRegistry(owner).claim(
                    "existing-owner",
                    timedelta(minutes=30),
                    (WorkType.HISTORICAL_ACQUISITION,),
                    work_ids=(identity,),
                )
                is not None
            )
            return original(self, request)

        monkeypatch.setattr(WorkRegistry, "enqueue", claim_before_binding)
        try:
            with pytest.raises(WorkConflict, match="unclaimed"):
                register_history_request(worker, job)
            assert owner.execute(
                "SELECT count(*) FROM football.product_history_work WHERE job_id=%s",
                (job,),
            ).fetchone() == (0,)
            assert owner.execute(
                "SELECT state FROM football.work_items WHERE work_id=%s",
                (identities[0],),
            ).fetchone() == ("RUNNING",)
        finally:
            for identity in identities:
                WorkRegistry(owner).cancel(identity)
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


def test_history_registration_locks_existing_work_before_domain_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football.product.history_work import register_history_request
    from football.work.storage import WorkRegistry

    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
        psycopg.connect(DATABASE_URL, autocommit=True) as observer,
    ):
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        original = WorkRegistry.enqueue
        identities = []

        def hold_work_after_enqueue(self: Any, request: Any) -> Any:
            identity = original(WorkRegistry(owner), request)
            identities.append(identity)
            result = original(self, request)
            owner.execute("BEGIN")
            owner.execute(
                "SELECT work_id FROM football.work_items WHERE work_id=%s FOR NO KEY UPDATE NOWAIT",
                (identity,),
            )
            return result

        monkeypatch.setattr(WorkRegistry, "enqueue", hold_work_after_enqueue)
        worker.execute("SET statement_timeout='5s'")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(register_history_request, worker, job)
                try:
                    deadline = monotonic() + 3
                    while monotonic() < deadline:
                        if observer.execute(
                            "SELECT pg_blocking_pids(%s)",
                            (worker.info.backend_pid,),
                        ).fetchone()[0]:
                            break
                        if future.done():
                            future.result()
                            pytest.fail(
                                "registration did not lock shared work before domain detail"
                            )
                        sleep(0.01)
                    else:
                        pytest.fail("registration did not reach the controlled work-row lock")
                    with observer.transaction():
                        observer.execute(
                            "SELECT job_id FROM football.product_history_sync_queue "
                            "WHERE job_id=%s FOR UPDATE NOWAIT",
                            (job,),
                        )
                finally:
                    owner.rollback()
                assert future.result(timeout=5) == identities[0]
        finally:
            owner.rollback()
            for identity in identities:
                WorkRegistry(owner).cancel(identity)
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


def test_shared_history_claim_and_completion_drive_legacy_detail_atomically() -> None:
    from football.product.history_work import claim_history_request, complete_history_request
    from football.work.contracts import WorkState
    from football.work.storage import WorkRegistry
    from psycopg.pq import TransactionStatus

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        claim = None
        try:
            claim = claim_history_request(
                connection, job, "history-worker", before, lease_duration=timedelta(minutes=30)
            )
            assert claim is not None
            assert connection.info.transaction_status == TransactionStatus.IDLE
            assert WorkRegistry(connection).state(claim.work_id) == WorkState.RUNNING
            assert connection.execute(
                "SELECT job_status,attempt_count,claimed_at IS NOT NULL "
                "FROM football.product_history_sync_queue WHERE job_id=%s",
                (job,),
            ).fetchone() == ("RUNNING", 1, True)
            complete_history_request(connection, claim, result_hash="a" * 64)
            assert WorkRegistry(connection).state(claim.work_id) == WorkState.SUCCEEDED
            assert connection.execute(
                "SELECT job_status,finished_at IS NOT NULL,claimed_at "
                "FROM football.product_history_sync_queue WHERE job_id=%s",
                (job,),
            ).fetchone() == ("SUCCEEDED", True, None)
            assert connection.info.transaction_status == TransactionStatus.IDLE
            completed = connection.execute(
                "SELECT to_jsonb(q) FROM football.product_history_sync_queue q WHERE job_id=%s",
                (job,),
            ).fetchone()
            next_batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            assert (
                claim_history_request(
                    connection,
                    job,
                    "repeat-worker",
                    next_batch,
                    lease_duration=timedelta(minutes=30),
                )
                is None
            )
            assert (
                connection.execute(
                    "SELECT to_jsonb(q) FROM football.product_history_sync_queue q WHERE job_id=%s",
                    (job,),
                ).fetchone()
                == completed
            )
        finally:
            if claim is not None:
                WorkRegistry(connection).cancel(claim.work_id)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_shared_history_failure_keeps_domain_retry_deadline_equal_to_work() -> None:
    from football.product.history_work import claim_history_request, fail_history_request
    from football.work.contracts import RetryClassification, WorkState
    from football.work.storage import WorkRegistry

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue
            (provider_competition_id,season,attempt_count)
            VALUES (%s,2099,2) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        claim = None
        try:
            claim = claim_history_request(
                connection, job, "history-worker", batch, lease_duration=timedelta(minutes=30)
            )
            assert claim is not None
            before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            assert (
                fail_history_request(
                    connection,
                    claim,
                    RetryClassification.RETRYABLE,
                    error_code="PROVIDER_TEMPORARY",
                    error_message="retry after provider failure",
                )
                == WorkState.RETRY_WAIT
            )
            row = connection.execute(
                """SELECT queue.job_status,queue.attempt_count,queue.next_attempt_at,
                work.available_at,queue.last_error FROM football.product_history_sync_queue queue
                JOIN football.product_history_work binding USING (job_id,queued_at)
                JOIN football.work_items work USING (work_id) WHERE queue.job_id=%s""",
                (job,),
            ).fetchone()
            assert row is not None
            assert row[0:2] == ("PENDING", 3)
            assert row[2] == row[3] and row[2] >= before + timedelta(seconds=240)
            assert row[4] == "retry after provider failure"
            next_batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            assert (
                claim_history_request(
                    connection,
                    job,
                    "early-worker",
                    next_batch,
                    lease_duration=timedelta(minutes=30),
                )
                is None
            )
        finally:
            if claim is not None:
                WorkRegistry(connection).cancel(claim.work_id)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


@pytest.mark.parametrize(
    ("owner_key", "lease"),
    [
        ("", timedelta(minutes=30)),
        ("worker", timedelta()),
        ("worker", timedelta(seconds=-1)),
    ],
)
def test_invalid_shared_history_claim_does_not_register_work(
    owner_key: str, lease: timedelta
) -> None:
    from football.product.history_work import claim_history_request
    from football.work.contracts import WorkContractError

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        before = connection.execute("SELECT count(*) FROM football.work_items").fetchone()
        try:
            with pytest.raises(WorkContractError):
                claim_history_request(connection, job, owner_key, batch, lease_duration=lease)
            assert (
                connection.execute("SELECT count(*) FROM football.work_items").fetchone() == before
            )
            assert connection.execute(
                "SELECT count(*) FROM football.product_history_work WHERE job_id=%s", (job,)
            ).fetchone() == (0,)
        finally:
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_busy_history_detail_does_not_consume_a_shared_attempt() -> None:
    from football.product.history_work import claim_history_request, register_history_request
    from football.work.storage import WorkRegistry

    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
    ):
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        identity = register_history_request(owner, job)
        assert identity is not None
        batch = owner.execute("SELECT clock_timestamp()").fetchone()[0]
        try:
            with owner.transaction():
                owner.execute(
                    "SELECT 1 FROM football.product_history_sync_queue WHERE job_id=%s FOR UPDATE",
                    (job,),
                )
                assert (
                    claim_history_request(
                        worker, job, "worker", batch, lease_duration=timedelta(minutes=30)
                    )
                    is None
                )
                assert worker.execute(
                    "SELECT state,attempt_count,lease_token FROM football.work_items "
                    "WHERE work_id=%s",
                    (identity,),
                ).fetchone() == ("PENDING", 0, None)
                with worker.transaction():
                    worker.execute(
                        "SELECT 1 FROM football.work_items WHERE work_id=%s FOR UPDATE NOWAIT",
                        (identity,),
                    )
        finally:
            WorkRegistry(owner).cancel(identity)
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


def test_expired_history_worker_cannot_complete_or_fail_its_replacement() -> None:
    from football.product.history_work import (
        claim_history_request,
        complete_history_request,
        fail_history_request,
    )
    from football.work.contracts import RetryClassification
    from football.work.storage import WorkLeaseLost, WorkRegistry

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        first = None
        try:
            first = claim_history_request(
                connection, job, "expired", batch, lease_duration=timedelta(milliseconds=30)
            )
            assert first is not None
            connection.execute(
                "SELECT pg_sleep(GREATEST(0,extract(epoch FROM "
                "(%s::timestamptz-clock_timestamp())))+0.005)",
                (first.lease_until,),
            )
            next_batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            replacement = claim_history_request(
                connection, job, "replacement", next_batch, lease_duration=timedelta(minutes=30)
            )
            assert replacement is not None and replacement.generation == first.generation + 1
            before = connection.execute(
                "SELECT to_jsonb(q) FROM football.product_history_sync_queue q WHERE job_id=%s",
                (job,),
            ).fetchone()
            with pytest.raises(WorkLeaseLost):
                complete_history_request(connection, first, result_hash="a" * 64)
            with pytest.raises(WorkLeaseLost):
                fail_history_request(
                    connection,
                    first,
                    RetryClassification.NON_RETRYABLE,
                    error_code="STALE",
                    error_message="Must not affect replacement",
                )
            assert (
                connection.execute(
                    "SELECT to_jsonb(q) FROM football.product_history_sync_queue q WHERE job_id=%s",
                    (job,),
                ).fetchone()
                == before
            )
            complete_history_request(connection, replacement, result_hash="b" * 64)
        finally:
            if first is not None:
                WorkRegistry(connection).cancel(first.work_id)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_history_transition_expiring_while_detail_is_locked_rolls_back(operation: str) -> None:
    from football.product.history_work import (
        claim_history_request,
        complete_history_request,
        fail_history_request,
    )
    from football.work.contracts import RetryClassification
    from football.work.storage import WorkLeaseLost, WorkRegistry

    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
        psycopg.connect(DATABASE_URL, autocommit=True) as observer,
    ):
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        batch = owner.execute("SELECT clock_timestamp()").fetchone()[0]
        claim = claim_history_request(
            worker, job, "worker", batch, lease_duration=timedelta(seconds=1)
        )
        assert claim is not None
        worker.execute("SET statement_timeout='5s'")
        before = owner.execute(
            "SELECT to_jsonb(q) FROM football.product_history_sync_queue q WHERE job_id=%s", (job,)
        ).fetchone()

        def transition() -> None:
            if operation == "complete":
                complete_history_request(worker, claim, result_hash="a" * 64)
            else:
                fail_history_request(
                    worker,
                    claim,
                    RetryClassification.NON_RETRYABLE,
                    error_code="TEST_FAILURE",
                    error_message="Owned failure",
                )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                with owner.transaction():
                    owner.execute(
                        "SELECT job_id FROM football.product_history_sync_queue "
                        "WHERE job_id=%s FOR UPDATE",
                        (job,),
                    )
                    future = pool.submit(transition)
                    deadline = monotonic() + 3
                    while monotonic() < deadline:
                        if observer.execute(
                            "SELECT pg_blocking_pids(%s)", (worker.info.backend_pid,)
                        ).fetchone()[0]:
                            break
                        if future.done():
                            future.result()
                            pytest.fail("transition did not reach its controlled detail lock")
                        sleep(0.01)
                    else:
                        pytest.fail("transition did not block on detail")
                    observer.execute(
                        "SELECT pg_sleep(GREATEST(0,extract(epoch FROM "
                        "(%s::timestamptz-clock_timestamp())))+0.005)",
                        (claim.lease_until,),
                    )
                with pytest.raises(WorkLeaseLost):
                    future.result(timeout=5)
            assert (
                owner.execute(
                    "SELECT to_jsonb(q) FROM football.product_history_sync_queue q WHERE job_id=%s",
                    (job,),
                ).fetchone()
                == before
            )
            assert owner.execute(
                "SELECT state,result_hash FROM football.work_items WHERE work_id=%s",
                (claim.work_id,),
            ).fetchone() == ("RUNNING", None)
        finally:
            WorkRegistry(owner).cancel(claim.work_id)
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


@pytest.mark.parametrize("batch", [None, "infinity", "-infinity"])
def test_sql_history_claim_rejects_nonfinite_batches_without_an_attempt(batch: Any) -> None:
    from football.product.history_work import register_history_request
    from football.work.storage import WorkRegistry

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        identity = register_history_request(connection, job)
        assert identity is not None
        try:
            with pytest.raises(psycopg.errors.InvalidParameterValue):
                connection.execute(
                    "SELECT * FROM football.claim_history_work(%s,%s,%s,%s::timestamptz)",
                    (identity, "worker", timedelta(minutes=30), batch),
                )
            assert connection.execute(
                "SELECT state,attempt_count FROM football.work_items WHERE work_id=%s",
                (identity,),
            ).fetchone() == ("PENDING", 0)
        finally:
            WorkRegistry(connection).cancel(identity)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_shared_history_reaps_its_last_expired_attempt_into_failed_detail() -> None:
    from football.product.history_work import claim_history_request
    from football.work.storage import WorkRegistry

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue
            (provider_competition_id,season,attempt_count)
            VALUES (%s,2099,2147483646) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        claim = None
        try:
            claim = claim_history_request(
                connection, job, "last-worker", batch, lease_duration=timedelta(milliseconds=30)
            )
            assert claim is not None
            connection.execute(
                "SELECT pg_sleep(GREATEST(0,extract(epoch FROM "
                "(%s::timestamptz-clock_timestamp())))+0.005)",
                (claim.lease_until,),
            )
            next_batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            assert (
                claim_history_request(
                    connection, job, "replacement", next_batch, lease_duration=timedelta(minutes=30)
                )
                is None
            )
            assert connection.execute(
                """SELECT queue.job_status,queue.attempt_count,work.state,work.last_error_code,
                queue.finished_at=work.finished_at FROM football.product_history_sync_queue queue
                JOIN football.product_history_work binding USING (job_id,queued_at)
                JOIN football.work_items work USING (work_id) WHERE queue.job_id=%s""",
                (job,),
            ).fetchone() == ("FAILED", 2147483647, "FAILED", "LEASE_EXPIRED", True)
        finally:
            if claim is not None:
                WorkRegistry(connection).cancel(claim.work_id)
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_history_batch_deferral_does_not_consume_a_shared_attempt() -> None:
    from football.product.history_work import claim_history_request
    from football.work.storage import WorkRegistry

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        job, stamp = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id,queued_at""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()
        try:
            assert (
                claim_history_request(
                    connection,
                    job,
                    "worker",
                    stamp - timedelta(seconds=1),
                    lease_duration=timedelta(minutes=30),
                )
                is None
            )
            row = connection.execute(
                """SELECT work.work_id,work.state,work.attempt_count,queue.job_status
                FROM football.product_history_sync_queue queue
                JOIN football.product_history_work binding USING (job_id,queued_at)
                JOIN football.work_items work USING (work_id) WHERE queue.job_id=%s""",
                (job,),
            ).fetchone()
            assert row is not None and row[1:] == ("PENDING", 0, "PENDING")
            WorkRegistry(connection).cancel(row[0])
        finally:
            connection.execute(
                "DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,)
            )


def test_shared_history_supports_connections_with_dictionary_rows() -> None:
    from football.product.history_work import claim_history_request, complete_history_request
    from football.work.storage import WorkRegistry
    from psycopg.rows import dict_row

    with psycopg.connect(DATABASE_URL, autocommit=True) as owner:
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2099) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        batch = owner.execute("SELECT clock_timestamp()").fetchone()[0]
        claim = None
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as worker:
                claim = claim_history_request(
                    worker, job, "worker", batch, lease_duration=timedelta(minutes=30)
                )
                assert claim is not None
                complete_history_request(worker, claim, result_hash="a" * 64)
        finally:
            if claim is not None:
                WorkRegistry(owner).cancel(claim.work_id)
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))


def test_history_expired_attempt_cleanup_skips_busy_detail_without_publishing_failure() -> None:
    from football.product.history_work import claim_history_request
    from football.work.storage import WorkRegistry

    with (
        psycopg.connect(DATABASE_URL, autocommit=True) as owner,
        psycopg.connect(DATABASE_URL, autocommit=True) as worker,
    ):
        job = owner.execute(
            """INSERT INTO football.product_history_sync_queue
            (provider_competition_id,season,attempt_count)
            VALUES (%s,2099,2147483646) RETURNING job_id""",
            (str(uuid4().int % 2_000_000_000),),
        ).fetchone()[0]
        batch = owner.execute("SELECT clock_timestamp()").fetchone()[0]
        claim = claim_history_request(
            worker, job, "expired", batch, lease_duration=timedelta(milliseconds=30)
        )
        assert claim is not None
        try:
            worker.execute(
                "SELECT pg_sleep(GREATEST(0,extract(epoch FROM "
                "(%s::timestamptz-clock_timestamp())))+0.005)",
                (claim.lease_until,),
            )
            worker.execute("SET statement_timeout='200ms'")
            next_batch = worker.execute("SELECT clock_timestamp()").fetchone()[0]
            with owner.transaction():
                owner.execute(
                    "SELECT job_id FROM football.product_history_sync_queue "
                    "WHERE job_id=%s FOR UPDATE",
                    (job,),
                )
                assert (
                    claim_history_request(
                        worker, job, "cleanup", next_batch, lease_duration=timedelta(minutes=30)
                    )
                    is None
                )
                assert worker.execute(
                    "SELECT state,last_error_code FROM football.work_items WHERE work_id=%s",
                    (claim.work_id,),
                ).fetchone() == ("RUNNING", None)
            assert (
                claim_history_request(
                    worker, job, "cleanup", next_batch, lease_duration=timedelta(minutes=30)
                )
                is None
            )
            assert owner.execute(
                "SELECT job_status FROM football.product_history_sync_queue WHERE job_id=%s",
                (job,),
            ).fetchone() == ("FAILED",)
        finally:
            WorkRegistry(owner).cancel(claim.work_id)
            owner.execute("DELETE FROM football.product_history_sync_queue WHERE job_id=%s", (job,))
