from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.cli.main import run
from psycopg import Connection


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as database_connection:
        yield database_connection


def test_provider_status_reads_real_lifecycle_evidence_and_excludes_fixture_data(
    connection: Connection[Any], tmp_path: Path
) -> None:
    provider_id, snapshot_id, resource_id, run_id, failure_job_id, failure_resource_id = (
        _real_lifecycle(connection, "provider_observability_first")
    )
    _successful_validation(connection, snapshot_id, resource_id)
    _real_change_set(connection, run_id, "first")
    _open_quarantine(connection, failure_job_id, failure_resource_id)
    _fixture_lifecycle(connection, provider_id)
    policy_path = tmp_path / "provider-sync-policies.json"
    policy_path.write_text(
        json.dumps(_policy_config("provider_observability_first")), encoding="utf-8"
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        [
            "provider",
            "status",
            "--provider-id",
            "provider_observability_first",
            "--resource-key",
            "results",
            "--scope-key",
            "competition=E0/season=1516",
            "--as-of",
            "2026-09-05T12:00:00+00:00",
            "--provider-sync-policy-config",
            str(policy_path),
        ],
        environ={},
        stdout=stdout,
        stderr=stderr,
        connection_factory=lambda _: nullcontext(connection),
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    snapshot = payload["snapshot"]
    assert payload["policy_version"] == "test-policy-v1"
    assert len(payload["policy_sha256"]) == 64
    assert snapshot["freshness_target_seconds"] == 3600
    assert snapshot["freshness_status"] == "FRESH"
    assert snapshot["last_successful_acquisition_at"] == "2026-09-05T11:30:00+00:00"
    assert snapshot["last_successful_validation_at"] == "2026-09-05T11:40:00+00:00"
    assert snapshot["last_successful_publication_at"] == "2026-09-05T11:45:00+00:00"
    assert snapshot["quarantine_count"] == 1
    assert snapshot["processing_failure_count"] == 1
    assert snapshot["fetched_count"] == 2
    assert snapshot["bytes_acquired"] == 30
    assert snapshot["change_set_emission_count"] == 1

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE football.quarantine_records
            SET status = 'resolved', resolved_at = created_at + INTERVAL '1 microsecond'
            WHERE acquisition_job_id = %s
            """,
            (failure_job_id,),
        )
        assert cursor.execute(
            "SELECT COUNT(*) FROM football.quarantine_records WHERE acquisition_job_id = %s",
            (failure_job_id,),
        ).fetchone() == (1,)
    resolved_stdout = StringIO()
    resolved_exit = run(
        _status_args("provider_observability_first", policy_path, "2026-09-05T12:00:00+00:00"),
        environ={},
        stdout=resolved_stdout,
        stderr=StringIO(),
        connection_factory=lambda _: nullcontext(connection),
    )

    assert resolved_exit == 0
    assert json.loads(resolved_stdout.getvalue())["snapshot"]["quarantine_count"] == 0


def test_provider_status_is_stale_with_history_and_fails_closed_without_policy(
    connection: Connection[Any], tmp_path: Path
) -> None:
    _real_lifecycle(connection, "provider_observability_second")
    configured = tmp_path / "configured.json"
    configured.write_text(
        json.dumps(_policy_config("provider_observability_second")), encoding="utf-8"
    )
    exact_boundary = _status_output(
        connection,
        "provider_observability_second",
        configured,
        "2026-09-05T12:30:00+00:00",
    )
    stale_output = _status_output(
        connection,
        "provider_observability_second",
        configured,
        "2026-09-05T12:30:01+00:00",
    )
    assert exact_boundary == _status_output(
        connection,
        "provider_observability_second",
        configured,
        "2026-09-05T12:30:00+00:00",
    )
    assert exact_boundary["snapshot"]["freshness_status"] == "FRESH"
    assert stale_output["snapshot"]["freshness_status"] == "STALE"
    assert stale_output["snapshot"]["last_successful_validation_at"] is None

    unresolved = tmp_path / "unresolved.json"
    unresolved.write_text(
        json.dumps(
            {"contract": "ProviderSyncPolicyRegistryV1", "registrations": [], "bindings": []}
        ),
        encoding="utf-8",
    )
    unresolved_stderr = StringIO()
    unresolved_exit = run(
        _status_args("provider_observability_second", unresolved, "2026-09-05T13:00:01+00:00"),
        environ={},
        stdout=StringIO(),
        stderr=unresolved_stderr,
        connection_factory=lambda _: nullcontext(connection),
    )

    assert unresolved_exit == 2
    assert unresolved_stderr.getvalue() == (
        "error: provider sync policy is unresolved for provider/resource/scope\n"
    )


def test_provider_status_reports_no_history_and_rejects_unknown_run_policy(
    connection: Connection[Any], tmp_path: Path
) -> None:
    empty_provider = "provider_observability_empty"
    _provider(connection, empty_provider)
    configured = tmp_path / "configured.json"
    configured.write_text(json.dumps(_policy_config(empty_provider)), encoding="utf-8")
    empty_stdout = StringIO()

    empty_exit = run(
        _status_args(empty_provider, configured, "2026-09-05T13:00:01+00:00"),
        environ={},
        stdout=empty_stdout,
        stderr=StringIO(),
        connection_factory=lambda _: nullcontext(connection),
    )

    assert empty_exit == 0
    empty_snapshot = json.loads(empty_stdout.getvalue())["snapshot"]
    assert empty_snapshot["freshness_status"] == "NEVER_SUCCEEDED"
    assert empty_snapshot["last_successful_acquisition_at"] is None
    assert empty_snapshot["last_successful_validation_at"] is None
    assert empty_snapshot["last_successful_publication_at"] is None

    unknown_provider = "provider_observability_unknown"
    _real_lifecycle(connection, unknown_provider, policy_version="unknown-policy-v7")
    unknown_config = tmp_path / "unknown-version.json"
    unknown_config.write_text(json.dumps(_policy_config(unknown_provider)), encoding="utf-8")
    unknown_stderr = StringIO()
    unknown_exit = run(
        _status_args(unknown_provider, unknown_config, "2026-09-05T13:00:01+00:00"),
        environ={},
        stdout=StringIO(),
        stderr=unknown_stderr,
        connection_factory=lambda _: nullcontext(connection),
    )

    assert unknown_exit == 2
    assert unknown_stderr.getvalue() == "error: provider sync policy version is unresolved\n"


def test_provider_status_reports_healthy_and_acquisition_without_validation(
    connection: Connection[Any], tmp_path: Path
) -> None:
    healthy_provider = "provider_observability_healthy"
    _, healthy_snapshot, healthy_resource, healthy_run, healthy_failure, _ = _real_lifecycle(
        connection, healthy_provider
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE football.acquisition_jobs SET status = 'validated' WHERE id = %s",
            (healthy_failure,),
        )
    _successful_validation(connection, healthy_snapshot, healthy_resource)
    _real_change_set(connection, healthy_run, "healthy")
    healthy_config = tmp_path / "healthy.json"
    healthy_config.write_text(json.dumps(_policy_config(healthy_provider)), encoding="utf-8")

    healthy = _status_output(
        connection, healthy_provider, healthy_config, "2026-09-05T12:00:00+00:00"
    )["snapshot"]

    assert healthy["freshness_status"] == "FRESH"
    assert healthy["last_successful_acquisition_at"] == "2026-09-05T11:30:00+00:00"
    assert healthy["last_successful_validation_at"] == "2026-09-05T11:40:00+00:00"
    assert healthy["last_successful_publication_at"] == "2026-09-05T11:45:00+00:00"
    assert healthy["quarantine_count"] == 0
    assert healthy["processing_failure_count"] == 0

    acquisition_provider = "provider_observability_acquisition"
    _, _, _, _, acquisition_failure, _ = _real_lifecycle(connection, acquisition_provider)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE football.acquisition_jobs SET status = 'validated' WHERE id = %s",
            (acquisition_failure,),
        )
    acquisition_config = tmp_path / "acquisition.json"
    acquisition_config.write_text(
        json.dumps(_policy_config(acquisition_provider)), encoding="utf-8"
    )

    acquisition_only = _status_output(
        connection, acquisition_provider, acquisition_config, "2026-09-05T12:00:00+00:00"
    )["snapshot"]

    assert acquisition_only["last_successful_acquisition_at"] == "2026-09-05T11:30:00+00:00"
    assert acquisition_only["last_successful_validation_at"] is None
    assert acquisition_only["last_successful_publication_at"] is None


def test_provider_status_keeps_validation_history_and_lifecycle_stages_separate(
    connection: Connection[Any], tmp_path: Path
) -> None:
    provider = "provider_observability_validation"
    _, snapshot_id, resource_id, _, failure_job_id, _ = _real_lifecycle(connection, provider)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE football.acquisition_jobs SET status = 'validated' WHERE id = %s",
            (failure_job_id,),
        )
    _validation(
        connection,
        snapshot_id,
        resource_id,
        "passed",
        datetime(2026, 9, 5, 11, 40, tzinfo=UTC),
        "1",
    )
    _validation(
        connection,
        snapshot_id,
        resource_id,
        "passed",
        datetime(2026, 9, 5, 11, 45, tzinfo=UTC),
        "2",
    )
    _validation(
        connection,
        snapshot_id,
        resource_id,
        "failed",
        datetime(2026, 9, 5, 11, 50, tzinfo=UTC),
        "3",
    )
    policy = tmp_path / "validation.json"
    policy.write_text(json.dumps(_policy_config(provider)), encoding="utf-8")

    snapshot = _status_output(connection, provider, policy, "2026-09-05T12:00:00+00:00")["snapshot"]

    assert snapshot["last_successful_acquisition_at"] == "2026-09-05T11:30:00+00:00"
    assert snapshot["last_successful_validation_at"] == "2026-09-05T11:45:00+00:00"
    assert snapshot["last_successful_publication_at"] is None
    assert snapshot["validation_failure_count"] == 1
    assert snapshot["processing_failure_count"] == 0


def _status_args(provider_id: str, policy_path: Path, as_of: str) -> list[str]:
    return [
        "provider",
        "status",
        "--provider-id",
        provider_id,
        "--resource-key",
        "results",
        "--scope-key",
        "competition=E0/season=1516",
        "--as-of",
        as_of,
        "--provider-sync-policy-config",
        str(policy_path),
    ]


def _status_output(
    connection: Connection[Any], provider_id: str, policy_path: Path, as_of: str
) -> dict[str, Any]:
    stdout = StringIO()
    exit_code = run(
        _status_args(provider_id, policy_path, as_of),
        environ={},
        stdout=stdout,
        stderr=StringIO(),
        connection_factory=lambda _: nullcontext(connection),
    )
    assert exit_code == 0
    return json.loads(stdout.getvalue())


def _real_lifecycle(
    connection: Connection[Any], provider_code: str, policy_version: str = "test-policy-v1"
) -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
    now = datetime(2026, 9, 5, 11, 30, tzinfo=UTC)
    with connection.cursor() as cursor:
        provider_id = cursor.execute(
            """
            INSERT INTO football.providers (code, name, source_type)
            VALUES (%s, 'Provider Observability', 'file_download')
            RETURNING id
            """,
            (provider_code,),
        ).fetchone()[0]
        snapshot_id, resource_id = _source(cursor, provider_id, "real", now, "a", "b")
        run_id = cursor.execute(
            """
            INSERT INTO football.provider_sync_runs
                (provider_id, policy_version, status, run_key, started_at, completed_at)
            VALUES (%s, %s, 'succeeded', %s, %s, %s)
            RETURNING id
            """,
            (provider_id, policy_version, sha256(provider_code.encode()).hexdigest(), now, now),
        ).fetchone()[0]
        successful_job_id = _job(cursor, run_id, provider_id, "real", "validated", 2)
        cursor.execute(
            """
            INSERT INTO football.acquired_resources
                (acquisition_job_id, source_snapshot_id, source_resource_id, raw_path,
                 raw_sha256, size_bytes, status, acquired_at)
            VALUES (%s, %s, %s, 'raw/real.csv', %s, 10, 'validated', %s)
            """,
            (successful_job_id, snapshot_id, resource_id, "b" * 64, now),
        )
        failure_snapshot_id, failure_resource_id = _source(
            cursor, provider_id, "failure", now, "d", "e"
        )
        failure_job_id = _job(cursor, run_id, provider_id, "failure", "failed", 1)
        cursor.execute(
            """
            INSERT INTO football.acquired_resources
                (acquisition_job_id, source_snapshot_id, source_resource_id, raw_path,
                 raw_sha256, size_bytes, status, acquired_at)
            VALUES (%s, %s, %s, 'raw/failure.csv', %s, 20, 'quarantined', %s)
            """,
            (failure_job_id, failure_snapshot_id, failure_resource_id, "e" * 64, now),
        )
    return provider_id, snapshot_id, resource_id, run_id, failure_job_id, failure_resource_id


def _provider(connection: Connection[Any], provider_code: str) -> UUID:
    with connection.cursor() as cursor:
        return cursor.execute(
            """
            INSERT INTO football.providers (code, name, source_type)
            VALUES (%s, 'Provider Observability', 'file_download')
            RETURNING id
            """,
            (provider_code,),
        ).fetchone()[0]


def _source(
    cursor: Any,
    provider_id: UUID,
    marker: str,
    acquired_at: datetime,
    revision: str,
    checksum: str,
) -> tuple[UUID, UUID]:
    snapshot_id = cursor.execute(
        """
        INSERT INTO football.source_snapshots
            (provider_id, source_identity, source_revision, acquired_at, manifest_path,
             manifest_sha256, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'acquired')
        RETURNING id
        """,
        (
            provider_id,
            f"https://example.test/{marker}.csv",
            revision * 64,
            acquired_at,
            f"manifests/{marker}.json",
            revision * 64,
        ),
    ).fetchone()[0]
    resource_id = cursor.execute(
        """
        INSERT INTO football.source_resources
            (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
             parse_status, validation_status, acquired_at)
        VALUES (%s, %s, %s, 10, 'text/csv', 'parsed', 'valid', %s)
        RETURNING id
        """,
        (snapshot_id, f"data/{marker}.csv", checksum * 64, acquired_at),
    ).fetchone()[0]
    return snapshot_id, resource_id


def _job(
    cursor: Any, run_id: UUID, provider_id: UUID, marker: str, status: str, attempt_count: int
) -> UUID:
    return cursor.execute(
        """
        INSERT INTO football.acquisition_jobs
            (sync_run_id, provider_id, resource_key, scope_key, resource_identity,
             resource_revision, status, attempt_count)
        VALUES (%s, %s, 'results', 'competition=E0/season=1516', %s, %s, %s, %s)
        RETURNING id
        """,
        (run_id, provider_id, f"data/{marker}.csv", marker * 64, status, attempt_count),
    ).fetchone()[0]


def _successful_validation(
    connection: Connection[Any], snapshot_id: UUID, resource_id: UUID
) -> None:
    _validation(
        connection,
        snapshot_id,
        resource_id,
        "passed",
        datetime(2026, 9, 5, 11, 40, tzinfo=UTC),
        "f",
    )


def _validation(
    connection: Connection[Any],
    snapshot_id: UUID,
    resource_id: UUID,
    status: str,
    completed_at: datetime,
    marker: str,
) -> None:
    with connection.cursor() as cursor:
        dataset_id = uuid4()
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash, schema_version,
                 schema_sha256, normalizer_version, manifest_path, manifest_sha256, status,
                 published_at)
            VALUES (%s, %s, 'results', 'normalized', %s, 'v1', %s, 'v1',
                    %s, %s, 'published', %s)
            """,
            (
                dataset_id,
                snapshot_id,
                sha256(f"dataset-{snapshot_id}-{marker}".encode()).hexdigest(),
                "1" * 64,
                f"datasets/results-{marker}.json",
                "2" * 64,
                completed_at,
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
            INSERT INTO football.validation_runs
                (id, dataset_version_id, source_snapshot_id, identity_hash, policy_version,
                 policy_sha256, validator_version, status, started_at, completed_at)
            VALUES (%s, %s, %s, %s, 'v1', %s, 'v1', %s, %s, %s)
            """,
            (
                uuid4(),
                dataset_id,
                snapshot_id,
                sha256(f"validation-{snapshot_id}-{marker}".encode()).hexdigest(),
                "4" * 64,
                status,
                completed_at,
                completed_at,
            ),
        )


def _real_change_set(connection: Connection[Any], run_id: UUID, marker: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.canonical_change_sets
                (sync_run_id, change_key, status, changes, publication_scope, published_at)
            VALUES (%s, %s, 'published', '{}'::jsonb, 'REAL_PROVIDER', %s)
            """,
            (
                run_id,
                sha256(f"change-set-{marker}".encode()).hexdigest(),
                datetime(2026, 9, 5, 11, 45, tzinfo=UTC),
            ),
        )


def _open_quarantine(connection: Connection[Any], job_id: UUID, resource_id: UUID) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.quarantine_records
                (acquisition_job_id, source_resource_id, finding_key, reason_code, details, status,
                 created_at)
            VALUES (%s, %s, %s, 'TEST_FAILURE', '{}'::jsonb, 'open', %s)
            """,
            (job_id, resource_id, "6" * 64, datetime(2026, 9, 5, 11, 50, tzinfo=UTC)),
        )


def _fixture_lifecycle(connection: Connection[Any], provider_id: UUID) -> None:
    now = datetime(2026, 9, 5, 11, 50, tzinfo=UTC)
    with connection.cursor() as cursor:
        snapshot_id = cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, acquired_at, manifest_path,
                 manifest_sha256, status, source_kind, fixture_id)
            VALUES (%s, 'fixture://f3', %s, %s, 'fixtures/f3.json', %s, 'validated',
                    'CONTRACT_FIXTURE', 'f3-observability')
            RETURNING id
            """,
            (provider_id, "7" * 64, now, "8" * 64),
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.fixture_sources (source_snapshot_id, fixture_id)
            VALUES (%s, 'f3-observability')
            """,
            (snapshot_id,),
        )
        resource_id = cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, 'f3.csv', %s, 99, 'text/csv', 'parsed', 'valid', %s)
            RETURNING id
            """,
            (snapshot_id, "9" * 64, now),
        ).fetchone()[0]
        run_id = cursor.execute(
            """
            INSERT INTO football.provider_sync_runs
                (provider_id, policy_version, status, run_key, started_at, completed_at)
            VALUES (%s, 'f3-v1', 'succeeded', %s, %s, %s)
            RETURNING id
            """,
            (provider_id, "a" * 64, now, now),
        ).fetchone()[0]
        job_id = _job(cursor, run_id, provider_id, "fixture", "quarantined", 1)
        cursor.execute(
            """
            INSERT INTO football.acquired_resources
                (acquisition_job_id, source_snapshot_id, source_resource_id, raw_path,
                 raw_sha256, size_bytes, status, acquired_at)
            VALUES (%s, %s, %s, 'raw/f3.csv', %s, 99, 'quarantined', %s)
            """,
            (job_id, snapshot_id, resource_id, "9" * 64, now),
        )


def _policy_config(provider_id: str) -> dict[str, object]:
    policy = {
        "contract": "ProviderSyncPolicyV1",
        "provider_id": provider_id,
        "enabled_resources": ["results"],
        "scopes": [{"competition_id": "E0", "season_id": "1516", "resources": ["results"]}],
        "discovery_cadence_seconds": 900,
        "fixture_lookahead_seconds": None,
        "result_backfill_seconds": 0,
        "historical_backfill": "disabled",
        "cursor_strategy": "none",
        "request_timeout_seconds": 30.0,
        "max_attempts": 3,
        "backoff_initial_seconds": 1.0,
        "backoff_max_seconds": 30.0,
        "steady_rate_limit_per_minute": None,
        "burst_limit": None,
        "freshness_target_seconds": 3600,
        "adapter_version": "test-v1",
    }
    return {
        "contract": "ProviderSyncPolicyRegistryV1",
        "registrations": [{"policy_version": "test-policy-v1", "policy": policy}],
        "bindings": [
            {
                "provider_id": provider_id,
                "resource_key": "results",
                "scope_key": "competition=E0/season=1516",
                "policy_version": "test-policy-v1",
            }
        ],
    }
