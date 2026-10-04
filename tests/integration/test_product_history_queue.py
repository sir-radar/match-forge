from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import psycopg
from football.product.api_football import ApiFootballError
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
            first_job = first_sync._claim_history_job()
            second_job = second_sync._claim_history_job()
            assert first_job is not None
            assert second_job is not None
            assert first_job[0] != second_job[0]
            assert first_sync._claim_history_job() is None

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
