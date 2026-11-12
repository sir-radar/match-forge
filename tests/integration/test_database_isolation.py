"""The integration suite cannot write to a database that identifies as authoritative."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import psycopg.conninfo
import pytest
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier

from tests.integration import database_isolation as isolation
from tests.integration.test_team_identity_correction import isolated_database

ROOT = Path(__file__).resolve().parents[2]
REGISTRATION_TABLE_PARTS = ("snapshot", "dataset", "manifest", "artifact", "forecast", "evaluation")


def _raw_connect(url: str) -> psycopg.Connection[Any]:
    """Bypass the guard to set up or inspect the simulated operating database."""
    original = isolation._ORIGINAL_CONNECT
    assert original is not None, "the conftest must install the guard"
    connection: psycopg.Connection[Any] = original(psycopg.Connection, url, autocommit=True)
    return connection


def _row_counts(url: str) -> dict[str, int]:
    with _raw_connect(url) as connection:
        tables = connection.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='football' AND c.relkind IN ('r','p') ORDER BY 1"
        ).fetchall()
        return {
            name: connection.execute(
                SQL("SELECT count(*) FROM football.{}").format(Identifier(name))
            ).fetchone()[0]
            for (name,) in tables
        }


@pytest.fixture(scope="module")
def authoritative_copy() -> Iterator[str]:
    """A migrated database that registers itself as the authoritative operating database.

    It also carries this run's disposable marker, the worst case: a copied configuration
    and a copied marker must still not open it to tests.
    """
    with isolated_database() as url:
        with _raw_connect(url) as connection:
            system_identifier, oid, name = connection.execute(
                "SELECT (SELECT system_identifier::text FROM pg_control_system()), d.oid, "
                "d.datname FROM pg_database d WHERE d.datname=current_database()"
            ).fetchone()
            connection.execute(
                "INSERT INTO football.storage_protections "
                "(backend, identity_key, identity, role, reason, recorded_by) "
                "VALUES ('postgres', %s, jsonb_build_object('system_identifier', %s::text, "
                "'oid', %s::bigint, 'database', %s::text), "
                "'AUTHORITATIVE_OPERATING_DATABASE', 'isolation regression', 'test')",
                (f"postgres:{system_identifier}:{oid}", system_identifier, oid, name),
            )
            connection.execute(
                SQL("COMMENT ON DATABASE {} IS {}").format(
                    Identifier(name),
                    psycopg.sql.Literal(isolation.marker_for(os.environ[isolation.TOKEN_ENV])),
                )
            )
        yield url


def test_in_process_connection_to_authoritative_database_is_refused(
    authoritative_copy: str,
) -> None:
    before = _row_counts(authoritative_copy)
    with pytest.raises(isolation.DatabaseIsolationError, match="authoritative"):
        psycopg.connect(authoritative_copy)
    with pytest.raises(isolation.DatabaseIsolationError, match="authoritative"):
        psycopg.Connection.connect(authoritative_copy, autocommit=True)
    assert _row_counts(authoritative_copy) == before


def test_python_child_process_is_guarded(authoritative_copy: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import psycopg,sys; psycopg.connect(sys.argv[1])",
            authoritative_copy,
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "DatabaseIsolationError" in result.stderr


@pytest.mark.parametrize("variable", ["TEST_DATABASE_URL", "DATABASE_URL"])
def test_whole_suite_refuses_to_start_against_authoritative_database(
    authoritative_copy: str, variable: str
) -> None:
    before = _row_counts(authoritative_copy)
    environment = {**os.environ, variable: authoritative_copy}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/integration"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "authoritative operating database" in result.stdout + result.stderr
    assert _row_counts(authoritative_copy) == before
    # No fixture, dataset, manifest, snapshot or registration from any test reached it.
    registrations = {
        name: count
        for name, count in before.items()
        if count and any(part in name for part in REGISTRATION_TABLE_PARTS)
    }
    assert registrations == {}


def test_suite_refuses_to_start_outside_the_harness() -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in (isolation.TOKEN_ENV, isolation.CLUSTER_ENV, isolation.PREEXISTING_ENV)
    }
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/integration"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "disposable-database harness" in result.stdout + result.stderr


def test_unmarked_preexisting_football_database_is_refused() -> None:
    with isolated_database() as url:
        with _raw_connect(url) as connection:
            identity = isolation.read_identity(connection)
        policy = isolation.IsolationPolicy.from_environment()
        preexisting = isolation.IsolationPolicy(
            policy.token, policy.cluster, policy.preexisting_oids | {identity.oid}, policy.protected
        )
        assert "not marked disposable" in (preexisting.rejection(identity) or "")
        protected = isolation.IsolationPolicy(
            policy.token, policy.cluster, policy.preexisting_oids, frozenset({identity.key})
        )
        assert "protected database identity" in (protected.rejection(identity) or "")


def test_prepare_refuses_existing_database() -> None:
    with pytest.raises(isolation.DatabaseIsolationError, match="not a freshly created"):
        isolation.prepare(os.environ["TEST_DATABASE_URL"])


def test_disposable_database_and_test_created_databases_are_allowed() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        # The check leaves no transaction open on a non-autocommit connection.
        assert connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert connection.execute("SELECT 1").fetchone() == (1,)
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection:
        assert connection.execute("SELECT 1 AS one").fetchone() == {"one": 1}
    with isolated_database() as url, psycopg.connect(url) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)


def test_test_created_database_is_tagged_with_run_ownership() -> None:
    with isolated_database() as url:
        with psycopg.connect(url) as connection:
            identity = isolation.read_identity(connection)
        assert identity.comment == isolation.owned_marker_for(os.environ[isolation.TOKEN_ENV])


def test_sweep_drops_only_databases_of_its_own_run() -> None:
    """An interrupted run's leftovers are found by ownership, not by name."""
    current = isolation.IsolationPolicy.from_environment()
    other = isolation.IsolationPolicy(
        "c" * 64, current.cluster, current.preexisting_oids, current.protected
    )
    url = os.environ["TEST_DATABASE_URL"]
    maintenance = psycopg.conninfo.make_conninfo(url, dbname="postgres")
    names = {"mine": "football_correction_sweep_" + uuid4().hex, "unowned": ""}
    names["unowned"] = "football_correction_sweep_" + uuid4().hex
    with _raw_connect(maintenance) as admin:
        for name in names.values():
            admin.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
        admin.execute(
            SQL("COMMENT ON DATABASE {} IS {}").format(
                Identifier(names["mine"]),
                psycopg.sql.Literal(isolation.owned_marker_for(other.token)),
            )
        )
        try:
            assert isolation.sweep(other, url) == [names["mine"]]
            present = {
                row[0]
                for row in admin.execute(
                    "SELECT datname FROM pg_database WHERE datname = ANY(%s)",
                    (list(names.values()),),
                )
            }
            assert present == {names["unowned"]}
            # The current run's own database carries a different marker and survives.
            with psycopg.connect(url) as connection:
                assert connection.execute("SELECT 1").fetchone() == (1,)
        finally:
            for name in names.values():
                admin.execute(
                    SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(Identifier(name))
                )


