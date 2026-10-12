"""Operator CLI for MVP synchronization and external-source status."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import urllib.error
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg

from football.product.api_football import (
    ApiFootballClient,
    ApiFootballError,
    PostgresApiFootballBudget,
)
from football.product.development_provider_preview import development_provider_preview
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.external_prediction_sources import SourceCollection, collect_sources
from football.product.external_predictions import import_predictions, parse_import
from football.product.football_data_org import FootballDataOrgClient, FootballDataOrgError
from football.product.football_data_uk import run_backfill as run_football_data_uk_backfill
from football.product.openfootball import run_backfill as run_openfootball_backfill
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.sync import HistoryWorkerFactory, ProductSync
from football.providers.fotmob import FotmobClient
from football.providers.pitchapi import PitchApiClient

_DATA_OPERATION_ERRORS = (
    ApiFootballError,
    FootballDataOrgError,
    psycopg.Error,
    OSError,
    subprocess.SubprocessError,
    urllib.error.URLError,
    ValueError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matchforge-product")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", aliases=["mvp-sync"])
    sync.add_argument("--date", type=date.fromisoformat, default=_lagos_today())
    sync.add_argument("--from-date", type=date.fromisoformat)
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
    for name in ("fotmob-sync", "pitchapi-sync"):
        provider_sync = commands.add_parser(name)
        provider_sync.add_argument("--date", type=date.fromisoformat, default=_lagos_today())
        provider_sync.add_argument("--from-date", type=date.fromisoformat)
        provider_sync.add_argument("--competition")
        provider_sync.add_argument(
            "--details-limit",
            type=int,
            default=int(os.environ.get("MATCHFORGE_PROVIDER_DETAILS_LIMIT", "10")),
        )
        provider_sync.add_argument("--live-details-limit", type=int, default=10)
        provider_sync.add_argument(
            "--data-root",
            type=Path,
            default=Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
        )
    all_sync = commands.add_parser("sync-all")
    all_sync.add_argument("--date", type=date.fromisoformat, default=_lagos_today())
    all_sync.add_argument("--from-date", type=date.fromisoformat)
    all_sync.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
    )
    for command in (sync, all_sync):
        command.add_argument(
            "--history-concurrency",
            type=int,
            default=int(os.environ.get("MVP_HISTORY_SYNC_CONCURRENCY", "3")),
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
    review = commands.add_parser("provider-mapping-review")
    review.add_argument("--provider", choices=("fotmob", "pitchapi"))
    review.add_argument("--limit", type=int, default=100)
    review.add_argument("--provider-match-id")
    review.add_argument("--fixture-id", type=UUID)
    preview = commands.add_parser("development-provider-preview")
    preview.add_argument("--fixture-id", type=UUID, required=True)
    preview.add_argument("--knowledge-cutoff", type=datetime.fromisoformat, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("error: DATABASE_URL is required", file=sys.stderr)
        return 2
    if args.command == "external-predictions":
        return _run_external_predictions(args)
    if args.command == "provider-mapping-review":
        return _run_provider_mapping_review(args)
    if args.command == "development-provider-preview":
        return _run_development_provider_preview(args)
    if args.command in {"fotmob-sync", "pitchapi-sync"}:
        return _run_operational_provider_sync(args)
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
        fallback_token = os.environ.get("FOOTBALL_DATA_DOT_ORG_API_TOKEN", "")
        history_fallback = FootballDataOrgClient(fallback_token) if fallback_token else None
        sync_run_id = _sync_run_id()
        with psycopg.connect(args.database_url) as connection:
            client = ApiFootballClient(
                api_key, request_budget=PostgresApiFootballBudget(args.database_url)
            )
            result = ProductSync(
                connection,
                client,
                args.data_root,
                MODEL_ARTIFACT_PATH,
                history_fallback,
                api_football_max_history_season=_api_football_max_history_season(),
                history_worker_factory=_history_worker_factory(
                    args.database_url,
                    api_key,
                    fallback_token,
                    args.data_root,
                    sync_run_id,
                ),
                sync_run_id=sync_run_id,
            ).run(
                args.date,
                fixture_from_date=args.from_date,
                history_concurrency=args.history_concurrency,
            )
    except (ApiFootballError, FootballDataOrgError, psycopg.Error, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _run_provider_mapping_review(args: argparse.Namespace) -> int:
    if not 1 <= args.limit <= 1000:
        print("error: limit must be between 1 and 1000", file=sys.stderr)
        return 2
    applying = args.provider_match_id is not None or args.fixture_id is not None
    if applying and (not args.provider or not args.provider_match_id or not args.fixture_id):
        print(
            "error: apply requires --provider, --provider-match-id, and --fixture-id",
            file=sys.stderr,
        )
        return 2
    with psycopg.connect(args.database_url) as connection, connection.cursor() as cursor:
        if applying:
            OperationalProviderSync(
                connection,
                Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
                provider_code=args.provider,
            ).apply_reviewed_mapping(args.provider_match_id, args.fixture_id)
            connection.commit()
            print(
                json.dumps(
                    {
                        "status": "MANUAL_ACCEPTED",
                        "provider": args.provider,
                        "provider_match_id": args.provider_match_id,
                        "fixture_id": str(args.fixture_id),
                    },
                    sort_keys=True,
                )
            )
            return 0
        cursor.execute(
            """SELECT provider_code, provider_match_id, candidate_fixture_id,
                      disposition, reason, evidence, observed_at
                 FROM football.product_provider_mapping_decisions
                WHERE disposition IN ('REVIEW_REQUIRED', 'CONTRADICTORY')
                  AND (%s IS NULL OR provider_code = %s)
                ORDER BY observed_at DESC, decision_id DESC LIMIT %s""",
            (args.provider, args.provider, args.limit),
        )
        rows = cursor.fetchall()
    print(
        json.dumps(
            [
                {
                    "provider": row[0],
                    "provider_match_id": row[1],
                    "candidate_fixture_id": str(row[2]) if row[2] else None,
                    "disposition": row[3],
                    "reason": row[4],
                    "evidence": row[5],
                    "observed_at": row[6].isoformat(),
                }
                for row in rows
            ],
            sort_keys=True,
        )
    )
    return 0


def _run_development_provider_preview(args: argparse.Namespace) -> int:
    try:
        with psycopg.connect(args.database_url) as connection:
            result = development_provider_preview(
                connection, args.fixture_id, args.knowledge_cutoff, MODEL_ARTIFACT_PATH
            )
    except (psycopg.Error, OSError, ValueError) as error:
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
    except _DATA_OPERATION_ERRORS as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("status") == "COMPLETED_WITH_ERRORS" else 0


def _run_operational_provider_sync(args: argparse.Namespace) -> int:
    from_date = args.from_date or args.date
    try:
        with psycopg.connect(args.database_url) as connection:
            stale_after = int(os.environ.get("MATCHFORGE_LIVE_STALE_AFTER_SECONDS", "180"))
            minimum_interval = float(
                os.environ.get("MATCHFORGE_PROVIDER_MIN_INTERVAL_SECONDS", "1")
            )
            if args.command == "fotmob-sync":
                enabled = os.environ.get("MATCHFORGE_FOTMOB_ENABLED", "false") == "true"
                result = OperationalProviderSync(
                    connection,
                    args.data_root,
                    provider_code="fotmob",
                    stale_after_seconds=stale_after,
                    minimum_interval_seconds=minimum_interval,
                ).sync_fotmob(
                    FotmobClient(
                        access_approved=enabled,
                        timeout_seconds=float(
                            os.environ.get("MATCHFORGE_PROVIDER_REQUEST_TIMEOUT_SECONDS", "20")
                        ),
                    ),
                    from_date,
                    args.date,
                    details_limit=args.details_limit,
                    live_details_limit=args.live_details_limit,
                    competition_id=args.competition,
                )
            else:
                result = OperationalProviderSync(
                    connection,
                    args.data_root,
                    provider_code="pitchapi",
                    stale_after_seconds=stale_after,
                    minimum_interval_seconds=minimum_interval,
                ).sync_pitchapi(
                    PitchApiClient(
                        os.environ.get("PITCH_API_TOKEN", ""),
                        connection_timeout_seconds=float(
                            os.environ.get("MATCHFORGE_PROVIDER_CONNECTION_TIMEOUT_SECONDS", "5")
                        ),
                        request_timeout_seconds=float(
                            os.environ.get("MATCHFORGE_PROVIDER_REQUEST_TIMEOUT_SECONDS", "20")
                        ),
                    ),
                    from_date,
                    args.date,
                    details_limit=args.details_limit,
                    live_details_limit=args.live_details_limit,
                    competition_id=args.competition,
                )
            connection.commit()
    except _DATA_OPERATION_ERRORS as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("status") == "COMPLETED_WITH_ERRORS" else 0


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
    errors: dict[str, str] = {}
    pitch_sync = OperationalProviderSync(
        connection, args.data_root, provider_code="pitchapi", minimum_interval_seconds=0
    )
    pitch_stored = _run_sync_step(
        connection, "pitchapi-stored", pitch_sync.backfill_stored_history, errors
    )
    pitch_acquired: list[dict[str, object]] = []
    if os.environ.get("MATCHFORGE_PITCHAPI_ENABLED", "false") == "true":
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.provider_competition_id, competition.season_label
                     FROM football.competition_provider_mappings mapping
                     JOIN football.providers provider ON provider.id = mapping.provider_id
                     JOIN football.product_competitions competition
                       ON competition.competition_id = mapping.competition_id
                    WHERE provider.code = 'pitchapi' AND mapping.valid_to IS NULL
                      AND competition.season_label ~ '^[0-9]{4}(/[0-9]{4})?$'
                      AND (%s::text IS NULL OR competition.season_label = %s)
                      AND (%s::text IS NULL OR mapping.provider_competition_id = %s
                           OR competition.name = %s)
                    ORDER BY competition.updated_at DESC, mapping.provider_competition_id
                    LIMIT 10""",
                (
                    args.season,
                    args.season,
                    args.competition,
                    args.competition,
                    args.competition,
                ),
            )
            scopes = cursor.fetchall()
        client = PitchApiClient(
            os.environ.get("PITCH_API_TOKEN", ""),
            connection_timeout_seconds=float(
                os.environ.get("MATCHFORGE_PROVIDER_CONNECTION_TIMEOUT_SECONDS", "5")
            ),
            request_timeout_seconds=float(
                os.environ.get("MATCHFORGE_PROVIDER_REQUEST_TIMEOUT_SECONDS", "20")
            ),
        )
        for league_id, season in scopes:
            acquired = _run_sync_step(
                connection,
                f"pitchapi-{league_id}-{season}",
                partial(pitch_sync.backfill_pitchapi_league, client, league_id, season),
                errors,
            )
            if acquired is not None:
                pitch_acquired.append(acquired)
    openfootball = _run_sync_step(
        connection, "openfootball", lambda: _openfootball(connection, args), errors
    )
    football_data_uk = _run_sync_step(
        connection,
        "football-data-uk",
        lambda: _football_data_uk(connection, args),
        errors,
    )
    fotmob = _run_sync_step(
        connection,
        "fotmob-stored",
        lambda: OperationalProviderSync(
            connection, args.data_root, provider_code="fotmob", minimum_interval_seconds=0
        ).backfill_stored_history(),
        errors,
    )
    return {
        "status": "COMPLETED_WITH_ERRORS" if errors else "COMPLETED",
        "errors": errors,
        "openfootball": openfootball,
        "football_data_uk": football_data_uk,
        "fotmob": fotmob,
        "pitchapi": {"stored": pitch_stored, "acquired": pitch_acquired},
    }


