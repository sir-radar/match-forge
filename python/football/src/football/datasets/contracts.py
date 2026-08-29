from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from football.contracts.source import (
    SHA1_PATTERN,
    SHA256_PATTERN,
    canonical_json_bytes,
    validate_relative_posix_path,
)


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

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "dataset_version_id": str(self.dataset_version_id),
            "dataset_name": self.dataset_name,
            "schema_version": self.schema_version,
            "schema_sha256": self.schema_sha256,
            "source_git_sha": self.source_git_sha,
            "normalizer_version": self.normalizer_version,
            "files": [file.to_dict() for file in self.files],
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"
