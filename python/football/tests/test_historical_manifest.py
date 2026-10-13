from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from football.product.historical_manifest import publish_manifest, verify_manifest
from football.storage.raw import ImmutableFileConflict


def test_manifest_hashes_actual_bytes_and_replay_preserves_acquisition(tmp_path: Path) -> None:
    observed = datetime(2026, 10, 1, tzinfo=UTC)
    kwargs: dict[str, Any] = dict(
        provider="openfootball",
        source_identity="repository",
        source_revision="abc",
        resources=[("2025/en.1.json", "raw/en.1.json", b'{"matches":[]}')],
    )
    manifest_path = publish_manifest(tmp_path, acquired_at=observed, **kwargs)
    manifest, digest = verify_manifest(tmp_path, manifest_path, "openfootball", "repository", "abc")
    import hashlib

    assert digest == hashlib.sha256((tmp_path / manifest_path).read_bytes()).hexdigest()
    assert manifest["acquired_at"] == observed.isoformat()
    assert (
        publish_manifest(tmp_path, acquired_at=observed + timedelta(days=2), **kwargs)
        == manifest_path
    )
    assert (
        verify_manifest(tmp_path, manifest_path, "openfootball", "repository", "abc")[0] == manifest
    )
    (tmp_path / "raw/en.1.json").write_bytes(b'{"tampered":true}')
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_manifest(tmp_path, manifest_path, "openfootball", "repository", "abc")
    with pytest.raises(ImmutableFileConflict):
        publish_manifest(tmp_path, acquired_at=observed, **kwargs)


def test_manifest_rejects_wrong_provider_schema_and_unsafe_paths(tmp_path: Path) -> None:
    path = publish_manifest(
        tmp_path,
        provider="football_data_uk",
        source_identity="url",
        source_revision="digest",
        acquired_at=datetime.now(UTC),
        resources=[("season.csv", "raw/season.csv", b"CSV")],
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        verify_manifest(tmp_path, path, "other_provider", "url", "digest")
    with pytest.raises(ValueError):
        publish_manifest(
            tmp_path,
            provider="football_data_uk",
            source_identity="url",
            source_revision="digest",
            acquired_at=datetime.now(UTC),
            resources=[("../escape", "raw/safe", b"CSV")],
        )
    (tmp_path / path).write_text('{"contract":"UnsupportedManifest"}')
    from jsonschema import ValidationError

    with pytest.raises(ValidationError):
        verify_manifest(tmp_path, path, "football_data_uk", "url", "digest")
