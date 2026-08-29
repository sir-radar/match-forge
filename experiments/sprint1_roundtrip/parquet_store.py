from __future__ import annotations

import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from jsonschema import validate as validate_json

from experiments.sprint1_roundtrip import NORMALIZER_VERSION
from experiments.sprint1_roundtrip.core import (
    DATASET_SCHEMA_PATH,
    PROJECT_ROOT,
    RUNTIME_ROOT,
    PrototypeError,
    dataset_uuid,
    event_schema_hash,
    load_fixture,
    load_json,
    logical_checksum,
    normalized_event_schema,
    sha256_bytes,
    sha256_path,
    three_sixty_schema,
    three_sixty_schema_hash,
    write_json_exclusive_or_verify,
)


@dataclass(frozen=True)
class PublishedFile:
    dataset_version_id: str
    dataset_name: str
    schema_version: str
    schema_sha256: str
    relative_path: str
    absolute_path: str
    physical_sha256: str
    logical_sha256: str
    row_count: int
    size_bytes: int
    status: str


def _write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=9,
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
        row_group_size=65536,
    )


def _publish(
    rows: list[dict[str, Any]],
    dataset_name: str,
    schema_version: str,
    schema_hash: str,
    schema: pa.Schema,
    competition_id: uuid.UUID,
    season_id: uuid.UUID,
    match_id: uuid.UUID,
    inject_staging_failure: bool = False,
) -> PublishedFile:
    fixture = load_fixture()
    dataset_id = dataset_uuid(str(fixture["source_git_sha"]), schema_hash, dataset_name)
    relative_path = (
        Path("normalized")
        / dataset_name
        / f"schema={schema_version}"
        / f"dataset={dataset_id}"
        / (f"competition_id={competition_id}")
        / f"season_id={season_id}"
        / f"match_id={match_id}"
        / f"{dataset_name}.parquet"
    )
    final_path = RUNTIME_ROOT / relative_path
    final_path.parent.mkdir(parents=True, exist_ok=True)
    expected_logical = logical_checksum(rows)

    if final_path.exists():
        read_table = pq.read_table(final_path, schema=schema)
        read_rows = read_table.to_pylist()
        actual_logical = logical_checksum(read_rows)
        if actual_logical != expected_logical or read_table.num_rows != len(rows):
            raise PrototypeError(
                "PARQUET_LOGICAL_CHECKSUM_MISMATCH",
                f"published Parquet conflicts with expected logical content: {final_path}",
            )
        status = "verified_published"
    else:
        staging_root = RUNTIME_ROOT / "staging" / str(dataset_id)
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_path = staging_root / f"{dataset_name}.parquet.part"
        _write_parquet(staging_path, rows, schema)
        staged_table = pq.read_table(staging_path, schema=schema)
        if staged_table.num_rows != len(rows):
            raise PrototypeError("PARQUET_ROW_COUNT_MISMATCH", str(staging_path))
        if logical_checksum(staged_table.to_pylist()) != expected_logical:
            raise PrototypeError("PARQUET_LOGICAL_CHECKSUM_MISMATCH", str(staging_path))
        if inject_staging_failure:
            raise PrototypeError(
                "INJECTED_PARQUET_STAGING_FAILURE",
                "injected after staging and before immutable publication",
            )
        os.replace(staging_path, final_path)
        status = "published"

    return PublishedFile(
        dataset_version_id=str(dataset_id),
        dataset_name=dataset_name,
        schema_version=schema_version,
        schema_sha256=schema_hash,
        relative_path=str(relative_path),
        absolute_path=str(final_path),
        physical_sha256=sha256_path(final_path),
        logical_sha256=expected_logical,
        row_count=len(rows),
        size_bytes=final_path.stat().st_size,
        status=status,
    )


def publish_events(
    rows: list[dict[str, Any]],
    competition_id: uuid.UUID,
    season_id: uuid.UUID,
    match_id: uuid.UUID,
) -> PublishedFile:
    return _publish(
        rows,
        "events",
        "v1",
        event_schema_hash(),
        normalized_event_schema(),
        competition_id,
        season_id,
        match_id,
    )


