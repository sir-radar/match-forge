from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest
from football.providers.resource_authority import (
    AuthorityError,
    AuthorityRegistry,
    ResourceAuthority,
    prepare_authority,
)
from football.providers.resource_capabilities import ResourceScope
from psycopg.errors import ForeignKeyViolation, RaiseException, UniqueViolation

NOW = datetime(2026, 10, 18, tzinfo=UTC)
SCOPE = ResourceScope(
    provider="authority_test", resource_type="results", competition="47", season="2025"
)


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c, c.transaction(force_rollback=True):
        c.execute(
            "INSERT INTO football.providers(code,name,source_type) "
            "VALUES (%s,'Authority test','http_api') ON CONFLICT DO NOTHING",
            (SCOPE.provider,),
        )
        yield c


def _authority():
    return ResourceAuthority(
        authority_id=UUID(int=400),
        scope=SCOPE,
        effective_from=NOW,
        effective_to=NOW + timedelta(days=1),
        authority_tier="reviewed-result-tier",
        qualification_state="QUALIFIED",
    )


def _publish(registry, root, item=None, *, predecessor=None, reason="Scoped qualification"):
    publication = prepare_authority(
        root,
        item or _authority(),
        decided_at=NOW,
        reason=reason,
        evidence_refs=("retained-qualification-report",),
        predecessor=predecessor,
    )
    identifier = registry.register(publication)
    return identifier, publication


def _known(c):
    return c.execute("SELECT clock_timestamp()").fetchone()[0]


def test_authority_registry_round_trip_retry_and_publication_knowledge(connection, tmp_path):
    registry = AuthorityRegistry(connection)
    before = _known(connection)
    identifier, publication = _publish(registry, tmp_path)
    assert registry.register(publication) == identifier
    assert registry.at(SCOPE, effective_at=NOW, knowledge_cutoff=before) == ()
    records = registry.at(SCOPE, effective_at=NOW, knowledge_cutoff=_known(connection))
    assert len(records) == 1 and records[0].authority == publication.authority
    assert records[0].decision_id == identifier
    assert (
        publication.decision.from_bytes(publication.artifact.path.read_bytes())
        == publication.decision
    )


@pytest.mark.parametrize(("offset", "expected"), [(-1, 0), (0, 1), (86400, 0), (86401, 0)])
def test_effective_intervals_are_half_open(connection, tmp_path, offset, expected):
    registry = AuthorityRegistry(connection)
    _publish(registry, tmp_path)
    records = registry.at(
        SCOPE, effective_at=NOW + timedelta(seconds=offset), knowledge_cutoff=_known(connection)
    )
    assert len(records) == expected


def test_interval_correction_never_resurrects_an_older_qualification(connection, tmp_path):
    registry = AuthorityRegistry(connection)
    first, _ = _publish(registry, tmp_path)
    before = _known(connection)
    corrected = replace(
        _authority(),
        effective_from=NOW + timedelta(days=1),
        effective_to=None,
        qualification_state="SUSPENDED",
    )
    second, _ = _publish(registry, tmp_path, corrected, predecessor=first)
    assert registry.at(SCOPE, effective_at=NOW, knowledge_cutoff=before)[0].decision_id == first
    assert registry.at(SCOPE, effective_at=NOW, knowledge_cutoff=_known(connection)) == ()
    records = registry.at(
        SCOPE, effective_at=corrected.effective_from, knowledge_cutoff=_known(connection)
    )
    assert len(records) == 1 and records[0].decision_id == second
    assert records[0].authority.qualification_state == "SUSPENDED"


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "other_provider"},
        {"resource_type": "lineups"},
        {"competition": "48"},
        {"season": "2024"},
        {"competition": None, "season": None},
    ],
)
def test_authority_never_falls_back_to_another_scope(connection, tmp_path, change):
    registry = AuthorityRegistry(connection)
    _publish(registry, tmp_path)
    assert (
        registry.at(replace(SCOPE, **change), effective_at=NOW, knowledge_cutoff=_known(connection))
        == ()
    )


