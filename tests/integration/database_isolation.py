"""Fail-closed isolation between integration tests and protected databases.

Between 29 August and 5 September 2026, integration tests committed 158 synthetic
registrations into the authoritative operating database. The harness always created a
disposable database, but nothing stopped a test run whose ``TEST_DATABASE_URL`` (or
``DATABASE_URL``) pointed at the operating database, and the tests commit.

This module closes that gap with checks that do not depend on database names:

* A harness marks each disposable database with a per-run token. Only the SHA-256 of the
  token is stored, as the database comment; the token itself is passed in the environment.
* Every psycopg connection opened while the guard is installed is checked against the
  cluster's stable identity (``pg_control_system().system_identifier`` plus the database
  OID). It is allowed only when the database carries this run's marker, or when it was
  created after the run started, or when it is a maintenance database with no ``football``
  schema. A database that registers itself in ``football.storage_protections`` as the
  ``AUTHORITATIVE_OPERATING_DATABASE`` is always rejected, marker or not, as is any
  identity listed in ``MATCHFORGE_PROTECTED_DATABASE_IDENTITIES``.
* Anything that cannot be verified is rejected.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import tuple_row

MARKER_PREFIX = "matchforge-disposable-test-database:v1:"
OWNED_PREFIX = "matchforge-test-owned-database:v1:"
TOKEN_ENV = "MATCHFORGE_DISPOSABLE_DATABASE_TOKEN"
CLUSTER_ENV = "MATCHFORGE_TEST_CLUSTER_IDENTIFIER"
PREEXISTING_ENV = "MATCHFORGE_TEST_PREEXISTING_DATABASE_OIDS"
PROTECTED_ENV = "MATCHFORGE_PROTECTED_DATABASE_IDENTITIES"
ACTIVE_ENV = "MATCHFORGE_TEST_ISOLATION_ACTIVE"
PREPARED_ENV = "MATCHFORGE_PREPARED_TEST_DATABASE_IDENTITY"
GUARDED_URL_ENVS = ("TEST_DATABASE_URL", "DATABASE_URL")
SITE_DIRECTORY = Path(__file__).resolve().parent / "isolation_site"

_IDENTITY_SQL = """
SELECT (SELECT system_identifier::text FROM pg_control_system()),
       d.oid::bigint, d.datname, shobj_description(d.oid, 'pg_database'),
       to_regnamespace('football') IS NOT NULL
FROM pg_database d WHERE d.datname = current_database()
"""

_SELF_AUTHORITATIVE_SQL = """
SELECT EXISTS (
  SELECT 1 FROM football.storage_protections p
  WHERE p.backend = 'postgres' AND p.role = 'AUTHORITATIVE_OPERATING_DATABASE'
    AND p.identity->>'system_identifier' = %s AND (p.identity->>'oid')::bigint = %s)
