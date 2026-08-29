from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Cursor

from football.contracts.source import (
    SourceContractError,
    SourceIntegrityError,
    SourceManifest,
    SourceResource,
    sha256_bytes,
)
from football.ingestion.acquisition import AcquisitionResult
from football.ingestion.errors import CanonicalIngestionError
from football.storage.raw import ImmutableRawStore

MAX_SOURCE_RESOURCE_BYTES = 128 * 1024 * 1024
MAX_SOURCE_MANIFEST_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class VerifiedSource:
    manifest: SourceManifest
    manifest_path: str
    manifest_sha256: str
    payloads: dict[str, bytes]


@dataclass(frozen=True)
class RegisteredSource:
    provider_id: UUID
    snapshot_id: UUID
    resource_ids: dict[str, UUID]


def verify_acquisition(data_root: Path, acquisition: AcquisitionResult) -> VerifiedSource:
    root = data_root.resolve()
    manifest_path = _regular_path_beneath(root, acquisition.manifest_path, "source manifest")
    manifest_payload = _read_bounded(
        manifest_path,
        MAX_SOURCE_MANIFEST_BYTES,
        "source manifest",
    )
    manifest_sha256 = sha256_bytes(manifest_payload)
    if manifest_sha256 != acquisition.manifest_sha256:
        raise SourceIntegrityError(
            "SOURCE_MANIFEST_CHECKSUM_MISMATCH",
            "source manifest checksum mismatch before database registration",
        )
    try:
        disk_manifest = SourceManifest.from_bytes(manifest_payload)
    except SourceContractError as error:
        raise SourceIntegrityError(
            "SOURCE_MANIFEST_INVALID",
            "source manifest is invalid before database registration",
        ) from error
    if disk_manifest != acquisition.manifest:
        raise SourceIntegrityError(
            "SOURCE_MANIFEST_SCOPE_MISMATCH",
            "source manifest object differs from immutable manifest bytes",
        )

    raw_store = ImmutableRawStore(root)
    payloads: dict[str, bytes] = {}
    for resource in disk_manifest.resources:
        descriptor = SourceResource(resource.path, resource.media_type)
        expected_raw_path = raw_store.relative_path(disk_manifest.snapshot, descriptor)
        if resource.raw_path != expected_raw_path:
            raise SourceIntegrityError(
                "SOURCE_MANIFEST_SCOPE_MISMATCH",
                f"source resource raw path does not match storage layout: {resource.path}",
            )
        raw_path = _regular_path_beneath(root, root / resource.raw_path, "source resource")
        if resource.size_bytes > MAX_SOURCE_RESOURCE_BYTES:
            raise SourceIntegrityError(
                "SOURCE_RESOURCE_TOO_LARGE",
                f"source resource exceeds {MAX_SOURCE_RESOURCE_BYTES} bytes: {resource.path}",
            )
        payload = _read_bounded(raw_path, MAX_SOURCE_RESOURCE_BYTES, resource.path)
        if len(payload) != resource.size_bytes or sha256_bytes(payload) != resource.sha256:
            raise SourceIntegrityError(
                "SB_SOURCE_CHECKSUM_MISMATCH",
                f"source resource checksum mismatch before database registration: {resource.path}",
            )
        payloads[resource.path] = payload

    relative_manifest_path = manifest_path.relative_to(root).as_posix()
    return VerifiedSource(
        manifest=disk_manifest,
        manifest_path=relative_manifest_path,
        manifest_sha256=manifest_sha256,
        payloads=payloads,
    )


