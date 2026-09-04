from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from football.ingestion import QuarantineReprocessRequestV1
from football.ingestion.quarantine_reprocess_storage import (
    PostgresQuarantineReprocessRequestStoreV1,
    QuarantineReprocessStorageError,
)


def test_store_registers_an_open_quarantine_request_idempotently() -> None:
    cursor = _Cursor()
    store = PostgresQuarantineReprocessRequestStoreV1()

    first = store.register(cast(Any, cursor), _request())
    retry = store.register(cast(Any, cursor), _request())

    assert first.request_id == _Cursor.REQUEST_ID
    assert first.status == "inserted"
    assert retry.status == "verified_existing"


def test_store_rejects_closed_or_missing_source_quarantine() -> None:
    with pytest.raises(QuarantineReprocessStorageError, match="remain open"):
        PostgresQuarantineReprocessRequestStoreV1().register(
            cast(Any, _Cursor(source_open=False)), _request()
        )


def test_store_rejects_conflicting_existing_request() -> None:
    with pytest.raises(QuarantineReprocessStorageError, match="conflicts"):
        PostgresQuarantineReprocessRequestStoreV1().register(
            cast(Any, _Cursor(conflicting=True)), _request()
        )


def _request() -> QuarantineReprocessRequestV1:
    return QuarantineReprocessRequestV1(
        request_id="football-data-uk-f3-reprocess-v1",
        source_quarantine_id=str(_Cursor.QUARANTINE_ID),
        trigger="MAPPING_REVIEWED",
        trigger_ref="resolution-decision-1",
        policy_version="FootballDataUkPhase1BReprocessV1",
        scheduled_at=datetime(2026, 9, 4, 18, tzinfo=UTC),
    )


class _Cursor:
    QUARANTINE_ID = UUID("00000000-0000-0000-0000-000000000001")
    REQUEST_ID = UUID("00000000-0000-0000-0000-000000000002")

    def __init__(self, *, source_open: bool = True, conflicting: bool = False) -> None:
        self.source_open = source_open
        self.conflicting = conflicting
        self.stored: tuple[object, ...] | None = None
        self.rowcount = 0
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Cursor:
        if "INSERT INTO football.quarantine_reprocess_requests" in query:
            if self.source_open and self.stored is None:
                self.stored = params[:-1]
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, source_quarantine_record_id" in query:
            if self.stored is None:
                self._row = None
            else:
                values = self.stored
                if self.conflicting:
                    values = (*values[:3], "different-ref", *values[4:])
                self._row = (self.REQUEST_ID, *values[1:])
        else:
            raise AssertionError(f"unexpected query: {query}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row
