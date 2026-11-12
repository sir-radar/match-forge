"""Seed pre-guard legacy rows in a disposable test database without a blanket bypass.

``session_replication_role = replica`` silences every trigger and foreign key on every table.
Seeding a legacy path-digest snapshot needs only the path-digest guard off, so this disables
that one trigger by name, inside the caller's transaction, and re-enables it before returning.
Fixtures roll the transaction back, so the DDL never outlives the test.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection, sql
from psycopg.pq import TransactionStatus

PATH_DIGEST_GUARD = ("source_snapshots", "source_snapshots_reject_path_digest")


@contextmanager
def without_trigger(connection: Connection[Any], table: str, trigger: str) -> Iterator[None]:
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise RuntimeError("legacy seeding must run inside a rolled-back test transaction")
    statement = sql.SQL("ALTER TABLE football.{} {} TRIGGER {}")
    connection.execute(
        statement.format(sql.Identifier(table), sql.SQL("DISABLE"), sql.Identifier(trigger))
    )
    try:
        yield
    finally:
        connection.execute(
            statement.format(sql.Identifier(table), sql.SQL("ENABLE"), sql.Identifier(trigger))
        )


@contextmanager
def legacy_path_digest(connection: Connection[Any]) -> Iterator[None]:
    """Allow a pre-guard path-digest snapshot; every other trigger and key stays enforced."""
    with without_trigger(connection, *PATH_DIGEST_GUARD):
        yield
