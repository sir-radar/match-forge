from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import Connection
from psycopg.errors import RaiseException
from psycopg.types.json import Jsonb

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
_TEMPORARY_RESTORE_PREFIX = "football_restore_test_"
_TEMPORARY_SOURCE_PREFIX = "football_storage_test_"


@dataclass(frozen=True)
class _RecoverySeed:
    source_resource_id: UUID
    fixture_snapshot_id: UUID
    fixture_change_set_id: UUID
    dataset_id: UUID
    model_artifact_id: UUID
    forecast_id: UUID
    evaluation_id: UUID


@dataclass(frozen=True)
class _RecoveryReport:
    source_database: str
    source_server_version: str
    migration_version: object
    backup_created_at: datetime
    code_git_sha: str
    dependency_lock_sha256: str
    backup_size_bytes: int
    backup_sha256: str
    restore_database: str
    restore_isolated: bool
    restore_completed: bool
    schema_verification: bool
    authoritative_state_verification: bool
    immutable_identity_verification: bool
    registered_checksum_verification: bool
    source_unchanged_verification: bool

    def to_json(self) -> str:
        return json.dumps(
            {
                "authoritative_state_verification": self.authoritative_state_verification,
                "backup_created_at": self.backup_created_at.isoformat(),
                "backup_sha256": self.backup_sha256,
                "backup_size_bytes": self.backup_size_bytes,
                "code_git_sha": self.code_git_sha,
                "dependency_lock_sha256": self.dependency_lock_sha256,
                "immutable_identity_verification": self.immutable_identity_verification,
                "migration_version": self.migration_version,
                "registered_checksum_verification": self.registered_checksum_verification,
                "restore_completed": self.restore_completed,
                "restore_database": self.restore_database,
                "restore_isolated": self.restore_isolated,
                "schema_verification": self.schema_verification,
                "source_database": self.source_database,
                "source_server_version": self.source_server_version,
                "source_unchanged_verification": self.source_unchanged_verification,
                "result": "PASS",
            },
            sort_keys=True,
        )


@pytest.mark.parametrize("_run_number", (1, 2))
def test_postgresql_backup_restore_preserves_authoritative_state(
    tmp_path: Path, _run_number: int
) -> None:
    source_database = _database_name(DATABASE_URL)
    _require_temporary_source_database(source_database)
    restore_database = f"{_TEMPORARY_RESTORE_PREFIX}{os.getpid()}_{uuid4().hex[:12]}"
    _require_isolated_restore(source_database, restore_database)
    with psycopg.connect(DATABASE_URL) as source_connection:
        seed = _seed_source(source_connection)
        source_manifest = _manifest(source_connection, seed)
        source_schema = _schema_manifest(source_connection)
        source_server_version = _server_version(source_connection)
        backup_path = tmp_path / "postgres-recovery.dump"
        _backup(source_database, backup_path)
        backup_created_at = datetime.now(UTC)
        backup_sha256 = _sha256(backup_path)
        _assert_readable_backup(backup_path)
        _create_database(restore_database)
        try:
            _restore(restore_database, backup_path)
            restore_url = _database_url(DATABASE_URL, restore_database)
            with psycopg.connect(restore_url) as restored_connection:
                assert restored_connection.info.dbname == restore_database
                assert _manifest(restored_connection, seed) == source_manifest
                assert _schema_manifest(restored_connection) == source_schema
                _assert_fixture_remains_not_model_eligible(restored_connection, seed)
            assert _manifest(source_connection, seed) == source_manifest
        finally:
            _drop_database(restore_database)
    assert backup_path.stat().st_size > 0
    assert len(backup_sha256) == 64
    report = _RecoveryReport(
        source_database=source_database,
        source_server_version=source_server_version,
        migration_version=source_schema[0],
        backup_created_at=backup_created_at,
        code_git_sha=_git_sha(),
        dependency_lock_sha256=_sha256(_project_root() / "uv.lock"),
        backup_size_bytes=backup_path.stat().st_size,
        backup_sha256=backup_sha256,
        restore_database=restore_database,
        restore_isolated=source_database != restore_database,
        restore_completed=True,
        schema_verification=True,
        authoritative_state_verification=True,
        immutable_identity_verification=True,
        registered_checksum_verification=True,
        source_unchanged_verification=True,
    )
    print(report.to_json())


