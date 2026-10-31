"""Immutable, byte-verifiable manifests for product historical imports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from football.contracts.source import validate_relative_posix_path
from football.storage.raw import ImmutableFileStore

_PACKAGED_SCHEMA = Path(__file__).with_name("historical-source-manifest-v1.schema.json")
_SCHEMA_PATH = (
    _PACKAGED_SCHEMA
    if _PACKAGED_SCHEMA.is_file()
    else Path(__file__).resolve().parents[5]
    / "schemas/contracts/historical-source-manifest-v1.schema.json"
)
MANIFEST_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_bytes())


def publish_manifest(
    root: Path,
    *,
    provider: str,
    source_identity: str,
    source_revision: str,
    acquired_at: datetime,
    resources: Sequence[tuple[str, str, bytes]],
) -> str:
    files = ImmutableFileStore(root)
    entries = []
    for provider_path, raw_path, payload in sorted(resources):
        validate_relative_posix_path(provider_path)
        stored = files.publish(raw_path, payload)
        entries.append(
            {
                "provider_path": provider_path,
                "raw_path": raw_path,
                "sha256": stored.sha256,
                "size_bytes": stored.size_bytes,
            }
        )
    identity = {
        "provider": provider,
        "source_identity": source_identity,
        "source_revision": source_revision,
        "resources": entries,
    }
    digest = hashlib.sha256(_serialize(identity)).hexdigest()
    relative_path = f"{provider}/manifests/{digest}.json"
    path = files.path_for(relative_path)
    if path.exists():
        existing, _ = verify_manifest(
            root, relative_path, provider, source_identity, source_revision
        )
        if any(existing[key] != value for key, value in identity.items()):
            raise ValueError("historical manifest identity changed")
    else:
        if acquired_at.tzinfo is None:
            raise ValueError("manifest acquisition time must be timezone-aware")
        files.publish(
            relative_path,
            _serialize(
                {
                    "contract": "HistoricalSourceManifestV1",
                    **identity,
                    "acquired_at": acquired_at.astimezone(UTC).isoformat(),
                }
            ),
        )
    return relative_path


def verify_manifest(
    root: Path,
    relative_path: str,
    provider: str,
    source_identity: str,
    source_revision: str,
    *,
    verify_resources: bool = True,
) -> tuple[dict[str, Any], str]:
    files = ImmutableFileStore(root)
    path = files.path_for(relative_path)
    if path.is_symlink():
        raise ValueError("historical manifest must not be a symlink")
    payload = path.read_bytes()
    manifest: dict[str, Any] = json.loads(payload)
    Draft202012Validator(MANIFEST_SCHEMA).validate(manifest)
    expected = (provider, source_identity, source_revision)
    if (
        tuple(manifest[key] for key in ("provider", "source_identity", "source_revision"))
        != expected
    ):
        raise ValueError("historical manifest source identity mismatch")
    acquired = datetime.fromisoformat(manifest["acquired_at"])
    if acquired.tzinfo is None:
        raise ValueError("manifest acquisition time must be timezone-aware")
    seen: set[str] = set()
    for resource in manifest["resources"]:
        validate_relative_posix_path(resource["provider_path"])
        if resource["provider_path"] in seen:
            raise ValueError("duplicate historical manifest resource")
        seen.add(resource["provider_path"])
        raw = files.path_for(resource["raw_path"])
        if raw.is_symlink():
            raise ValueError("historical resource must not be a symlink")
        if not verify_resources:
            continue
        raw_payload = raw.read_bytes()
        if (
            len(raw_payload) != resource["size_bytes"]
            or hashlib.sha256(raw_payload).hexdigest() != resource["sha256"]
        ):
            raise ValueError("historical resource checksum mismatch")
    return manifest, hashlib.sha256(payload).hexdigest()


def _serialize(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
