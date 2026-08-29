from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from football.contracts.source import validate_relative_posix_path
from football.normalization.statsbomb_events import logical_sha256

EVENT_ARROW_SCHEMA = pa.schema(
    [
        pa.field("canonical_event_id", pa.string(), nullable=False),
        pa.field("canonical_match_id", pa.string(), nullable=False),
        pa.field("provider_event_id", pa.string(), nullable=False),
        pa.field("provider_match_id", pa.string(), nullable=False),
        pa.field("event_index", pa.int32(), nullable=False),
        pa.field("period", pa.int8(), nullable=False),
        pa.field("timestamp", pa.string(), nullable=False),
        pa.field("minute", pa.int16(), nullable=False),
        pa.field("second", pa.int16(), nullable=False),
        pa.field("provider_event_type_id", pa.string(), nullable=False),
        pa.field("provider_event_type_name", pa.string(), nullable=False),
        pa.field("canonical_event_type_id", pa.string()),
        pa.field("canonical_team_id", pa.string()),
        pa.field("provider_team_id", pa.string()),
        pa.field("canonical_player_id", pa.string()),
        pa.field("provider_player_id", pa.string()),
        pa.field("source_coordinate_system", pa.string()),
        pa.field("source_x", pa.float64()),
        pa.field("source_y", pa.float64()),
        pa.field("x_norm", pa.float64()),
        pa.field("y_norm", pa.float64()),
        pa.field("location_quality", pa.string(), nullable=False),
        pa.field("provider_payload_json", pa.string(), nullable=False),
    ]
)


class ParquetPublicationError(RuntimeError):
    """Immutable Parquet publication or verification failed."""


@dataclass(frozen=True)
class PublishedParquetFile:
    relative_path: str
    absolute_path: Path
    physical_sha256: str
    logical_sha256: str
    row_count: int
    size_bytes: int
    status: str


class ImmutableEventParquetStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def publish(
        self,
        relative_path: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> PublishedParquetFile:
        final_path = self._path_for(relative_path)
        materialized = tuple(dict(row) for row in rows)
        table = _event_table(materialized)
        expected_logical = logical_sha256(materialized)
        if final_path.exists() or final_path.is_symlink():
            return self._verify(final_path, relative_path, expected_logical, len(materialized))
        final_path.parent.mkdir(parents=True, exist_ok=True)
        _assert_beneath(self._root, final_path)
        staging_path = self._staging_path(relative_path)
        _assert_beneath(self._root, staging_path)
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        if not staging_path.exists():
            self._write_staging(staging_path, table)
        self._verify(staging_path, relative_path, expected_logical, len(materialized))
        try:
            os.link(staging_path, final_path)
            _fsync_directory(final_path.parent)
            status = "published"
        except FileExistsError:
            self._verify(final_path, relative_path, expected_logical, len(materialized))
            status = "verified_published"
        staging_path.unlink(missing_ok=True)
        verified = self._verify(final_path, relative_path, expected_logical, len(materialized))
        return PublishedParquetFile(
            relative_path=verified.relative_path,
            absolute_path=verified.absolute_path,
            physical_sha256=verified.physical_sha256,
            logical_sha256=verified.logical_sha256,
            row_count=verified.row_count,
            size_bytes=verified.size_bytes,
            status=status,
        )

    def read_rows(self, relative_path: str) -> tuple[dict[str, Any], ...]:
        path = self._path_for(relative_path)
        table = _read_event_table(path)
        return tuple(table.to_pylist())

    def _path_for(self, relative_path: str) -> Path:
        validated = validate_relative_posix_path(relative_path)
        if not validated.endswith(".parquet"):
            raise ParquetPublicationError("event dataset path must end with .parquet")
        path = self._root.joinpath(*validated.split("/"))
        _assert_beneath(self._root, path)
        return path

    def _staging_path(self, relative_path: str) -> Path:
        identity = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
        filename = Path(relative_path).name
        return self._root / "staging" / "datasets" / identity / f"{filename}.part"

    def _write_staging(self, staging_path: Path, table: pa.Table) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".write-",
            suffix=".parquet",
            dir=staging_path.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            pq.write_table(
                table,
                temporary,
                compression="zstd",
                compression_level=9,
                use_dictionary=False,
                write_statistics=True,
                data_page_version="1.0",
                row_group_size=65536,
            )
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            try:
                os.link(temporary, staging_path)
                _fsync_directory(staging_path.parent)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)

    def _verify(
        self,
        path: Path,
        relative_path: str,
        expected_logical: str,
        expected_rows: int,
    ) -> PublishedParquetFile:
        try:
            table = _read_event_table(path)
            rows = tuple(table.to_pylist())
            actual_logical = logical_sha256(rows)
        except (OSError, ValueError, pa.ArrowException) as error:
            raise ParquetPublicationError(
                f"published Parquet is invalid: {relative_path}"
            ) from error
        if table.num_rows != expected_rows or actual_logical != expected_logical:
            raise ParquetPublicationError(
                f"published Parquet conflicts with expected logical content: {relative_path}"
            )
        return PublishedParquetFile(
            relative_path=relative_path,
            absolute_path=path,
            physical_sha256=_sha256_path(path),
            logical_sha256=actual_logical,
            row_count=table.num_rows,
            size_bytes=path.stat().st_size,
            status="verified_published",
        )


def _event_table(rows: Sequence[Mapping[str, Any]]) -> pa.Table:
    try:
        return pa.Table.from_pylist([dict(row) for row in rows], schema=EVENT_ARROW_SCHEMA)
    except (TypeError, ValueError, pa.ArrowException) as error:
        raise ParquetPublicationError(
            "event rows do not satisfy normalized Arrow schema"
        ) from error


def _read_event_table(path: Path) -> pa.Table:
    if not path.is_file() or path.is_symlink():
        raise ParquetPublicationError(f"published Parquet is not a regular file: {path}")
    table = pq.ParquetFile(path).read()
    if not table.schema.equals(EVENT_ARROW_SCHEMA, check_metadata=False):
        raise ParquetPublicationError(f"published Parquet schema conflicts: {path}")
    return table


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_beneath(root: Path, path: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as error:
        raise ParquetPublicationError(f"dataset path escapes configured root: {path}") from error


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
