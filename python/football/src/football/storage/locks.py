"""Ordered PostgreSQL transaction locks; callers retain their transaction ownership."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum
from typing import Any
from uuid import UUID

from psycopg import Connection, Cursor, Error
from psycopg.errors import InvalidParameterValue
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

LOCK_ORDER_SQLSTATE = "MFL01"


class LockOrderError(RuntimeError):
    """A transaction attempts incompatible or reversed lock acquisition."""


class LockClass(IntEnum):
    SOURCE = 10
    IDENTITY = 20
    COMPETITION = 30
    FIXTURE = 40
    WORK = 50
    FEATURE = 60
    PUBLICATION = 70


@dataclass(frozen=True, slots=True)
class LockRequest:
    lock_class: LockClass
    key: str
    legacy_hash: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.lock_class, LockClass):
            raise LockOrderError("an explicit lock class is required")
        if not isinstance(self.key, str) or not self.key.strip():
            raise LockOrderError("a nonblank lock key is required")
        if type(self.legacy_hash) is not bool:
            raise LockOrderError("lock hash convention must be explicit")


IDENTITY_ADMISSION_LOCK = LockRequest(LockClass.IDENTITY, "product-identity-admission")
FIXTURE_CROSSWALK_LOCK = LockRequest(
    LockClass.IDENTITY, "product_fixture_crosswalk", legacy_hash=True
)


def ordered_locks(requests: Iterable[LockRequest]) -> tuple[LockRequest, ...]:
    unique: dict[str, LockRequest] = {}
    for item in requests:
        if item.key in unique and unique[item.key] != item:
            raise LockOrderError("one lock key cannot have different classes or hash conventions")
        unique[item.key] = item
    return tuple(sorted(unique.values(), key=lambda item: (item.lock_class, item.key)))


def acquire_locks(executor: Connection[Any] | Cursor[Any], requests: Iterable[LockRequest]) -> None:
    _require_transaction(executor)
    for item in ordered_locks(requests):
        try:
            executor.execute(
                "SELECT football.acquire_transaction_lock(%s,%s,%s)",
                (int(item.lock_class), item.key, item.legacy_hash),
            )
        except InvalidParameterValue as error:
            raise LockOrderError(str(error)) from error
        except Error as error:
            if error.sqlstate == LOCK_ORDER_SQLSTATE:
                raise LockOrderError(str(error)) from error
            raise


def lock_fixtures(
    executor: Connection[Any] | Cursor[Any], fixture_ids: Iterable[UUID], *, wait: bool = True
) -> bool:
    """Lock existing competition/fixture scopes before publication; false means busy."""
    connection = _require_transaction(executor)
    identifiers = tuple(fixture_ids)
    if (
        any(not isinstance(identifier, UUID) for identifier in identifiers)
        or type(wait) is not bool
    ):
        raise LockOrderError("fixture locks require UUIDs and an explicit wait mode")
    try:
        with connection.cursor(row_factory=tuple_row) as cursor:
            row = cursor.execute(
                "SELECT football.lock_product_fixtures(%s::uuid[],%s)",
                (list(identifiers), wait),
            ).fetchone()
    except Error as error:
        if error.sqlstate == LOCK_ORDER_SQLSTATE:
            raise LockOrderError(str(error)) from error
        raise
    assert row is not None
    return bool(row[0])


def _require_transaction(executor: Connection[Any] | Cursor[Any]) -> Connection[Any]:
    connection = executor.connection if isinstance(executor, Cursor) else executor
    if connection.autocommit and connection.info.transaction_status == TransactionStatus.IDLE:
        raise LockOrderError("transaction locks require a transaction that remains open")
    return connection
