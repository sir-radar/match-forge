from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.providers.capability_registry import CapabilityRegistry, prepare_capability
from football.providers.resource_capabilities import (
    CapabilityError,
    ResourceCapability,
    ResourceScope,
)
from football.providers.sources.contracts import ProviderPayload
from psycopg.errors import RaiseException, UniqueViolation
from psycopg.pq import TransactionStatus

NOW = datetime(2026, 10, 18, tzinfo=UTC)
SCOPE = ResourceScope(
    provider="capability_test", resource_type="lineups", competition="39", season="2025"
)
VERSIONS = {"adapter_version": "api-v1", "normalizer_version": "lineup-v1"}


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c, c.transaction(force_rollback=True):
        c.execute(
            "INSERT INTO football.providers(code,name,source_type) "
            "VALUES (%s,'Capability test','http_api') ON CONFLICT DO NOTHING",
            (SCOPE.provider,),
        )
        yield c


def _publication(
    root,
    availability="SUPPORTED",
    *,
    scope=SCOPE,
    predecessor=None,
    reason="Verified resource access",
):
    return prepare_capability(
        root,
        scope,
        ResourceCapability(
            availability=availability,
            **VERSIONS,
            historical_start=NOW.date() - timedelta(days=365),
            historical_end=NOW.date(),
            freshness_seconds=60,
            expected_completeness=0.8,
            entitlement="reviewed-account",
            rate_limit_per_minute=10,
            retention_status="reviewed-retention",
            timestamp_precision="EXACT",
            identity_quality="provider-native-ids",
        ),
        decided_at=NOW,
        reason=reason,
        evidence_refs=("retained-qualified-scope-report",),
        predecessor=predecessor,
    )


def test_runtime_registry_round_trip_retry_and_knowledge_time(connection, tmp_path):
    registry = CapabilityRegistry(connection)
    publication = _publication(tmp_path)
    before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    identifier = registry.register(publication)
    assert registry.register(publication) == identifier
    assert registry.at(SCOPE, before) is None
    known = connection.execute(
        "SELECT known_at FROM football.provider_resource_capabilities WHERE decision_id=%s",
        (identifier,),
    ).fetchone()[0]
    snapshot = registry.at(SCOPE, known)
    assert snapshot is not None and snapshot.capability == publication.capability
    assert snapshot.decision_id == publication.decision.decision_id
    assert registry.plan(SCOPE, **VERSIONS).allowed
    assert registry.plan(SCOPE, **VERSIONS).decision_id == identifier
    artifact = publication.decision.from_bytes(publication.artifact.path.read_bytes())
    assert artifact == publication.decision
    assert artifact.evidence["scope"]["competition"] == "39"


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "other_provider"},
        {"competition": "40"},
        {"season": "2024"},
        {"resource_type": "shots"},
        {"competition": None, "season": None},
    ],
)
def test_runtime_states_never_fall_back_between_scopes(connection, tmp_path, change):
    registry = CapabilityRegistry(connection)
    registry.register(_publication(tmp_path))
    other = replace(SCOPE, **change)
    assert not registry.plan(other, **VERSIONS).allowed
    assert registry.plan(other, **VERSIONS).availability == "UNKNOWN"


def test_negative_transition_blocks_planning_without_erasing_prior_knowledge(connection, tmp_path):
    registry = CapabilityRegistry(connection)
    first = registry.register(_publication(tmp_path))
    first_known = connection.execute(
        "SELECT known_at FROM football.provider_resource_capabilities WHERE decision_id=%s",
        (first,),
    ).fetchone()[0]
    second = registry.register(_publication(tmp_path, "PLAN_RESTRICTED", predecessor=first))
    assert registry.at(SCOPE, first_known).capability.availability == "SUPPORTED"
    plan = registry.plan(SCOPE, **VERSIONS)
    assert not plan.allowed and plan.availability == "PLAN_RESTRICTED"
    assert registry.register(_publication(tmp_path)) == first
    with pytest.raises(CapabilityError, match="predecessor"):
        registry.register(_publication(tmp_path, "UNSUPPORTED", predecessor=first))
    assert (
        registry.at(SCOPE, connection.execute("SELECT clock_timestamp()").fetchone()[0]).decision_id
        == second
    )


def test_catalog_scope_is_an_exact_runtime_scope(connection, tmp_path):
    scope = replace(SCOPE, resource_type="competitions", competition=None, season=None)
    registry = CapabilityRegistry(connection)
    registry.register(_publication(tmp_path, scope=scope))
    assert registry.plan(scope, **VERSIONS).allowed
    assert not registry.plan(replace(scope, competition="39"), **VERSIONS).allowed


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_capability_history_is_immutable(connection, tmp_path, operation):
    CapabilityRegistry(connection).register(_publication(tmp_path))
    query = (
        "UPDATE football.provider_resource_capabilities SET availability=availability"
        if operation == "UPDATE"
        else operation
        + (" FROM" if operation == "DELETE" else "")
        + " football.provider_resource_capabilities"
    )
    with pytest.raises(RaiseException, match="immutable"), connection.transaction():
        connection.execute(query)


