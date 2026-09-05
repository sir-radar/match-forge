from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from football.contracts.source import (
    SHA1_PATTERN,
    SHA256_PATTERN,
    canonical_json_bytes,
    validate_relative_posix_path,
)


class DatasetBuildSpecError(ValueError):
    """A deterministic dataset build specification violates its contract."""


RebuildRequestReasonV1 = Literal["SOURCE_CORRECTION", "MANUAL_REPLAY", "FAILED_PUBLICATION"]
RebuildRequestStatusV1 = Literal["REQUESTED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
_REBUILD_REASONS = frozenset(("SOURCE_CORRECTION", "MANUAL_REPLAY", "FAILED_PUBLICATION"))
_REBUILD_STATUSES = frozenset(("REQUESTED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"))


@dataclass(frozen=True, slots=True)
class DatasetBuildSpecV1:
    """Immutable inputs and policy identity for one dataset build."""

    dataset_contract: str
    dataset_version: str
    source_input_refs: tuple[str, ...]
    canonical_input_refs: tuple[str, ...]
    football_cutoff: datetime | None
    knowledge_cutoff: datetime | None
    knowledge_mode: Literal["historical", "current"] | None
    feature_versions: tuple[str, ...]
    quality_policy_version: str
    resolution_policy_version: str
    code_git_sha: str
    dependency_lock_sha256: str
    configuration: dict[str, object]
    contract: str = "DatasetBuildSpecV1"

    def __post_init__(self) -> None:
        if self.contract != "DatasetBuildSpecV1":
            raise DatasetBuildSpecError("unsupported dataset build specification contract")
        if not self.dataset_contract or not self.dataset_version:
            raise DatasetBuildSpecError("dataset contract and version are required")
        _require_unique_refs(self.source_input_refs, "source inputs")
        _require_unique_refs(self.canonical_input_refs, "canonical inputs")
        if not self.source_input_refs and not self.canonical_input_refs:
            raise DatasetBuildSpecError("dataset build requires immutable input references")
        if not self.feature_versions or any(not value for value in self.feature_versions):
            raise DatasetBuildSpecError("feature versions are required")
        if not self.quality_policy_version or not self.resolution_policy_version:
            raise DatasetBuildSpecError("quality and resolution policy versions are required")
        if not SHA1_PATTERN.fullmatch(self.code_git_sha):
            raise DatasetBuildSpecError("code_git_sha must be a 40-character lowercase Git SHA")
        if not SHA256_PATTERN.fullmatch(self.dependency_lock_sha256):
            raise DatasetBuildSpecError("dependency lock must be a SHA-256")
        if self.knowledge_mode not in {None, "historical", "current"}:
            raise DatasetBuildSpecError("knowledge mode is unsupported")
        _validate_cutoffs(self)
        try:
            canonical_json_bytes(self.configuration)
        except (TypeError, ValueError) as error:
            raise DatasetBuildSpecError("configuration must be canonical JSON") from error

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "dataset_contract": self.dataset_contract,
            "dataset_version": self.dataset_version,
            "source_input_refs": list(self.source_input_refs),
            "canonical_input_refs": list(self.canonical_input_refs),
            "football_cutoff": _iso(self.football_cutoff),
            "knowledge_cutoff": _iso(self.knowledge_cutoff),
            "knowledge_mode": self.knowledge_mode,
            "feature_versions": list(self.feature_versions),
            "quality_policy_version": self.quality_policy_version,
            "resolution_policy_version": self.resolution_policy_version,
            "code_git_sha": self.code_git_sha,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "configuration": self.configuration,
        }


def _require_unique_refs(values: tuple[str, ...], label: str) -> None:
    if any(not value for value in values):
        raise DatasetBuildSpecError(f"{label} must not contain empty references")
    if len(values) != len(set(values)):
        raise DatasetBuildSpecError(f"{label} must be unique")


def _validate_cutoffs(spec: DatasetBuildSpecV1) -> None:
    for name, value in (
        ("football_cutoff", spec.football_cutoff),
        ("knowledge_cutoff", spec.knowledge_cutoff),
    ):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise DatasetBuildSpecError(f"{name} must include a timezone")
    if spec.knowledge_mode == "historical" and spec.knowledge_cutoff is None:
        raise DatasetBuildSpecError("historical knowledge mode requires a cutoff")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@dataclass(frozen=True, slots=True)
