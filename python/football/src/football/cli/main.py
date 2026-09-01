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
from football.forecasting.corner_labels import CornerLabelError
from football.forecasting.evidence import Sprint2EvidenceProvenanceV1
from football.forecasting.kickoff import KickoffClaimError
from football.forecasting.lifecycle import LifecycleClaimError
from football.ingestion import CanonicalIngestionError, SourceIntegrityError
from football.providers import (
    FootballDataProvider,
    ProviderFetchError,
    StatsBombOpenDataAdapter,
)
from football.reports import IngestionReportError
from football.validation import DatasetValidationError

DEFAULT_DATABASE_URL = (
    "postgresql://football:football-local-only@127.0.0.1:55433/football?sslmode=disable"
)
DEFAULT_DATA_ROOT = Path(".local/football-data")
DEFAULT_SPRINT2_REPORT_ROOT = Path(".local/reports/sprint2")
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
    parser.add_argument("--report-root", type=Path, help="Sprint 2 evaluation report root")
    parser.add_argument("--source-git-sha", help="pinned StatsBomb Open Data Git SHA")
    parser.add_argument("--quality-policy", type=Path, help="quality policy JSON path")
    parser.add_argument("--code-commit-sha", help="code Git SHA for evaluation artifacts")
    parser.add_argument(
        "--dependency-lock-sha256", help="dependency lock SHA-256 for evaluation artifacts"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="acquire and ingest provider data")
    ingest_scopes = ingest.add_subparsers(dest="scope", required=True)
    ingest_scopes.add_parser("competitions", help="ingest competition and season catalog")
    ingest_season = ingest_scopes.add_parser("season", help="ingest one complete season")
    ingest_season.add_argument("season_id", type=positive_identifier)
    ingest_season.add_argument(
        "--competition-id",
        type=positive_identifier,
        help="provider competition ID; required when season ID is ambiguous or absent from catalog",
    )

    validate = commands.add_parser("validate", help="validate published datasets")
    validate_scopes = validate.add_subparsers(dest="scope", required=True)
    validate_season = validate_scopes.add_parser("season", help="validate latest season dataset")
    validate_season.add_argument("season_id", type=positive_identifier)
    validate_season.add_argument(
        "--competition-id",
        type=positive_identifier,
        help="provider competition ID; required when season ID is ambiguous",
    )

    resolve = commands.add_parser("resolve", help="publish governed source-fact resolutions")
    resolve_scopes = resolve.add_subparsers(dest="scope", required=True)
    resolve_scopes.add_parser(
        "sprint2-lifecycle",
        help="publish completed lifecycle claims for the approved Sprint 2 corpus",
    )
    resolve_scopes.add_parser(
        "sprint2-kickoffs",
        help="publish UTC kickoff claims for the approved Sprint 2 corpus",
    )
    resolve_scopes.add_parser(
        "sprint2-corners",
        help="publish corner outcome labels for the approved Sprint 2 corpus",
    )

    evaluate = commands.add_parser("evaluate", help="run phase-gated historical evaluation")
    evaluate_scopes = evaluate.add_subparsers(dest="scope", required=True)
    evaluate_scopes.add_parser("sprint2", help="run the authoritative Sprint 2 baseline gate")
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
    report_root = args.report_root or Path(
        environment.get("FOOTBALL_SPRINT2_REPORT_ROOT", str(DEFAULT_SPRINT2_REPORT_ROOT))
    )
    quality_policy = args.quality_policy or Path(
        environment.get("FOOTBALL_QUALITY_POLICY", str(DEFAULT_QUALITY_POLICY))
    )
    source_git_sha = args.source_git_sha or environment.get("FOOTBALL_STATSBOMB_GIT_SHA")
    code_commit_sha = args.code_commit_sha or environment.get("FOOTBALL_CODE_COMMIT_SHA")
    dependency_lock_sha256 = args.dependency_lock_sha256 or environment.get(
        "FOOTBALL_DEPENDENCY_LOCK_SHA256"
    )
    if args.command == "ingest" and not source_git_sha:
        print(
            "error: source Git SHA is required; set FOOTBALL_STATSBOMB_GIT_SHA or --source-git-sha",
            file=errors,
        )
        return 2
    needs_quality_policy = _needs_quality_policy(args.command, args.scope)
    if needs_quality_policy and not quality_policy.is_file():
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
            evaluation_provenance = (
                Sprint2EvidenceProvenanceV1(code_commit_sha, dependency_lock_sha256)
                if code_commit_sha and dependency_lock_sha256
                else None
            )
            application = FootballApplication(
                connection,
                data_root,
                provider,
                quality_policy,
                report_root,
                evaluation_provenance,
            )
            return _execute(application, args, output)
    except ValueError as error:
        print(f"error: {error}", file=errors)
        return 2
    except (ProviderFetchError, SourceIntegrityError) as error:
        print(f"error: {error}", file=errors)
        return 3
    except (
        CanonicalIngestionError,
        CornerLabelError,
        DatasetPublicationError,
        DatasetValidationError,
        IngestionReportError,
        KickoffClaimError,
        LifecycleClaimError,
    ) as error:
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


