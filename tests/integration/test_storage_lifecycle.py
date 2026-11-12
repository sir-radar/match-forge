"""Lifecycle review and hygiene invariants against disposable PostgreSQL only."""

from __future__ import annotations

import hashlib
import os
import subprocess
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from tests.integration.test_team_identity_correction import isolated_database


def test_storage_review_is_append_only_and_cleanup_cannot_be_enabled() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        work = uuid4()
        connection.execute(
            "INSERT INTO football.product_sync_runs(run_id,sync_type,status) "
            "VALUES(%s,'STORAGE_LIFECYCLE','QUEUED')",
            (work,),
        )
        assert connection.execute(
            "SELECT work_type FROM football.work_items WHERE work_id=%s", (work,)
        ).fetchone() == ("STORAGE_LIFECYCLE",)
        connection.execute(
            "INSERT INTO football.storage_reviews(work_id,policy_sha256,manifest_sha256,manifest) "
            "VALUES(%s,%s,%s,'{}')",
            (work, "a" * 64, "b" * 64),
        )
        with pytest.raises(psycopg.Error, match="append-only"), connection.transaction():
            connection.execute("DELETE FROM football.storage_reviews WHERE work_id=%s", (work,))
        identity = hashlib.sha256(b"protected").hexdigest()
        connection.execute(
            "INSERT INTO football.storage_resources(resource_id,backend,location,kind,subsystem,"
            "logical_bytes) VALUES(%s,'filesystem',%s,'file','test',1)",
            (identity, str(work)),
        )
        for state in ("QUARANTINED", "DELETED"):
            with pytest.raises(psycopg.Error, match="disabled"), connection.transaction():
                connection.execute(
                    "UPDATE football.storage_resources SET state=%s WHERE resource_id=%s",
                    (state, identity),
                )
        connection.rollback()


def test_competition_noop_preserves_heap_and_material_changes_still_write() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        competition = uuid4()
        connection.execute("INSERT INTO football.competitions(id) VALUES(%s)", (competition,))
        connection.execute(
            "INSERT INTO football.product_competitions(competition_id,name,country,continent,"
            "division,competition_type,season_label,source_roles,availability_status,updated_at) "
            "VALUES(%s,'League','England','Europe',1,'LEAGUE','2026',%s,'NOT_ENOUGH_HISTORY',clock_timestamp())",
            (competition, Jsonb({"fixtures": ["provider"]})),
        )
        before = connection.execute(
            "SELECT ctid::text,xmin::text,updated_at FROM football.product_competitions "
            "WHERE competition_id=%s",
            (competition,),
        ).fetchone()
        result = connection.execute(
            "UPDATE football.product_competitions SET updated_at=clock_timestamp(),"
            "source_roles=source_roles WHERE competition_id=%s",
            (competition,),
        )
        assert result.rowcount == 0
        assert (
            connection.execute(
                "SELECT ctid::text,xmin::text,updated_at FROM football.product_competitions "
                "WHERE competition_id=%s",
                (competition,),
            ).fetchone()
            == before
        )
        assert (
            connection.execute(
                "UPDATE football.product_competitions SET name='Corrected League',"
                "updated_at=clock_timestamp() WHERE competition_id=%s",
                (competition,),
            ).rowcount
            == 1
        )
        connection.rollback()


def test_storage_upgrade_preserves_existing_work_history() -> None:
    with isolated_database("202611100300") as url, psycopg.connect(url) as connection:
        run = uuid4()
        connection.execute(
            "INSERT INTO football.product_sync_runs(run_id,sync_type,status) "
            "VALUES(%s,'FOTMOB_SYNC','QUEUED')",
            (run,),
        )
        before = connection.execute(
            "SELECT to_jsonb(w) FROM football.work_items w WHERE work_id=%s", (run,)
        ).fetchone()
        connection.commit()
        upgraded = subprocess.run(
            ["goose", "-dir", "infrastructure/migrations", "up"],
            env={**os.environ, "GOOSE_DRIVER": "postgres", "GOOSE_DBSTRING": url},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert upgraded.returncode == 0, upgraded.stderr
        assert (
            connection.execute(
                "SELECT to_jsonb(w) FROM football.work_items w WHERE work_id=%s", (run,)
            ).fetchone()
            == before
        )
        assert connection.execute("SELECT count(*) FROM football.storage_reviews").fetchone() == (
            0,
        )
