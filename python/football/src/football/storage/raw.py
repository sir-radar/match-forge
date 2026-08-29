from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from football.contracts.source import (
    ResourceStatus,
    SourceIntegrityError,
    SourceResource,
    SourceSnapshot,
    sha256_bytes,
    validate_relative_posix_path,
)


class ImmutableFileConflict(RuntimeError):
    """An immutable path already contains different bytes."""


class RawResourceConflict(SourceIntegrityError, ImmutableFileConflict):
    """A provider path at an immutable source revision changed bytes."""


@dataclass(frozen=True)
class ImmutableWrite:
    path: Path
    relative_path: str
    size_bytes: int
    sha256: str
    status: ResourceStatus


class ImmutableFileStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, relative_path: str) -> Path:
        validated = validate_relative_posix_path(relative_path)
        candidate = self.root.joinpath(*validated.split("/"))
        _assert_beneath_root(self.root, candidate)
        return candidate

    def publish(self, relative_path: str, payload: bytes) -> ImmutableWrite:
        path = self.path_for(relative_path)
        digest = sha256_bytes(payload)
        if path.exists() or path.is_symlink():
            return self._verify_existing(path, relative_path, payload, digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        _assert_beneath_root(self.root, path)
        try:
            _publish_exclusive(path, payload)
        except FileExistsError:
            return self._verify_existing(path, relative_path, payload, digest)
        return ImmutableWrite(path, relative_path, len(payload), digest, "acquired")

    def _verify_existing(
        self,
        path: Path,
        relative_path: str,
        payload: bytes,
        digest: str,
    ) -> ImmutableWrite:
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise ImmutableFileConflict(f"immutable file conflict: {relative_path}")
        return ImmutableWrite(path, relative_path, len(payload), digest, "verified_existing")


class ImmutableRawStore:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()
        self._files = ImmutableFileStore(self.data_root)

    def relative_path(self, snapshot: SourceSnapshot, resource: SourceResource) -> str:
        return (
            f"raw/provider={snapshot.provider}/snapshot={snapshot.source_git_sha}/{resource.path}"
        )

    def path_for(self, snapshot: SourceSnapshot, resource: SourceResource) -> Path:
        return self._files.path_for(self.relative_path(snapshot, resource))

    def publish(
        self,
        snapshot: SourceSnapshot,
        resource: SourceResource,
        payload: bytes,
    ) -> ImmutableWrite:
        relative_path = self.relative_path(snapshot, resource)
        try:
            return self._files.publish(relative_path, payload)
        except ImmutableFileConflict as error:
            raise RawResourceConflict(
                "SB_SOURCE_CHECKSUM_MISMATCH",
                f"immutable raw resource conflict: {resource.path}",
            ) from error


def _assert_beneath_root(root: Path, candidate: Path) -> None:
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as error:
        raise ValueError("storage path escapes configured root") from error


def _publish_exclusive(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".staging-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)
