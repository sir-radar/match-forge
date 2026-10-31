"""Read-only retirement preparation; queue emptiness never authorizes code removal."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from psycopg import Connection

from football.product.resolution_migration import migration_report

SOURCES = {
    "operator_runner": "go/api/internal/app/admin_sync.go",
    "history_worker": "python/football/src/football/product/history_worker.py",
    "provider_scope_owner": "python/football/src/football/product/provider_history_scopes.py",
    "forecast_generation_owner": "python/football/src/football/product/forecast_work.py",
    "public_report_owner": "python/football/src/football/product/public_reports.py",
    "shared_domain_adapters": "infrastructure/migrations/202610182000_domain_work_adapters.sql",
    "history_registration": "infrastructure/migrations/202610181700_history_work_registration.sql",
    "shared_work_state_machine": "infrastructure/migrations/202610180700_work_orchestration.sql",
}


def legacy_inventory(connection: Connection[Any], repo: Path) -> dict[str, Any]:
    report = migration_report(repo)
    domains = domain_queues(connection)
    states = connection.execute(
        "SELECT work_type,state,count(*) FROM football.work_items GROUP BY work_type,state "
        "ORDER BY work_type,state"
    ).fetchall()
    ownership = connection.execute(
        """SELECT jsonb_build_object('active_leases',count(*) FILTER(
          WHERE state='RUNNING' AND lease_until>clock_timestamp()),
        'expired_claims_requiring_recovery',count(*) FILTER(
          WHERE state='RUNNING' AND lease_until<=clock_timestamp()),
        'blocked_or_failed',count(*) FILTER(WHERE state IN('BLOCKED','FAILED')))
        FROM football.work_items"""
    ).fetchone()
    dependencies = connection.execute(
        """SELECT count(*) FROM football.work_dependencies d
        JOIN football.work_items child ON child.work_id=d.work_id
        JOIN football.work_items parent ON parent.work_id=d.dependency_work_id
        WHERE child.state IN('PENDING','RUNNING','RETRY_WAIT','BLOCKED')
          AND parent.state<>'SUCCEEDED'"""
    ).fetchone()
    assert ownership and dependencies
    return {
        "status": "BLOCKED",
        "live_retirement": "BLOCKED",
        "code_removal_authorized": False,
        "phase_35_runtime_cutover": report["production_cutover"],
        "required_parity_status": report["status"],
        "deployed_scheduler_inventory": "NOT_VERIFIED_BY_REPOSITORY_SOURCE_OR_QUEUE_COUNTS",
        "owner_acceptance_and_stabilization": "NOT_ESTABLISHED",
        "domain_queues": domains,
        "shared_ownership": ownership[0],
        "unfinished_dependencies": dependencies[0],
        "shared_work_states": [
            {"work_type": kind, "state": state, "count": count} for kind, state, count in states
        ],
        "source_bindings": source_inventory(repo),
        "compatibility_policy": "Preserve unbound pre-migration rows and their original consumers; "
        "drain or explicitly transfer them only after accepted cutover.",
        "generation_policy": "Forecast generations register shared work when claimed; "
        "an unregistered pending generation is not proof of an orphan or safe retirement.",
        "remaining_consumers": "Operator, history, provider-scope, forecast and report owners "
        "remain required. Source review does not prove deployed process state.",
        "next_action": "Complete and accept Phase35, inventory deployed schedulers and remaining "
        "readers, prove every pending/in-flight scope has an owner, approve a "
        "stabilization/rollback period, then authorize incremental retirement.",
        "scope": "READ_ONLY_CURRENT_DATABASE_AND_TRACKED_SOURCE; NO_SCHEDULER_OR_QUEUE_MUTATION",
    }


def source_inventory(repo: Path) -> list[dict[str, Any]]:
    result = []
    for owner, path in SOURCES.items():
        try:
            digest = hashlib.sha256((repo / path).read_bytes()).hexdigest()
            result.append(
                {
                    "owner": owner,
                    "path": path,
                    "sha256": digest,
                    "status": "CURRENT_REPOSITORY_SOURCE; DEPLOYMENT_NOT_VERIFIED",
                }
            )
        except OSError:
            result.append({"owner": owner, "path": path, "status": "SOURCE_UNAVAILABLE"})
    return result


def domain_queues(connection: Connection[Any]) -> dict[str, Any]:
    row = connection.execute("""SELECT jsonb_build_object(
      'operator_runs',(SELECT jsonb_build_object(
        'outstanding',count(*) FILTER(WHERE r.status IN('QUEUED','RUNNING')),
        'running',count(*) FILTER(WHERE r.status='RUNNING'),
        'compatibility_unbound',count(*) FILTER(
          WHERE r.status IN('QUEUED','RUNNING') AND w.work_id IS NULL),
        'compatibility_unbound_running',count(*) FILTER(
          WHERE r.status='RUNNING' AND w.work_id IS NULL))
        FROM football.product_sync_runs r LEFT JOIN football.work_items w ON w.work_id=r.run_id),
      'history_queue',(SELECT jsonb_build_object(
        'outstanding',count(*) FILTER(WHERE q.job_status IN('PENDING','RUNNING','FAILED')),
        'running',count(*) FILTER(WHERE q.job_status='RUNNING'),
        'compatibility_unbound',count(*) FILTER(
          WHERE q.job_status IN('PENDING','RUNNING','FAILED') AND b.work_id IS NULL))
        FROM football.product_history_sync_queue q LEFT JOIN football.product_history_work b
        ON b.job_id=q.job_id AND b.queued_at=q.queued_at),
      'provider_scopes',(SELECT jsonb_build_object(
        'outstanding',count(*) FILTER(WHERE s.status IN('PENDING','RUNNING','FAILED')),
        'running',count(*) FILTER(WHERE s.status='RUNNING'),
        'compatibility_unbound',count(*) FILTER(
          WHERE s.status IN('PENDING','RUNNING','FAILED') AND b.work_id IS NULL))
        FROM football.product_provider_history_scopes s
        LEFT JOIN football.product_provider_scope_work b
        USING(provider_code,provider_competition_id,season_label)),
      'forecast_generations',(SELECT jsonb_build_object(
        'pending_generations',count(*),
        'lazy_registration_pending',count(*) FILTER(WHERE w.work_id IS NULL))
        FROM football.product_forecast_refresh_work f LEFT JOIN football.work_items w
        ON w.semantic_key='product-forecast:'||f.fixture_id||':'||f.generation
        WHERE f.generation>f.completed_generation))""").fetchone()
    assert row is not None
    return dict(row[0])
