"""Real immutable source bytes for historical persistence integration tests."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from football.product import historical_backfill, identity_admission
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest
from football.storage.locks import IDENTITY_ADMISSION_LOCK, LockRequest
from psycopg import Connection, Cursor


def test_snapshot(
    store: HistoricalBackfillStore,
    root: Path,
    *,
    source_identity: str,
    source_revision: str,
    acquired_at: datetime,
    manifest_path: str,
    payload: bytes = b'{"test_source":true}\n',
) -> UUID:
    store.data_root = root
    manifest = publish_manifest(
        root,
        provider=store.provider_code,
        source_identity=source_identity,
        source_revision=source_revision,
        acquired_at=acquired_at,
        resources=[(manifest_path, manifest_path, payload)],
    )
    snapshot = store.ensure_snapshot(
        source_identity=source_identity,
        source_revision=source_revision,
        acquired_at=acquired_at,
        manifest_path=manifest,
    )
    store.record_resource(
        snapshot_id=snapshot,
        provider_path=manifest_path,
        payload=payload,
        media_type="text/csv" if manifest_path.endswith(".csv") else "application/json",
        acquired_at=acquired_at,
    )
    return snapshot


@contextmanager
def legacy_identity_locking(connection: Connection[Any]) -> Iterator[None]:
    """Seed pre-Phase-15 schemas using their original physical lock contract.

    Current writers require the later shared SQL guard. Upgrade fixtures must
    create old data before that function exists, then restore current writers
    before checking the upgraded database. No eligibility or decision logic changes.
    """
    assert connection.execute(
        "SELECT to_regprocedure('football.acquire_transaction_lock(integer,text,boolean,boolean)')"
    ).fetchone() == (None,)

    def acquire_original(
        executor: Connection[Any] | Cursor[Any], requests: Iterable[LockRequest]
    ) -> None:
        assert tuple(requests) == (IDENTITY_ADMISSION_LOCK,)
        executor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('product-identity-admission',0))"
        )

    with pytest.MonkeyPatch.context() as overrides:
        overrides.setattr(historical_backfill, "acquire_locks", acquire_original)
        overrides.setattr(identity_admission, "acquire_locks", acquire_original)
        yield
