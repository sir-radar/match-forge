from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path

import pytest
from football.cli.main import (
    DEFAULT_QUALITY_POLICY,
    build_parser,
    immutable_identifier,
    positive_identifier,
    run,
)


def test_default_quality_policy_is_available() -> None:
    assert DEFAULT_QUALITY_POLICY.is_file()


def test_parser_accepts_required_sprint1_commands() -> None:
    parser = build_parser()

    competitions = parser.parse_args(["ingest", "competitions"])
    season = parser.parse_args(["ingest", "season", "106"])
    explicit_season = parser.parse_args(["ingest", "season", "27", "--competition-id", "2"])
    validation = parser.parse_args(["validate", "season", "106"])
    lifecycle = parser.parse_args(["resolve", "sprint2-lifecycle"])
    kickoffs = parser.parse_args(["resolve", "sprint2-kickoffs"])
    integrity = parser.parse_args(["integrity", "dataset", "10000000-0000-4000-8000-000000000001"])
    hard_gate = parser.parse_args(["integrity", "hard-gate"])
    retire = parser.parse_args(
        [
            "retire",
            "approved-test-forecast-lineage",
            "--evidence-reference",
            "decision:APPROVE_APPEND_ONLY_TEST_LINEAGE_RETIREMENT",
        ]
    )
    provider_status = parser.parse_args(
        ["provider", "status", "--provider-id", "statsbomb_open_data"]
    )

    assert (competitions.command, competitions.scope) == ("ingest", "competitions")
    assert (season.command, season.scope, season.season_id) == ("ingest", "season", 106)
    assert explicit_season.competition_id == 2
    assert (validation.command, validation.scope, validation.season_id) == (
        "validate",
        "season",
        106,
    )
    assert (lifecycle.command, lifecycle.scope) == ("resolve", "sprint2-lifecycle")
    assert (kickoffs.command, kickoffs.scope) == ("resolve", "sprint2-kickoffs")
    assert (integrity.command, integrity.scope, str(integrity.artifact_id)) == (
        "integrity",
        "dataset",
        "10000000-0000-4000-8000-000000000001",
    )
    assert (hard_gate.command, hard_gate.scope) == ("integrity", "hard-gate")
    assert (retire.command, retire.scope, retire.evidence_reference) == (
        "retire",
        "approved-test-forecast-lineage",
        "decision:APPROVE_APPEND_ONLY_TEST_LINEAGE_RETIREMENT",
    )
    assert (provider_status.command, provider_status.scope, provider_status.provider_id) == (
        "provider",
        "status",
        "statsbomb_open_data",
    )


def test_provider_status_is_read_only_and_does_not_connect() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(["provider", "status"], environ={}, stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert '"provider_id": "statsbomb_open_data"' in stdout.getvalue()


def test_provider_status_rejects_partial_lifecycle_scope_before_connecting() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["provider", "status", "--provider-id", "statsbomb_open_data", "--resource-key", "events"],
        environ={},
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "--provider-sync-policy-config" in stderr.getvalue()


def test_provider_status_does_not_accept_a_cli_freshness_target() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "provider",
                "status",
                "--provider-id",
                "statsbomb_open_data",
                "--freshness-target",
                "60",
            ]
        )


@pytest.mark.parametrize("value", ("0", "-1", "abc", "1.5"))
def test_positive_identifier_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="positive integer"):
        positive_identifier(value)


def test_integrity_identifier_rejects_non_uuid() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="UUID"):
        immutable_identifier("not-a-uuid")


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