def test_postgresql_recovery_rejects_corrupt_backup(tmp_path: Path) -> None:
    restore_database = f"{_TEMPORARY_RESTORE_PREFIX}{os.getpid()}_{uuid4().hex[:12]}"
    corrupt_backup = tmp_path / "corrupt-postgres-recovery.dump"
    corrupt_backup.write_bytes(b"not a PostgreSQL custom-format backup")
    _create_database(restore_database)
    try:
        with pytest.raises(AssertionError):
            _restore(restore_database, corrupt_backup)
    finally:
        _drop_database(restore_database)


def test_postgresql_recovery_detects_restored_state_mismatch(tmp_path: Path) -> None:
    source_database = _database_name(DATABASE_URL)
    _require_temporary_source_database(source_database)
    restore_database = f"{_TEMPORARY_RESTORE_PREFIX}{os.getpid()}_{uuid4().hex[:12]}"
    _require_isolated_restore(source_database, restore_database)
    with psycopg.connect(DATABASE_URL) as source_connection:
        seed = _seed_source(source_connection)
        source_manifest = _manifest(source_connection, seed)
        backup_path = tmp_path / "postgres-recovery-mismatch.dump"
        _backup(source_database, backup_path)
        _create_database(restore_database)
        try:
            _restore(restore_database, backup_path)
            restore_url = _database_url(DATABASE_URL, restore_database)
            with psycopg.connect(restore_url) as restored_connection:
                with restored_connection.transaction(), restored_connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE football.source_resources SET size_bytes = 2 WHERE id = %s",
                        (seed.source_resource_id,),
                    )
                assert _manifest(restored_connection, seed) != source_manifest
            assert _manifest(source_connection, seed) == source_manifest
        finally:
            _drop_database(restore_database)


@pytest.mark.parametrize(
    ("database", "accepted"),
    (
        ("football_restore_test_123", True),
        ("football_storage_test_123", False),
        ("postgres", False),
    ),
)
def test_temporary_restore_database_guard(database: str, accepted: bool) -> None:
    if accepted:
        _require_temporary_database(database)
    else:
        with pytest.raises(AssertionError):
            _require_temporary_database(database)


def test_temporary_source_database_guard() -> None:
    _require_temporary_source_database("football_storage_test_123")
    with pytest.raises(AssertionError):
        _require_temporary_source_database("football")


