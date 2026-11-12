"""Bounded read-report production on the common work registry; no fitting or promotion."""

from __future__ import annotations

import hashlib
import math
import re
import subprocess
import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection, Error
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row, tuple_row

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.postmatch_storage import MONITORING_HORIZONS
from football.product.public_analytics import (
    POLICY_VERSION,
    PerformanceObservation,
    performance_report,
    selection_agreement,
)
from football.product.public_context import context_features
from football.storage.locks import LockClass, LockRequest, acquire_locks
from football.work.contracts import RetryClassification, RetryPolicy, WorkRequest, WorkType
from football.work.storage import WorkLeaseLost, WorkRegistry

REPORT_KINDS = ("PERFORMANCE", "CONTEXT", "COMPARISON")
CONTEXT_REPORT_BATCH_LIMIT = 32


def _snapshot(connection: Connection[Any], kind: str, scope: UUID, horizon: str) -> dict[str, Any]:
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        observed = cursor.execute("SELECT statement_timestamp() AS clock").fetchone()
        assert observed is not None
        if kind == "PERFORMANCE":
            row = cursor.execute(
                "SELECT * FROM football.public_performance_source(%s,%s)",
                (scope, MONITORING_HORIZONS[horizon]),
            ).fetchone()
            assert row is not None
            source = cursor.execute(
                "SELECT * FROM football.public_performance_rows(%s,%s) "
                "ORDER BY kickoff_at,fixture_id",
                (scope, MONITORING_HORIZONS[horizon]),
            ).fetchall()
            records = tuple(PerformanceObservation.from_source(item) for item in source)
            report = performance_report(str(scope), records, horizon=horizon)
            manifest = [
                {
                    key: _wire(value)
                    for key, value in item.items()
                    if key not in ("probabilities", "score_matrix")
                }
                for item in source
            ]
            fingerprint = row["source_fingerprint"]
        else:
            function = (
                "public_context_source_v2" if kind == "CONTEXT" else "public_comparison_source"
            )
            row = cursor.execute(
                f"SELECT source,encode(sha256(convert_to(source::text,'UTF8')),'hex') "
                f"AS fingerprint FROM (SELECT football.{function}(%s) AS source) s",
                (scope,),
            ).fetchone()
            if row is None or row["source"] is None:
                raise ValueError("public report scope does not exist")
            manifest = row["source"]
            fingerprint = row["fingerprint"]
            report = context_features(manifest) if kind == "CONTEXT" else _comparison(manifest)
        return {
            "source_observed_at": observed["clock"],
            "source_fingerprint": fingerprint,
            "source_manifest": manifest,
            "report": report,
        }


def _wire(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value) if isinstance(value, UUID) else value


def _comparison(source: dict[str, Any]) -> dict[str, Any]:
    values = source["probabilities"] or {}
    if not isinstance(values, dict) or any(
        type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
        for value in values.values()
    ):
        raise ValueError("invalid stored comparison probabilities")
    probability, agreement = selection_agreement(source["market"], source["selection"], values)
    return {
        "prediction_id": source["prediction_id"],
        "forecast_id": source["forecast_id"],
        "matchforge_probability": probability,
        "agreement": agreement,
    }


def _publish(
    connection: Connection[Any],
    request: WorkRequest,
    snapshot: dict[str, Any],
    inputs: dict[str, Any],
    lease: timedelta,
    owner: str,
) -> str:
    registry = WorkRegistry(connection)
    registry.enqueue(request)
    claim = registry.claim(
        owner, lease, (WorkType.READ_MODEL_PROJECTION,), work_ids=(request.work_id,)
    )
    if claim is None:
        return "busy_or_complete"
    payload = canonical_json_bytes(snapshot["report"])
    result_hash = sha256_bytes(payload)
    try:
        with connection.transaction(), registry.publication(claim, result_hash=result_hash):
            acquire_locks(
                connection,
                (LockRequest(LockClass.PUBLICATION, f"public-report:{request.input_hash}"),),
            )
            with connection.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(
                    """INSERT INTO football.product_read_reports
                    (input_sha256,work_id,report_kind,scope_id,horizon,source_fingerprint,
                     source_observed_at,input_bytes,record_bytes,record_sha256)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(input_sha256) DO NOTHING""",
                    (
                        request.input_hash,
                        request.work_id,
                        inputs["report_kind"],
                        inputs["scope_id"],
                        inputs["horizon"],
                        inputs["source_fingerprint"],
                        snapshot["source_observed_at"],
                        canonical_json_bytes(inputs),
                        payload,
                        result_hash,
                    ),
                )
                row = cursor.execute(
                    "SELECT record_bytes FROM football.product_read_reports WHERE input_sha256=%s",
                    (request.input_hash,),
                ).fetchone()
                if row is None or bytes(row[0]) != payload:
                    raise ValueError("public read report conflict")
        return "published"
    except WorkLeaseLost:
        return "lease_lost"
    except (Error, ValueError, RuntimeError) as error:
        registry.fail(
            claim,
            RetryClassification.RETRYABLE,
            error_code="PUBLIC_REPORT_FAILED",
            error_message=str(error),
        )
        return "failed"


