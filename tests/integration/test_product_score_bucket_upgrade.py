import os
import subprocess
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier

from tests.integration.test_live_context import FIXTURE, _insert_forecast, _seed_fixture
from tests.integration.test_product_identity_upgrade import _migrate


def test_score_bucket_upgrade_preserves_legacy_forecast_and_is_idempotent() -> None:
    database = "football_score_bucket_upgrade_" + uuid4().hex
    test_url = os.environ["TEST_DATABASE_URL"]
    admin_url = make_conninfo(test_url, dbname="postgres")
    upgrade_url = make_conninfo(test_url, dbname=database)
    forecast_id = uuid4()
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(database)))
        try:
            _migrate(upgrade_url, "up-to", "202610130200")
            with psycopg.connect(upgrade_url) as connection:
                _seed_fixture(connection)
                _insert_forecast(connection, forecast_id, "a" * 64, "d" * 64)
                original = connection.execute(
                    "SELECT to_jsonb(f) FROM football.product_forecasts f WHERE forecast_id = %s",
                    (forecast_id,),
                ).fetchone()
            _migrate(upgrade_url, "up")
            with psycopg.connect(upgrade_url) as connection:
                assert (
                    connection.execute(
                        """SELECT to_jsonb(f)-'score_matrix_version'
                       FROM football.product_forecasts f WHERE forecast_id = %s""",
                        (forecast_id,),
                    ).fetchone()
                    == original
                )
                assert connection.execute(
                    """SELECT score_matrix_version FROM football.product_forecasts
                       WHERE forecast_id = %s""",
                    (forecast_id,),
                ).fetchone() == (None,)
                pending = connection.execute(
                    """SELECT to_jsonb(w) FROM football.product_forecast_refresh_work w
                       WHERE fixture_id = %s""",
                    (FIXTURE,),
                ).fetchone()
                assert (
                    pending is not None
                    and pending[0]["generation"] > pending[0]["completed_generation"]
                )
            _migrate(upgrade_url, "up")
            with psycopg.connect(upgrade_url) as connection:
                assert (
                    connection.execute(
                        """SELECT to_jsonb(w) FROM football.product_forecast_refresh_work w
                           WHERE fixture_id = %s""",
                        (FIXTURE,),
                    ).fetchone()
                    == pending
                )
            down = subprocess.run(
                ["goose", "-dir", "infrastructure/migrations", "postgres", upgrade_url, "down"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert down.returncode != 0 and "forward-only" in down.stderr
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(database)))
