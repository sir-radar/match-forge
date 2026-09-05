from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.datasets.contracts import DatasetManifest, DatasetManifestFile
from football.forecasting.artifacts import ModelArtifactPublisher
from football.forecasting.contracts import ModelFitSpecV1, PointInTimeScopeV1
from football.integrity import PostgresIntegrityVerifier
from football.normalization.statsbomb_events import EVENT_SCHEMA_SHA256, NORMALIZER_VERSION
from football.storage.parquet import ImmutableEventParquetStore
from football.storage.raw import ImmutableFileStore
from psycopg import Connection

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


def test_verifies_registered_raw_dataset_and_model_bytes(
    connection: Connection[Any], tmp_path: Path
) -> None:
    raw_id, dataset_id, artifact_id, paths = _registered_artifacts(connection, tmp_path)
    verifier = PostgresIntegrityVerifier(connection, tmp_path)

    raw = verifier.verify_raw_resource(raw_id)
    dataset = verifier.verify_dataset(dataset_id)
    model = verifier.verify_model_artifact(artifact_id)

    assert raw.status == "PASS"
    assert dataset.status == "PASS"
    assert model.status == "PASS"
    assert raw.expected_sha256 == raw.actual_sha256
    assert dataset.expected_sha256 == dataset.actual_sha256
    assert model.expected_sha256 == model.actual_sha256
    assert all(result.status == "PASS" for result in model.files)
    assert {item.path for item in (raw, dataset, model)} == {
        paths["raw"],
        paths["dataset_manifest"],
        paths["model_manifest"],
    }
    report = verifier.build_report(
        report_id="integrity-test-1",
        policy_version="foundation-integrity-v1",
        created_at=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        code_git_sha="4" * 40,
        dependency_lock_sha256="5" * 64,
        raw_resources=(raw,),
        datasets=(dataset,),
        model_artifacts=(model,),
        postgres_backup="PASS",
        postgres_restore="PASS",
        forecast_evaluation_integrity="PASS",
    )

    assert report.status == "PASS"
    assert report.to_dict()["contract"] == "IntegrityVerificationReportV1"


@pytest.mark.parametrize("kind", ("raw", "dataset", "model"))
def test_detects_missing_registered_artifact_bytes(
    connection: Connection[Any], tmp_path: Path, kind: str
) -> None:
    raw_id, dataset_id, artifact_id, paths = _registered_artifacts(connection, tmp_path)
    verifier = PostgresIntegrityVerifier(connection, tmp_path)
    target = {
        "raw": paths["raw"],
        "dataset": paths["dataset"],
        "model": paths["model"],
    }[kind]
    (tmp_path / target).unlink()

    result = {
        "raw": lambda: verifier.verify_raw_resource(raw_id),
        "dataset": lambda: verifier.verify_dataset(dataset_id),
        "model": lambda: verifier.verify_model_artifact(artifact_id),
    }[kind]()

    assert result.status == "MISSING"
    assert result.failure_reason == "registered bytes are missing"


@pytest.mark.parametrize("kind", ("raw", "dataset", "model"))
def test_detects_changed_registered_artifact_bytes(
    connection: Connection[Any], tmp_path: Path, kind: str
) -> None:
    raw_id, dataset_id, artifact_id, paths = _registered_artifacts(connection, tmp_path)
    verifier = PostgresIntegrityVerifier(connection, tmp_path)
    target = {
        "raw": paths["raw"],
        "dataset": paths["dataset"],
        "model": paths["model"],
    }[kind]
    (tmp_path / target).write_bytes(b"changed bytes")

    result = {
        "raw": lambda: verifier.verify_raw_resource(raw_id),
        "dataset": lambda: verifier.verify_dataset(dataset_id),
        "model": lambda: verifier.verify_model_artifact(artifact_id),
    }[kind]()

    assert result.status == "CHECKSUM_MISMATCH"
    assert result.failure_reason == "registered checksum does not match bytes"


