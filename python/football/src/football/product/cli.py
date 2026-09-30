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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "external-predictions":
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
        with psycopg.connect(args.database_url) as connection:
            result = ProductSync(
                connection,
                client,
                args.data_root,
                MODEL_ARTIFACT_PATH,
            ).run(args.date, max_history_leagues=args.max_history_leagues)
    except (ApiFootballError, psycopg.Error, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