def _sync_all(connection: psycopg.Connection[Any], args: argparse.Namespace) -> dict[str, object]:
    api_key = os.environ.get("API_FOOTBALL_API_KEY", "")
    fallback_token = os.environ.get("FOOTBALL_DATA_DOT_ORG_API_TOKEN", "")
    sync_run_id = _sync_run_id()
    errors: dict[str, str] = {}

    def mvp_sync() -> dict[str, int]:
        fallback = FootballDataOrgClient(fallback_token) if fallback_token else None
        return ProductSync(
            connection,
            ApiFootballClient(api_key, request_budget=PostgresApiFootballBudget(args.database_url)),
            args.data_root,
            MODEL_ARTIFACT_PATH,
            fallback,
            api_football_max_history_season=_api_football_max_history_season(),
            history_worker_factory=_history_worker_factory(
                args.database_url,
                api_key,
                fallback_token,
                args.data_root,
                sync_run_id,
            ),
            sync_run_id=sync_run_id,
        ).run(
            args.date,
            fixture_from_date=args.from_date,
            history_concurrency=args.history_concurrency,
        )

    mvp = _run_sync_step(connection, "mvp", mvp_sync, errors)
    selectors = argparse.Namespace(
        data_root=args.data_root,
        season=None,
        competition=None,
        country=None,
        refresh=False,
    )
    history = {
        "openfootball": _run_sync_step(
            connection, "openfootball", lambda: _openfootball(connection, selectors), errors
        ),
        "football_data_uk": _run_sync_step(
            connection,
            "football_data_uk",
            lambda: _football_data_uk(connection, selectors),
            errors,
        ),
    }
    fixture_start = args.from_date or args.date - timedelta(days=1)
    fixtures_from_history = _run_sync_step(
        connection,
        "fixture_history",
        lambda: ProductSync(
            connection,
            ApiFootballClient("stored-data-only"),
            args.data_root,
            MODEL_ARTIFACT_PATH,
        ).backfill_fixtures_from_history(fixture_start, args.date, datetime.now(UTC)),
        errors,
    )
    if mvp is not None and fixtures_from_history is not None:
        mvp["fixtures_from_history"] += fixtures_from_history
    forecasts = _run_sync_step(
        connection,
        "forecasts",
        lambda: _refresh(connection, args.data_root),
        errors,
    )
    external_args = argparse.Namespace(
        database_url=args.database_url,
        date=args.date,
        source=None,
        import_file=None,
    )
    external_status = _run_external_predictions(external_args)
    if external_status != 0:
        errors["external_predictions"] = f"exited with status {external_status}"
    operational: dict[str, object | None] = {}
    if os.environ.get("MATCHFORGE_PITCHAPI_ENABLED", "false") == "true":
        operational["pitchapi"] = _run_sync_step(
            connection,
            "pitchapi",
            lambda: OperationalProviderSync(
                connection, args.data_root, provider_code="pitchapi"
            ).sync_pitchapi(
                PitchApiClient(os.environ.get("PITCH_API_TOKEN", "")),
                args.from_date or args.date,
                args.date,
            ),
            errors,
        )
    if os.environ.get("MATCHFORGE_FOTMOB_ENABLED", "false") == "true":
        operational["fotmob"] = _run_sync_step(
            connection,
            "fotmob",
            lambda: OperationalProviderSync(
                connection, args.data_root, provider_code="fotmob"
            ).sync_fotmob(
                FotmobClient(access_approved=True),
                args.from_date or args.date,
                args.date,
            ),
            errors,
        )
    return {
        "status": "COMPLETED_WITH_ERRORS" if errors else "COMPLETED",
        "errors": errors,
        "mvp": mvp,
        "history": history,
        "fixtures_from_history": fixtures_from_history,
        "forecasts_created": forecasts,
        "external_predictions_exit_code": external_status,
        "operational_providers": operational,
    }


