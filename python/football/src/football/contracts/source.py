from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Literal, cast
from urllib.parse import urlsplit

SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PROVIDER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

ResourceStatus = Literal["acquired", "verified_existing"]


class SourceContractError(ValueError):
    """A source descriptor or manifest violates its public contract."""


class SourceIntegrityError(RuntimeError):
    """Preserved source bytes or lineage failed integrity verification."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_relative_posix_path(value: str) -> str:
    if not value or "\\" in value or any(ord(character) < 32 for character in value):
        raise SourceContractError("source path must be a normalized relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value or value == ".":
        raise SourceContractError("source path must be a normalized relative POSIX path")
    return value


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class SourceSnapshot:
    provider: str
    repository: str
    source_git_sha: str
    license: str
    license_url: str
    attribution: str

    def __post_init__(self) -> None:
        if not PROVIDER_PATTERN.fullmatch(self.provider):
            raise SourceContractError("provider must use lowercase snake_case")
        if not SHA1_PATTERN.fullmatch(self.source_git_sha):
            raise SourceContractError("source_git_sha must be a 40-character lowercase Git SHA")
        _validate_https_url(self.repository, "repository")
        _validate_https_url(self.license_url, "license_url")
        if not self.license or not self.attribution:
            raise SourceContractError("license and attribution must not be empty")


@dataclass(frozen=True)
class SourceResource:
    path: str
    media_type: str = "application/json"

    def __post_init__(self) -> None:
        validate_relative_posix_path(self.path)
        if not self.media_type:
            raise SourceContractError("media_type must not be empty")


@dataclass(frozen=True)
class ManifestResource:
    path: str
    size_bytes: int
    sha256: str
    raw_path: str
    media_type: str
    status: ResourceStatus

    def __post_init__(self) -> None:
        validate_relative_posix_path(self.path)
        validate_relative_posix_path(self.raw_path)
        if self.size_bytes < 0:
            raise SourceContractError("size_bytes must not be negative")
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise SourceContractError("sha256 must be 64 lowercase hexadecimal characters")
        if not self.media_type:
            raise SourceContractError("media_type must not be empty")
        if self.status not in ("acquired", "verified_existing"):
            raise SourceContractError("invalid source resource status")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "raw_path": self.raw_path,
            "media_type": self.media_type,
            "status": self.status,
        }


@dataclass(frozen=True)
class SourceManifest:
    snapshot: SourceSnapshot
    acquired_at: datetime
    resources: tuple[ManifestResource, ...]
    contract: str = "SourceManifestV1"

    def __post_init__(self) -> None:
        if self.contract != "SourceManifestV1":
            raise SourceContractError("unsupported source manifest contract")
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise SourceContractError("acquired_at must include a timezone")
        if not self.resources:
            raise SourceContractError("source manifest must contain at least one resource")
        paths = [resource.path for resource in self.resources]
        if len(paths) != len(set(paths)):
            raise SourceContractError("source manifest resource paths must be unique")

    def to_dict(self) -> dict[str, object]:
        acquired_at = self.acquired_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return {
            "contract": self.contract,
            "provider": self.snapshot.provider,
            "repository": self.snapshot.repository,
            "source_git_sha": self.snapshot.source_git_sha,
            "license": self.snapshot.license,
            "license_url": self.snapshot.license_url,
            "attribution": self.snapshot.attribution,
            "acquired_at": acquired_at,
            "resources": [resource.to_dict() for resource in self.resources],
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    @classmethod
    def from_bytes(cls, payload: bytes) -> SourceManifest:
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceContractError("source manifest is not valid UTF-8 JSON") from error
        if not isinstance(value, dict):
            raise SourceContractError("source manifest must be a JSON object")
        return _parse_manifest(value)


def _validate_https_url(value: str, field: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise SourceContractError(f"{field} must be an HTTPS URL without credentials")


def _required_string(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise SourceContractError(f"source manifest {field} must be a non-empty string")
    return item


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SourceContractError("source manifest acquired_at is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceContractError("source manifest acquired_at must include a timezone")
    return parsed


def _parse_resource(value: object) -> ManifestResource:
    if not isinstance(value, dict):
        raise SourceContractError("source manifest resource must be a JSON object")
    expected = {"path", "size_bytes", "sha256", "raw_path", "media_type", "status"}
    if set(value) != expected:
        raise SourceContractError("source manifest resource fields do not match contract")
    size_bytes = value["size_bytes"]
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
        raise SourceContractError("source manifest size_bytes must be an integer")
    status = _required_string(value, "status")
    if status not in ("acquired", "verified_existing"):
        raise SourceContractError("invalid source resource status")
    return ManifestResource(
        path=_required_string(value, "path"),
        size_bytes=size_bytes,
        sha256=_required_string(value, "sha256"),
        raw_path=_required_string(value, "raw_path"),
        media_type=_required_string(value, "media_type"),
        status=cast(ResourceStatus, status),
    )


def _parse_manifest(value: dict[str, object]) -> SourceManifest:
    expected = {
        "contract",
        "provider",
        "repository",
        "source_git_sha",
        "license",
        "license_url",
        "attribution",
        "acquired_at",
        "resources",
    }
    if set(value) != expected:
        raise SourceContractError("source manifest fields do not match SourceManifestV1")
    resources = value["resources"]
    if not isinstance(resources, list):
        raise SourceContractError("source manifest resources must be an array")
    snapshot = SourceSnapshot(
        provider=_required_string(value, "provider"),
        repository=_required_string(value, "repository"),
        source_git_sha=_required_string(value, "source_git_sha"),
        license=_required_string(value, "license"),
        license_url=_required_string(value, "license_url"),
        attribution=_required_string(value, "attribution"),
    )
    return SourceManifest(
        contract=_required_string(value, "contract"),
        snapshot=snapshot,
        acquired_at=_parse_datetime(_required_string(value, "acquired_at")),
        resources=tuple(_parse_resource(resource) for resource in resources),
    )
