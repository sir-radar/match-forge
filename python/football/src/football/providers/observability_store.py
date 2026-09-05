from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Cursor

from football.providers.observability import ProviderObservabilitySnapshotV1
from football.providers.sync_policy import ProviderSyncPolicyRegistryV1


class ProviderObservabilityStoreError(ValueError):
    """Durable provider lifecycle evidence cannot produce a status snapshot."""


class PostgresProviderObservabilityStoreV1:
    """Read one provider lifecycle scope without changing operational state."""

    def snapshot(
        self,
        cursor: Cursor[Any],
        *,
        policies: ProviderSyncPolicyRegistryV1,
        provider_id: str,
        resource_key: str,
        scope_key: str,
        observed_at: datetime,
    ) -> ProviderObservabilitySnapshotV1:
        registration = policies.resolve(provider_id, resource_key, scope_key)
        provider = cursor.execute(
            "SELECT id FROM football.providers WHERE code = %s", (provider_id,)
        ).fetchone()
        if provider is None:
            raise ProviderObservabilityStoreError("provider lifecycle evidence is unavailable")
        policy_versions = cursor.execute(
            _POLICY_VERSIONS_SQL,
            (provider[0], resource_key, scope_key),
        ).fetchall()
        for policy_version in policy_versions:
            policies.resolve_version(provider_id, str(policy_version[0]))
        row = cursor.execute(
            _SNAPSHOT_SQL,
            (provider[0], resource_key, scope_key, *(observed_at,) * 10),
        ).fetchone()
        if row is None:
            raise ProviderObservabilityStoreError(
                "provider lifecycle evidence query returned no result"
            )
        return ProviderObservabilitySnapshotV1(
            provider_id=provider_id,
            resource_id=f"{resource_key}:{scope_key}",
            observed_at=observed_at,
            last_successful_sync_at=row[0],
            last_successful_acquisition_at=row[1],
            last_successful_validation_at=row[2],
            last_successful_publication_at=row[3],
            freshness_target_seconds=registration.policy.freshness_target_seconds,
            discovered_count=row[4],
            fetched_count=row[5],
            unchanged_count=0,
            bytes_acquired=row[6],
            validation_failure_count=row[7],
            resolution_attempt_count=0,
            resolution_success_count=0,
            quarantine_count=row[8],
            unresolved_conflict_count=0,
            retry_count=row[9],
            rate_limit_response_count=0,
            processing_latency_ms=0,
            publication_failure_count=0,
            reconciliation_failure_count=0,
            change_set_emission_count=row[10],
            cursor_lag_seconds=None,
            circuit_state="CLOSED",
            processing_failure_count=row[11],
        )


_SNAPSHOT_SQL = """
WITH scoped_jobs AS (
    SELECT job.id, job.sync_run_id, job.status, job.attempt_count, job.created_at
    FROM football.acquisition_jobs AS job
    WHERE job.provider_id = %s
      AND job.resource_key = %s
      AND job.scope_key = %s
),
real_resources AS (
    SELECT acquired.id, acquired.acquisition_job_id, acquired.source_resource_id,
           acquired.size_bytes, acquired.acquired_at
    FROM football.acquired_resources AS acquired
    JOIN scoped_jobs AS job ON job.id = acquired.acquisition_job_id
    JOIN football.source_snapshots AS snapshot ON snapshot.id = acquired.source_snapshot_id
    WHERE snapshot.source_kind = 'REAL_PROVIDER'
),
real_jobs AS (
    SELECT DISTINCT job.id, job.sync_run_id, job.status, job.attempt_count, job.created_at
    FROM scoped_jobs AS job
    JOIN real_resources AS acquired ON acquired.acquisition_job_id = job.id
),
scoped_validation AS (
    SELECT validation.status, validation.completed_at
    FROM football.validation_runs AS validation
    JOIN football.dataset_inputs AS input
      ON input.dataset_version_id = validation.dataset_version_id
     AND input.source_snapshot_id = validation.source_snapshot_id
    JOIN real_resources AS acquired ON acquired.source_resource_id = input.source_resource_id
    JOIN football.source_snapshots AS snapshot ON snapshot.id = validation.source_snapshot_id
    WHERE snapshot.source_kind = 'REAL_PROVIDER'
),
scoped_quarantine AS (
    SELECT quarantine.status, quarantine.created_at, quarantine.resolved_at
    FROM football.quarantine_records AS quarantine
    JOIN real_jobs AS job ON job.id = quarantine.acquisition_job_id
)
SELECT
    (
        SELECT MAX(run.completed_at)
        FROM football.provider_sync_runs AS run
        JOIN real_jobs AS job ON job.sync_run_id = run.id
        WHERE run.status = 'succeeded' AND run.completed_at <= %s
    ),
    (SELECT MAX(acquired_at) FROM real_resources WHERE acquired_at <= %s),
    (
        SELECT MAX(completed_at) FROM scoped_validation
        WHERE status IN ('passed', 'warnings') AND completed_at <= %s
    ),
    (
        SELECT MAX(change_set.published_at)
        FROM football.canonical_change_sets AS change_set
        JOIN real_jobs AS job ON job.sync_run_id = change_set.sync_run_id
        WHERE change_set.status IN ('published', 'verified_existing')
          AND change_set.publication_scope = 'REAL_PROVIDER'
          AND change_set.published_at <= %s
    ),
    (SELECT COUNT(*)::integer FROM real_jobs WHERE status = 'discovered'),
    (SELECT COUNT(*)::integer FROM real_resources WHERE acquired_at <= %s),
    (SELECT COALESCE(SUM(size_bytes), 0)::bigint FROM real_resources WHERE acquired_at <= %s),
    (
        SELECT COUNT(*)::integer FROM scoped_validation
        WHERE status IN ('quarantined', 'failed') AND completed_at <= %s
    ),
    (
        SELECT COUNT(*)::integer FROM scoped_quarantine
        WHERE created_at <= %s AND (resolved_at IS NULL OR resolved_at > %s)
    ),
    (SELECT COALESCE(SUM(GREATEST(attempt_count - 1, 0)), 0)::integer FROM real_jobs),
    (
        SELECT COUNT(DISTINCT change_set.id)::integer
        FROM football.canonical_change_sets AS change_set
        JOIN real_jobs AS job ON job.sync_run_id = change_set.sync_run_id
        WHERE change_set.status IN ('published', 'verified_existing')
          AND change_set.publication_scope = 'REAL_PROVIDER'
          AND change_set.published_at <= %s
    ),
    (SELECT COUNT(*)::integer FROM real_jobs WHERE status = 'failed')
"""


_POLICY_VERSIONS_SQL = """
SELECT DISTINCT run.policy_version
FROM football.provider_sync_runs AS run
JOIN football.acquisition_jobs AS job ON job.sync_run_id = run.id
JOIN football.acquired_resources AS acquired ON acquired.acquisition_job_id = job.id
JOIN football.source_snapshots AS snapshot ON snapshot.id = acquired.source_snapshot_id
WHERE run.provider_id = %s
  AND job.resource_key = %s
  AND job.scope_key = %s
  AND snapshot.source_kind = 'REAL_PROVIDER'
ORDER BY run.policy_version
"""
