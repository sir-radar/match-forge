"""Verify isolated database selection before experimental publication or acquisition."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.conninfo import conninfo_to_dict, make_conninfo

_MARKER = "matchforge.database_role=experimental"
_ROUTING_ENV = frozenset(
    {
        "PGDATABASE",
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGUSER",
        "PGOPTIONS",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGTARGETSESSIONATTRS",
        "PGLOADBALANCEHOSTS",
    }
)


class IsolationError(ValueError):
    """The explicit experimental target could not be proven separate from operations."""


def _parameters(database_url: str) -> dict[str, str]:
    if _ROUTING_ENV.intersection(os.environ):
        raise IsolationError(
            "ambiguous PostgreSQL connection environment; remove routing PG* settings"
        )
    try:
        values = {k: str(v) for k, v in conninfo_to_dict(database_url).items() if v is not None}
    except psycopg.Error as error:
        raise IsolationError("invalid explicit database connection settings") from error
    if not all(values.get(k) for k in ("host", "port", "dbname", "user")):
        raise IsolationError("explicit database target requires host, port, dbname and user")
    if any(values.get(k) for k in ("service", "servicefile", "options")):
        raise IsolationError("service and session overrides are not experimental database identity")
    if any("," in values.get(k, "") for k in ("host", "hostaddr", "port")):
        raise IsolationError("experimental targets require one explicit PostgreSQL endpoint")
    if any(c in values["dbname"] for c in "/=:? "):
        raise IsolationError("database name must not contain nested connection settings")
    return values


def _identity(connection: Connection[Any]) -> tuple[str, int, str, bool]:
    row = connection.execute(
        """SELECT control.system_identifier::text,d.oid::bigint,d.datname,
           EXISTS (SELECT 1 FROM pg_catalog.pg_db_role_setting s
                   WHERE s.setdatabase=d.oid AND s.setrole=0 AND %s=ANY(s.setconfig))
           FROM pg_catalog.pg_database d CROSS JOIN pg_catalog.pg_control_system() control
           WHERE d.datname=pg_catalog.current_database()""",
        (_MARKER,),
    ).fetchone()
    if row is None:
        raise IsolationError("PostgreSQL database identity unavailable")
    return str(row[0]), int(row[1]), str(row[2]), bool(row[3])


@contextmanager
def experimental_connection(
    database_url: str, operating_database_url: str
) -> Iterator[Connection[Any]]:
    """Use the verified connection for writes; neither URL has an environment default.

    The marker is database-owned catalog metadata, not a session GUC or name suffix.
    Read-only verification happens before any provider request, quota debit or file
    publication in the caller. The operating connection always stays read-only.
    """
    target = _parameters(database_url)
    operating = _parameters(operating_database_url)
    with psycopg.connect(
        make_conninfo(**operating),
        autocommit=True,
        options="-c default_transaction_read_only=on",
        connect_timeout=5,
    ) as reference:
        operating_identity = _identity(reference)
    with psycopg.connect(
        make_conninfo(**target),
        autocommit=True,
        options="-c default_transaction_read_only=on",
        connect_timeout=5,
    ) as connection:
        identity = _identity(connection)
        if identity[:2] == operating_identity[:2]:
            raise IsolationError("experimental target resolves to the operating database")
        if not identity[3]:
            raise IsolationError("target lacks persistent experimental database marker")
        print(
            json.dumps(
                {
                    "experimental_database": identity[2],
                    "database_oid": identity[1],
                    "postgres_system_identifier": identity[0],
                    "isolated_from_operating": True,
                }
            ),
            file=sys.stderr,
            flush=True,
        )
        connection.execute("SET default_transaction_read_only=off")
        yield connection


def _pinned_url(database_url: str, connection: Connection[Any]) -> str:
    # Resolve DNS/service/environment choices once. Children reconnect to this endpoint.
    return make_conninfo(
        **{
            **_parameters(database_url),
            "host": connection.info.host,
            "hostaddr": connection.info.hostaddr,
            "port": str(connection.info.port),
            "dbname": connection.info.dbname,
            "user": connection.info.user,
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--operating-database-url", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("an experimental command is required after --")
    try:
        with experimental_connection(args.database_url, args.operating_database_url) as connection:
            target = _pinned_url(args.database_url, connection)
            environment = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
            environment.update(DATABASE_URL=target, FOOTBALL_DATABASE_URL=target)
            return subprocess.run(command, env=environment, check=False).returncode
    except (IsolationError, psycopg.Error) as error:
        print(f"Experimental database refused ({type(error).__name__}): {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
