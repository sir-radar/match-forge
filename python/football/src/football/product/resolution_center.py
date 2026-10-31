"""Qualified JSON bridge for the private-local Go Admin Resolution Center."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg import Connection

from football.product.resolution_actions import apply_one, preview
from football.product.resolution_batches import apply_batch, preview_batch, validate_batch
from football.product.resolution_cases import case_detail, case_page
from football.product.resolution_data import missing_page
from football.product.resolution_migration import migration_page
from football.product.resolution_recovery import run_pending_recovery

VIEWS = {"identity", "fixtures", "missing", "parity", "cutover", "history", "detail"}

ACTIONS = {
    "APPROVE",
    "REJECT",
    "CORRECT",
    "QUARANTINE",
    "REQUEST_EVIDENCE",
    "BLOCK",
    "REVALIDATE",
    "RESOLVE_DUPLICATE",
    "DEFER",
    "VERIFY",
    "RECOVER",
    "EXCLUDE",
}
FIELDS = {"case_key", "action", "reason", "candidate", "evidence_version", "request_id", "approved"}


def validate_case(request: dict[str, Any], *, applying: bool = False) -> None:
    if not isinstance(request, dict) or set(request) - FIELDS:
        raise ValueError("unsupported decision fields")
    key, action, reason = request.get("case_key"), request.get("action"), request.get("reason")
    if not isinstance(key, str) or not re.fullmatch(r"[a-z_]+:[A-Za-z0-9_.:-]{1,220}", key):
        raise ValueError("invalid case key")
    if not isinstance(action, str) or action not in ACTIONS:
        raise ValueError("unsupported decision action")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 2000:
        raise ValueError("a review reason is required (maximum 2000 characters)")
    candidate = request.get("candidate", {})
    if not isinstance(candidate, dict) or any(
        not isinstance(v, str) or len(v) > 256 for v in candidate.values()
    ):
        raise ValueError("candidate fields must be strings")
    if set(candidate) - {
        "target_mapping_id",
        "original_decision_id",
        "fixture_registration_id",
        "orientation",
        "fixture_id",
        "source_snapshot_id",
        "target_path",
        "recovery_path",
        "exclusion_scope",
    }:
        raise ValueError("unsupported candidate fields")
    if applying:
        validate_approval(request)


def validate_approval(request: dict[str, Any]) -> None:
    if request.get("approved") is not True:
        raise ValueError("explicit operator approval is required")
    UUID(request["request_id"])
    if not re.fullmatch(r"[a-f0-9]{64}", request.get("evidence_version", "")):
        raise ValueError("preview evidence version is required")


def validate_query(query: dict[str, Any]) -> None:
    if not isinstance(query, dict) or set(query) - {
        "provider",
        "status",
        "kind",
        "q",
        "page",
        "page_size",
        "case_key",
    }:
        raise ValueError("unsupported query fields")
    page, size = query.get("page", 1), query.get("page_size", 20)
    if (
        type(page) is not int
        or type(size) is not int
        or page < 1
        or size not in {20, 50, 100}
        or page > (2**63 - 1) // size
    ):
        raise ValueError("invalid pagination; page_size must be 20, 50, or 100")
    for key in ("provider", "status", "kind", "q", "case_key"):
        if not isinstance(query.get(key, ""), str) or len(query.get(key, "")) > 256:
            raise ValueError("invalid filter")


def read_view(
    connection: Connection[Any], repo: Path, root: Path, request: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(request, dict) or set(request) - {"operation", "view", "query"}:
        raise ValueError("unsupported resolution request")
    view, query = request.get("view"), request.get("query", {})
    validate_query(query)
    if view not in VIEWS:
        raise ValueError("unsupported resolution view")
    if view in {"identity", "fixtures", "history"}:
        return case_page(connection, view, query)
    if view == "missing":
        return missing_page(connection, root, query)
    if view in {"parity", "cutover"}:
        return migration_page(repo, view, query)
    return case_detail(connection, root, query.get("case_key", ""))


def execute(
    connection: Connection[Any], repo: Path, root: Path, request: dict[str, Any]
) -> dict[str, Any]:
    operation = request.get("operation")
    if operation == "recover_work":
        return run_pending_recovery(connection, root)
    if operation == "read":
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return read_view(connection, repo, root, request)
    if operation == "preview":
        validate_case(request["request"])
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return preview(connection, root, request["request"])
    if operation in {"batch_preview", "batch_apply"}:
        return execute_batch(connection, root, request)
    if operation != "apply":
        raise ValueError("unsupported operation")
    actor = request.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"owner:[a-f0-9]{16}", actor):
        raise ValueError("authenticated owner identity is required")
    validate_case(request["request"], applying=True)
    return apply_one(connection, root, request["request"], actor)


def execute_batch(
    connection: Connection[Any], root: Path, request: dict[str, Any]
) -> dict[str, Any]:
    requests = request["requests"]
    validate_batch(requests)
    applying = request["operation"] == "batch_apply"
    for item in requests:
        validate_case(item, applying=applying)
    if not applying:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return preview_batch(connection, root, requests)
    actor = request.get("actor")
    if not isinstance(actor, str) or not re.fullmatch(r"owner:[a-f0-9]{16}", actor):
        raise ValueError("authenticated owner identity is required")
    return apply_batch(connection, root, requests, actor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.load(sys.stdin)
        root = Path(
            os.environ.get("FOOTBALL_DATA_ROOT", str(args.repo_root / ".local/football-data"))
        )
        if not root.is_absolute():
            root = args.repo_root / root
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as connection:
            connection.execute("SET statement_timeout='20s'")
            connection.commit()
            result = execute(connection, args.repo_root, root, request)
        print(json.dumps({"status_code": 200, "data": result}, default=str))
    except (ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status_code": 409, "error": str(error)}))
    except (OSError, psycopg.Error):
        print(json.dumps({"status_code": 503, "error": "Resolution evidence unavailable or busy"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