def _seed_source(connection: Connection[Any]) -> _RecoverySeed:
    marker = uuid4().hex
    timestamp = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    with connection.transaction(), connection.cursor() as cursor:
        provider_id = UUID(
            str(
                cursor.execute(
                    """
                    INSERT INTO football.providers (code, name, source_type)
                    VALUES (%s, %s, 'file_download')
                    RETURNING id
                    """,
                    (f"recovery_{marker}", f"Recovery {marker}"),
                ).fetchone()[0]
            )
        )
        snapshot_id = cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, acquired_at, manifest_path,
                 manifest_sha256, status)
            VALUES (%s, %s, 'v1', %s, %s, %s, 'validated')
            RETURNING id
            """,
            (
                provider_id,
                f"recovery/{marker}",
                timestamp,
                f"manifests/{marker}.json",
                _checksum(marker, "source-manifest"),
            ),
        ).fetchone()[0]
        resource_id = cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, 'results.csv', %s, 1, 'text/csv', 'parsed', 'valid', %s)
            RETURNING id
            """,
            (snapshot_id, _checksum(marker, "source-resource"), timestamp),
        ).fetchone()[0]
        fixture_id = f"recovery_fixture_{marker}"
        fixture_snapshot_id = cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, acquired_at, manifest_path,
                 manifest_sha256, status, source_kind, fixture_id)
            VALUES (%s, %s, 'v1', %s, %s, %s, 'validated', 'CONTRACT_FIXTURE', %s)
            RETURNING id
            """,
            (
                provider_id,
                f"fixture://recovery/{marker}",
                timestamp,
                f"fixtures/{marker}.json",
                _checksum(marker, "fixture-manifest"),
                fixture_id,
            ),
        ).fetchone()[0]
        cursor.execute(
            "INSERT INTO football.fixture_sources (source_snapshot_id, fixture_id) VALUES (%s, %s)",
            (fixture_snapshot_id, fixture_id),
        )
        cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, 'fixture.csv', %s, 1, 'text/csv', 'parsed', 'valid', %s)
            """,
            (fixture_snapshot_id, _checksum(marker, "fixture-resource"), timestamp),
        )
        sync_run_id = cursor.execute(
            """
            INSERT INTO football.provider_sync_runs
                (provider_id, policy_version, status, run_key, started_at, completed_at)
            VALUES (%s, 'recovery-v1', 'succeeded', %s, %s, %s)
            RETURNING id
            """,
            (provider_id, uuid4().hex * 2, timestamp, timestamp),
        ).fetchone()[0]
        job_id = cursor.execute(
            """
            INSERT INTO football.acquisition_jobs
                (sync_run_id, provider_id, resource_key, scope_key, resource_identity,
                 resource_revision, status)
            VALUES (%s, %s, 'results', 'global', %s, 'v1', 'validated')
            RETURNING id
            """,
            (sync_run_id, provider_id, f"recovery/{marker}"),
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.acquired_resources
                (acquisition_job_id, source_snapshot_id, source_resource_id, raw_path, raw_sha256,
                 size_bytes, status, acquired_at)
            VALUES (%s, %s, %s, %s, %s, 1, 'validated', %s)
            """,
            (
                job_id,
                snapshot_id,
                resource_id,
                f"raw/{marker}.csv",
                _checksum(marker, "source-resource"),
                timestamp,
            ),
        )
        change_set_id = cursor.execute(
            """
            INSERT INTO football.canonical_change_sets
                (sync_run_id, change_key, status, changes, publication_scope, published_at)
            VALUES (%s, %s, 'published', %s, 'REAL_PROVIDER', %s)
            RETURNING id
            """,
            (
                sync_run_id,
                _checksum(marker, "change-set"),
                Jsonb(
                    {
                        "source_resources": [
                            {
                                "resource_ref": f"recovery_{marker}/results.csv",
                                "sha256": _checksum(marker, "source-resource"),
                            }
                        ],
                        "added_observation_refs": [],
                        "superseding_observation_refs": [],
                    }
                ),
                timestamp,
            ),
        ).fetchone()[0]
        fixture_change_set_id = cursor.execute(
            """
            INSERT INTO football.canonical_change_sets
                (sync_run_id, change_key, status, changes, publication_scope, published_at)
            VALUES (%s, %s, 'published', %s, 'CONTRACT_FIXTURE', %s)
            RETURNING id
            """,
            (
                sync_run_id,
                _checksum(marker, "fixture-change-set"),
                Jsonb(
                    {
                        "source_resources": [
                            {
                                "resource_ref": f"fixture://recovery/{marker}/fixture.csv",
                                "sha256": _checksum(marker, "fixture-resource"),
                            }
                        ],
                        "added_observation_refs": [],
                        "superseding_observation_refs": [],
                    }
                ),
                timestamp,
            ),
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.quarantine_records
                (acquisition_job_id, source_resource_id, finding_key, reason_code, details, status)
            VALUES (%s, %s, %s, 'RECOVERY_TEST', '{}'::jsonb, 'open')
            """,
            (job_id, resource_id, _checksum(marker, "quarantine")),
        )
        dataset_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'recovery_data', 'normalized', %s, 'v1', %s, 'recovery-v1',
                    %s, %s, 'published', %s)
            """,
            (
                dataset_id,
                snapshot_id,
                _checksum(marker, "dataset-identity"),
                _checksum(marker, "dataset-schema"),
                f"manifests/{marker}.json",
                _checksum(marker, "dataset-manifest"),
                timestamp,
            ),
        )
        cursor.execute(
            """
            INSERT INTO football.dataset_inputs
                (dataset_version_id, source_snapshot_id, source_resource_id, input_role)
            VALUES (%s, %s, %s, 'source')
            """,
            (dataset_id, snapshot_id, resource_id),
        )
        cursor.execute(
            """
            INSERT INTO football.dataset_files
                (dataset_version_id, relative_path, physical_sha256, logical_sha256,
                 row_count, size_bytes, schema_sha256)
            VALUES (%s, 'recovery/events.parquet', %s, %s, 1, 1, %s)
            """,
            (
                dataset_id,
                _checksum(marker, "dataset-physical"),
                _checksum(marker, "dataset-logical"),
                _checksum(marker, "dataset-schema"),
            ),
        )
        cursor.execute(
            """
            INSERT INTO football.dependency_edges
                (upstream_kind, upstream_id, relationship, downstream_kind, downstream_id)
            VALUES ('SOURCE_RESOURCE', %s, 'INPUT_TO', 'DATASET', %s)
            """,
            (resource_id, dataset_id),
        )
        cursor.execute(
            """
            INSERT INTO football.derived_state_events
                (object_kind, object_id, state, reason, cause_change_set_id, recorded_at)
            VALUES ('DATASET', %s, 'REBUILD_REQUIRED', 'recovery verification', %s, %s)
            """,
            (dataset_id, change_set_id, timestamp),
        )
        competition_id = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        season_id = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (competition_id,),
        ).fetchone()[0]
        match_id = cursor.execute(
            """
            INSERT INTO football.matches (competition_id, season_id)
            VALUES (%s, %s) RETURNING id
            """,
            (competition_id, season_id),
        ).fetchone()[0]
        artifact_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.model_artifacts
                (id, model_family, fit_spec_sha256, logical_model_state_sha256, schema_version,
                 algorithm_version, serializer_version, manifest_path, manifest_sha256, status,
                 published_at)
            VALUES (%s, 'TEAM_ELO', %s, %s, 'v1', 'recovery-v1', 'json-v1', %s, %s,
                    'published', %s)
            """,
            (
                artifact_id,
                _checksum(marker, "fit-spec"),
                _checksum(marker, "model-state"),
                f"models/{marker}.json",
                _checksum(marker, "model-manifest"),
                timestamp,
            ),
        )
        cursor.execute(
            """
            INSERT INTO football.model_artifact_inputs
                (model_artifact_id, dataset_version_id, source_snapshot_id, feature_set_version,
                 football_cutoff, knowledge_cutoff, knowledge_mode, quality_policy_sha256,
                 target_set_sha256)
            VALUES (%s, %s, %s, 'recovery-v1', %s, %s, 'recovery-v1', %s, %s)
            """,
            (
                artifact_id,
                dataset_id,
                snapshot_id,
                timestamp,
                timestamp,
                _checksum(marker, "quality-policy"),
                _checksum(marker, "target-set"),
            ),
        )
        forecast_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.baseline_forecasts
                (id, semantic_sha256, match_id, prediction_cutoff, dataset_version_id,
                 source_snapshot_id, feature_set_version, probability_variant, payload_path,
                 payload_sha256, target_set_sha256, knowledge_cutoff, knowledge_mode,
                 quality_policy_sha256, forecast_context_sha256, probability_contract_version,
                 output_version, status, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'recovery-v1', 'MODEL_RAW', %s, %s, %s,
                    %s, 'recovery-v1', %s, %s, 'recovery-v1', 'recovery-v1', 'published', %s)
            """,
            (
                forecast_id,
                _checksum(marker, "forecast-semantic"),
                match_id,
                timestamp,
                dataset_id,
                snapshot_id,
                f"forecasts/{marker}.json",
                _checksum(marker, "forecast-payload"),
                _checksum(marker, "target-set"),
                timestamp,
                _checksum(marker, "quality-policy"),
                _checksum(marker, "forecast-context"),
                timestamp,
            ),
        )
        cursor.execute(
            """
            INSERT INTO football.forecast_artifacts (forecast_id, model_artifact_id, artifact_role)
            VALUES (%s, %s, 'PRIMARY')
            """,
            (forecast_id, artifact_id),
        )
        evaluation_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.sprint2_evaluation_runs
                (id, policy_version, dataset_version_id, source_snapshot_id, target_set_sha256,
                 report_path, report_sha256, status, completed_at)
            VALUES (%s, 'recovery-v1', %s, %s, %s, %s, %s, 'FAIL', %s)
            """,
            (
                evaluation_id,
                dataset_id,
                snapshot_id,
                _checksum(marker, "target-set"),
                f"reports/{marker}.json",
                _checksum(marker, "evaluation-report"),
                timestamp,
            ),
        )
    return _RecoverySeed(
        source_resource_id=UUID(str(resource_id)),
        fixture_snapshot_id=UUID(str(fixture_snapshot_id)),
        fixture_change_set_id=UUID(str(fixture_change_set_id)),
        dataset_id=UUID(str(dataset_id)),
        model_artifact_id=UUID(str(artifact_id)),
        forecast_id=UUID(str(forecast_id)),
        evaluation_id=UUID(str(evaluation_id)),
    )


