"""Bounded read-report production on the common work registry; no fitting or promotion."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
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
            function = "public_context_source" if kind == "CONTEXT" else "public_comparison_source"
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
    for scope in scope_ids[:limit]:
        snapshot = _snapshot(connection, report_kind, scope, horizon)
        inputs = {
            "report_kind": report_kind,
            "scope_id": str(scope),
            "horizon": horizon,
            "source_fingerprint": snapshot["source_fingerprint"],
            "source_manifest": snapshot["source_manifest"],
            "policy_version": POLICY_VERSION,
            "code_commit_sha": code_commit_sha,
            "dependency_lock_sha256": dependency_lock_sha256,
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
        counts[_publish(connection, request, snapshot, inputs, lease_duration, owner)] += 1
    return {
        "status": "COMPLETED_WITH_ERRORS"
        if counts["failed"] or counts["lease_lost"]
        else "COMPLETED",
        "selected": min(len(scope_ids), limit),
        "policy_version": POLICY_VERSION,
        **counts,
    }


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
