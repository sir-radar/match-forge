from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.cli.main import run
from football.forecasting.governance import EvaluationCorpusV1
from jsonschema import Draft202012Validator, FormatChecker
from psycopg import Connection

from tests.support.sprint1_fixtures import FixtureProvider, load_sprint1_fixture

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "schemas/quality/statsbomb-quality-policy-v1.json"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "schemas/contracts/ingestion-report-v1.schema.json"


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


@pytest.mark.parametrize(
    ("fixture_name", "expected_status", "expected_exit"),
    (("valid", "passed", 0), ("quality", "quarantined", 5)),
)
def test_cli_ingests_and_validates_fixture_season(
    connection: Connection[Any],
    tmp_path: Path,
    fixture_name: str,
    expected_status: str,
    expected_exit: int,
) -> None:
    fixture = load_sprint1_fixture(fixture_name)

    @contextmanager
    def connection_factory(_database_url: str) -> Iterator[Connection[Any]]:
        yield connection

    def provider_factory(_source_git_sha: str) -> FixtureProvider:
        return FixtureProvider(fixture)

    common = [
        "--database-url",
        DATABASE_URL,
        "--data-root",
        str(tmp_path),
        "--quality-policy",
        str(POLICY_PATH),
        "--source-git-sha",
        fixture.snapshot.source_git_sha,
    ]

    def invoke(arguments: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        exit_code = run(
            [*common, *arguments],
            environ={},
            stdout=stdout,
            stderr=stderr,
            connection_factory=connection_factory,
            provider_factory=provider_factory,
        )
        return exit_code, stdout.getvalue(), stderr.getvalue()

    competitions_exit, competitions_output, competitions_error = invoke(["ingest", "competitions"])
    season_exit, season_output, season_error = invoke(
        ["ingest", "season", str(_season_id(fixture_name))]
    )
    reports = sorted(tmp_path.glob("reports/ingestion/report=*/ingestion-report-v1.json"))
    assert len(reports) == 2
    report_bytes = {path: path.read_bytes() for path in reports}
    report_mtimes = {path: path.stat().st_mtime_ns for path in reports}

    repeated_exit, repeated_output, repeated_error = invoke(
        ["ingest", "season", str(_season_id(fixture_name))]
    )
    validation_exit, validation_output, validation_error = invoke(
        [
            "validate",
            "season",
            str(_season_id(fixture_name)),
            "--competition-id",
            str(_season_id(fixture_name)),
        ]
    )

    assert competitions_exit == 0
    assert season_exit == expected_exit
    assert repeated_exit == expected_exit
    assert validation_exit == expected_exit
    assert competitions_error == season_error == repeated_error == validation_error == ""
    assert competitions_output.startswith("ingested competitions: source_snapshot_id=")
    assert "report_json=" in competitions_output
    assert f"ingested season {_season_id(fixture_name)}:" in season_output
    assert "matches=1" in season_output
    assert f"events={fixture.expected.dataset_rows}" in season_output
    assert f"validation_status={expected_status}" in season_output
    assert repeated_output == season_output
    assert f"validated season {_season_id(fixture_name)}:" in validation_output
    assert f"status={expected_status}" in validation_output

    schema = json.loads(REPORT_SCHEMA_PATH.read_bytes())
    documents = [json.loads(path.read_bytes()) for path in reports]
    for document in documents:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    season_report = next(
        document for document in documents if document["operation"] == "ingest_season"
    )
    assert season_report["scope"] == {
        "competition_id": _season_id(fixture_name),
        "season_id": _season_id(fixture_name),
    }
    assert season_report["dataset"]["row_count"] == fixture.expected.dataset_rows
    assert season_report["validation"]["status"] == expected_status
    assert season_report["validation"]["findings_by_rule"] == fixture.expected.finding_counts
    for path in reports:
        assert path.read_bytes() == report_bytes[path]
        assert path.stat().st_mtime_ns == report_mtimes[path]
        assert path.with_suffix(".md").is_file()


def test_cli_evaluate_sprint2_retains_failed_corpus_report(tmp_path: Path) -> None:
    transaction_modes: list[tuple[bool, psycopg.pq.TransactionStatus]] = []

    @contextmanager
    def connection_factory(database_url: str) -> Iterator[Connection[Any]]:
        with psycopg.connect(database_url) as owned:
            yield owned
            transaction_modes.append((owned.autocommit, owned.info.transaction_status))

    stdout = StringIO()
    stderr = StringIO()
    exit_code = run(
        [
            "--database-url",
            DATABASE_URL,
            "--report-root",
            str(tmp_path),
            "evaluate",
            "sprint2",
        ],
        environ={},
        stdout=stdout,
        stderr=stderr,
        connection_factory=connection_factory,
    )

    reports = tuple(tmp_path.glob("run=*/Sprint2EvaluationReportV1.json"))
    assert transaction_modes == [(True, psycopg.pq.TransactionStatus.IDLE)]
    assert exit_code == 7
    assert stderr.getvalue() == ""
    assert "Sprint 2 evaluation: status=FAIL stage=corpus-resolution" in stdout.getvalue()
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    schema = json.loads(
        (PROJECT_ROOT / "schemas/contracts/sprint2-evaluation-report-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload["scope"] is None
    assert payload["raw_match_result_metrics"] is None
    assert payload["status"] == "FAIL"
    assert payload["corpus"] == {
        "provider_code": "statsbomb_open_data",
        "provider_competition_id": 2,
        "provider_season_id": 27,
        "minimum_team_history": 10,
        "minimum_competition_history": 100,
        "minimum_scored_targets": 250,
        "competition_rules": EvaluationCorpusV1().competition_rules.to_dict(),
    }
    assert reports[0].with_suffix(".md").is_file()


def _season_id(fixture_name: str) -> int:
    return 1 if fixture_name == "valid" else 2


def test_cli_evaluation_does_not_commit_a_borrowed_transaction(
    connection: Connection[Any], tmp_path: Path
) -> None:
    connection.execute("CREATE TEMP TABLE caller_work (id integer)")
    connection.execute("INSERT INTO caller_work VALUES (1)")

    @contextmanager
    def connection_factory(_database_url: str) -> Iterator[Connection[Any]]:
        yield connection

    errors = StringIO()
    assert (
        run(
            ["--database-url", DATABASE_URL, "--report-root", str(tmp_path), "evaluate", "sprint2"],
            environ={},
            stdout=StringIO(),
            stderr=errors,
            connection_factory=connection_factory,
        )
        == 4
    )
    assert "database operation failed" in errors.getvalue()
    assert connection.autocommit is False
    assert connection.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
    assert connection.execute("SELECT id FROM caller_work").fetchall() == [(1,)]
