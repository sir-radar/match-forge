"""Explicit bounded worker and read-only monitoring commands."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from football.forecasting.postmatch import validate_review_limits
from football.forecasting.postmatch_storage import (
    MONITORING_HORIZONS,
    monitor_postmatch,
    run_postmatch,
)


def add_postmatch_commands(scopes: argparse._SubParsersAction[Any]) -> None:
    for name in ("postmatch-evaluate", "postmatch-monitor"):
        command = scopes.add_parser(name)
        command.add_argument("--competition", required=True, action="append", type=UUID)
        command.add_argument("--window-start", required=True, type=datetime.fromisoformat)
        command.add_argument("--window-end", required=True, type=datetime.fromisoformat)
        command.add_argument("--horizon", choices=tuple(MONITORING_HORIZONS), default="LATEST")
        if name == "postmatch-evaluate":
            command.add_argument("--limit", required=True, type=int)
            command.add_argument("--lease-seconds", required=True, type=int)
        else:
            command.add_argument("--knowledge-cutoff", required=True, type=datetime.fromisoformat)
            command.add_argument("--review-limits", type=Path)


def run_postmatch_command(
    args: argparse.Namespace, environment: Mapping[str, str]
) -> dict[str, Any]:
    database_url = (
        args.database_url
        or environment.get("FOOTBALL_DATABASE_URL")
        or environment.get("DATABASE_URL")
    )
    if not database_url:
        raise ValueError("DATABASE_URL is required for post-match monitoring")
    limits = {}
    if args.scope == "postmatch-monitor" and args.review_limits:
        limits = json.loads(args.review_limits.read_bytes())
        if not isinstance(limits, dict):
            raise ValueError("review limits must be a JSON object")
        validate_review_limits(limits)
    scope = {
        "competitions": tuple(args.competition),
        "window_start": args.window_start,
        "window_end": args.window_end,
        "horizon": args.horizon,
    }
    with psycopg.connect(database_url) as connection:
        if args.scope == "postmatch-evaluate":
            return run_postmatch(
                connection,
                **scope,
                code_commit_sha=args.code_commit_sha
                or environment.get("FOOTBALL_CODE_COMMIT_SHA", ""),
                dependency_lock_sha256=args.dependency_lock_sha256
                or environment.get("FOOTBALL_DEPENDENCY_LOCK_SHA256", ""),
                limit=args.limit,
                lease_duration=timedelta(seconds=args.lease_seconds),
            )
        connection.execute("SET TRANSACTION READ ONLY")
        return monitor_postmatch(
            connection, **scope, knowledge_cutoff=args.knowledge_cutoff, review_limits=limits
        )