def run_public_reports(
    connection: Connection[Any],
    *,
    report_kind: str,
    scope_ids: tuple[UUID, ...],
    horizon: str,
    limit: int,
    lease_duration: timedelta,
    code_commit_sha: str,
    dependency_lock_sha256: str,
) -> dict[str, Any]:
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("public reports require an idle connection")
    _validate(
        report_kind,
        scope_ids,
        horizon,
        limit,
        lease_duration,
        code_commit_sha,
        dependency_lock_sha256,
    )
    counts = dict.fromkeys(("published", "busy_or_complete", "lease_lost", "failed"), 0)
    owner = f"public-reports:{uuid4()}"
    outcomes = []
    for scope in scope_ids[:limit]:
        try:
            state = _run_scope(
                connection,
                report_kind,
                scope,
                horizon,
                lease_duration,
                owner,
                code_commit_sha,
                dependency_lock_sha256,
            )
            error = None
        except (Error, ValueError, RuntimeError) as failure:
            state, error = "failed", str(failure)[:1000]
        counts[state] += 1
        outcomes.append({"scope_id": str(scope), "state": state, "error": error})
    return {
        "status": "COMPLETED_WITH_ERRORS"
        if counts["failed"] or counts["lease_lost"]
        else "COMPLETED",
        "selected": min(len(scope_ids), limit),
        "policy_version": POLICY_VERSION,
        "scopes": outcomes,
        **counts,
    }


def _run_scope(
    connection: Connection[Any],
    kind: str,
    scope: UUID,
    horizon: str,
    lease: timedelta,
    owner: str,
    code: str,
    dependency: str,
) -> str:
    snapshot = _snapshot(connection, kind, scope, horizon)
    inputs = {
        "report_kind": kind,
        "scope_id": str(scope),
        "horizon": horizon,
        "source_fingerprint": snapshot["source_fingerprint"],
        "source_manifest": snapshot["source_manifest"],
        "policy_version": POLICY_VERSION,
        "code_commit_sha": code,
        "dependency_lock_sha256": dependency,
    }
    digest = sha256_bytes(canonical_json_bytes(inputs))
    request = WorkRequest(
        work_type=WorkType.READ_MODEL_PROJECTION,
        semantic_key=f"public-report:{digest}",
        input_hash=digest,
        priority=0,
        available_at=snapshot["source_observed_at"],
        max_attempts=2**31 - 1,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()),
    )
    return _publish(connection, request, snapshot, inputs, lease, owner)


def report_provenance(environment: Mapping[str, str]) -> tuple[str, str]:
    """Resolve the committed code and lockfile identities used by read reports."""
    root = Path(__file__).resolve().parents[5]
    code_commit_sha = environment.get("FOOTBALL_CODE_COMMIT_SHA", "")
    if not code_commit_sha:
        try:
            code_commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                check=True,
                text=True,
                timeout=15,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("code Git SHA is required; set FOOTBALL_CODE_COMMIT_SHA") from error
    dependency_lock_sha256 = environment.get("FOOTBALL_DEPENDENCY_LOCK_SHA256", "")
    if not dependency_lock_sha256:
        try:
            dependency_lock_sha256 = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
        except OSError as error:
            raise ValueError(
                "dependency lock SHA256 is required; set FOOTBALL_DEPENDENCY_LOCK_SHA256"
            ) from error
    return code_commit_sha, dependency_lock_sha256


