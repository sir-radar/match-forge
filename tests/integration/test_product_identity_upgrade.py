"""A populated upgrade must preserve evidence and admit only prospectively."""

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from football.product.identity_admission import admit_provider_mappings
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier

from tests.integration.historical_source_fixture import legacy_identity_locking
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
                with legacy_identity_locking(connection):
                    _history(connection, tmp_path)
                before = _cutoff(connection)
                retained = connection.execute(
                    "SELECT to_jsonb(m) FROM football.team_provider_mappings m ORDER BY id"
                ).fetchall()
                snapshots = connection.execute(
                    "SELECT to_jsonb(s) FROM football.source_snapshots s ORDER BY id"
                ).fetchall()
            _migrate(upgrade_url, "up-to", "202610121100")
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
            _migrate(upgrade_url, "up-to", "202610121100")
            with psycopg.connect(upgrade_url) as connection:
                assert (
                    connection.execute(
                        "SELECT decision_id, decided_at "
                        "FROM football.product_match_history_decisions"
                    ).fetchall()
                    == initial
                )
                with legacy_identity_locking(connection):
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


def test_bulk_history_upgrade_does_not_exhaust_advisory_locks(tmp_path: Path) -> None:
    test_url = os.environ["TEST_DATABASE_URL"]
    database = "football_identity_upgrade_" + uuid4().hex
    upgrade_url = make_conninfo(test_url, dbname=database)
    with psycopg.connect(make_conninfo(test_url, dbname="postgres"), autocommit=True) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(database)))
        try:
            _migrate(upgrade_url, "up-to", "202610121000")
            with psycopg.connect(upgrade_url) as connection:
                with legacy_identity_locking(connection):
                    _history(connection, tmp_path)
                connection.execute(
                    """WITH original AS (
                           SELECT h.*, m.season_id FROM football.product_team_match_history h
                           JOIN football.matches m ON m.id=h.fixture_id
                       ), seeds AS (
                           SELECT uuidv7() AS id, n FROM generate_series(1,30000) n
                       ), added AS (
                           INSERT INTO football.matches (id, competition_id, season_id)
                           SELECT seeds.id, competition_id, season_id FROM original, seeds
                           RETURNING id
                       )
                       INSERT INTO football.product_team_match_history
                       SELECT added.id, h.competition_id, h.home_team_id, h.away_team_id,
                              h.kickoff_at - seeds.n * interval '1 day',
                              h.home_goals, h.away_goals, h.home_xg, h.away_xg,
                              h.source_provider_code, h.source_snapshot_id,
                              h.source_kickoff_precision
                       FROM added JOIN seeds USING(id), original h"""
                )
                before = _cutoff(connection)
            _migrate(upgrade_url, "up-to", "202610121100")
            with psycopg.connect(upgrade_url) as connection:
                assert connection.execute(
                    """SELECT count(*),count(*) FILTER (WHERE eligible),
                              count(*) FILTER (WHERE decided_at <= %s)
                       FROM football.product_match_history_decisions""",
                    (before,),
                ).fetchone() == (30001, 0, 0)
                assert _eligible(connection, before) == []
                assert _eligible(connection, _cutoff(connection)) == []
                assert connection.execute(
                    "SELECT count(*) FROM football.product_identity_admissions"
                ).fetchone() == (0,)
                assert connection.execute(
                    """SELECT count(*) FROM football.product_match_history_decisions d
                       JOIN football.product_team_match_history h USING(fixture_id)
                       JOIN football.source_snapshots s ON s.id=h.source_snapshot_id
                       WHERE (to_jsonb(d)-'decision_id'-'decided_at'-'eligible'-'reason'
                              -'source_known_at')=to_jsonb(h)
                         AND d.source_known_at=s.acquired_at"""
                ).fetchone() == (30001,)
            _migrate(upgrade_url, "up-to", "202610121100")
            with psycopg.connect(upgrade_url) as connection:
                assert connection.execute(
                    "SELECT count(*) FROM football.product_match_history_decisions"
                ).fetchone() == (30001,)
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(database)))