def test_corrupt_and_asserted_capability_artifacts_cannot_be_registered(connection, tmp_path):
    publication = _publication(tmp_path)
    registry = CapabilityRegistry(connection)
    with pytest.raises(CapabilityError, match="differs"):
        registry.register(
            replace(
                publication, capability=replace(publication.capability, availability="UNSUPPORTED")
            )
        )
    publication.artifact.path.write_bytes(b"changed")
    with pytest.raises(CapabilityError, match="bytes differ"):
        registry.register(publication)
    assert registry.at(SCOPE, connection.execute("SELECT clock_timestamp()").fetchone()[0]) is None


def test_future_and_backdated_revisions_are_rejected(connection, tmp_path):
    registry = CapabilityRegistry(connection)
    original = _publication(tmp_path)
    identifier = registry.register(original)
    for clock, predecessor in [
        (NOW - timedelta(seconds=1), identifier),
        (
            connection.execute("SELECT clock_timestamp()").fetchone()[0] + timedelta(days=1),
            identifier,
        ),
    ]:
        item = prepare_capability(
            tmp_path,
            SCOPE,
            original.capability,
            decided_at=clock,
            reason="Invalid publication clock",
            evidence_refs=("clock-test",),
            predecessor=predecessor,
        )
        with pytest.raises(RaiseException), connection.transaction():
            registry.register(item)


def test_acquisition_rejects_open_transactions_before_any_provider_io(connection):
    calls = []
    with pytest.raises(CapabilityError, match="idle database"):
        CapabilityRegistry(connection).acquire(SCOPE, lambda: calls.append("called"), **VERSIONS)
    assert calls == []


def test_acquisition_uses_current_registry_and_finishes_transaction_before_io(tmp_path):
    # This test commits only append-only test evidence in the disposable database.
    # Other tests use different native scope keys and the entire database is dropped.
    scope = replace(SCOPE, provider="capability_acquire_test", competition=str(uuid4()))
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as c:
        c.execute(
            "INSERT INTO football.providers(code,name,source_type) "
            "VALUES (%s,'Acquisition test','http_api') ON CONFLICT DO NOTHING",
            (scope.provider,),
        )
        registry = CapabilityRegistry(c)
        calls = []

        def fetch():
            assert c.info.transaction_status == TransactionStatus.IDLE
            calls.append("called")
            return ProviderPayload(
                provider=scope.provider,
                resource_key="lineups",
                acquired_at=NOW,
                raw=b"original",
                media_type="application/json",
            )

        with pytest.raises(CapabilityError, match="UNKNOWN"):
            registry.acquire(scope, fetch, **VERSIONS)
        first = registry.register(_publication(tmp_path, scope=scope))
        assert registry.acquire(scope, fetch, **VERSIONS).raw == b"original"
        for status in (
            "UNSUPPORTED",
            "PARTIAL",
            "PLAN_RESTRICTED",
            "AUTHORIZATION_REQUIRED",
            "TEMPORARILY_UNAVAILABLE",
            "UNKNOWN",
        ):
            first = registry.register(
                _publication(
                    tmp_path,
                    status,
                    scope=scope,
                    predecessor=first,
                    reason="Observed transition " + status,
                )
            )
            if status == "PARTIAL":
                assert registry.acquire(scope, fetch, **VERSIONS).raw == b"original"
            else:
                with pytest.raises(CapabilityError, match=status):
                    registry.acquire(scope, fetch, **VERSIONS)
        assert calls == ["called", "called"]


@pytest.mark.parametrize("catalog", [False, True])
def test_database_prevents_concurrent_root_and_successor_forks(connection, tmp_path, catalog):
    registry = CapabilityRegistry(connection)
    scope = replace(SCOPE, competition=None, season=None) if catalog else SCOPE
    first = registry.register(_publication(tmp_path, scope=scope))
    query = """INSERT INTO football.provider_resource_capabilities(
        decision_id,scope_sha256,provider_id,resource_type,competition_key,season_key,
        availability,adapter_version,normalizer_version,predecessor_decision_id,
        decided_at,decision_contract_version,schema_sha256,artifact_path,artifact_sha256)
        SELECT %s,scope_sha256,provider_id,resource_type,competition_key,season_key,
        'UNKNOWN',adapter_version,normalizer_version,%s,decided_at,decision_contract_version,
        schema_sha256,artifact_path,artifact_sha256
        FROM football.provider_resource_capabilities WHERE decision_id=%s"""
    with pytest.raises(UniqueViolation), connection.transaction():
        connection.execute(query, (UUID(int=9101), None, first))
    connection.execute(query, (UUID(int=9102), first, first))
    with pytest.raises(UniqueViolation), connection.transaction():
        connection.execute(query, (UUID(int=9103), first, first))
