from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.cli.main import run
from psycopg import Connection

from tests.support.sprint1_fixtures import FixtureProvider, load_sprint1_fixture

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "schemas/quality/statsbomb-quality-policy-v1.json"


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
    stdout = StringIO()
    stderr = StringIO()

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
    competitions_exit = run(
        [*common, "ingest", "competitions"],
        environ={},
        stdout=stdout,
        stderr=stderr,
        connection_factory=connection_factory,
        provider_factory=provider_factory,
    )
    season_exit = run(
        [*common, "ingest", "season", str(_season_id(fixture_name))],
        environ={},
        stdout=stdout,
        stderr=stderr,
        connection_factory=connection_factory,
        provider_factory=provider_factory,
    )
    validation_exit = run(
        [*common, "validate", "season", str(_season_id(fixture_name))],
        environ={},
        stdout=stdout,
        stderr=stderr,
        connection_factory=connection_factory,
        provider_factory=provider_factory,
    )

    assert competitions_exit == 0
    assert season_exit == 0
    assert validation_exit == expected_exit
    assert stderr.getvalue() == ""
    lines = stdout.getvalue().splitlines()
    assert lines[0].startswith("ingested competitions: source_snapshot_id=")
    assert f"ingested season {_season_id(fixture_name)}:" in lines[1]
    assert "matches=1" in lines[1]
    assert f"events={fixture.expected.dataset_rows}" in lines[1]
    assert f"validated season {_season_id(fixture_name)}:" in lines[2]
    assert f"status={expected_status}" in lines[2]


def _season_id(fixture_name: str) -> int:
    return 1 if fixture_name == "valid" else 2