def run_pending_context_reports(
    connection: Connection[Any],
    *,
    limit: int = CONTEXT_REPORT_BATCH_LIMIT,
    lease_duration: timedelta = timedelta(minutes=2),
    code_commit_sha: str,
    dependency_lock_sha256: str,
) -> dict[str, Any]:
    """Publish queued context projections, then complete only current generations."""
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("context report refresh requires an idle connection")
    if type(limit) is not int or limit <= 0 or limit > CONTEXT_REPORT_BATCH_LIMIT:
        raise ValueError("context report refresh limit must be between 1 and 32")
    if lease_duration <= timedelta():
        raise ValueError("context report refresh requires a positive lease")

    # Half the batch is reserved for the oldest eligible backlog. The remainder
    # prefers the live/pre-match context window. Failed items rotate by attempt
    # time and wait at least one scheduler tick before another attempt.
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            """WITH oldest AS (
                SELECT work.fixture_id,work.generation
                FROM football.product_context_report_refresh_work work
                WHERE work.generation>work.completed_generation AND work.retry_at<=clock_timestamp()
                ORDER BY work.last_attempt_at NULLS FIRST,work.requested_at,work.fixture_id
                LIMIT %s
            ), relevant AS (
                SELECT work.fixture_id,work.generation
                FROM football.product_context_report_refresh_work work
                JOIN football.product_fixtures fixture USING (fixture_id)
                WHERE work.generation>work.completed_generation AND work.retry_at<=clock_timestamp()
                  AND NOT EXISTS (SELECT 1 FROM oldest WHERE oldest.fixture_id=work.fixture_id)
                ORDER BY CASE WHEN fixture.kickoff_at BETWEEN
                    clock_timestamp()-interval '24 hours' AND clock_timestamp()+interval '72 hours'
                    THEN 0 ELSE 1 END,
                    work.last_attempt_at NULLS FIRST,work.requested_at,
                    fixture.kickoff_at,work.fixture_id
                LIMIT %s
            ) SELECT * FROM oldest UNION ALL SELECT * FROM relevant""",
            ((limit + 1) // 2, limit // 2),
        )
        selected = [("CONTEXT", row[0], "LATEST", row[1]) for row in cursor.fetchall()]
    result = _refresh_selected(
        connection, selected, lease_duration, code_commit_sha, dependency_lock_sha256
    )
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        row = cursor.execute(
            """SELECT count(*) FROM football.product_context_report_refresh_work
            WHERE generation>completed_generation"""
        ).fetchone()
    result["context_reports_pending"] = row[0] if row is not None else 0
    result["context_reports_published"] = result.pop("published")
    return result


CONTEXT_BACKFILL_LIMIT = 50_000


def enqueue_pre_policy_context_reports(connection: Connection[Any], limit: int) -> dict[str, int]:
    """Queue fixtures whose latest context report predates the form policy.

    A report built from public_context_source (v1) has no ``form`` object. The
    API keeps serving it with RECENT_FORM_POLICY_UNKNOWN until a v2 report
    exists, so queuing is safe at any pace: published reports are immutable and
    a rebuild only adds a new record. Newest kickoffs go first; fixtures already
    pending are left as they are so the near-term priority of the worker holds.
    """
    if type(limit) is not int or not 0 < limit <= CONTEXT_BACKFILL_LIMIT:
        raise ValueError(f"backfill limit must be between 1 and {CONTEXT_BACKFILL_LIMIT}")
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        row = cursor.execute(
            """WITH latest AS (
                   SELECT DISTINCT ON (r.scope_id) r.scope_id, r.record_bytes
                   FROM football.product_read_reports r
                   WHERE r.report_kind='CONTEXT' AND r.horizon='LATEST'
                   ORDER BY r.scope_id, r.source_observed_at DESC, r.registered_at DESC,
                            r.input_sha256 DESC
               ), pre_policy AS (
                   SELECT f.fixture_id, f.kickoff_at
                   FROM latest
                   JOIN football.product_fixtures f ON f.fixture_id=latest.scope_id
                   WHERE jsonb_typeof(convert_from(latest.record_bytes,'UTF8')::jsonb->'form')
                         IS DISTINCT FROM 'object'
                     AND NOT EXISTS (
                         SELECT 1 FROM football.product_context_report_refresh_work w
                         WHERE w.fixture_id=f.fixture_id AND w.generation>w.completed_generation)
               ), chosen AS (
                   SELECT fixture_id FROM pre_policy ORDER BY kickoff_at DESC, fixture_id LIMIT %s
               ), queued AS (
                   SELECT football.enqueue_product_context_report_refresh(fixture_id) FROM chosen
               )
               SELECT (SELECT count(*) FROM queued), (SELECT count(*) FROM pre_policy)""",
            (limit,),
        ).fetchone()
    assert row is not None
    return {"queued": row[0], "pre_policy_before": row[1], "pre_policy_after": row[1] - row[0]}