def _manifest(connection: Connection[Any], seed: _RecoverySeed) -> tuple[object, ...]:
    with connection.cursor() as cursor:
        migration = cursor.execute("SELECT max(version_id) FROM goose_db_version").fetchone()[0]
        counts = tuple(
            cursor.execute(f"SELECT count(*) FROM football.{table}").fetchone()[0]
            for table in (
                "providers",
                "source_snapshots",
                "source_resources",
                "fixture_sources",
                "quarantine_records",
                "canonical_change_sets",
                "dataset_versions",
                "dependency_edges",
                "derived_state_events",
                "model_artifacts",
                "baseline_forecasts",
                "sprint2_evaluation_runs",
            )
        )
        identities = cursor.execute(
            """
            SELECT resource.sha256, resource.size_bytes, dataset.identity_hash,
                   artifact.logical_model_state_sha256, forecast.semantic_sha256,
                   evaluation.report_sha256
            FROM football.source_resources AS resource
            JOIN football.dataset_inputs AS input ON input.source_resource_id = resource.id
            JOIN football.dataset_versions AS dataset ON dataset.id = input.dataset_version_id
            JOIN football.model_artifact_inputs AS artifact_input
              ON artifact_input.dataset_version_id = dataset.id
            JOIN football.model_artifacts AS artifact
              ON artifact.id = artifact_input.model_artifact_id
            JOIN football.baseline_forecasts AS forecast
              ON forecast.dataset_version_id = dataset.id
            JOIN football.sprint2_evaluation_runs AS evaluation
              ON evaluation.dataset_version_id = dataset.id
            WHERE resource.id = %s AND dataset.id = %s AND artifact.id = %s
              AND forecast.id = %s AND evaluation.id = %s
            """,
            (
                seed.source_resource_id,
                seed.dataset_id,
                seed.model_artifact_id,
                seed.forecast_id,
                seed.evaluation_id,
            ),
        ).fetchone()
        fixture_semantics = cursor.execute(
            """
            SELECT snapshot.source_kind, snapshot.fixture_id, fixture.fixture_id,
                   change_set.publication_scope,
                   (SELECT count(*) FROM football.dataset_versions
                    WHERE source_snapshot_id = snapshot.id)
            FROM football.source_snapshots AS snapshot
            JOIN football.fixture_sources AS fixture ON fixture.source_snapshot_id = snapshot.id
            JOIN football.canonical_change_sets AS change_set ON change_set.id = %s
            WHERE snapshot.id = %s
            """,
            (seed.fixture_change_set_id, seed.fixture_snapshot_id),
        ).fetchone()
    if identities is None or fixture_semantics is None:
        raise AssertionError("recovery verification manifest is incomplete")
    return migration, counts, identities, fixture_semantics