class DatasetRebuildRequestV1:
    """Durable, idempotent request to produce a new dataset version."""

    request_id: str
    dataset_ref: str
    build_spec_sha256: str
    requested_at: datetime
    reason: RebuildRequestReasonV1
    status: RebuildRequestStatusV1
    attempt: int = 1
    source_change_set_ref: str | None = None
    contract: str = "DatasetRebuildRequestV1"

    def __post_init__(self) -> None:
        if self.contract != "DatasetRebuildRequestV1":
            raise DatasetBuildSpecError("unsupported dataset rebuild request contract")
        if not self.request_id or not self.dataset_ref:
            raise DatasetBuildSpecError("rebuild request identity is required")
        if not SHA256_PATTERN.fullmatch(self.build_spec_sha256):
            raise DatasetBuildSpecError("rebuild request build spec must be a SHA-256")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise DatasetBuildSpecError("rebuild request timestamp must include a timezone")
        if self.reason not in _REBUILD_REASONS:
            raise DatasetBuildSpecError("rebuild request reason is unsupported")
        if self.status not in _REBUILD_STATUSES:
            raise DatasetBuildSpecError("rebuild request status is unsupported")
        if self.attempt <= 0:
            raise DatasetBuildSpecError("rebuild request attempt must be positive")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "request_id": self.request_id,
            "dataset_ref": self.dataset_ref,
            "build_spec_sha256": self.build_spec_sha256,
            "requested_at": self.requested_at.isoformat(),
            "reason": self.reason,
            "status": self.status,
            "attempt": self.attempt,
            "source_change_set_ref": self.source_change_set_ref,
        }


@dataclass(frozen=True)
class DatasetManifestFile:
    relative_path: str
    row_count: int
    size_bytes: int
    physical_sha256: str
    logical_sha256: str

    def __post_init__(self) -> None:
        validate_relative_posix_path(self.relative_path)
        if not self.relative_path.endswith(".parquet"):
            raise ValueError("dataset manifest file must be Parquet")
        if self.row_count < 0 or self.size_bytes <= 0:
            raise ValueError("dataset manifest file counts are invalid")
        if not SHA256_PATTERN.fullmatch(self.physical_sha256) or not SHA256_PATTERN.fullmatch(
            self.logical_sha256
        ):
            raise ValueError("dataset manifest file checksums are invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "row_count": self.row_count,
            "size_bytes": self.size_bytes,
            "physical_sha256": self.physical_sha256,
            "logical_sha256": self.logical_sha256,
        }


@dataclass(frozen=True)
class DatasetManifest:
    dataset_version_id: UUID
    dataset_name: str
    schema_version: str
    schema_sha256: str
    source_git_sha: str
    normalizer_version: str
    files: tuple[DatasetManifestFile, ...]
    build_spec: DatasetBuildSpecV1 | None = None
    build_spec_sha256: str | None = None
    contract: str = "DatasetManifestV1"

    def __post_init__(self) -> None:
        if self.contract != "DatasetManifestV1":
            raise ValueError("unsupported dataset manifest contract")
        if not self.dataset_name or not self.schema_version or not self.normalizer_version:
            raise ValueError("dataset manifest metadata must not be empty")
        if not SHA256_PATTERN.fullmatch(self.schema_sha256):
            raise ValueError("dataset manifest schema checksum is invalid")
        if not SHA1_PATTERN.fullmatch(self.source_git_sha):
            raise ValueError("dataset manifest source revision is invalid")
        if not self.files:
            raise ValueError("dataset manifest requires at least one file")
        paths = [file.relative_path for file in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("dataset manifest file paths must be unique")
        if (self.build_spec is None) != (self.build_spec_sha256 is None):
            raise ValueError("dataset manifest build specification is incomplete")
        if self.build_spec is not None and self.build_spec_sha256 != self.build_spec.sha256:
            raise ValueError("dataset manifest build specification checksum conflicts")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract": self.contract,
            "dataset_version_id": str(self.dataset_version_id),
            "dataset_name": self.dataset_name,
            "schema_version": self.schema_version,
            "schema_sha256": self.schema_sha256,
            "source_git_sha": self.source_git_sha,
            "normalizer_version": self.normalizer_version,
            "files": [file.to_dict() for file in self.files],
        }
        if self.build_spec is not None:
            payload["build_spec"] = self.build_spec.to_dict()
            payload["build_spec_sha256"] = self.build_spec_sha256
        return payload

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"
