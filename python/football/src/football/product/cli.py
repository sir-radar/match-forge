"""Operator CLI for MVP synchronization and external-source status."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import urllib.error
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from football.product.api_football import ApiFootballClient, ApiFootballError
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.external_prediction_sources import SourceCollection, collect_sources
from football.product.external_predictions import import_predictions, parse_import
from football.product.football_data_org import FootballDataOrgClient, FootballDataOrgError
from football.product.football_data_uk import run_backfill as run_football_data_uk_backfill
from football.product.openfootball import run_backfill as run_openfootball_backfill
from football.product.sync import ProductSync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matchforge-product")
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql://football:football-local-only@127.0.0.1:55433/football?sslmode=disable",
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", aliases=["mvp-sync"])
    sync.add_argument("--date", type=date.fromisoformat, default=_lagos_today())
    sync.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
    )
    for name in ("backfill-openfootball", "backfill-football-data-uk", "backfill-history"):
        backfill = commands.add_parser(name)
        backfill.add_argument("--season")
        backfill.add_argument("--competition")
        backfill.add_argument("--country")
        backfill.add_argument("--all", action="store_true")
        backfill.add_argument("--refresh", action="store_true")
        backfill.add_argument(
            "--data-root",
            type=Path,
            default=Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
        )
    commands.add_parser("refresh-forecasts")
    all_sync = commands.add_parser("sync-all")
    all_sync.add_argument("--date", type=date.fromisoformat, default=_lagos_today())
    all_sync.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
    )
    sync.add_argument(
        "--max-history-leagues",
        type=int,
        default=int(os.environ.get("MVP_MAX_HISTORY_LEAGUES", "20")),
    )
    external = commands.add_parser("external-predictions")
    external.add_argument("--date", type=date.fromisoformat, default=_lagos_today())
    external.add_argument("--source")
    external.add_argument(
        "--import-file",
        type=Path,
        default=(
            Path(os.environ["MVP_EXTERNAL_PREDICTIONS_IMPORT_FILE"])
            if os.environ.get("MVP_EXTERNAL_PREDICTIONS_IMPORT_FILE")
            else None
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "external-predictions":
        return _run_external_predictions(args)
    if args.command in {
        "backfill-openfootball",
        "backfill-football-data-uk",
        "backfill-history",
        "refresh-forecasts",
        "sync-all",
    }:
        return _run_data_operation(args)
    api_key = os.environ.get("API_FOOTBALL_API_KEY", "")
    try:
        client = ApiFootballClient(api_key)
        fallback_token = os.environ.get("FOOTBALL_DATA_DOT_ORG_API_TOKEN", "")
        history_fallback = FootballDataOrgClient(fallback_token) if fallback_token else None
        with psycopg.connect(args.database_url) as connection:
            result = ProductSync(
                connection,
                client,
                args.data_root,
                MODEL_ARTIFACT_PATH,
                history_fallback,
            ).run(args.date, max_history_leagues=args.max_history_leagues)
    except (ApiFootballError, FootballDataOrgError, psycopg.Error, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _run_data_operation(args: argparse.Namespace) -> int:
    try:
        with psycopg.connect(args.database_url) as connection:
            if args.command == "refresh-forecasts":
                result: dict[str, object] = {
                    "forecasts_created": ProductSync(
                        connection,
                        ApiFootballClient("stored-data-only"),
                        Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
                        MODEL_ARTIFACT_PATH,
                    ).refresh_forecasts()
                }
                connection.commit()
            elif args.command == "backfill-openfootball":
                result = _openfootball(connection, args)
            elif args.command == "backfill-football-data-uk":
                result = _football_data_uk(connection, args)
            elif args.command == "backfill-history":
                result = _history_backfill(connection, args)
            else:
                result = _sync_all(connection, args)
    except (
        ApiFootballError,
        FootballDataOrgError,
        psycopg.Error,
        OSError,
        subprocess.SubprocessError,
        urllib.error.URLError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _openfootball(
    connection: psycopg.Connection[Any], args: argparse.Namespace
) -> dict[str, object]:
    result = run_openfootball_backfill(
        connection,
        mirror=Path(os.environ.get("OPENFOOTBALL_MIRROR", ".local/providers/openfootball")),
        data_root=args.data_root,
        season=args.season,
        competition=args.competition,
        country=args.country,
    )
    if args.refresh:
        result["forecasts_created"] = _refresh(connection, args.data_root)
    return result


def _football_data_uk(
    connection: psycopg.Connection[Any], args: argparse.Namespace
) -> dict[str, object]:
    result = run_football_data_uk_backfill(
        connection,
        data_root=args.data_root,
        season=args.season,
        competition=args.competition,
        country=args.country,
    )
    if args.refresh:
        result["forecasts_created"] = _refresh(connection, args.data_root)
    return result


def _history_backfill(
    connection: psycopg.Connection[Any], args: argparse.Namespace
) -> dict[str, object]:
    return {
        "openfootball": _openfootball(connection, args),
        "football_data_uk": _football_data_uk(connection, args),
    }


def _sync_all(connection: psycopg.Connection[Any], args: argparse.Namespace) -> dict[str, object]:
    api_key = os.environ.get("API_FOOTBALL_API_KEY", "")
    fallback_token = os.environ.get("FOOTBALL_DATA_DOT_ORG_API_TOKEN", "")
    fallback = FootballDataOrgClient(fallback_token) if fallback_token else None
    product = ProductSync(
        connection, ApiFootballClient(api_key), args.data_root, MODEL_ARTIFACT_PATH, fallback
    )
    mvp = product.run(
        args.date, max_history_leagues=int(os.environ.get("MVP_MAX_HISTORY_LEAGUES", "20"))
    )
    selectors = argparse.Namespace(
        data_root=args.data_root,
        season=None,
        competition=None,
        country=None,
        refresh=False,
    )
    history = _history_backfill(connection, selectors)
    forecasts = _refresh(connection, args.data_root)
    external_args = argparse.Namespace(
        database_url=args.database_url,
        date=args.date,
        source=None,
        import_file=None,
    )
    external_status = _run_external_predictions(external_args)
    return {
        "mvp": mvp,
        "history": history,
        "forecasts_created": forecasts,
        "external_predictions_exit_code": external_status,
    }


def _refresh(connection: psycopg.Connection[Any], data_root: Path) -> int:
    count = ProductSync(
        connection, ApiFootballClient("stored-data-only"), data_root, MODEL_ARTIFACT_PATH
    ).refresh_forecasts()
    connection.commit()
    return count


def _lagos_today() -> date:
    return datetime.now(ZoneInfo("Africa/Lagos")).date()


def _run_external_predictions(args: argparse.Namespace) -> int:
    if args.import_file is not None:
        return _run_external_import(args)
    usage_mode = os.environ.get("EXTERNAL_PREDICTION_USAGE_MODE", "PRIVATE_LOCAL")
    if usage_mode != "PRIVATE_LOCAL":
        print(
            json.dumps(
                {
                    "collected": 0,
                    "enabled_sources": 0,
                    "requested_date": args.date.isoformat(),
                    "requested_source": args.source,
                    "status": "USAGE_MODE_DISABLED",
                    "usage_mode": usage_mode,
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        results = list(
            collect_sources(
                args.date,
                requested_source=args.source,
                today=_lagos_today(),
            )
        )
        with psycopg.connect(args.database_url) as connection:
            results, collected = _persist_collections(connection, results)
    except (psycopg.Error, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    enabled = sum(result.source_code != "forebet" for result in results)
    print(
        json.dumps(
            {
                "collected": collected,
                "enabled_sources": enabled,
                "requested_date": args.date.isoformat(),
                "requested_source": args.source,
                "sources": [_collection_payload(result) for result in results],
                "status": "COMPLETED",
                "usage_mode": usage_mode,
            },
            sort_keys=True,
        )
    )
    return 0


def _persist_collections(
    connection: psycopg.Connection[Any], results: list[SourceCollection]
) -> tuple[list[SourceCollection], int]:
    collected = 0
    updated: list[SourceCollection] = []
    for result in results:
        if not result.rows:
            updated.append(result)
            continue
        try:
            inserted = import_predictions(connection, result.rows, source_code=result.source_code)
        except psycopg.Error as error:
            connection.rollback()
            updated.append(
                dataclasses.replace(result, status="PERSISTENCE_FAILED", error=str(error))
            )
            continue
        collected += inserted
        updated.append(result)
    return updated, collected


def _collection_payload(result: SourceCollection) -> dict[str, object]:
    return {
        "source": result.source_code,
        "source_page": result.source_page,
        "status": result.status,
        "parsed": len(result.rows),
        "error": result.error,
    }


def _run_external_import(args: argparse.Namespace) -> int:
    try:
        with psycopg.connect(args.database_url) as connection:
            collected = import_predictions(
                connection,
                parse_import(args.import_file),
                source_code=args.source or "manual_import",
            )
    except (json.JSONDecodeError, psycopg.Error, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "collected": collected,
                "enabled_sources": 1,
                "requested_date": args.date.isoformat(),
                "requested_source": args.source,
                "status": "IMPORTED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