def _schema_manifest(connection: Connection[Any]) -> tuple[object, tuple[object, ...]]:
    required_relations = (
        "football.source_snapshots",
        "football.source_resources",
        "football.fixture_sources",
        "football.quarantine_records",
        "football.canonical_change_sets",
        "football.dataset_versions",
        "football.model_artifacts",
        "football.baseline_forecasts",
        "football.sprint2_evaluation_runs",
    )
    with connection.cursor() as cursor:
        migration = cursor.execute("SELECT max(version_id) FROM goose_db_version").fetchone()[0]
        relations = tuple(
            cursor.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0]
            for relation in required_relations
        )
        constraints = tuple(
            cursor.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid IN (
                    'football.source_snapshots'::regclass,
                    'football.fixture_sources'::regclass,
                    'football.dataset_versions'::regclass
                )
                ORDER BY conname
                """
            ).fetchall()
        )
    if any(relation is None for relation in relations):
        raise AssertionError("restored database is missing a required relation")
    return migration, relations + constraints


def _server_version(connection: Connection[Any]) -> str:
    with connection.cursor() as cursor:
        return str(cursor.execute("SHOW server_version").fetchone()[0])


def _assert_fixture_remains_not_model_eligible(
    connection: Connection[Any], seed: _RecoverySeed
) -> None:
    with (
        connection.cursor() as cursor,
        pytest.raises(RaiseException, match="cannot create analytical datasets"),
        connection.transaction(),
    ):
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'fixture_recovery', 'normalized', %s, 'v1', %s,
                    'recovery-v1', 'fixtures/recovery.json', %s, 'published', %s)
            """,
            (
                uuid4(),
                seed.fixture_snapshot_id,
                _checksum(str(seed.fixture_snapshot_id), "fixture-dataset-identity"),
                _checksum(str(seed.fixture_snapshot_id), "fixture-dataset-schema"),
                _checksum(str(seed.fixture_snapshot_id), "fixture-dataset-manifest"),
                datetime.now(UTC),
            ),
        )


