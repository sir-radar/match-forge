"""Operator CLI for MVP synchronization and external-source status."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg

from football.product.api_football import ApiFootballClient, ApiFootballError
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.external_predictions import import_predictions, parse_import
from football.product.football_data_org import FootballDataOrgClient, FootballDataOrgError
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
    sync = commands.add_parser("sync")
    sync.add_argument("--date", type=date.fromisoformat, default=date.today())
    sync.add_argument(
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
    external.add_argument("--date", type=date.fromisoformat, default=date.today())
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
        if args.import_file is not None:
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
        print(
            json.dumps(
                {
                    "collected": 0,
                    "enabled_sources": 0,
                    "requested_date": args.date.isoformat(),
                    "requested_source": args.source,
                    "status": "NO_APPROVED_SOURCES",
                },
                sort_keys=True,
            )
        )
        return 0
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


if __name__ == "__main__":
    raise SystemExit(main())