"""


class DatabaseIsolationError(RuntimeError):
    """A test tried to reach a database it cannot prove is disposable."""


@dataclass(frozen=True)
class DatabaseIdentity:
    system_identifier: str
    oid: int
    name: str
    comment: str | None
    has_football_schema: bool
    self_authoritative: bool

    @property
    def key(self) -> str:
        return f"{self.system_identifier}:{self.oid}"


def marker_for(token: str) -> str:
    if len(token) < 32:
        raise DatabaseIsolationError("disposable database token is too short")
    return MARKER_PREFIX + hashlib.sha256(token.encode()).hexdigest()


def owned_marker_for(token: str) -> str:
    """Comment that records which run created a database, so cleanup can find it."""
    return OWNED_PREFIX + hashlib.sha256(token.encode()).hexdigest()


def read_identity(connection: psycopg.Connection[Any]) -> DatabaseIdentity:
    """Read the stable identity of the connected database without writing."""
    try:
        # Tuple rows regardless of the connection's row factory (tests use dict_row).
        with connection.cursor(row_factory=tuple_row) as cursor:
            row = cursor.execute(_IDENTITY_SQL).fetchone()
            if row is None or row[0] is None:
                raise DatabaseIsolationError("cannot read the cluster system identifier")
            authoritative = False
            present = cursor.execute(
                "SELECT to_regclass('football.storage_protections') IS NOT NULL"
            ).fetchone()
            if present == (True,):
                found = cursor.execute(_SELF_AUTHORITATIVE_SQL, (row[0], row[1])).fetchone()
                authoritative = bool(found and found[0])
    except psycopg.Error as error:
        raise DatabaseIsolationError(f"cannot verify database identity: {error}") from error
    finally:
        if not connection.autocommit:
            connection.rollback()
    return DatabaseIdentity(
        system_identifier=str(row[0]),
        oid=int(row[1]),
        name=str(row[2]),
        comment=row[3],
        has_football_schema=bool(row[4]),
        self_authoritative=authoritative,
    )


@dataclass(frozen=True)
class IsolationPolicy:
    token: str
    cluster: str
    preexisting_oids: frozenset[int]
    protected: frozenset[str]
    # Identity ``prepare`` proved fresh (no football schema, no comment) when it marked it.
    prepared: str = ""

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> IsolationPolicy:
        env = os.environ if environ is None else environ
        token = env.get(TOKEN_ENV, "")
        cluster = env.get(CLUSTER_ENV, "")
        raw_oids = env.get(PREEXISTING_ENV)
        if not token or not cluster or raw_oids is None:
            raise DatabaseIsolationError(
                "integration tests must run through the disposable-database harness "
                "(make integration); "
                f"{TOKEN_ENV}, {CLUSTER_ENV} and {PREEXISTING_ENV} are required"
            )
        try:
            oids = frozenset(int(value) for value in raw_oids.split(",") if value)
        except ValueError as error:
            raise DatabaseIsolationError(f"invalid {PREEXISTING_ENV}") from error
        protected = frozenset(
            value.strip() for value in env.get(PROTECTED_ENV, "").split(",") if value.strip()
        )
        marker_for(token)
        return cls(token, cluster, oids, protected, env.get(PREPARED_ENV, ""))

    def environment(self) -> dict[str, str]:
        return {
            TOKEN_ENV: self.token,
            CLUSTER_ENV: self.cluster,
            PREEXISTING_ENV: ",".join(str(oid) for oid in sorted(self.preexisting_oids)),
            PROTECTED_ENV: ",".join(sorted(self.protected)),
            PREPARED_ENV: self.prepared,
        }

    def rejection(self, identity: DatabaseIdentity) -> str | None:
        """Return why a connection must be refused, or ``None`` when it is allowed."""
        label = f"database {identity.name!r} ({identity.key})"
        if identity.self_authoritative and not self._is_prepared(identity):
            return f"{label} is registered as the authoritative operating database"
        if identity.key in self.protected:
            return f"{label} is a protected database identity"
        if identity.comment == marker_for(self.token):
            return None
        if identity.system_identifier != self.cluster:
            return f"{label} is on a cluster this test run did not verify"
        if identity.oid not in self.preexisting_oids:
            return None
        if not identity.has_football_schema:
            return None
        return f"{label} existed before this test run and is not marked disposable"

    def _is_prepared(self, identity: DatabaseIdentity) -> bool:
        """The run's own marked database, which may register itself while under test.

        Storage tests run ``VerifyAuthority`` against it, which records the connected
        database as authoritative in its own registry. ``prepare`` proved it fresh before
        any test ran, so that later self-registration does not make it the operating
        database. A copied marker on any other database is still refused.
        """
        return (
            bool(self.prepared)
            and identity.key == self.prepared
            and identity.comment == marker_for(self.token)
        )

    def check(self, connection: psycopg.Connection[Any]) -> DatabaseIdentity:
        identity = read_identity(connection)
        reason = self.rejection(identity)
        if reason is not None:
            raise DatabaseIsolationError(f"integration test isolation: {reason}")
        if (
            identity.comment is None
            and identity.system_identifier == self.cluster
            and identity.oid not in self.preexisting_oids
        ):
            self._record_ownership(connection, identity)
        return identity

    def _record_ownership(
        self, connection: psycopg.Connection[Any], identity: DatabaseIdentity
    ) -> None:
        """Tag a database this run created, so an interrupted run's leftovers are found."""
        autocommit = connection.autocommit
        connection.autocommit = True
        try:
            with connection.cursor(row_factory=tuple_row) as cursor:
                read_only = cursor.execute("SHOW transaction_read_only").fetchone()
            if read_only == ("on",):
                # A read-only session cannot tag; a later writable connection will.
                return
            connection.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(identity.name), sql.Literal(owned_marker_for(self.token))
                )
            )
        except psycopg.Error as error:
            raise DatabaseIsolationError(f"cannot record test ownership: {error}") from error
        finally:
            connection.autocommit = autocommit


_ORIGINAL_CONNECT: Callable[..., Any] | None = None


def install(policy: IsolationPolicy) -> None:
    """Check every new psycopg connection in this process against ``policy``."""
    global _ORIGINAL_CONNECT
    if _ORIGINAL_CONNECT is not None:
        return
    original = psycopg.Connection.connect.__func__  # type: ignore[attr-defined]
    _ORIGINAL_CONNECT = original
    previous_connect = psycopg.connect

    def guarded(cls: type[psycopg.Connection[Any]], *args: Any, **kwargs: Any) -> Any:
        connection = original(cls, *args, **kwargs)
        try:
            policy.check(connection)
        except BaseException:
            connection.close()
            raise
        return connection

    psycopg.Connection.connect = classmethod(guarded)  # type: ignore[method-assign,assignment]
    psycopg.connect = psycopg.Connection.connect
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "connect", None) is previous_connect:
            try:
                module.connect = psycopg.connect  # type: ignore[attr-defined]
            except (AttributeError, TypeError):
                continue


