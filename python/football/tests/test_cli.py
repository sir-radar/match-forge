from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path

import pytest
from football.cli.main import DEFAULT_QUALITY_POLICY, build_parser, positive_identifier, run


def test_default_quality_policy_is_available() -> None:
    assert DEFAULT_QUALITY_POLICY.is_file()


def test_parser_accepts_required_sprint1_commands() -> None:
    parser = build_parser()

    competitions = parser.parse_args(["ingest", "competitions"])
    season = parser.parse_args(["ingest", "season", "106"])
    explicit_season = parser.parse_args(["ingest", "season", "27", "--competition-id", "2"])
    validation = parser.parse_args(["validate", "season", "106"])
    lifecycle = parser.parse_args(["resolve", "sprint2-lifecycle"])

    assert (competitions.command, competitions.scope) == ("ingest", "competitions")
    assert (season.command, season.scope, season.season_id) == ("ingest", "season", 106)
    assert explicit_season.competition_id == 2
    assert (validation.command, validation.scope, validation.season_id) == (
        "validate",
        "season",
        106,
    )
    assert (lifecycle.command, lifecycle.scope) == ("resolve", "sprint2-lifecycle")


@pytest.mark.parametrize("value", ("0", "-1", "abc", "1.5"))
def test_positive_identifier_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="positive integer"):
        positive_identifier(value)


def test_ingest_requires_pinned_source_revision_before_connecting() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["ingest", "competitions"],
        environ={},
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "error: source Git SHA is required; set FOOTBALL_STATSBOMB_GIT_SHA or --source-git-sha\n"
    )


def test_validate_does_not_require_source_revision() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["--database-url", "invalid://database", "validate", "season", "106"],
        environ={"FOOTBALL_STATSBOMB_GIT_SHA": "invalid"},
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 4
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "error: database operation failed\n"


def test_season_ingestion_requires_quality_policy_before_connecting(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        [
            "--source-git-sha",
            "1" * 40,
            "--quality-policy",
            str(tmp_path / "missing.json"),
            "ingest",
            "season",
            "106",
        ],
        environ={},
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "error: quality policy does not exist; set FOOTBALL_QUALITY_POLICY or --quality-policy\n"
    )
