from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, TextIO

import psycopg
from psycopg import Connection

from football.cli.application import FootballApplication
from football.datasets import DatasetPublicationError
from football.ingestion import CanonicalIngestionError, SourceIntegrityError
from football.providers import (
    FootballDataProvider,
    ProviderFetchError,
    StatsBombOpenDataAdapter,
)
from football.validation import DatasetValidationError

DEFAULT_DATABASE_URL = (
    "postgresql://football:football-local-only@127.0.0.1:55433/football?sslmode=disable"
)
DEFAULT_DATA_ROOT = Path(".local/football-data")
_PACKAGED_QUALITY_POLICY = (
    Path(__file__).resolve().parents[1] / "validation/statsbomb-quality-policy-v1.json"
)
_REPOSITORY_QUALITY_POLICY = (
    Path(__file__).resolve().parents[5] / "schemas/quality/statsbomb-quality-policy-v1.json"
)
DEFAULT_QUALITY_POLICY = (
    _PACKAGED_QUALITY_POLICY if _PACKAGED_QUALITY_POLICY.is_file() else _REPOSITORY_QUALITY_POLICY
)

ConnectionFactory = Callable[[str], AbstractContextManager[Connection[Any]]]
ProviderFactory = Callable[[str], FootballDataProvider]


def _statsbomb_provider(source_git_sha: str) -> FootballDataProvider:
    return StatsBombOpenDataAdapter(source_git_sha=source_git_sha)


def positive_identifier(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("identifier must be a positive integer") from error
    if parsed <= 0 or str(parsed) != value:
        raise argparse.ArgumentTypeError("identifier must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="football", description="Football data pipeline")
    parser.add_argument("--database-url", help="PostgreSQL connection URL")
    parser.add_argument("--data-root", type=Path, help="immutable data root")
    parser.add_argument("--source-git-sha", help="pinned StatsBomb Open Data Git SHA")
    parser.add_argument("--quality-policy", type=Path, help="quality policy JSON path")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="acquire and ingest provider data")
    ingest_scopes = ingest.add_subparsers(dest="scope", required=True)
    ingest_scopes.add_parser("competitions", help="ingest competition and season catalog")
    ingest_season = ingest_scopes.add_parser("season", help="ingest one complete season")
    ingest_season.add_argument("season_id", type=positive_identifier)

    validate = commands.add_parser("validate", help="validate published datasets")
    validate_scopes = validate.add_subparsers(dest="scope", required=True)
    validate_season = validate_scopes.add_parser("season", help="validate latest season dataset")
    validate_season.add_argument("season_id", type=positive_identifier)
    return parser


def run(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    connection_factory: ConnectionFactory = psycopg.connect,
    provider_factory: ProviderFactory = _statsbomb_provider,
) -> int:
    environment = os.environ if environ is None else environ
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    args = build_parser().parse_args(argv)
    database_url = (
        args.database_url
        or environment.get("FOOTBALL_DATABASE_URL")
        or environment.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    data_root = args.data_root or Path(
        environment.get("FOOTBALL_DATA_ROOT", str(DEFAULT_DATA_ROOT))
    )
    quality_policy = args.quality_policy or Path(
        environment.get("FOOTBALL_QUALITY_POLICY", str(DEFAULT_QUALITY_POLICY))
    )
    source_git_sha = args.source_git_sha or environment.get("FOOTBALL_STATSBOMB_GIT_SHA")
    if args.command == "ingest" and not source_git_sha:
        print(
            "error: source Git SHA is required; set FOOTBALL_STATSBOMB_GIT_SHA or --source-git-sha",
            file=errors,
        )
        return 2
    if args.command == "validate" and not quality_policy.is_file():
        print(
            "error: quality policy does not exist; set FOOTBALL_QUALITY_POLICY or --quality-policy",
            file=errors,
        )
        return 2

    try:
        provider = (
            provider_factory(source_git_sha)
            if args.command == "ingest" and source_git_sha
            else None
        )
        with connection_factory(database_url) as connection:
            application = FootballApplication(connection, data_root, provider, quality_policy)
            if args.command == "ingest" and args.scope == "competitions":
                competition_result = application.ingest_competitions()
                print(
                    "ingested competitions: "
                    f"source_snapshot_id={competition_result.source_snapshot_id} "
                    f"competitions={competition_result.competitions} "
                    f"seasons={competition_result.seasons}",
                    file=output,
                )
                return 0
            if args.command == "ingest" and args.scope == "season":
                season_result = application.ingest_season(args.season_id)
                dataset_id = season_result.dataset_version_id or "none"
                print(
                    f"ingested season {season_result.season_id}: "
                    f"competition_id={season_result.competition_id} "
                    f"matches={season_result.matches} events={season_result.events} "
                    f"source_snapshot_id={season_result.source_snapshot_id} "
                    f"dataset_version_id={dataset_id}",
                    file=output,
                )
                return 0
            validation_result = application.validate_season(args.season_id)
            print(
                f"validated season {validation_result.season_id}: "
                f"dataset_version_id={validation_result.dataset_version_id} "
                f"validation_run_id={validation_result.validation_run_id} "
                f"status={validation_result.status} findings={validation_result.findings}",
                file=output,
            )
            return {"quarantined": 5, "failed": 6}.get(validation_result.status, 0)
    except ValueError as error:
        print(f"error: {error}", file=errors)
        return 2
    except (ProviderFetchError, SourceIntegrityError) as error:
        print(f"error: {error}", file=errors)
        return 3
    except (CanonicalIngestionError, DatasetPublicationError, DatasetValidationError) as error:
        print(f"error: {error}", file=errors)
        return 4
    except OSError as error:
        path = error.filename or "configured path"
        print(f"error: filesystem operation failed: {path}", file=errors)
        return 4
    except psycopg.Error:
        print("error: database operation failed", file=errors)
        return 4


def main() -> int:
    return run()