def _run_sync_step[T](
    connection: psycopg.Connection[Any],
    name: str,
    operation: Callable[[], T],
    errors: dict[str, str],
) -> T | None:
    try:
        result = operation()
        connection.commit()
        return result
    except _DATA_OPERATION_ERRORS as error:
        connection.rollback()
        errors[name] = str(error)
        return None


def _refresh(connection: psycopg.Connection[Any], data_root: Path) -> int:
    count = ProductSync(
        connection, ApiFootballClient("stored-data-only"), data_root, MODEL_ARTIFACT_PATH
    ).refresh_forecasts()
    connection.commit()
    return count


def _lagos_today() -> date:
    return datetime.now(ZoneInfo("Africa/Lagos")).date()


def _api_football_max_history_season() -> int | None:
    value = os.environ.get("API_FOOTBALL_MAX_HISTORY_SEASON")
    return int(value) if value else None


def _sync_run_id() -> UUID | None:
    value = os.environ.get("MATCHFORGE_SYNC_RUN_ID")
    return UUID(value) if value else None


def _history_worker_factory(
    database_url: str,
    api_key: str,
    fallback_token: str,
    data_root: Path,
    sync_run_id: UUID | None,
) -> HistoryWorkerFactory:
    @contextmanager
    def create_worker() -> Iterator[ProductSync]:
        fallback = FootballDataOrgClient(fallback_token) if fallback_token else None
        with psycopg.connect(database_url) as connection:
            yield ProductSync(
                connection,
                ApiFootballClient(api_key, request_budget=PostgresApiFootballBudget(database_url)),
                data_root,
                MODEL_ARTIFACT_PATH,
                fallback,
                api_football_max_history_season=_api_football_max_history_season(),
                sync_run_id=sync_run_id,
            )

    return create_worker


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
