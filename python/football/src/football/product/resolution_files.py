"""Checksum-bound retained-file recovery; approved jobs precede filesystem publication."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection, Error
from psycopg.types.json import Jsonb

from football.product.domain import sha256_json
from football.product.resolution_data import data_detail
from football.product.sync import HISTORY_JOB_LEASE
from football.storage.raw import ImmutableFileConflict, ImmutableFileStore
from football.work.contracts import (
    RetryClassification,
    RetryPolicy,
    WorkClaim,
    WorkRequest,
    WorkType,
)
from football.work.storage import WorkLeaseLost, WorkRegistry


def recovery_plan(root: Path, detail: dict[str, Any], candidate: dict[str, str]) -> dict[str, Any]:
    target = next(
        (
            item
            for item in detail["registered_files"]
            if item["path"] == candidate.get("target_path")
        ),
        None,
    )
    if target is None:
        raise ValueError("choose an exact registered recovery target")
    payload = retained_bytes(root, candidate["recovery_path"])
    if hashlib.sha256(payload).hexdigest() != target["sha256"]:
        raise ValueError("retained bytes do not match the original registered SHA-256")
    if target["size_bytes"] is not None and len(payload) != target["size_bytes"]:
        raise ValueError("retained bytes do not match the original registered size")
    files = ImmutableFileStore(root)
    path = files.path_for(target["path"])
    if path.exists() and (path.is_symlink() or path.read_bytes() != payload):
        raise ValueError("registered path contains different bytes; recovery cannot overwrite it")
    return {
        "case_key": detail["case_key"],
        "target_path": target["path"],
        "recovery_path": candidate["recovery_path"],
        "sha256": target["sha256"],
        "size_bytes": len(payload),
        "registration_sha256": sha256_json(detail["registration"]),
    }


def retained_bytes(root: Path, relative: str) -> bytes:
    path = ImmutableFileStore(root).path_for(relative)
    if path.is_symlink() or not path.is_file():
        raise ValueError("recovery input must be a retained regular file")
    return path.read_bytes()


def enqueue_file_recovery(
    connection: Connection[Any], request_id: str, plan: dict[str, Any]
) -> UUID:
    request = WorkRequest(
        work_type=WorkType.PROVIDER_ACQUISITION,
        semantic_key=f"resolution-file:{UUID(request_id)}",
        input_hash=sha256_json(plan),
        priority=0,
        available_at=datetime.now(UTC),
        max_attempts=2**31 - 1,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()),
    )
    WorkRegistry(connection).enqueue(request)
    connection.execute(
        "INSERT INTO football.resolution_file_recovery_work(work_id,request_id,plan) "
        "VALUES (%s,%s,%s)",
        (request.work_id, request_id, Jsonb(plan)),
    )
    return request.work_id


def registered_plan(
    connection: Connection[Any], root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    detail = data_detail(connection, root, plan["case_key"])
    if sha256_json(detail["registration"]) != plan["registration_sha256"]:
        raise ValueError("registration changed; preview and approve a fresh recovery")
    target = next(
        (item for item in detail["registered_files"] if item["path"] == plan["target_path"]), None
    )
    if target is None or target["sha256"] != plan["sha256"]:
        raise ValueError("registered file identity changed; no recovery published")
    return detail


def publish_file(connection: Connection[Any], root: Path, claim: WorkClaim) -> dict[str, Any]:
    registry = WorkRegistry(connection)
    try:
        with connection.transaction():
            row = connection.execute(
                "SELECT request_id,plan FROM football.resolution_file_recovery_work "
                "WHERE work_id=%s",
                (claim.work_id,),
            ).fetchone()
            if row is None or sha256_json(row[1]) != claim.input_hash:
                raise ValueError("file recovery work does not match its approved inputs")
            request_id, plan = row
            registered_plan(connection, root, plan)
        # Verify and publish outside database coordination/publication locks. Publication is
        # exclusive and idempotent; a lost lease cannot replace different bytes or mark completion.
        target = ImmutableFileStore(root).path_for(plan["target_path"])
        # A crash may publish the authentic target before the receipt commits. Reconcile it
        # even if the temporary retained recovery copy was subsequently removed.
        payload = retained_bytes(
            root, plan["target_path"] if target.is_file() else plan["recovery_path"]
        )
        if (
            len(payload) != plan["size_bytes"]
            or hashlib.sha256(payload).hexdigest() != plan["sha256"]
        ):
            raise ValueError("recovery input changed since approval")
        claim = registry.heartbeat(claim, HISTORY_JOB_LEASE)
        write = ImmutableFileStore(root).publish(plan["target_path"], payload)
        with connection.transaction():
            current = registered_plan(connection, root, plan)
        outcome = {
            "status": "FILE_VERIFIED",
            "case_status": current["status"],
            "target_path": plan["target_path"],
            "sha256": write.sha256,
            "publication": write.status,
            "verification": current["verification"],
            "parity_status": "RECHECK_REQUIRED; FILE_RECOVERY_IS_NOT_PARITY",
        }
        with connection.transaction():
            if current["status"] == "PASS":
                from football.product.resolution_recovery import enqueue_recovery

                outcome["recovery_work_id"] = str(
                    enqueue_recovery(
                        connection,
                        str(request_id),
                        {
                            "detail": current,
                            "candidate": {},
                            "qualification": {},
                            "case_key": plan["case_key"],
                        },
                        claim.work_id,
                    )
                )
            with registry.publication(claim, result_hash=sha256_json(outcome)):
                connection.execute(
                    "UPDATE football.resolution_file_recovery_work SET outcome=%s WHERE work_id=%s",
                    (Jsonb(outcome), claim.work_id),
                )
        return {"status": "PROCESSED", "work_id": str(claim.work_id), "outcome": outcome}
    except WorkLeaseLost:
        return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
    except (ValueError, OSError, ImmutableFileConflict, Error) as error:
        connection.rollback()
        classification = (
            RetryClassification.RETRYABLE
            if isinstance(error, Error)
            else RetryClassification.BLOCKED_EXTERNAL
        )
        try:
            registry.fail(
                claim,
                classification,
                error_code="FILE_RECOVERY_FAILED",
                error_message=type(error).__name__ if isinstance(error, Error) else str(error),
            )
        except WorkLeaseLost:
            return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
        return {
            "status": "RETRY_WAIT"
            if classification == RetryClassification.RETRYABLE
            else "BLOCKED",
            "work_id": str(claim.work_id),
        }