def drain_context_reports(
    connection: Connection[Any],
    *,
    seconds: float,
    lease_duration: timedelta,
    code_commit_sha: str,
    dependency_lock_sha256: str,
) -> dict[str, Any]:
    """Run the normal context worker repeatedly until the queue is empty or time is up."""
    started = time.monotonic()
    totals: Counter[str] = Counter()
    runs = 0
    pending = None
    while time.monotonic() - started < seconds:
        result = run_pending_context_reports(
            connection,
            lease_duration=lease_duration,
            code_commit_sha=code_commit_sha,
            dependency_lock_sha256=dependency_lock_sha256,
        )
        runs += 1
        for key in ("context_reports_published", "failed", "lease_lost", "busy_or_complete"):
            totals[key] += int(result.get(key, 0))
        pending = result["context_reports_pending"]
        if not result["selected"] or not pending:
            break
    elapsed = time.monotonic() - started
    return {
        "runs": runs,
        **dict(totals),
        "context_reports_pending": pending,
        "seconds": round(elapsed, 1),
        "published_per_second": round(totals["context_reports_published"] / max(elapsed, 1e-9), 2),
    }


def run_pending_public_reports(
    connection: Connection[Any],
    *,
    limit: int = CONTEXT_REPORT_BATCH_LIMIT,
    lease_duration: timedelta = timedelta(minutes=2),
    code_commit_sha: str,
    dependency_lock_sha256: str,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Normal scheduled worker; each report kind has its own bounded capacity.

    With a data root it first repairs recently missed history qualification so
    the context reports refreshed in this run see it.
    """
    from football.product.external_prediction_recovery import settle_pending_predictions
    from football.product.history_requalification import maintain_history

    integrity: dict[str, Any] | None = None
    if data_root is not None:
        try:
            integrity = maintain_history(connection, data_root)
        except (Error, ValueError, RuntimeError) as error:
            connection.rollback()
            integrity = {"error": str(error)[:500]}
    settled = settle_pending_predictions(connection, datetime.now(UTC), limit=limit)
    context = run_pending_context_reports(
        connection,
        limit=limit,
        lease_duration=lease_duration,
        code_commit_sha=code_commit_sha,
        dependency_lock_sha256=dependency_lock_sha256,
    )
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        selected = []
        for kind in ("PERFORMANCE", "COMPARISON"):
            selected.extend(
                cursor.execute(
                    """SELECT report_kind,scope_id,horizon,generation
                FROM football.product_report_refresh_work
                WHERE report_kind=%s AND generation>completed_generation
                  AND retry_at<=clock_timestamp()
                ORDER BY last_attempt_at NULLS FIRST,requested_at,scope_id,horizon LIMIT %s""",
                    (kind, limit),
                ).fetchall()
            )
    result = _refresh_selected(
        connection, selected, lease_duration, code_commit_sha, dependency_lock_sha256
    )
    result["external_settlement_revisions"] = settled
    if integrity is not None:
        result["integrity"] = integrity
    result["selected"] += context["selected"]
    result["context_reports_published"] = context["context_reports_published"]
    result["context_reports_pending"] = context["context_reports_pending"]
    for key in ("failed", "lease_lost", "busy_or_complete"):
        result[key] += context[key]
    if context["status"] != "COMPLETED":
        result["status"] = "COMPLETED_WITH_ERRORS"
    return result


def _refresh_selected(
    connection: Connection[Any],
    selected: list[tuple[str, UUID, str, int]],
    lease: timedelta,
    code: str,
    dependency: str,
) -> dict[str, Any]:
    counts = dict.fromkeys(("published", "busy_or_complete", "lease_lost", "failed"), 0)
    for kind, scope, horizon, generation in selected:
        result = run_public_reports(
            connection,
            report_kind=kind,
            scope_ids=(scope,),
            horizon=horizon,
            limit=1,
            lease_duration=lease,
            code_commit_sha=code,
            dependency_lock_sha256=dependency,
        )
        outcome = result["scopes"][0]
        try:
            _finish_refresh(connection, kind, scope, horizon, generation, outcome)
        except (Error, ValueError, RuntimeError):
            # A concurrent malformed source must not abort sibling scopes either.
            outcome = {"state": "failed", "error": "REPORT_COMPLETION_FAILED"}
            _finish_refresh(connection, kind, scope, horizon, generation, outcome)
        counts[outcome["state"]] += 1
    return {
        "status": "COMPLETED_WITH_ERRORS"
        if counts["failed"] or counts["lease_lost"]
        else "COMPLETED",
        "selected": len(selected),
        **counts,
    }


def _finish_refresh(
    connection: Connection[Any],
    kind: str,
    scope: UUID,
    horizon: str,
    generation: int,
    outcome: dict[str, Any],
) -> None:
    from psycopg import sql

    table = (
        "product_context_report_refresh_work"
        if kind == "CONTEXT"
        else "product_report_refresh_work"
    )
    identity = (
        "fixture_id=%s" if kind == "CONTEXT" else "scope_id=%s AND report_kind=%s AND horizon=%s"
    )
    key = (scope,) if kind == "CONTEXT" else (scope, kind, horizon)
    error = outcome["error"] or (
        outcome["state"].upper() if outcome["state"] in ("failed", "lease_lost") else None
    )
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute("SELECT football.authorize_worker_publication()")
        complete = False
        if error is None:
            if kind == "PERFORMANCE":
                row = cursor.execute(
                    "SELECT source_fingerprint FROM football.public_performance_source(%s,%s)",
                    (scope, MONITORING_HORIZONS[horizon]),
                ).fetchone()
            else:
                function = (
                    "public_context_source_v2" if kind == "CONTEXT" else "public_comparison_source"
                )
                row = cursor.execute(
                    sql.SQL(
                        "SELECT encode(sha256(convert_to(football.{}(%s)::text,'UTF8')),'hex')"
                    ).format(sql.Identifier(function)),
                    (scope,),
                ).fetchone()
            complete = bool(
                row
                and cursor.execute(
                    "SELECT 1 FROM football.product_read_reports "
                    "WHERE report_kind=%s AND scope_id=%s "
                    "AND horizon=%s AND source_fingerprint=%s LIMIT 1",
                    (kind, scope, horizon, row[0]),
                ).fetchone()
            )
        cursor.execute(
            sql.SQL(
                "UPDATE football.{} SET last_attempt_at=clock_timestamp(),last_error=%s,"
                "retry_at=clock_timestamp()+interval '1 minute',"
                "completed_generation=CASE WHEN %s THEN %s ELSE completed_generation END,"
                "completed_at=CASE WHEN %s THEN clock_timestamp() ELSE completed_at END "
                "WHERE " + identity + " AND generation=%s"
            ).format(sql.Identifier(table)),
            (error, complete, generation, complete, *key, generation),
        )


def _validate(
    kind: str,
    scopes: tuple[UUID, ...],
    horizon: str,
    limit: int,
    lease: timedelta,
    code: str,
    dependency: str,
) -> None:
    if kind not in REPORT_KINDS or horizon not in MONITORING_HORIZONS:
        raise ValueError("unsupported public report kind or horizon")
    if kind != "PERFORMANCE" and horizon != "LATEST":
        raise ValueError("only performance reports have forecast horizons")
    if (
        not scopes
        or any(not isinstance(scope, UUID) for scope in scopes)
        or len(set(scopes)) != len(scopes)
    ):
        raise ValueError("explicit unique public report scope UUIDs are required")
    if type(limit) is not int or limit <= 0 or lease <= timedelta():
        raise ValueError("public reports require a positive limit and lease")
    if not re.fullmatch(r"[0-9a-f]{40}", code) or not re.fullmatch(r"[0-9a-f]{64}", dependency):
        raise ValueError("public reports require code and dependency hashes")
