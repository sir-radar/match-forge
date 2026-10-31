"""Read-only JSON bridge for the private-local Go Admin Resolution Center."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

from football.product.resolution_cases import case_detail, case_page
from football.product.resolution_data import missing_page
from football.product.resolution_migration import migration_page

VIEWS = {"identity", "fixtures", "missing", "parity", "cutover", "history", "detail"}


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
    if request.get("operation") != "read":
        raise ValueError("Resolution Center is read-only")
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
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    return read_view(connection, repo, root, request)


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
    except ValueError as error:
        print(json.dumps({"status_code": 400, "error": str(error)}))
    except (KeyError, TypeError, OSError, psycopg.Error):
        print(json.dumps({"status_code": 503, "error": "Resolution evidence unavailable or busy"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