def publish_three_sixty(
    rows: list[dict[str, Any]],
    competition_id: uuid.UUID,
    season_id: uuid.UUID,
    match_id: uuid.UUID,
) -> PublishedFile:
    return _publish(
        rows,
        "three_sixty",
        "v1",
        three_sixty_schema_hash(),
        three_sixty_schema(),
        competition_id,
        season_id,
        match_id,
    )


def create_dataset_manifest(
    source_sha: str,
    published: list[PublishedFile],
) -> tuple[dict[str, Any], Path, str]:
    events_file = next(item for item in published if item.dataset_name == "events")
    manifest = {
        "contract": "DatasetManifestV1",
        "dataset_version_id": events_file.dataset_version_id,
        "dataset_name": "events",
        "schema_version": events_file.schema_version,
        "schema_sha256": events_file.schema_sha256,
        "source_git_sha": source_sha,
        "normalizer_version": NORMALIZER_VERSION,
        "files": [
            {
                "relative_path": item.relative_path,
                "row_count": item.row_count,
                "size_bytes": item.size_bytes,
                "physical_sha256": item.physical_sha256,
                "logical_sha256": item.logical_sha256,
            }
            for item in published
        ],
    }
    validate_json(manifest, load_json(DATASET_SCHEMA_PATH))
    manifest_path = RUNTIME_ROOT / "manifests" / "dataset-manifest-v1.json"
    write_json_exclusive_or_verify(manifest_path, manifest)
    return manifest, manifest_path, sha256_path(manifest_path)


def prove_deterministic_rebuild(
    rows: list[dict[str, Any]],
    published: PublishedFile,
) -> dict[str, Any]:
    rebuild_path = RUNTIME_ROOT / "rebuild" / "events.parquet"
    rebuild_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = rebuild_path.with_suffix(".parquet.part")
    _write_parquet(temporary, rows, normalized_event_schema())
    os.replace(temporary, rebuild_path)
    rebuild_table = pq.read_table(rebuild_path, schema=normalized_event_schema())
    rebuild_logical = logical_checksum(rebuild_table.to_pylist())
    rebuild_physical = sha256_path(rebuild_path)
    return {
        "schema_hash_match": event_schema_hash() == published.schema_sha256,
        "row_count_match": rebuild_table.num_rows == published.row_count,
        "logical_checksum_match": rebuild_logical == published.logical_sha256,
        "physical_checksum_match": rebuild_physical == published.physical_sha256,
        "rebuild_logical_sha256": rebuild_logical,
        "rebuild_physical_sha256": rebuild_physical,
    }


def prove_staging_failure(
    rows: list[dict[str, Any]],
    competition_id: uuid.UUID,
    season_id: uuid.UUID,
    match_id: uuid.UUID,
) -> dict[str, Any]:
    schema_hash = sha256_bytes(b"failure-staging-schema-v1")
    dataset_id = dataset_uuid(load_fixture()["source_git_sha"], schema_hash, "failure_staging")
    final_path = (
        RUNTIME_ROOT / "failure-fixtures" / "staging-failure" / str(dataset_id) / "events.parquet"
    )
    if final_path.exists():
        raise PrototypeError("UNEXPECTED_FINAL_ARTIFACT", str(final_path))
    staging_path = final_path.with_suffix(".parquet.part")
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    _write_parquet(staging_path, rows[:10], normalized_event_schema())
    injected = True
    return {
        "injected": injected,
        "final_path_absent": not final_path.exists(),
        "staging_artifact_recognizable": staging_path.exists(),
        "staging_path": str(staging_path.relative_to(PROJECT_ROOT)),
        "partition_ids": [str(competition_id), str(season_id), str(match_id)],
    }


def published_file_dict(item: PublishedFile) -> dict[str, Any]:
    return asdict(item)
