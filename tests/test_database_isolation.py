"""Policy rules for the integration-test database guard, without a database."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.database_isolation import (
    CLUSTER_ENV,
    PREEXISTING_ENV,
    TOKEN_ENV,
    DatabaseIdentity,
    DatabaseIsolationError,
    IsolationPolicy,
    marker_for,
)

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "a" * 64
POLICY = IsolationPolicy(
    TOKEN, "7679", frozenset({5, 16384, 900}), frozenset({"7679:777"}), "7679:900"
)


def identity(**changes: object) -> DatabaseIdentity:
    values: dict[str, object] = {
        "system_identifier": "7679",
        "oid": 16384,
        "name": "football",
        "comment": None,
        "has_football_schema": True,
        "self_authoritative": False,
    }
    values.update(changes)
    return DatabaseIdentity(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("database", "reason"),
    [
        (identity(self_authoritative=True), "authoritative"),
        (identity(self_authoritative=True, comment=marker_for(TOKEN)), "authoritative"),
        # Only the prepared identity is exempt; a copied marker elsewhere is not.
        (identity(oid=901, self_authoritative=True, comment=marker_for(TOKEN)), "authoritative"),
        (identity(oid=900, self_authoritative=True), "authoritative"),
        (identity(oid=777, comment=marker_for(TOKEN)), "protected database identity"),
        (identity(), "not marked disposable"),
        (identity(name="football_storage_test_1"), "not marked disposable"),
        (identity(comment=marker_for("b" * 64)), "not marked disposable"),
        (identity(system_identifier="other", oid=12), "did not verify"),
    ],
)
def test_rejections(database: DatabaseIdentity, reason: str) -> None:
    assert reason in (POLICY.rejection(database) or "")


@pytest.mark.parametrize(
    "database",
    [
        identity(oid=900, comment=marker_for(TOKEN)),
        identity(oid=900, comment=marker_for(TOKEN), self_authoritative=True),
        identity(oid=123456, name="football_correction_x"),
        identity(oid=5, name="postgres", has_football_schema=False),
        identity(system_identifier="other", oid=900, comment=marker_for(TOKEN)),
    ],
)
def test_allowed(database: DatabaseIdentity) -> None:
    assert POLICY.rejection(database) is None


def test_environment_round_trip_and_fail_closed() -> None:
    assert IsolationPolicy.from_environment(POLICY.environment()) == POLICY
    for missing in (TOKEN_ENV, CLUSTER_ENV, PREEXISTING_ENV):
        environment = dict(POLICY.environment())
        del environment[missing]
        with pytest.raises(DatabaseIsolationError, match="harness"):
            IsolationPolicy.from_environment(environment)
    with pytest.raises(DatabaseIsolationError, match="too short"):
        IsolationPolicy.from_environment({**POLICY.environment(), TOKEN_ENV: "short"})


def test_marker_does_not_reveal_token() -> None:
    assert TOKEN not in marker_for(TOKEN)


def test_every_integration_test_runs_under_the_harness() -> None:
    """An integration test missing from the harness silently never runs in CI."""
    manifest = ROOT / "scripts" / "storage-integration-tests.txt"
    listed = {}
    for line in manifest.read_text().splitlines():
        shard, path = line.split()
        assert shard in {"storage", "browser"}, line
        assert path not in listed, path
        listed[path] = shard

    present = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests" / "integration").glob("test_*.py")
    }
    assert listed.keys() == present
    assert set(listed.values()) == {"storage", "browser"}