def _regular_path_beneath(root: Path, path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise SourceIntegrityError(
            "SOURCE_RESOURCE_PATH_INVALID",
            f"{label} is not a regular file: {path}",
        )
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise SourceIntegrityError(
            "SOURCE_RESOURCE_PATH_INVALID",
            f"{label} escapes configured data root: {path}",
        ) from error
    return resolved


def _read_bounded(path: Path, max_bytes: int, label: str) -> bytes:
    with path.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise SourceIntegrityError(
            "SOURCE_RESOURCE_TOO_LARGE",
            f"{label} exceeds {max_bytes} bytes",
        )
    return payload


class PostgresSourceRegistry:
    def register(self, cursor: Cursor[Any], source: VerifiedSource) -> RegisteredSource:
        provider_id = self._provider(cursor, source)
        snapshot_id = self._snapshot(cursor, provider_id, source)
        resource_ids = {
            resource.path: self._resource(cursor, snapshot_id, source, resource.path)
            for resource in source.manifest.resources
        }
        return RegisteredSource(provider_id, snapshot_id, resource_ids)

    @staticmethod
    def _provider(cursor: Cursor[Any], source: VerifiedSource) -> UUID:
        code = source.manifest.snapshot.provider
        if code != "statsbomb_open_data":
            raise CanonicalIngestionError(f"unsupported canonical provider: {code}")
        cursor.execute(
            """
            INSERT INTO football.providers (code, name, source_type)
            VALUES (%s, 'StatsBomb Open Data', 'git_repository')
            ON CONFLICT (code) DO NOTHING
            """,
            (code,),
        )
        row = cursor.execute(
            "SELECT id, name, source_type FROM football.providers WHERE code = %s",
            (code,),
        ).fetchone()
        if row is None:
            raise CanonicalIngestionError(f"provider registration failed: {code}")
        if row[1:] != ("StatsBomb Open Data", "git_repository"):
            raise CanonicalIngestionError(f"provider metadata conflicts with registration: {code}")
        return UUID(str(row[0]))

    @staticmethod
    def _snapshot(cursor: Cursor[Any], provider_id: UUID, source: VerifiedSource) -> UUID:
        snapshot = source.manifest.snapshot
        source_identity = source.manifest_path.rsplit("/", 1)[0]
        values = (
            provider_id,
            source_identity,
            snapshot.source_git_sha,
            snapshot.repository,
            snapshot.source_git_sha,
            source.manifest.acquired_at,
            source.manifest_path,
            source.manifest_sha256,
        )
        cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, repository, git_sha,
                 acquired_at, manifest_path, manifest_sha256, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'acquired')
            ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
            """,
            values,
        )
        row = cursor.execute(
            """
            SELECT id, repository, git_sha, acquired_at, manifest_path, manifest_sha256
            FROM football.source_snapshots
            WHERE provider_id = %s AND source_identity = %s AND source_revision = %s
            """,
            (provider_id, source_identity, snapshot.source_git_sha),
        ).fetchone()
        if row is None:
            raise CanonicalIngestionError("source snapshot registration failed")
        expected = (
            snapshot.repository,
            snapshot.source_git_sha,
            source.manifest.acquired_at,
            source.manifest_path,
            source.manifest_sha256,
        )
        if row[1:] != expected:
            raise CanonicalIngestionError(
                "source snapshot revision conflicts with an existing manifest"
            )
        return UUID(str(row[0]))

    @staticmethod
    def _resource(
        cursor: Cursor[Any],
        snapshot_id: UUID,
        source: VerifiedSource,
        provider_path: str,
    ) -> UUID:
        resource = next(item for item in source.manifest.resources if item.path == provider_path)
        cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, %s, %s, %s, %s, 'pending', 'pending', %s)
            ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
            """,
            (
                snapshot_id,
                provider_path,
                resource.sha256,
                resource.size_bytes,
                resource.media_type,
                source.manifest.acquired_at,
            ),
        )
        row = cursor.execute(
            """
            SELECT id, sha256, size_bytes, media_type, acquired_at
            FROM football.source_resources
            WHERE source_snapshot_id = %s AND provider_path = %s
            """,
            (snapshot_id, provider_path),
        ).fetchone()
        expected = (
            resource.sha256,
            resource.size_bytes,
            resource.media_type,
            source.manifest.acquired_at,
        )
        if row is None or row[1:] != expected:
            raise CanonicalIngestionError(
                f"source resource conflicts with registration: {provider_path}"
            )
        return UUID(str(row[0]))
