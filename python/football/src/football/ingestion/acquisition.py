from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from football.contracts.source import (
    ManifestResource,
    SourceContractError,
    SourceManifest,
    SourceResource,
    SourceSnapshot,
    canonical_json_bytes,
    sha256_bytes,
)
from football.contracts.source import SourceIntegrityError as SourceIntegrityError
from football.storage.raw import (
    ImmutableFileConflict,
    ImmutableFileStore,
    ImmutableRawStore,
)


class AcquisitionProvider(Protocol):
    @property
    def snapshot(self) -> SourceSnapshot: ...

    def fetch(self, resource: SourceResource) -> bytes: ...


@dataclass(frozen=True)
class AcquisitionResult:
    manifest: SourceManifest
    manifest_path: Path
    manifest_sha256: str
    statuses: dict[str, str]


class SourceAcquirer:
    def __init__(
        self,
        data_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.data_root = data_root.resolve()
        self._raw = ImmutableRawStore(self.data_root)
        self._files = ImmutableFileStore(self.data_root)
        self._clock = clock or (lambda: datetime.now(UTC))

    def acquire(
        self,
        provider: AcquisitionProvider,
        resources: Sequence[SourceResource],
    ) -> AcquisitionResult:
        ordered = _ordered_unique_resources(resources)
        manifest_relative = _manifest_relative_path(provider.snapshot, ordered)
        manifest_path = self._files.path_for(manifest_relative)
        if manifest_path.exists():
            manifest = self._load_manifest(manifest_path)
            self._validate_scope(manifest, provider.snapshot, ordered)
            statuses = self._verify_manifest_resources(provider, manifest)
            return _result(manifest, manifest_path, statuses)

        acquired_at = self._clock()
        if acquired_at.tzinfo is None or acquired_at.utcoffset() is None:
            raise ValueError("acquisition clock must return a timezone-aware datetime")
        stored = [
            self._raw.publish(provider.snapshot, resource, provider.fetch(resource))
            for resource in ordered
        ]
        manifest = SourceManifest(
            snapshot=provider.snapshot,
            acquired_at=acquired_at,
            resources=tuple(
                ManifestResource(
                    path=resource.path,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    raw_path=item.relative_path,
                    media_type=resource.media_type,
                    status=item.status,
                )
                for resource, item in zip(ordered, stored, strict=True)
            ),
        )
        try:
            self._files.publish(manifest_relative, manifest.to_bytes())
        except ImmutableFileConflict:
            manifest = self._load_manifest(manifest_path)
            self._validate_scope(manifest, provider.snapshot, ordered)
        statuses = {
            resource.path: item.status for resource, item in zip(ordered, stored, strict=True)
        }
        return _result(manifest, manifest_path, statuses)

    def _load_manifest(self, path: Path) -> SourceManifest:
        if not path.is_file() or path.is_symlink():
            raise SourceIntegrityError(
                "SOURCE_MANIFEST_INVALID",
                f"immutable source manifest is not a regular file: {path}",
            )
        try:
            return SourceManifest.from_bytes(path.read_bytes())
        except (OSError, SourceContractError) as error:
            raise SourceIntegrityError(
                "SOURCE_MANIFEST_INVALID",
                f"invalid immutable source manifest: {path}",
            ) from error

    def _validate_scope(
        self,
        manifest: SourceManifest,
        snapshot: SourceSnapshot,
        resources: tuple[SourceResource, ...],
    ) -> None:
        if manifest.snapshot != snapshot:
            raise SourceIntegrityError(
                "SOURCE_MANIFEST_SCOPE_MISMATCH",
                "source manifest snapshot does not match provider",
            )
        expected = [(resource.path, resource.media_type) for resource in resources]
        observed = [(resource.path, resource.media_type) for resource in manifest.resources]
        if observed != expected:
            raise SourceIntegrityError(
                "SOURCE_MANIFEST_SCOPE_MISMATCH",
                "source manifest resources do not match acquisition scope",
            )
        for descriptor, stored in zip(resources, manifest.resources, strict=True):
            expected_path = self._raw.relative_path(snapshot, descriptor)
            if stored.raw_path != expected_path:
                raise SourceIntegrityError(
                    "SOURCE_MANIFEST_SCOPE_MISMATCH",
                    "source manifest raw path does not match storage layout",
                )

    def _verify_manifest_resources(
        self,
        provider: AcquisitionProvider,
        manifest: SourceManifest,
    ) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for expected in manifest.resources:
            resource = SourceResource(expected.path, expected.media_type)
            try:
                raw_path = self._raw.path_for(provider.snapshot, resource)
            except ValueError as error:
                raise SourceIntegrityError(
                    "SOURCE_RESOURCE_PATH_INVALID",
                    f"unsafe preserved raw resource path: {resource.path}",
                ) from error
            if raw_path.exists():
                _verify_path(raw_path, expected)
                statuses[resource.path] = "verified_existing"
                continue
            payload = provider.fetch(resource)
            if len(payload) != expected.size_bytes or sha256_bytes(payload) != expected.sha256:
                raise SourceIntegrityError(
                    "SB_SOURCE_CHECKSUM_MISMATCH",
                    f"source recovery checksum mismatch: {resource.path}",
                )
            statuses[resource.path] = self._raw.publish(
                provider.snapshot,
                resource,
                payload,
            ).status
        return statuses


def _ordered_unique_resources(
    resources: Sequence[SourceResource],
) -> tuple[SourceResource, ...]:
    if not resources:
        raise ValueError("acquisition requires at least one source resource")
    ordered = tuple(sorted(resources, key=lambda resource: resource.path))
    paths = [resource.path for resource in ordered]
    if len(paths) != len(set(paths)):
        raise ValueError("acquisition resource paths must be unique")
    return ordered


def _manifest_relative_path(
    snapshot: SourceSnapshot,
    resources: tuple[SourceResource, ...],
) -> str:
    scope = sha256_bytes(
        canonical_json_bytes(
            {
                "provider": snapshot.provider,
                "source_git_sha": snapshot.source_git_sha,
                "resources": [
                    {"path": resource.path, "media_type": resource.media_type}
                    for resource in resources
                ],
            }
        )
    )
    return (
        f"manifests/provider={snapshot.provider}/snapshot={snapshot.source_git_sha}/"
        f"scope={scope}/source-manifest-v1.json"
    )


def _verify_path(path: Path, expected: ManifestResource) -> None:
    if not path.is_file() or path.is_symlink():
        raise SourceIntegrityError(
            "SOURCE_RESOURCE_PATH_INVALID",
            f"preserved raw resource is not a regular file: {expected.path}",
        )
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise SourceIntegrityError(
            "SOURCE_RESOURCE_READ_FAILED",
            f"cannot read preserved raw resource: {expected.path}",
        ) from error
    if len(payload) != expected.size_bytes or sha256_bytes(payload) != expected.sha256:
        raise SourceIntegrityError(
            "SB_SOURCE_CHECKSUM_MISMATCH",
            f"source resource checksum mismatch: {expected.path}",
        )


def _result(
    manifest: SourceManifest,
    manifest_path: Path,
    statuses: dict[str, str],
) -> AcquisitionResult:
    return AcquisitionResult(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_sha256=sha256_bytes(manifest_path.read_bytes()),
        statuses=statuses,
    )
