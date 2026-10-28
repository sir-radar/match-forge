"""Explicit scopes for derived public reports; no implicit provider or model execution."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

import psycopg

from football.forecasting.postmatch_storage import MONITORING_HORIZONS
from football.product.public_reports import (
    REPORT_KINDS,
    report_provenance,
    run_public_reports,
)


def add_public_report_command(scopes: argparse._SubParsersAction[Any]) -> None:
    command = scopes.add_parser("public-reports", help="publish derived public read reports")
    command.add_argument("--report-kind", required=True, choices=REPORT_KINDS)
    command.add_argument("--scope-id", required=True, action="append", type=UUID)
    command.add_argument("--horizon", choices=tuple(MONITORING_HORIZONS), default="LATEST")
    command.add_argument("--limit", required=True, type=int)
    command.add_argument("--lease-seconds", required=True, type=int)


def run_public_report_command(
    args: argparse.Namespace, environment: Mapping[str, str]
) -> dict[str, Any]:
    url = (
        args.database_url
        or environment.get("FOOTBALL_DATABASE_URL")
        or environment.get("DATABASE_URL")
    )
    if not url:
        raise ValueError("DATABASE_URL is required for public reports")
    lineage = dict(environment)
    if args.code_commit_sha:
        lineage["FOOTBALL_CODE_COMMIT_SHA"] = args.code_commit_sha
    if args.dependency_lock_sha256:
        lineage["FOOTBALL_DEPENDENCY_LOCK_SHA256"] = args.dependency_lock_sha256
    code_commit_sha, dependency_lock_sha256 = report_provenance(lineage)
    with psycopg.connect(url) as connection:
        return run_public_reports(
            connection,
            report_kind=args.report_kind,
            scope_ids=tuple(args.scope_id),
            horizon=args.horizon,
            limit=args.limit,
            lease_duration=timedelta(seconds=args.lease_seconds),
            code_commit_sha=code_commit_sha,
            dependency_lock_sha256=dependency_lock_sha256,
        )