def _backup(source_database: str, backup_path: Path) -> None:
    with backup_path.open("wb") as handle:
        _postgres(("pg_dump", "-U", "football", "-Fc", source_database), stdout=handle)
    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        raise AssertionError("PostgreSQL backup is missing or empty")


def _assert_readable_backup(backup_path: Path) -> None:
    _postgres(("pg_restore", "--list"), input_bytes=backup_path.read_bytes())


def _create_database(database: str) -> None:
    _require_temporary_database(database)
    _postgres(("createdb", "-U", "football", database))


def _restore(database: str, backup_path: Path) -> None:
    _require_temporary_database(database)
    _postgres(
        ("pg_restore", "-U", "football", "--no-owner", "--no-privileges", "-d", database),
        input_bytes=backup_path.read_bytes(),
    )


def _drop_database(database: str) -> None:
    _require_temporary_database(database)
    _postgres(("dropdb", "--if-exists", "--force", "-U", "football", database))


def _postgres(
    arguments: tuple[str, ...], *, input_bytes: bytes | None = None, stdout: BinaryIO | None = None
) -> None:
    result = subprocess.run(
        ("docker", "compose", "exec", "-T", "postgres", *arguments),
        check=False,
        cwd=_project_root(),
        input=input_bytes,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))


def _database_name(url: str) -> str:
    name = urlsplit(url).path.removeprefix("/")
    if not name or "/" in name:
        raise AssertionError("recovery source database name is invalid")
    return name


def _database_url(url: str, database: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", parsed.query, parsed.fragment))


def _require_isolated_restore(source_database: str, restore_database: str) -> None:
    _require_temporary_source_database(source_database)
    _require_temporary_database(restore_database)
    if source_database == restore_database:
        raise AssertionError("restore database must differ from source database")


def _require_temporary_database(database: str) -> None:
    _require_temporary_database_name(database, _TEMPORARY_RESTORE_PREFIX)


def _require_temporary_source_database(database: str) -> None:
    _require_temporary_database_name(database, _TEMPORARY_SOURCE_PREFIX)


def _require_temporary_database_name(database: str, prefix: str) -> None:
    suffix = database.removeprefix(prefix)
    if not suffix or suffix == database or not suffix.replace("_", "").isalnum():
        raise AssertionError("database name is outside the approved temporary namespace")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum(marker: str, label: str) -> str:
    return hashlib.sha256(f"{marker}:{label}".encode()).hexdigest()


def _project_root() -> Path:
    return Path(__file__).parents[2]


def _git_sha() -> str:
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        cwd=_project_root(),
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