def test_overlapping_assignments_remain_explicit_instead_of_inventing_a_winner(
    connection, tmp_path
):
    registry = AuthorityRegistry(connection)
    _publish(registry, tmp_path)
    other = replace(
        _authority(),
        authority_id=UUID(int=401),
        authority_tier="different-review-tier",
        qualification_state="REVIEW_REQUIRED",
    )
    _publish(registry, tmp_path, other)
    records = registry.at(SCOPE, effective_at=NOW, knowledge_cutoff=_known(connection))
    assert [row.authority.qualification_state for row in records] == [
        "QUALIFIED",
        "REVIEW_REQUIRED",
    ]
    assert [row.authority.authority_id for row in records] == [UUID(int=400), UUID(int=401)]


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_authority_history_is_immutable(connection, tmp_path, operation):
    registry = AuthorityRegistry(connection)
    _publish(registry, tmp_path)
    query = (
        "UPDATE football.provider_resource_authority SET authority_tier=authority_tier"
        if operation == "UPDATE"
        else operation
        + (" FROM" if operation == "DELETE" else "")
        + " football.provider_resource_authority"
    )
    with pytest.raises(RaiseException, match="immutable"), connection.transaction():
        connection.execute(query)


def test_stale_revision_and_scope_relabel_are_blocked(connection, tmp_path):
    registry = AuthorityRegistry(connection)
    first, _ = _publish(registry, tmp_path)
    second, _ = _publish(
        registry,
        tmp_path,
        replace(_authority(), qualification_state="SUSPENDED"),
        predecessor=first,
    )
    with pytest.raises(AuthorityError, match="predecessor"):
        _publish(registry, tmp_path, predecessor=first, reason="Stale fork")
    changed = replace(_authority(), scope=replace(SCOPE, resource_type="lineups"))
    with pytest.raises((RaiseException, ForeignKeyViolation)), connection.transaction():
        _publish(registry, tmp_path, changed, predecessor=second)


def test_tampered_artifact_cannot_publish_authority(connection, tmp_path):
    item = _authority()
    publication = prepare_authority(
        tmp_path, item, decided_at=NOW, reason="Qualification", evidence_refs=("report",)
    )
    publication.artifact.path.write_bytes(b"changed")
    registry = AuthorityRegistry(connection)
    with pytest.raises(AuthorityError, match="artifact bytes"):
        registry.register(publication)
    assert registry.at(SCOPE, effective_at=NOW, knowledge_cutoff=_known(connection)) == ()


def test_future_decision_cannot_be_published(connection, tmp_path):
    publication = prepare_authority(
        tmp_path,
        _authority(),
        decided_at=_known(connection) + timedelta(days=1),
        reason="Future decision",
        evidence_refs=("report",),
    )
    with pytest.raises(RaiseException, match="decision time"):
        AuthorityRegistry(connection).register(publication)


def test_database_constraints_reject_assignment_forks(connection, tmp_path):
    registry = AuthorityRegistry(connection)
    first, _ = _publish(registry, tmp_path)
    query = """INSERT INTO football.provider_resource_authority(
        decision_id,authority_id,scope_sha256,provider_id,resource_type,competition_key,season_key,
        effective_from,effective_to,authority_tier,qualification_state,predecessor_decision_id,
        decided_at,decision_contract_version,schema_sha256,artifact_path,artifact_sha256)
        SELECT %s,authority_id,scope_sha256,provider_id,resource_type,competition_key,season_key,
        effective_from,effective_to,authority_tier,'SUSPENDED',%s,
        decided_at,decision_contract_version,schema_sha256,artifact_path,artifact_sha256
        FROM football.provider_resource_authority WHERE decision_id=%s"""
    with pytest.raises(UniqueViolation), connection.transaction():
        connection.execute(query, (UUID(int=9201), None, first))
    connection.execute(query, (UUID(int=9202), first, first))
    with pytest.raises(UniqueViolation), connection.transaction():
        connection.execute(query, (UUID(int=9203), first, first))


def test_capability_support_does_not_grant_resource_authority(connection, tmp_path):
    from football.providers.capability_registry import CapabilityRegistry, prepare_capability
    from football.providers.resource_capabilities import ResourceCapability

    capability = ResourceCapability(
        availability="SUPPORTED", adapter_version="test-v1", normalizer_version="test-v1"
    )
    publication = prepare_capability(
        tmp_path,
        SCOPE,
        capability,
        decided_at=NOW,
        reason="Capability availability only",
        evidence_refs=("access-evidence",),
    )
    CapabilityRegistry(connection).register(publication)
    assert (
        AuthorityRegistry(connection).at(
            SCOPE, effective_at=NOW, knowledge_cutoff=_known(connection)
        )
        == ()
    )
