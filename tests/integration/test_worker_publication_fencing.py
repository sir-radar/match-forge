"""Real database fencing: revoked workers cannot publish or revive ownership."""

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import LockNotAvailable, ObjectNotInPrerequisiteState

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.mark.parametrize("state", ["FAILED", "CANCELLED", "expired", "wrong-token"])
def test_worker_publication_rejects_lost_ownership(state: str) -> None:
    run_id = uuid4()
    with psycopg.connect(DATABASE_URL, autocommit=True) as owner:
        owner.execute(
            """INSERT INTO football.product_sync_runs
               (run_id, sync_type, status, worker_id, heartbeat_at)
               VALUES (%s, 'FOTMOB_SYNC', 'RUNNING', %s, clock_timestamp())""",
            (run_id, str(run_id)),
        )
        try:
            with psycopg.connect(DATABASE_URL) as worker:
                worker.execute(
                    "SELECT set_config('matchforge.sync_run_id', %s, false)", (str(run_id),)
                )
                worker.execute(
                    "SELECT set_config('matchforge.sync_worker_id', %s, false)", (str(run_id),)
                )
                worker.commit()
                # Even a no-op write acquires and verifies publication ownership.
                worker.execute("UPDATE football.product_fixtures SET status = status WHERE false")
                owner.execute("SET lock_timeout = '100ms'")
                owner.execute(
                    """UPDATE football.product_sync_runs SET heartbeat_at = clock_timestamp()
                       WHERE run_id = %s""",
                    (run_id,),
                )
                with pytest.raises(LockNotAvailable):
                    owner.execute(
                        """UPDATE football.product_sync_runs SET status = 'CANCELLED',
                           error_message = 'cancelled' WHERE run_id = %s""",
                        (run_id,),
                    )
                owner.execute("SET lock_timeout = 0")
                worker.commit()
                if state in ("FAILED", "CANCELLED"):
                    owner.execute(
                        """UPDATE football.product_sync_runs SET status = %s,
                           error_message = 'ownership revoked', finished_at = clock_timestamp()
                           WHERE run_id = %s""",
                        (state, run_id),
                    )
                elif state == "expired":
                    owner.execute(
                        """UPDATE football.product_sync_runs
                           SET heartbeat_at = clock_timestamp() - interval '3 minutes'
                           WHERE run_id = %s""",
                        (run_id,),
                    )
                else:
                    owner.execute(
                        """UPDATE football.product_sync_runs SET worker_id = 'replacement'
                           WHERE run_id = %s""",
                        (run_id,),
                    )
                with pytest.raises(ObjectNotInPrerequisiteState, match="ownership lost"):
                    worker.execute(
                        "UPDATE football.product_fixtures SET status = status WHERE false"
                    )
                worker.rollback()
                if state in ("FAILED", "CANCELLED"):
                    with pytest.raises(ObjectNotInPrerequisiteState, match="terminal sync run"):
                        owner.execute(
                            """UPDATE football.product_sync_runs SET status = 'SUCCEEDED'
                               WHERE run_id = %s""",
                            (run_id,),
                        )
        finally:
            owner.execute("DELETE FROM football.product_sync_runs WHERE run_id = %s", (run_id,))


def test_replaced_history_claim_cannot_publish() -> None:
    token = uuid4()
    league = str(uuid4())
    with psycopg.connect(DATABASE_URL, autocommit=True) as owner:
        owner.execute(
            """INSERT INTO football.product_provider_history_scopes
               (provider_code, provider_competition_id, season_label, status,
                claimed_at, claim_token)
               VALUES ('pitchapi', %s, '2026', 'RUNNING', clock_timestamp(), %s)""",
            (league, token),
        )
        try:
            with psycopg.connect(DATABASE_URL) as worker:
                worker.execute(
                    "SELECT set_config('matchforge.history_claim_token', %s, false)", (str(token),)
                )
                worker.commit()
                owner.execute(
                    """UPDATE football.product_provider_history_scopes SET claim_token = %s
                       WHERE provider_code = 'pitchapi' AND provider_competition_id = %s""",
                    (uuid4(), league),
                )
                with pytest.raises(ObjectNotInPrerequisiteState, match="scope ownership lost"):
                    worker.execute(
                        "UPDATE football.product_fixtures SET status = status WHERE false"
                    )
                worker.rollback()
        finally:
            owner.execute(
                """DELETE FROM football.product_provider_history_scopes
                   WHERE provider_competition_id = %s""",
                (league,),
            )
