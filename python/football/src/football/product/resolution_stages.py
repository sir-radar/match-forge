"""Closed stage controls; actual projection rehearsals always restore the prior route."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection, Error
from psycopg.types.json import Jsonb

from football.product.domain import sha256_json
from football.storage.locks import LockClass, LockRequest, acquire_locks
from football.work.contracts import (
    RetryClassification,
    RetryPolicy,
    WorkClaim,
    WorkRequest,
    WorkType,
)
from football.work.storage import WorkLeaseLost, WorkRegistry

STAGE_LOCK = LockRequest(LockClass.CONTROL, "resolution-stage-control")


def stage_controls(
    connection: Connection[Any], stages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ready = connection.execute(
        "SELECT to_regclass('football.resolution_stage_settings')"
    ).fetchone()
    if not ready or not ready[0]:
        return stages
    database = connection.execute("SELECT current_database()").fetchone()
    assert database
    isolated = (
        re.fullmatch(r"football_(correction|resolution_rehearsal)_[a-f0-9]{32}", database[0])
        is not None
    )
    heads = dict(
        connection.execute(
            "SELECT stage,to_jsonb(s)-'trial_lease_token' FROM football.resolution_stage_settings s"
        )
    )
    for stage in stages:
        order = stage["order"]
        history = [
            row[0]
            for row in connection.execute(
                "SELECT to_jsonb(e) FROM football.resolution_stage_events e WHERE stage=%s "
                "ORDER BY generation DESC LIMIT 20",
                (order,),
            )
        ]
        stage.update(
            configuration=heads[order],
            switch_config_status="VERSIONED_FAIL_CLOSED",
            environment="ISOLATED" if isolated else "PRODUCTION_OR_UNREGISTERED",
            production_switch="BLOCKED; COMPLETE_PARITY_AND_SEPARATE_ACCEPTANCE_REQUIRED",
            runtime_binding="fixture_read_model"
            if order == 8
            else "NO_QUALIFIED_PRODUCTION_REPLACEMENT",
            rehearsal_available=isolated and order == 8,
            rollback_ready=order == 8
            and any(item["result"].get("restored_route") == "LEGACY" for item in history),
            rollback_control_implemented=order == 8,
            dependency_status="READY" if order == 1 else "BLOCKED; UPSTREAM_STAGE_NOT_CUT_OVER",
            approval_history_scope="LATEST_20_EVENTS; ALL_EVENTS_RETAINED",
            approval_execution_history=history,
            rehearsal_status=history[0]["result"]["status"] if history else "NOT_RUN",
            current_route="LEGACY",
            v2_ready=False,
        )
        if order == 8:
            route = connection.execute("SELECT football.resolution_fixture_route()").fetchone()
            assert route
            stage["current_route"] = route[0]
    return stages


def qualify_stage(request: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    action = request["action"]
    if action == "SWITCH_STAGE":
        raise ValueError(
            "Stage advance is blocked: complete production parity, upstream cutover, "
            "qualified runtime binding and separate owner acceptance are required"
        )
    if action not in {"REHEARSE_STAGE", "ROLLBACK_STAGE"}:
        raise ValueError("unsupported stage control")
    if detail.get("environment") != "ISOLATED":
        raise ValueError("rehearsals and rollback tests require a disposable isolated database")
    if detail["order"] != 8:
        raise ValueError(
            "No qualified production replacement is wired for this stage; preserve "
            "its explicit shadow operation until complete parity and adapter approval"
        )
    if action == "REHEARSE_STAGE" and not detail["current_projection"]["rows"]:
        raise ValueError("projection rehearsal requires a nonempty retained fixture scope")
    return {
        "status": "QUALIFIED",
        "reason": "ISOLATED_PROJECTION_ONLY; RESTORE_PRIOR_ROUTE",
        "stage": 8,
        "generation": detail["configuration"]["generation"],
    }


def enqueue_stage(
    connection: Connection[Any], request: dict[str, Any], current: dict[str, Any]
) -> UUID:
    database = connection.execute("SELECT current_database(),clock_timestamp()").fetchone()
    assert database is not None
    inputs = {
        "stage": current["qualification"]["stage"],
        "action": request["action"],
        "generation": current["qualification"]["generation"],
        "database": database[0],
        "projection": current["detail"]["current_projection"],
    }
    work = WorkRequest(
        work_type=WorkType.READ_MODEL_PROJECTION,
        semantic_key=f"resolution-stage:{UUID(request['request_id'])}",
        input_hash=sha256_json(inputs),
        priority=0,
        available_at=database[1],
        max_attempts=2**31 - 1,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()),
    )
    WorkRegistry(connection).enqueue(work)
    connection.execute(
        "INSERT INTO football.resolution_stage_work(work_id,request_id,inputs) VALUES (%s,%s,%s)",
        (work.work_id, request["request_id"], Jsonb(inputs)),
    )
    return work.work_id


def projection_digest(connection: Connection[Any], relation: str) -> dict[str, Any]:
    if relation not in {"product_serving_fixtures", "fixture_read_model"}:
        raise ValueError("unsupported fixture projection")
    # Closed relation names; order and multiplicity are part of the existing projection contract.
    row = connection.execute(
        "SELECT count(*),encode(sha256(convert_to(coalesce(string_agg("
        "to_jsonb(f)::text,E'\\n' ORDER BY fixture_id),''),'UTF8')),'hex') FROM football."
        + relation
        + " f"
    ).fetchone()
    assert row
    return {"rows": row[0], "sha256": row[1]}


class RehearsalFinished(Exception):
    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence


def projection_trial(connection: Connection[Any], claim: WorkClaim) -> dict[str, Any]:
    try:
        with connection.transaction():
            before = projection_digest(connection, "product_serving_fixtures")
            if not before["rows"]:
                raise ValueError("projection rehearsal requires a nonempty retained fixture scope")
            connection.execute("REFRESH MATERIALIZED VIEW football.fixture_read_model")
            connection.execute(
                "UPDATE football.resolution_stage_settings SET route='V2',generation=generation+1, "
                "trial_work_id=%s,trial_lease_token=%s,trial_generation=%s WHERE stage=8",
                (claim.work_id, claim.lease_token, claim.generation),
            )
            route = connection.execute("SELECT football.resolution_fixture_route()").fetchone()
            after = projection_digest(connection, "fixture_read_model")
            if route != ("V2",) or before != after:
                raise ValueError("read-model route or exact projection comparison failed")
            raise RehearsalFinished(
                {
                    "status": "REHEARSAL_PASS_ROLLED_BACK",
                    "legacy": before,
                    "v2": after,
                    "selected_route": route[0],
                    "scope": "CURRENT_FIXTURE_PROJECTION_ONLY; NOT_FULL_PRODUCTION_PARITY",
                }
            )
    except RehearsalFinished as result:
        return result.evidence
    except (Error, ValueError) as error:
        return {
            "status": "REHEARSAL_FAILED_ROLLED_BACK",
            "error": str(error),
            "scope": "CURRENT_FIXTURE_PROJECTION_ONLY; NOT_FULL_PRODUCTION_PARITY",
        }


def publish_stage(connection: Connection[Any], claim: WorkClaim) -> dict[str, Any]:
    registry = WorkRegistry(connection)
    try:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            acquire_locks(connection, (STAGE_LOCK,))
            row = connection.execute(
                "SELECT request_id,inputs FROM football.resolution_stage_work WHERE work_id=%s",
                (claim.work_id,),
            ).fetchone()
            if not row or sha256_json(row[1]) != claim.input_hash:
                raise ValueError("stage work differs from its approved immutable inputs")
            request_id, inputs = row
            database = connection.execute("SELECT current_database()").fetchone()
            if (
                not database
                or database[0] != inputs["database"]
                or inputs["stage"] != 8
                or re.fullmatch(
                    r"football_(correction|resolution_rehearsal)_[a-f0-9]{32}", database[0]
                )
                is None
            ):
                raise ValueError("stage operation is not bound to this isolated database")
            head = connection.execute(
                "SELECT generation,route FROM football.resolution_stage_settings "
                "WHERE stage=%s FOR UPDATE",
                (inputs["stage"],),
            ).fetchone()
            if not head or head[0] != inputs["generation"]:
                raise ValueError("stage configuration changed; obtain a fresh preview")
            if head[1] != "LEGACY" and inputs["action"] != "ROLLBACK_STAGE":
                raise ValueError("rollback the previous stage trial before a new rehearsal")
            if (
                inputs["action"] == "REHEARSE_STAGE"
                and projection_digest(connection, "product_serving_fixtures")
                != inputs["projection"]
            ):
                raise ValueError("fixture projection changed; obtain a fresh rehearsal preview")
            original_cache = projection_state(connection)
            with registry.progress(claim):
                outcome: dict[str, Any] = (
                    projection_trial(connection, claim)
                    if inputs["action"] == "REHEARSE_STAGE"
                    else {"status": "ROLLBACK_VERIFIED", "scope": "ISOLATED_CONFIGURATION_ONLY"}
                )
                outcome = verify_rollback(connection, outcome, original_cache)
                outcome["previous_target"] = head[1]
                connection.execute(
                    "INSERT INTO football.resolution_stage_events "
                    "(stage,generation,request_id,work_id,result) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (inputs["stage"], head[0] + 1, request_id, claim.work_id, Jsonb(outcome)),
                )
                connection.execute(
                    "UPDATE football.resolution_stage_settings "
                    "SET generation=generation+1,route='LEGACY', "
                    "trial_work_id=NULL,trial_lease_token=NULL,trial_generation=NULL "
                    "WHERE stage=%s",
                    (inputs["stage"],),
                )
            with registry.publication(claim, result_hash=sha256_json(outcome)):
                connection.execute(
                    "UPDATE football.resolution_stage_work SET outcome=%s WHERE work_id=%s",
                    (Jsonb(outcome), claim.work_id),
                )
        return {"status": "PROCESSED", "work_id": str(claim.work_id), "outcome": outcome}
    except WorkLeaseLost:
        return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
    except (ValueError, Error) as error:
        connection.rollback()
        try:
            registry.fail(
                claim,
                RetryClassification.RETRYABLE
                if isinstance(error, Error)
                else RetryClassification.BLOCKED_EXTERNAL,
                error_code="STAGE_CONTROL_BLOCKED",
                error_message=type(error).__name__ if isinstance(error, Error) else str(error),
            )
        except WorkLeaseLost:
            return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
        return {
            "status": "RETRY_WAIT" if isinstance(error, Error) else "BLOCKED",
            "work_id": str(claim.work_id),
        }


def projection_state(connection: Connection[Any]) -> dict[str, Any]:
    row = connection.execute(
        "SELECT relispopulated FROM pg_class WHERE oid='football.fixture_read_model'::regclass"
    ).fetchone()
    if not row:
        raise ValueError("fixture projection registration is missing")
    return {
        "populated": row[0],
        "digest": projection_digest(connection, "fixture_read_model") if row[0] else None,
    }


def verify_rollback(
    connection: Connection[Any], outcome: dict[str, Any], original_cache: dict[str, Any]
) -> dict[str, Any]:
    restored = connection.execute("SELECT football.resolution_fixture_route()").fetchone()
    if restored != ("LEGACY",):
        raise ValueError("rollback did not restore the original serving route")
    restored_cache = projection_state(connection)
    if restored_cache != original_cache:
        raise ValueError("rollback did not preserve the original projection cache")
    result = {
        **outcome,
        "restored_route": "LEGACY",
        "production_cutover": False,
        "cache_before": original_cache,
        "cache_after": restored_cache,
    }
    if "legacy" in outcome:
        result["restored_projection"] = projection_digest(connection, "product_serving_fixtures")
        if result["restored_projection"] != outcome["legacy"]:
            raise ValueError("rollback did not preserve original fixture rows")
    return result
