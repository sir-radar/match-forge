"""Physical database identity and persisted role precede all experimental side effects."""

import json
import os
import sys
from uuid import uuid4

import psycopg
import pytest
from football.observations.cli import main as observation_main
from football.providers.normalization.cli import main as normalization_main
from football.storage import experimental
from psycopg import sql
from psycopg.conninfo import make_conninfo

from tests.integration.test_resource_observation_artifacts import _observation
from tests.integration.test_team_identity_correction import isolated_database
from tests.integration.test_v4_development_isolation import _source


def _mark(c):
    c.execute(
        sql.SQL("ALTER DATABASE {} SET matchforge.database_role='experimental'").format(
            sql.Identifier(c.info.dbname)
        )
    )
    c.commit()


def test_physical_identity_and_catalog_marker_are_both_required(tmp_path, monkeypatch, capsys):
    with isolated_database() as operating, isolated_database() as shadow:
        # A different URL/hostname still resolves to the same physical database.
        alias = make_conninfo(operating, host="localhost")
        with (
            pytest.raises(experimental.IsolationError, match="operating database"),
            experimental.experimental_connection(alias, operating),
        ):
            pytest.fail("operating database was accepted")
        with (
            pytest.raises(experimental.IsolationError, match="persistent experimental"),
            experimental.experimental_connection(shadow, operating),
        ):
            pytest.fail("unmarked database was accepted")
        with psycopg.connect(shadow) as c:
            _mark(c)
        identity = experimental._identity
        verified = []

        def readonly_identity(c):
            assert c.execute("SHOW transaction_read_only").fetchone() == ("on",)
            value = identity(c)
            verified.append(value)
            return value

        monkeypatch.setattr(experimental, "_identity", readonly_identity)
        with experimental.experimental_connection(shadow, operating) as c:
            assert c.execute("SHOW transaction_read_only").fetchone() == ("off",)
            c.execute("CREATE TABLE isolation_probe (value integer)")
            c.execute("INSERT INTO isolation_probe VALUES (42)")
        assert len(verified) == 2 and verified[0][:2] != verified[1][:2]
        receipt = json.loads(capsys.readouterr().err)
        assert receipt["isolated_from_operating"] and receipt["database_oid"] == verified[1][1]
        assert "password" not in receipt
        with psycopg.connect(operating) as c:
            assert c.execute("SELECT to_regclass('isolation_probe')").fetchone() == (None,)


def test_launcher_refuses_operating_before_command_and_pins_shadow_environment(tmp_path):
    script = tmp_path / "probe.py"
    side_effect = tmp_path / "published.json"
    script.write_text(
        "import json,os,psycopg\n"
        "from pathlib import Path\n"
        "assert os.environ['FOOTBALL_DATABASE_URL']==os.environ['DATABASE_URL']\n"
        "assert not any(k.startswith('PG') for k in os.environ)\n"
        "with psycopg.connect(os.environ['DATABASE_URL']) as c:\n"
        " row=c.execute('SELECT current_database()').fetchone()\n"
        f"Path({str(side_effect)!r}).write_text(json.dumps(row))\n"
    )
    with isolated_database() as operating, isolated_database() as shadow:
        command = ["--", sys.executable, str(script)]
        assert (
            experimental.main(
                [
                    "--database-url",
                    operating,
                    "--operating-database-url",
                    operating,
                    *command,
                ]
            )
            == 2
        )
        assert not side_effect.exists()
        with psycopg.connect(shadow) as c:
            _mark(c)
            name = c.info.dbname
        # Conflicting ordinary defaults cannot override the verified explicit target.
        saved = dict(os.environ)
        try:
            os.environ.update(DATABASE_URL=operating, FOOTBALL_DATABASE_URL=operating)
            assert (
                experimental.main(
                    [
                        "--database-url",
                        shadow,
                        "--operating-database-url",
                        operating,
                        *command,
                    ]
                )
                == 0
            )
        finally:
            os.environ.clear()
            os.environ.update(saved)
        assert json.loads(side_effect.read_text()) == [name]


def test_shadow_publication_clis_verify_before_artifact_or_work_publication(tmp_path):
    with isolated_database() as operating, isolated_database() as shadow:
        rejected = tmp_path / "rejected"
        args = [
            "--source-resource-id",
            str(uuid4()),
            "--resource",
            "results",
            "--data-root",
            str(tmp_path),
            "--artifact-root",
            str(rejected),
            "--persist",
            "--database-url",
            operating,
            "--operating-database-url",
            operating,
        ]
        with pytest.raises(experimental.IsolationError, match="operating database"):
            normalization_main(args)
        assert not rejected.exists()
        with psycopg.connect(shadow, autocommit=True) as c:
            _mark(c)
            context, raw, resource_type = _source(c, tmp_path, "understat")
            source = context.provenance.source_resource_id
            before = c.execute(
                "SELECT count(*) FROM football.resource_observation_artifacts"
            ).fetchone()
        assert (
            normalization_main(
                [
                    "--source-resource-id",
                    str(source),
                    "--resource",
                    resource_type,
                    "--data-root",
                    str(tmp_path),
                    "--artifact-root",
                    str(tmp_path),
                    "--persist",
                    "--database-url",
                    shadow,
                    "--operating-database-url",
                    operating,
                ]
            )
            == 0
        )
        with psycopg.connect(shadow) as c:
            assert (
                c.execute(
                    "SELECT count(*) FROM football.resource_observation_artifacts"
                ).fetchone()[0]
                > before[0]
            )
            item = _observation(c, tmp_path, fixture_id=987654)
        document = tmp_path / "observation.json"
        document.write_bytes(item.to_bytes())
        assert (
            observation_main(
                [
                    "store",
                    str(document),
                    "--data-root",
                    str(tmp_path),
                    "--database-url",
                    shadow,
                    "--operating-database-url",
                    operating,
                ]
            )
            == 0
        )
        with psycopg.connect(operating) as c:
            assert c.execute(
                "SELECT count(*) FROM football.resource_observation_artifacts"
            ).fetchone() == (0,)
            assert c.execute("SELECT count(*) FROM football.work_items").fetchone() == (0,)