def test_prepare_registers_the_run_database_for_lifecycle_cleanup(
    authoritative_copy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record binds cluster, OID, name, marker digests and the owning process."""
    current = isolation.IsolationPolicy.from_environment()
    url = os.environ["TEST_DATABASE_URL"]
    name = "football_lifecycle_run_" + uuid4().hex
    with _raw_connect(psycopg.conninfo.make_conninfo(url, dbname="postgres")) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
        try:
            found = admin.execute("SELECT oid FROM pg_database WHERE datname=%s", (name,))
            oid = found.fetchone()[0]
            run = isolation.IsolationPolicy(
                "d" * 64, current.cluster, frozenset(), frozenset(), f"{current.cluster}:{oid}"
            )
            # The harness registers outside the guard; the test bypasses it the same way.
            monkeypatch.setattr(
                isolation.psycopg, "connect", lambda target, **_: _raw_connect(target)
            )
            monkeypatch.setenv(isolation.OWNER_PID_ENV, str(os.getpid()))
            assert isolation.register_lifecycle(url, run, name) is False  # not authoritative
            assert isolation.register_lifecycle(authoritative_copy, run, name) is True
            with _raw_connect(authoritative_copy) as connection:
                row = connection.execute(
                    "SELECT resource_class, state, identity, owner_ref FROM "
                    "football.storage_lifecycle_resources WHERE identity_key=%s",
                    (f"postgres:{current.cluster}:{oid}",),
                ).fetchone()
                events = connection.execute(
                    "SELECT event FROM football.storage_lifecycle_events WHERE identity_key=%s",
                    (f"postgres:{current.cluster}:{oid}",),
                ).fetchall()
        finally:
            admin.execute(SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(Identifier(name)))
    assert row is not None
    resource_class, state, identity, owner = row
    assert (resource_class, state) == ("TEST_DATABASE", "ACTIVE")
    assert identity == {"system_identifier": current.cluster, "oid": oid, "database": name}
    assert owner["marker"] == isolation.marker_for(run.token)
    assert owner["owned_marker"] == isolation.owned_marker_for(run.token)
    assert owner["pid"] == os.getpid() and owner["process_started"]
    assert run.token not in str(owner)
    assert events == [("REGISTERED",)]
