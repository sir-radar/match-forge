"""Both pre-integration migration histories upgrade without changing old claims."""

from __future__ import annotations

import subprocess
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from tests.integration.test_product_identity_admission import _history
from tests.integration.test_product_identity_upgrade import _migrate
from tests.integration.test_team_identity_correction import isolated_database


@pytest.mark.parametrize("legacy_native", [False, True])
def test_native_mapping_upgrade_preserves_both_histories(
    tmp_path: Path, legacy_native: bool
) -> None:
    with isolated_database("202610310800") as url:
        if legacy_native:
            result = subprocess.run(
                [
                    "goose",
                    "-dir",
                    "infrastructure/migrations/legacy-v4",
                    "postgres",
                    url,
                    "up",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert result.returncode == 0, result.stderr
        _migrate(url, "up-to", "202611100100")
        with psycopg.connect(url) as c:
            _history(c, tmp_path)
            tables = (
                "team_provider_mappings",
                "provider_mapping_history",
                "source_snapshots",
                "source_resources",
                "product_match_history_decisions",
                "product_identity_admissions",
            )
            before = {
                table: c.execute(
                    sql.SQL(
                        "SELECT to_jsonb(t) FROM football.{} t ORDER BY to_jsonb(t)::text"
                    ).format(sql.Identifier(table))
                ).fetchall()
                for table in tables
            }
            assert before["team_provider_mappings"]
            history = c.execute("SELECT * FROM public.goose_db_version ORDER BY id").fetchall()
        # An interrupted/failed Goose transaction must preserve both constraints
        # and version history before an ordinary retry completes the upgrade.
        failed = tmp_path / "failed-migration"
        failed.mkdir()
        migration = Path(
            "infrastructure/migrations/202611100200_provider_native_mapping_method.sql"
        )
        (failed / migration.name).write_text(
            migration.read_text().replace(";", ";\nSELECT 1 / 0;", 1)
        )
        with psycopg.connect(url) as c:
            constraints = c.execute(
                "SELECT oid,pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace='football'::regnamespace ORDER BY oid"
            ).fetchall()
        interrupted = subprocess.run(
            ["goose", "-dir", str(failed), "postgres", url, "up"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert interrupted.returncode != 0 and "division by zero" in interrupted.stderr
        with psycopg.connect(url) as c:
            assert (
                c.execute("SELECT * FROM public.goose_db_version ORDER BY id").fetchall() == history
            )
            assert (
                c.execute(
                    "SELECT oid,pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE connamespace='football'::regnamespace ORDER BY oid"
                ).fetchall()
                == constraints
            )
        _migrate(url, "up-to", "202611100200")
        _migrate(url, "up-to", "202611100200")
        with psycopg.connect(url) as c:
            for table, rows in before.items():
                assert (
                    c.execute(
                        sql.SQL(
                            "SELECT to_jsonb(t) FROM football.{} t ORDER BY to_jsonb(t)::text"
                        ).format(sql.Identifier(table))
                    ).fetchall()
                    == rows
                )
            upgraded = c.execute("SELECT * FROM public.goose_db_version ORDER BY id").fetchall()
            assert upgraded[:-1] == history
            assert upgraded[-1][1:3] == (202611100200, True)
            definitions = c.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace='football'::regnamespace "
                "AND conname IN ('competition_provider_mappings_mapping_method_check',"
                "'season_provider_mappings_mapping_method_check',"
                "'team_provider_mappings_mapping_method_check',"
                "'player_provider_mappings_mapping_method_check',"
                "'match_provider_mappings_mapping_method_check',"
                "'provider_mapping_history_mapping_method_check')"
            ).fetchall()
            assert len(definitions) == 6
            assert all("provider_native" in definition[0] for definition in definitions)
        result = subprocess.run(
            ["goose", "-dir", "infrastructure/migrations", "postgres", url, "down"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode != 0 and "forward-only" in result.stderr
        with psycopg.connect(url) as c:
            assert (
                c.execute("SELECT * FROM public.goose_db_version ORDER BY id").fetchall()
                == upgraded
            )
