import os
import subprocess
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier

from tests.integration.test_product_identity_upgrade import _migrate


def test_serving_protocols_query_cancellation_and_durable_job_lifetime() -> None:
    database = "football_serving_limits_" + uuid4().hex
    base_url = os.environ["TEST_DATABASE_URL"]
    url = make_conninfo(base_url, dbname=database)
    with psycopg.connect(make_conninfo(base_url, dbname="postgres"), autocommit=True) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(database)))
        try:
            _migrate(url, "up")
            result = subprocess.run(
                ["go", "test", "./internal/app", "-run", "^TestServingDatabase", "-count=1", "-v"],
                cwd="go/api",
                env={**os.environ, "TEST_DATABASE_URL": url},
                capture_output=True,
                text=True,
                timeout=80,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(database)))