def child_environment(policy: IsolationPolicy) -> dict[str, str]:
    """Environment that makes Python child processes install the same guard."""
    path = os.environ.get("PYTHONPATH", "")
    site = str(SITE_DIRECTORY)
    parts = [site, *[part for part in path.split(os.pathsep) if part and part != site]]
    return {**policy.environment(), ACTIVE_ENV: "1", "PYTHONPATH": os.pathsep.join(parts)}


def guard_urls(policy: IsolationPolicy, environ: dict[str, str] | None = None) -> None:
    """Verify every database URL the tests read from the environment."""
    env = os.environ if environ is None else environ
    url = env.get("TEST_DATABASE_URL")
    if not url:
        raise DatabaseIsolationError("TEST_DATABASE_URL must name a disposable database")
    for name in GUARDED_URL_ENVS:
        value = env.get(name)
        if not value:
            continue
        with psycopg.connect(value, autocommit=True) as connection:
            identity = read_identity(connection)
        reason = policy.rejection(identity)
        if reason is None and identity.comment != marker_for(policy.token):
            reason = f"database {identity.name!r} is not marked for this test run"
        if reason is not None:
            raise DatabaseIsolationError(f"{name}: integration test isolation: {reason}")


def prepare(url: str, protected: Iterable[str] = ()) -> IsolationPolicy:
    """Mark a freshly created database disposable and return the run's policy.

    Refuses a database that already holds a ``football`` schema or any other comment, so
    an existing database cannot be converted into a test target by accident.
    """
    token = secrets.token_hex(32)
    with psycopg.connect(url, autocommit=True) as connection:
        identity = read_identity(connection)
        if identity.self_authoritative or identity.has_football_schema or identity.comment:
            raise DatabaseIsolationError(
                f"refusing to mark {identity.name!r}: it is not a freshly created database"
            )
        connection.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(identity.name), sql.Literal(marker_for(token))
            )
        )
        oids = connection.execute("SELECT oid::bigint FROM pg_database").fetchall()
    return IsolationPolicy(
        token=token,
        cluster=identity.system_identifier,
        preexisting_oids=frozenset(int(row[0]) for row in oids),
        protected=frozenset(protected),
        prepared=identity.key,
    )


def sweep(policy: IsolationPolicy, url: str) -> list[str]:
    """Drop every database this run created or marked; return their names.

    Only databases carrying this run's marker or ownership tag are touched; only this run
    knows the token those comments are derived from. Protected identities are skipped.
    """
    markers = (marker_for(policy.token), owned_marker_for(policy.token))
    maintenance = make_conninfo(url, dbname="postgres")
    original = _ORIGINAL_CONNECT or psycopg.Connection.connect.__func__  # type: ignore[attr-defined]
    dropped: list[str] = []
    with original(psycopg.Connection, maintenance, autocommit=True) as connection:
        cluster = connection.execute(
            "SELECT system_identifier::text FROM pg_control_system()"
        ).fetchone()
        if cluster is None or cluster[0] != policy.cluster:
            raise DatabaseIsolationError("sweep target is not this run's cluster")
        rows = connection.execute(
            "SELECT oid::bigint, datname FROM pg_database "
            "WHERE shobj_description(oid, 'pg_database') = ANY(%s) ORDER BY oid",
            (list(markers),),
        ).fetchall()
        for oid, name in rows:
            if f"{policy.cluster}:{oid}" in policy.protected:
                continue
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
            dropped.append(str(name))
    return dropped


def _protected_from(url: str | None) -> list[str]:
    """Identities of databases that register themselves as authoritative, if reachable."""
    if not url:
        return []
    try:
        with psycopg.connect(url, autocommit=True, connect_timeout=5) as connection:
            identity = read_identity(connection)
    except (psycopg.Error, DatabaseIsolationError):
        return []
    return [identity.key] if identity.self_authoritative else []


def main(argv: list[str]) -> int:
    """``prepare URL [OPERATING_URL]`` prints shell exports; ``verify`` checks the env."""
    if len(argv) >= 2 and argv[0] == "prepare":
        policy = prepare(argv[1], _protected_from(argv[2] if len(argv) > 2 else None))
        for key, value in policy.environment().items():
            print(f"{key}={json.dumps(value)}")
        return 0
    if len(argv) == 2 and argv[0] == "sweep":
        for name in sweep(IsolationPolicy.from_environment(), argv[1]):
            print(f"dropped test database {name}")
        return 0
    if argv == ["verify"]:
        guard_urls(IsolationPolicy.from_environment())
        return 0
    print(
        "usage: database_isolation prepare URL [OPERATING_URL] | verify | sweep URL",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except DatabaseIsolationError as error:
        print(f"database isolation: {error}", file=sys.stderr)
        raise SystemExit(8) from error