def test_integrity_report_fails_closed_when_a_selected_artifact_fails(
    connection: Connection[Any], tmp_path: Path
) -> None:
    raw_id, dataset_id, artifact_id, paths = _registered_artifacts(connection, tmp_path)
    verifier = PostgresIntegrityVerifier(connection, tmp_path)
    (tmp_path / paths["dataset"]).write_bytes(b"changed bytes")

    report = verifier.build_report(
        report_id="integrity-test-2",
        policy_version="foundation-integrity-v1",
        created_at=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        code_git_sha="4" * 40,
        dependency_lock_sha256="5" * 64,
        raw_resources=(verifier.verify_raw_resource(raw_id),),
        datasets=(verifier.verify_dataset(dataset_id),),
        model_artifacts=(verifier.verify_model_artifact(artifact_id),),
        postgres_backup="PASS",
        postgres_restore="PASS",
        forecast_evaluation_integrity="PASS",
    )

    assert report.dataset_manifest_integrity == "FAIL"
    assert report.status == "FAIL"


@pytest.mark.parametrize(
    ("kind", "statement"),
    (
        (
            "dataset",
            "UPDATE football.dataset_versions SET schema_version = 'v2' WHERE id = %s",
        ),
        (
            "model",
            "UPDATE football.model_artifacts SET schema_version = 'v2' WHERE id = %s",
        ),
    ),
)
def test_rejects_conflicting_or_invalid_registration(
    connection: Connection[Any],
    tmp_path: Path,
    kind: str,
    statement: str,
) -> None:
    raw_id, dataset_id, artifact_id, _ = _registered_artifacts(connection, tmp_path)
    artifact_id_by_kind = {"raw": raw_id, "dataset": dataset_id, "model": artifact_id}
    with connection.cursor() as cursor:
        cursor.execute(statement, (artifact_id_by_kind[kind],))
    verifier = PostgresIntegrityVerifier(connection, tmp_path)

    result = {
        "raw": lambda: verifier.verify_raw_resource(raw_id),
        "dataset": lambda: verifier.verify_dataset(dataset_id),
        "model": lambda: verifier.verify_model_artifact(artifact_id),
    }[kind]()

    assert result.status == "INVALID_REGISTRATION"