def _needs_quality_policy(command: str, scope: str) -> bool:
    return command in ("validate", "evaluate") or (command == "ingest" and scope == "season")


def _execute(application: FootballApplication, args: argparse.Namespace, output: TextIO) -> int:
    if args.command == "ingest" and args.scope == "competitions":
        competition_result = application.ingest_competitions()
        print(
            "ingested competitions: "
            f"source_snapshot_id={competition_result.source_snapshot_id} "
            f"competitions={competition_result.competitions} "
            f"seasons={competition_result.seasons} "
            f"report_json={competition_result.report_json_path} "
            f"report_markdown={competition_result.report_markdown_path}",
            file=output,
        )
        return 0
    if args.command == "ingest":
        season_result = application.ingest_season(args.season_id, args.competition_id)
        print(
            f"ingested season {season_result.season_id}: "
            f"competition_id={season_result.competition_id} "
            f"matches={season_result.matches} events={season_result.events} "
            f"source_snapshot_id={season_result.source_snapshot_id} "
            f"dataset_version_id={season_result.dataset_version_id or 'none'} "
            f"validation_status={season_result.validation_status or 'not_applicable'} "
            f"findings={season_result.findings} report_json={season_result.report_json_path} "
            f"report_markdown={season_result.report_markdown_path}",
            file=output,
        )
        return {"quarantined": 5, "failed": 6}.get(season_result.validation_status or "", 0)
    if args.command == "evaluate":
        evaluation = application.evaluate_sprint2()
        print(
            f"Sprint 2 evaluation: status={evaluation.status} stage={evaluation.stage} "
            f"evaluation_run_id={evaluation.evaluation_run_id} "
            f"report_json={evaluation.json_path} "
            f"report_markdown={evaluation.markdown_path}",
            file=output,
        )
        return 0 if evaluation.status in ("PASS", "PASS_WITH_WARNINGS") else 7
    if args.command == "resolve":
        if args.scope == "sprint2-lifecycle":
            resolution = application.resolve_sprint2_lifecycle()
            print(
                "resolved Sprint 2 lifecycle: "
                f"status={resolution.status} claims={resolution.claims} "
                f"dataset_version_id={resolution.dataset_version_id} "
                f"validation_run_id={resolution.validation_run_id}",
                file=output,
            )
            return 0
        if args.scope == "sprint2-kickoffs":
            kickoffs = application.resolve_sprint2_kickoffs()
            print(
                "resolved Sprint 2 kickoffs: "
                f"status={kickoffs.status} claims={kickoffs.claims} "
                f"chronological_batches={kickoffs.chronological_batches}",
                file=output,
            )
            return 0
        corners = application.resolve_sprint2_corners()
        print(
            "resolved Sprint 2 corners: "
            f"status={corners.status} labels={corners.labels} "
            f"corner_events={corners.corner_events} "
            f"dataset_version_id={corners.dataset_version_id}",
            file=output,
        )
        return 0
    validation_result = application.validate_season(args.season_id, args.competition_id)
    print(
        f"validated season {validation_result.season_id}: "
        f"dataset_version_id={validation_result.dataset_version_id} "
        f"validation_run_id={validation_result.validation_run_id} "
        f"status={validation_result.status} findings={validation_result.findings}",
        file=output,
    )
    return {"quarantined": 5, "failed": 6}.get(validation_result.status, 0)
