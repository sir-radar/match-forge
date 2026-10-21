from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest
from football.coverage.resources import (
    CanonicalCoverage,
    CanonicalCoverageScope,
    CoverageError,
    ProviderCoverage,
)
from football.coverage.storage import CoverageRegistry, load_coverage, prepare_coverage
from football.providers.resource_capabilities import ResourceScope
from psycopg.errors import ForeignKeyViolation, RaiseException

NOW = datetime(2026, 10, 18, tzinfo=UTC)
SCOPE = ResourceScope(
    provider="coverage_test", resource_type="results", competition="47", season="2025"
)


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c, c.transaction(force_rollback=True):
        for code in (SCOPE.provider, "coverage_test_other"):
            c.execute(
                "INSERT INTO football.providers(code,name,source_type) "
                "VALUES (%s,'Coverage test','manual') ON CONFLICT DO NOTHING",
                (code,),
            )
        yield c


def _provider():
    return ProviderCoverage(
        scope=SCOPE,
        knowledge_cutoff=NOW,
        expected_units=("one", "two"),
        observed_units=("one",),
        qualified_units=("one",),
        evidence_refs=("eligible-snapshot",),
    )


def _canonical(c):
    competition = c.execute(
        "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
    ).fetchone()[0]
    season = c.execute(
        "INSERT INTO football.seasons(competition_id) VALUES (%s) RETURNING id", (competition,)
    ).fetchone()[0]
    scope = CanonicalCoverageScope(
        competition_id=competition, season_id=season, resource_type="results"
    )
    return CanonicalCoverage(
        scope=scope,
        knowledge_cutoff=NOW,
        expected_units=(UUID(int=1), UUID(int=2)),
        qualified_support=(
            (UUID(int=1), SCOPE.provider),
            (UUID(int=1), "coverage_test_other"),
            (UUID(int=2), "coverage_test_other"),
        ),
        evidence_refs=("canonical-eligible-snapshot",),
    )


def _known(c):
    return c.execute("SELECT clock_timestamp()").fetchone()[0]


def test_partial_provider_complete_canonical_and_exact_artifact_round_trips(connection, tmp_path):
    provider, canonical = _provider(), _canonical(connection)
    registry = CoverageRegistry(connection)
    before = _known(connection)
    first = registry.register(prepare_coverage(tmp_path, provider))
    second = registry.register(prepare_coverage(tmp_path, canonical))
    assert registry.register(prepare_coverage(tmp_path, provider)) == first
    assert registry.register(prepare_coverage(tmp_path, canonical)) == second
    assert registry.provider_at(SCOPE, before) is None
    assert registry.canonical_at(canonical.scope, before) is None
    p = registry.provider_at(SCOPE, _known(connection))
    c = registry.canonical_at(canonical.scope, _known(connection))
    assert p.metrics.status == "PARTIAL" and p.metrics.coverage_ratio == 0.5 and p.observed == 1
    assert c.metrics.status == "COMPLETE" and c.metrics.qualified == 2
    assert c.supporting_providers == ("coverage_test", "coverage_test_other")
    assert load_coverage(tmp_path, p) == provider.to_dict()
    assert load_coverage(tmp_path, c) == canonical.to_dict()
    assert connection.execute(
        "SELECT expected_canonical_units,qualified_canonical_units,coverage_ratio,status "
        "FROM football.canonical_resource_coverage WHERE report_id=%s",
        (second,),
    ).fetchone() == (2, 2, 1.0, "COMPLETE")


@pytest.mark.parametrize(
    "change",
    [
        {"competition": "48"},
        {"season": "2024"},
        {"resource_type": "lineups"},
        {"competition": None, "season": None},
    ],
)
def test_provider_coverage_never_falls_back_between_scopes(connection, tmp_path, change):
    registry = CoverageRegistry(connection)
    registry.register(prepare_coverage(tmp_path, _provider()))
    assert registry.provider_at(replace(SCOPE, **change), _known(connection)) is None


def test_newly_published_older_input_does_not_override_a_newer_snapshot(connection, tmp_path):
    registry = CoverageRegistry(connection)
    newer = _provider()
    registry.register(prepare_coverage(tmp_path, newer))
    older = replace(newer, knowledge_cutoff=NOW - timedelta(days=1), qualified_units=())
    registry.register(prepare_coverage(tmp_path, older))
    assert registry.provider_at(SCOPE, _known(connection)).report_id == newer.report_id


@pytest.mark.parametrize("table", ["provider_resource_coverage", "canonical_resource_coverage"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_coverage_snapshots_are_immutable(connection, tmp_path, table, operation):
    registry = CoverageRegistry(connection)
    report = _provider() if table == "provider_resource_coverage" else _canonical(connection)
    registry.register(prepare_coverage(tmp_path, report))
    query = (
        f"UPDATE football.{table} SET qualified=qualified"
        if operation == "UPDATE"
        else operation + (" FROM" if operation == "DELETE" else "") + f" football.{table}"
    )
    if table == "canonical_resource_coverage" and operation == "UPDATE":
        query = f"UPDATE football.{table} SET qualified_canonical_units=qualified_canonical_units"
    with pytest.raises(RaiseException, match="immutable"), connection.transaction():
        connection.execute(query)


def test_unknown_expectation_remains_unknown_in_database(connection, tmp_path):
    registry = CoverageRegistry(connection)
    report = replace(_provider(), expected_units=None)
    registry.register(prepare_coverage(tmp_path, report))
    record = registry.provider_at(SCOPE, _known(connection))
    assert record.metrics.expected is None and record.metrics.coverage_ratio is None
    assert record.metrics.status == "UNKNOWN" and record.metrics.qualified == 1


def test_invalid_supporting_provider_and_competition_season_pair_are_rejected(connection, tmp_path):
    registry = CoverageRegistry(connection)
    report = _canonical(connection)
    bad = replace(report, qualified_support=((UUID(int=1), "unregistered_coverage_provider"),))
    with pytest.raises(CoverageError, match="providers"):
        registry.register(prepare_coverage(tmp_path, bad))
    other = _canonical(connection)
    bad = replace(report, scope=replace(report.scope, season_id=other.scope.season_id))
    with pytest.raises(ForeignKeyViolation), connection.transaction():
        registry.register(prepare_coverage(tmp_path, bad))


def test_future_knowledge_and_corrupted_artifacts_cannot_be_published(connection, tmp_path):
    registry = CoverageRegistry(connection)
    report = replace(_provider(), knowledge_cutoff=_known(connection) + timedelta(days=1))
    with pytest.raises(RaiseException, match="future knowledge"):
        registry.register(prepare_coverage(tmp_path, report))
    prepared = prepare_coverage(tmp_path, _provider())
    prepared.artifact.path.write_bytes(b"changed")
    with pytest.raises(CoverageError, match="artifact bytes"):
        registry.register(prepared)
    assert registry.provider_at(SCOPE, _known(connection)) is None