def _registered_artifacts(
    connection: Connection[Any], data_root: Path
) -> tuple[UUID, UUID, UUID, dict[str, str]]:
    now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    raw_path = "raw/provider=statsbomb_open_data/snapshot=" + "a" * 40 + "/data/test.json"
    raw_write = ImmutableFileStore(data_root).publish(raw_path, b'{"match":1}\n')
    with connection.cursor() as cursor:
        provider_row = cursor.execute(
            """
            INSERT INTO football.providers (code, name, source_type)
            VALUES ('statsbomb_open_data', 'StatsBomb Open Data', 'git_repository')
            RETURNING id
            """
        ).fetchone()
        assert provider_row is not None
        provider_id = provider_row[0]
        snapshot_row = cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, repository, git_sha,
                 acquired_at, manifest_path, manifest_sha256, status)
            VALUES (%s, 'integrity-test', %s, 'https://example.test', %s, %s,
                    'manifests/source.json', %s, 'acquired')
            RETURNING id
            """,
            (provider_id, "a" * 40, "a" * 40, now, "b" * 64),
        ).fetchone()
        assert snapshot_row is not None
        snapshot_id = snapshot_row[0]
        raw_row = cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, 'data/test.json', %s, %s, 'application/json', 'parsed', 'valid', %s)
            RETURNING id
            """,
            (snapshot_id, raw_write.sha256, raw_write.size_bytes, now),
        ).fetchone()
        assert raw_row is not None
        raw_id = raw_row[0]
        dataset_row = cursor.execute("SELECT uuidv7()").fetchone()
        artifact_row = cursor.execute("SELECT uuidv7()").fetchone()
        assert dataset_row is not None and artifact_row is not None
        dataset_id = dataset_row[0]
        artifact_id = artifact_row[0]

    dataset_path = f"normalized/events/dataset={dataset_id}/events.parquet"
    dataset_write = ImmutableEventParquetStore(data_root).publish(dataset_path, [_event_row()])
    manifest_path = f"manifests/datasets/dataset={dataset_id}/dataset-manifest-v1.json"
    manifest = DatasetManifest(
        dataset_version_id=dataset_id,
        dataset_name="events",
        schema_version="v1",
        schema_sha256=EVENT_SCHEMA_SHA256,
        source_git_sha="a" * 40,
        normalizer_version=NORMALIZER_VERSION,
        files=(
            DatasetManifestFile(
                relative_path=dataset_write.relative_path,
                row_count=dataset_write.row_count,
                size_bytes=dataset_write.size_bytes,
                physical_sha256=dataset_write.physical_sha256,
                logical_sha256=dataset_write.logical_sha256,
            ),
        ),
    )
    manifest_write = ImmutableFileStore(data_root).publish(manifest_path, manifest.to_bytes())
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'events', 'normalized', %s, 'v1', %s,
                    'statsbomb-normalizer-v1', %s, %s, 'published', %s)
            """,
            (
                dataset_id,
                snapshot_id,
                uuid4().hex * 2,
                EVENT_SCHEMA_SHA256,
                manifest_path,
                manifest_write.sha256,
                now,
            ),
        )
        cursor.execute(
            """
            INSERT INTO football.dataset_files
                (dataset_version_id, relative_path, physical_sha256, logical_sha256,
                 row_count, size_bytes, schema_sha256)
            VALUES (%s, %s, %s, %s, 1, %s, %s)
            """,
            (
                dataset_id,
                dataset_path,
                dataset_write.physical_sha256,
                dataset_write.logical_sha256,
                dataset_write.size_bytes,
                EVENT_SCHEMA_SHA256,
            ),
        )

    fit_spec = ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="integrity-v1",
        config_sha256="e" * 64,
        scope=PointInTimeScopeV1(
            dataset_version_id=dataset_id,
            source_snapshot_id=snapshot_id,
            feature_set_version="sprint2-features-v1",
            football_cutoff=now,
            knowledge_cutoff=now,
            knowledge_mode="bitemporal",
            quality_policy_sha256="f" * 64,
            target_set_sha256="1" * 64,
        ),
        code_commit_sha="2" * 40,
        dependency_lock_sha256="3" * 64,
    )
    artifact = ModelArtifactPublisher(connection, data_root).publish(
        model_artifact_id=artifact_id,
        fit_spec=fit_spec,
        state={"contract": "IntegrityTestStateV1", "coefficient": 0.2},
        created_at=now,
    )
    return (
        UUID(str(raw_id)),
        UUID(str(dataset_id)),
        UUID(str(artifact_id)),
        {
            "raw": raw_path,
            "dataset": dataset_path,
            "dataset_manifest": manifest_path,
            "model": artifact.manifest.files[0].relative_path,
            "model_manifest": artifact.manifest_path,
        },
    )


def _event_row() -> dict[str, object]:
    return {
        "canonical_event_id": "10000000-0000-4000-8000-000000000001",
        "canonical_match_id": "20000000-0000-4000-8000-000000000001",
        "provider_event_id": "30000000-0000-4000-8000-000000000001",
        "provider_match_id": "1",
        "event_index": 1,
        "period": 1,
        "timestamp": "00:00:00.000",
        "minute": 0,
        "second": 0,
        "provider_event_type_id": "30",
        "provider_event_type_name": "Pass",
        "canonical_event_type_id": "pass",
        "canonical_team_id": None,
        "provider_team_id": None,
        "canonical_player_id": None,
        "provider_player_id": None,
        "source_coordinate_system": None,
        "source_x": None,
        "source_y": None,
        "x_norm": None,
        "y_norm": None,
        "location_quality": "missing",
        "provider_payload_json": "{}",
    }
