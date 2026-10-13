"""A populated upgrade must preserve evidence and admit only prospectively."""

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from football.product.identity_admission import admit_provider_mappings
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier

from tests.integration.test_product_identity_admission import _cutoff, _eligible, _history


def _migrate(database_url: str, *arguments: str) -> None:
    result = subprocess.run(
        ["goose", "-dir", "infrastructure/migrations", "postgres", database_url, *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_populated_identity_upgrade_is_forward_only_and_idempotent(tmp_path: Path) -> None:
    test_url = os.environ["TEST_DATABASE_URL"]
    database = "football_identity_upgrade_" + uuid4().hex
    admin_url = make_conninfo(test_url, dbname="postgres")
    upgrade_url = make_conninfo(test_url, dbname=database)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(database)))
        try:
            _migrate(upgrade_url, "up-to", "202610121000")
            with psycopg.connect(upgrade_url) as connection:
                _history(connection, tmp_path)
                before = _cutoff(connection)
                retained = connection.execute(
                    "SELECT to_jsonb(m) FROM football.team_provider_mappings m ORDER BY id"
                ).fetchall()
                snapshots = connection.execute(
                    "SELECT to_jsonb(s) FROM football.source_snapshots s ORDER BY id"
                ).fetchall()
            _migrate(upgrade_url, "up")
            with psycopg.connect(upgrade_url) as connection:
                assert (
                    connection.execute(
                        "SELECT to_jsonb(m) FROM football.team_provider_mappings m ORDER BY id"
                    ).fetchall()
                    == retained
                )
                assert (
                    connection.execute(
                        "SELECT to_jsonb(s) FROM football.source_snapshots s ORDER BY id"
                    ).fetchall()
                    == snapshots
                )
                assert _eligible(connection, before) == []
                assert _eligible(connection, _cutoff(connection)) == []
                initial = connection.execute(
                    "SELECT decision_id, decided_at FROM football.product_match_history_decisions"
                ).fetchall()
                assert len(initial) == 1 and initial[0][1] > before
            _migrate(upgrade_url, "up")
            with psycopg.connect(upgrade_url) as connection:
                assert (
                    connection.execute(
                        "SELECT decision_id, decided_at "
                        "FROM football.product_match_history_decisions"
                    ).fetchall()
                    == initial
                )
                admit_provider_mappings(connection, tmp_path, "football_data_uk")
                admitted = _cutoff(connection)
                assert len(_eligible(connection, admitted)) == 1
                assert _eligible(connection, before) == []
            result = subprocess.run(
                ["goose", "-dir", "infrastructure/migrations", "postgres", upgrade_url, "down"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert result.returncode != 0 and "forward-only" in result.stderr
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(database)))
