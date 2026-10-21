"""Bounded production monitoring through shared work and immutable result snapshots."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection, Error
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row, tuple_row

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.postmatch import (
    POLICY_VERSION,
    evaluate_postmatch,
    summarize_postmatch,
    validate_review_limits,
)
from football.forecasting.postmatch_contract import validate_postmatch_record
from football.storage.locks import LockClass, LockRequest, acquire_locks, lock_fixtures
from football.work.contracts import (
    RetryClassification,
    RetryPolicy,
    WorkClaim,
    WorkRequest,
    WorkType,
)
from football.work.storage import WorkLeaseLost, WorkRegistry

# Same minimum-lead-time selections as the current operational performance API.
MONITORING_HORIZONS = {
    "LATEST": 0,
    "7D": 604800,
    "3D": 259200,
    "24H": 86400,
    "6H": 21600,
    "1H": 3600,
    "15M": 900,
}
_SOURCE = """SELECT p.competition_id,p.fixture_id,p.kickoff_at,p.home_score,p.away_score,
    p.outcome_known_at,p.issued_at,f.forecast_id,f.payload_sha256,f.football_cutoff,
    f.knowledge_cutoff,f.model_algorithm_version,f.model_artifact_sha256,
    f.expected_home_goals,f.expected_away_goals,f.probabilities,f.score_matrix,
    p.score_matrix_version,c.season_label
    FROM football.product_performance_forecasts(%s::uuid[],%s) p
    JOIN football.product_forecasts f ON f.forecast_id=p.forecast_id
    JOIN football.product_competitions c ON c.competition_id=p.competition_id
    WHERE p.outcome_known_at>p.kickoff_at AND p.outcome_known_at<=clock_timestamp()"""


class PostMatchInputChanged(RuntimeError):
    """Result, identity or selected forecast changed before publication."""


def _inputs(
    row: Mapping[str, Any], horizon: str, code_commit_sha: str, dependency_lock_sha256: str
) -> dict[str, Any]:
    return {
        "contract": "PostMatchEvaluationInput",
        "policy_version": POLICY_VERSION,
        "code_commit_sha": code_commit_sha,
        "dependency_lock_sha256": dependency_lock_sha256,
        "forecast_id": str(row["forecast_id"]),
        "forecast_payload_sha256": row["payload_sha256"],
        "fixture_id": str(row["fixture_id"]),
        "competition_id": str(row["competition_id"]),
        "season": row["season_label"],
        "model_id": row["model_algorithm_version"],
        "model_artifact_sha256": row["model_artifact_sha256"],
        "horizon": horizon,
        "data_quality_tier": "UNKNOWN",
        **{
            key: row[key].astimezone(UTC).isoformat()
            for key in (
                "kickoff_at",
                "issued_at",
                "football_cutoff",
                "knowledge_cutoff",
                "outcome_known_at",
            )
        },
        "home_goals": row["home_score"],
        "away_goals": row["away_score"],
    }


def _window(start: datetime, end: datetime, competitions: tuple[UUID, ...], horizon: str) -> None:
    if (
        start.utcoffset() is None
        or end.utcoffset() is None
        or start >= end
        or not competitions
        or any(not isinstance(item, UUID) for item in competitions)
        or len(set(competitions)) != len(competitions)
        or horizon not in MONITORING_HORIZONS
    ):
        raise ValueError(
            "monitoring requires explicit competitions, aware window and supported horizon"
        )


def _candidates(
    connection: Connection[Any],
    competitions: tuple[UUID, ...],
    horizon: str,
    start: datetime,
    end: datetime,
    limit: int,
    code_commit_sha: str,
    dependency_lock_sha256: str,
) -> list[dict[str, Any]]:
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _SOURCE
            + """ AND p.kickoff_at>=%s AND p.kickoff_at<%s
        AND NOT EXISTS (
            SELECT 1 FROM football.post_match_evaluation_inputs i
            JOIN football.post_match_evaluations e USING(input_sha256)
            WHERE i.forecast_id=p.forecast_id AND i.horizon=%s
              AND i.outcome_known_at=p.outcome_known_at
              AND i.home_goals=p.home_score AND i.away_goals=p.away_score
              AND convert_from(i.record_bytes,'UTF8')::jsonb->>'policy_version'=%s
              AND convert_from(i.record_bytes,'UTF8')::jsonb->>'code_commit_sha'=%s
              AND convert_from(i.record_bytes,'UTF8')::jsonb->>'dependency_lock_sha256'=%s
              AND convert_from(i.record_bytes,'UTF8')::jsonb->>'season'=c.season_label
              AND convert_from(i.record_bytes,'UTF8')::jsonb->>'competition_id'
                  =p.competition_id::text)
        ORDER BY p.kickoff_at,p.fixture_id LIMIT %s""",
            (
                list(competitions),
                MONITORING_HORIZONS[horizon],
                start,
                end,
                horizon,
                POLICY_VERSION,
                code_commit_sha,
                dependency_lock_sha256,
                limit,
            ),
        )
        return cursor.fetchall()


def _register(connection: Connection[Any], inputs: dict[str, Any]) -> WorkRequest:
    payload = canonical_json_bytes(inputs)
    digest = sha256_bytes(payload)
    request = WorkRequest(
        work_type=WorkType.POST_MATCH_EVALUATION,
        semantic_key=f"postmatch:{digest}",
        input_hash=digest,
        priority=0,
        available_at=datetime.fromisoformat(inputs["outcome_known_at"]),
        max_attempts=2**31 - 1,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()),
    )
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        WorkRegistry(connection).enqueue(request)
        cursor.execute(
            """INSERT INTO football.post_match_evaluation_inputs
            (input_sha256,work_id,forecast_id,fixture_id,horizon,outcome_known_at,home_goals,away_goals,record_bytes)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(input_sha256) DO NOTHING""",
            (
                digest,
                request.work_id,
                inputs["forecast_id"],
                inputs["fixture_id"],
                inputs["horizon"],
                inputs["outcome_known_at"],
                inputs["home_goals"],
                inputs["away_goals"],
                payload,
            ),
        )
        row = cursor.execute(
            "SELECT work_id,record_bytes FROM football.post_match_evaluation_inputs "
            "WHERE input_sha256=%s",
            (digest,),
        ).fetchone()
        if row is None or row[0] != request.work_id or bytes(row[1]) != payload:
            raise ValueError("post-match input registration conflict")
    return request


def publish_postmatch(
    connection: Connection[Any], claim: WorkClaim, inputs: dict[str, Any], result: dict[str, Any]
) -> None:
    """Revalidate canonical state, then publish with exact lease ownership."""
    digest = sha256_bytes(canonical_json_bytes(inputs))
    if (
        claim.work_type is not WorkType.POST_MATCH_EVALUATION
        or claim.input_hash != digest
        or result["input_sha256"] != digest
        or result["input"] != inputs
    ):
        raise ValueError("post-match publication identity mismatch")
    validate_postmatch_record(result)
    payload = canonical_json_bytes(result)
    result_hash = sha256_bytes(payload)
    with connection.transaction():
        lock_fixtures(connection, (UUID(inputs["fixture_id"]),))
        with WorkRegistry(connection).publication(claim, result_hash=result_hash):
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    _SOURCE + " AND p.forecast_id=%s",
                    (
                        [UUID(inputs["competition_id"])],
                        MONITORING_HORIZONS[inputs["horizon"]],
                        inputs["forecast_id"],
                    ),
                ).fetchone()
            if (
                row is None
                or _inputs(
                    row,
                    inputs["horizon"],
                    inputs["code_commit_sha"],
                    inputs["dependency_lock_sha256"],
                )
                != inputs
            ):
                raise PostMatchInputChanged("final result or selected pre-match forecast changed")
            acquire_locks(connection, (LockRequest(LockClass.EVALUATION, f"postmatch:{digest}"),))
            with connection.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(
                    """INSERT INTO football.post_match_evaluations
                    (input_sha256,result_sha256,record_bytes) VALUES(%s,%s,%s)
                    ON CONFLICT(input_sha256) DO NOTHING""",
                    (digest, result_hash, payload),
                )
                existing = cursor.execute(
                    "SELECT record_bytes FROM football.post_match_evaluations "
                    "WHERE input_sha256=%s",
                    (digest,),
                ).fetchone()
                if existing is None or bytes(existing[0]) != payload:
                    raise ValueError("post-match evaluation conflict")


def _process(
    connection: Connection[Any],
    row: dict[str, Any],
    horizon: str,
    owner: str,
    lease_duration: timedelta,
    code_commit_sha: str,
    dependency_lock_sha256: str,
) -> str:
    inputs = _inputs(row, horizon, code_commit_sha, dependency_lock_sha256)
    request = _register(connection, inputs)
    registry = WorkRegistry(connection)
    claim = registry.claim(
        owner, lease_duration, (WorkType.POST_MATCH_EVALUATION,), work_ids=(request.work_id,)
    )
    if claim is None:
        return "busy_or_complete"
    try:
        # Pure scoring finishes before canonical, work and publication locks.
        result = evaluate_postmatch(inputs, row)
        publish_postmatch(connection, claim, inputs, result)
        return "published"
    except PostMatchInputChanged as error:
        registry.fail(
            claim,
            RetryClassification.CANCELLED,
            error_code="POSTMATCH_INPUT_CHANGED",
            error_message=str(error),
        )
        return "stale"
    except WorkLeaseLost:
        return "lease_lost"
    except (Error, ValueError, RuntimeError) as error:
        registry.fail(
            claim,
            RetryClassification.RETRYABLE,
            error_code="POSTMATCH_EVALUATION_FAILED",
            error_message=str(error),
        )
        return "failed"


def run_postmatch(
    connection: Connection[Any],
    *,
    competitions: tuple[UUID, ...],
    window_start: datetime,
    window_end: datetime,
    horizon: str,
    limit: int,
    lease_duration: timedelta,
    code_commit_sha: str,
    dependency_lock_sha256: str,
) -> dict[str, Any]:
    _window(window_start, window_end, competitions, horizon)
    if not re.fullmatch(r"[0-9a-f]{40}", code_commit_sha) or not re.fullmatch(
        r"[0-9a-f]{64}", dependency_lock_sha256
    ):
        raise ValueError("post-match scoring requires code and dependency lock hashes")
    if (
        connection.info.transaction_status != TransactionStatus.IDLE
        or type(limit) is not int
        or limit <= 0
        or lease_duration <= timedelta()
    ):
        raise ValueError("post-match worker requires an idle connection, positive limit and lease")
    rows = _candidates(
        connection,
        competitions,
        horizon,
        window_start,
        window_end,
        limit,
        code_commit_sha,
        dependency_lock_sha256,
    )
    counts = {
        name: 0 for name in ("published", "busy_or_complete", "stale", "lease_lost", "failed")
    }
    owner = f"postmatch:{uuid4()}"
    for row in rows:
        counts[
            _process(
                connection,
                row,
                horizon,
                owner,
                lease_duration,
                code_commit_sha,
                dependency_lock_sha256,
            )
        ] += 1
    return {
        "status": "COMPLETED_WITH_ERRORS"
        if counts["failed"] or counts["lease_lost"]
        else "COMPLETED",
        "selected": len(rows),
        **counts,
        "policy_version": POLICY_VERSION,
    }


def monitor_postmatch(
    connection: Connection[Any],
    *,
    competitions: tuple[UUID, ...],
    window_start: datetime,
    window_end: datetime,
    knowledge_cutoff: datetime,
    horizon: str,
    review_limits: Mapping[str, float],
) -> dict[str, Any]:
    _window(window_start, window_end, competitions, horizon)
    validate_review_limits(review_limits)
    if knowledge_cutoff.utcoffset() is None:
        raise ValueError("monitoring requires an explicit aware knowledge cutoff")
    with connection.cursor(row_factory=tuple_row) as cursor:
        rows = cursor.execute(
            """SELECT DISTINCT ON (i.fixture_id,
            convert_from(i.record_bytes,'UTF8')::jsonb->>'model_id',i.horizon)
            e.record_bytes,e.result_sha256
            FROM football.post_match_evaluation_inputs i
            JOIN football.post_match_evaluations e USING(input_sha256)
            WHERE (convert_from(i.record_bytes,'UTF8')::jsonb->>'competition_id')::uuid
                  =ANY(%s::uuid[])
              AND (convert_from(i.record_bytes,'UTF8')::jsonb->>'kickoff_at')::timestamptz>=%s
              AND (convert_from(i.record_bytes,'UTF8')::jsonb->>'kickoff_at')::timestamptz<%s
              AND i.horizon=%s AND i.registered_at<=%s AND e.evaluated_at<=%s
            ORDER BY i.fixture_id,convert_from(i.record_bytes,'UTF8')::jsonb->>'model_id',
                     i.horizon,i.registered_at DESC,i.work_id DESC""",
            (
                list(competitions),
                window_start,
                window_end,
                horizon,
                knowledge_cutoff,
                knowledge_cutoff,
            ),
        ).fetchall()
    records = []
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for payload, digest in rows:
        if sha256_bytes(bytes(payload)) != digest:
            raise ValueError("post-match result checksum mismatch")
        record = json.loads(bytes(payload))
        validate_postmatch_record(record)
        records.append(record)
        key = tuple(
            record["input"][name]
            for name in ("model_id", "competition_id", "season", "horizon", "data_quality_tier")
        )
        groups[key].append(record)
    dimensions = ("model_id", "competition_id", "season", "horizon", "data_quality_tier")
    return {
        "policy_version": POLICY_VERSION,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "knowledge_cutoff": knowledge_cutoff.isoformat(),
        "overall": summarize_postmatch(tuple(records), review_limits=review_limits),
        "segments": [
            {
                **dict(zip(dimensions, key, strict=True)),
                **summarize_postmatch(tuple(items), review_limits=review_limits),
            }
            for key, items in sorted(groups.items())
        ],
        "coverage_scope": (
            "Selected published pre-match forecasts; excludes fixtures without forecasts."
        ),
    }
