"""Real immutable source bytes for historical persistence integration tests."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest


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
