from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest
from football.canonical_resources.resolution import (
    CanonicalBinding,
    CanonicalCandidate,
    CanonicalResolutionError,
    resolve_canonical_resource,
)
from football.canonical_resources.storage import (
    CanonicalResolutionRegistry,
    load_canonical_decision,
    prepare_canonical_resolution,
)
from football.contracts.observations import ResultObservationV1
from football.ingestion.conflicts import ConflictRecordV1
from football.ingestion.resolution import ResolutionDecisionV1
from football.ingestion.resolution_storage import PostgresResolutionDecisionStoreV1
from football.observations.storage import ObservationArtifactStore
from psycopg.errors import RaiseException
from test_resource_observation_artifacts import NOW, _observation


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[Any]]:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as database,
        database.transaction(force_rollback=True),
    ):
        yield database


def _resolution(connection, root, *, register_identity=True, register_observation=True):
    fixture = _observation(connection, root)
    observation = ResultObservationV1(
        provenance=fixture.provenance,
        time=fixture.time,
        versions=fixture.versions,
        fixture=fixture.fixture,
        status="FINISHED",
        score_basis="REGULATION_90",
        home_goals=2,
        away_goals=1,
    )
    if register_observation:
        ObservationArtifactStore(connection, root).publish(observation)
    canonical = UUID(int=100)
    identity = ResolutionDecisionV1(
        decision_id="canonical-test-identity",
        subject_type="match",
        provider_id="api_football",
        provider_entity_id="42",
        evidence_refs=(str(fixture.provenance.source_resource_id),),
        candidate_canonical_ids=(str(canonical),),
        rule_version="reviewed-fixture",
        confidence=1,
        status="MANUALLY_APPROVED",
        selected_canonical_id=str(canonical),
        actor="test-operator",
        reason="Exact source fixture review",
        created_at=NOW,
    )
    if register_identity:
        provider = connection.execute(
            "SELECT id FROM football.providers WHERE code='api_football'"
        ).fetchone()[0]
        with connection.cursor() as cursor:
            PostgresResolutionDecisionStoreV1().register(
                cursor, provider_id=provider, decision=identity
            )
    proof = identity.to_decision_record(str(canonical))
    candidate = CanonicalCandidate(
        observation=observation,
        canonical_subject_id=canonical,
        subject_identity=proof,
        bindings=(CanonicalBinding("/fixture", canonical, proof),),
    )
    choice = ConflictRecordV1(
        conflict_id="explicit-result-review",
        subject_type=f"ResultObservation:{canonical}",
        observation_refs=(str(observation.observation_id),),
        policy_version="operator-review",
        disposition="RESOLVED",
        selected_observation_ref=str(observation.observation_id),
        reason="Reviewed retained result",
        created_at=NOW,
    )
    return resolve_canonical_resource((candidate,), choice, knowledge_cutoff=NOW)


def test_publication_round_trip_retry_and_explicit_knowledge(connection, tmp_path):
    resolution = _resolution(connection, tmp_path)
    prepared = prepare_canonical_resolution(tmp_path, resolution)
    registry = CanonicalResolutionRegistry(connection)
    before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    identifier = registry.register(resolution, prepared)
    assert registry.register(resolution, prepared) == identifier
    known = connection.execute(
        "SELECT known_at FROM football.canonical_resource_resolutions WHERE decision_id=%s",
        (identifier,),
    ).fetchone()[0]
    args = (
        resolution.resource_type,
        resolution.canonical_subject_id,
        resolution.candidates[0].context_sha256,
    )
    assert registry.latest_id_at(*args, before) is None
    assert registry.latest_id_at(*args, known) == identifier
    assert (
        load_canonical_decision(tmp_path, identifier, resolution.decision.sha256)
        == resolution.decision
    )
    assert connection.execute(
        "SELECT observation_id,role,observation_sha256 FROM football.canonical_resolution_evidence"
    ).fetchall() == [
        (
            resolution.selected.observation.observation_id,
            "SUPPORTING",
            resolution.selected.observation.sha256,
        )
    ]


@pytest.mark.parametrize("missing", ["identity", "observation"])
def test_unregistered_evidence_cannot_create_a_canonical_conclusion(connection, tmp_path, missing):
    resolution = _resolution(
        connection,
        tmp_path,
        register_identity=missing != "identity",
        register_observation=missing != "observation",
    )
    prepared = prepare_canonical_resolution(tmp_path, resolution)
    with pytest.raises(CanonicalResolutionError, match="unregistered"):
        CanonicalResolutionRegistry(connection).register(resolution, prepared)
    assert connection.execute(
        "SELECT count(*) FROM football.canonical_resource_resolutions"
    ).fetchone() == (0,)


def test_revision_retains_old_result_and_review_replaces_winner(connection, tmp_path):
    original = _resolution(connection, tmp_path)
    registry = CanonicalResolutionRegistry(connection)
    first = registry.register(original, prepare_canonical_resolution(tmp_path, original))
    old_known = connection.execute(
        "SELECT known_at FROM football.canonical_resource_resolutions WHERE decision_id=%s",
        (first,),
    ).fetchone()[0]
    choice = replace(
        original.selection,
        disposition="REVIEW_REQUIRED",
        selected_observation_ref=None,
        reason="New discrepancy needs review",
        created_at=NOW + timedelta(seconds=1),
    )
    review = resolve_canonical_resource(
        original.candidates, choice, knowledge_cutoff=NOW, predecessor=first
    )
    second = registry.register(review, prepare_canonical_resolution(tmp_path, review))
    now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    args = (review.resource_type, review.canonical_subject_id, review.candidates[0].context_sha256)
    assert registry.latest_id_at(*args, old_known) == first
    assert registry.latest_id_at(*args, now) == second
    assert registry.register(original, prepare_canonical_resolution(tmp_path, original)) == first
    stale = resolve_canonical_resource(
        original.candidates,
        replace(choice, reason="Stale fork"),
        knowledge_cutoff=NOW,
        predecessor=first,
    )
    with pytest.raises(CanonicalResolutionError, match="predecessor"):
        registry.register(stale, prepare_canonical_resolution(tmp_path, stale))
    assert load_canonical_decision(tmp_path, first, original.decision.sha256) == original.decision


@pytest.mark.parametrize(
    "table", ["canonical_resource_resolutions", "canonical_resolution_evidence"]
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_canonical_metadata_and_lineage_are_immutable(connection, tmp_path, table, operation):
    resolution = _resolution(connection, tmp_path)
    CanonicalResolutionRegistry(connection).register(
        resolution, prepare_canonical_resolution(tmp_path, resolution)
    )
    query = (
        f"UPDATE football.{table} SET decision_id=decision_id"
        if operation == "UPDATE"
        else f"{operation} {'FROM ' if operation == 'DELETE' else ''}football.{table}"
    )
    connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
    with pytest.raises(RaiseException, match="immutable"), connection.transaction():
        connection.execute(query + (" CASCADE" if operation == "TRUNCATE" else ""))


def test_invalid_prepared_metadata_rolls_back_before_publication(connection, tmp_path):
    resolution = _resolution(connection, tmp_path)
    prepared = prepare_canonical_resolution(tmp_path, resolution)
    prepared = replace(prepared, artifact=replace(prepared.artifact, sha256="f" * 64))
    with pytest.raises(CanonicalResolutionError, match="prepared"):
        CanonicalResolutionRegistry(connection).register(resolution, prepared)
    assert connection.execute(
        "SELECT count(*) FROM football.canonical_resource_resolutions"
    ).fetchone() == (0,)


def test_database_rejects_future_decision_clock(connection, tmp_path):
    resolution = _resolution(connection, tmp_path)
    future = connection.execute("SELECT clock_timestamp()").fetchone()[0] + timedelta(days=1)
    resolution = resolve_canonical_resource(
        resolution.candidates,
        replace(resolution.selection, created_at=future),
        knowledge_cutoff=NOW,
    )
    with pytest.raises(RaiseException, match="available knowledge"):
        CanonicalResolutionRegistry(connection).register(
            resolution, prepare_canonical_resolution(tmp_path, resolution)
        )
    assert connection.execute(
        "SELECT count(*) FROM football.canonical_resource_resolutions"
    ).fetchone() == (0,)


def test_failure_between_decision_and_lineage_rolls_back_atomic_registration(
    connection, tmp_path, monkeypatch
):
    from football.canonical_resources import storage

    resolution = _resolution(connection, tmp_path)
    prepared = prepare_canonical_resolution(tmp_path, resolution)

    def fail(*args):
        raise RuntimeError("injected evidence failure")

    monkeypatch.setattr(storage, "_register_evidence", fail)
    with pytest.raises(RuntimeError, match="injected evidence failure"):
        CanonicalResolutionRegistry(connection).register(resolution, prepared)
    assert connection.execute(
        "SELECT count(*) FROM football.canonical_resource_resolutions"
    ).fetchone() == (0,)
    assert prepared.artifact.path.is_file()


def test_changed_and_superseded_identity_proofs_cannot_be_published(connection, tmp_path):
    resolution = _resolution(connection, tmp_path)
    prepared = prepare_canonical_resolution(tmp_path, resolution)
    with connection.transaction(force_rollback=True):
        connection.execute("UPDATE football.resolution_decisions SET reason='Changed decision'")
        with pytest.raises(CanonicalResolutionError, match="unregistered, superseded or changed"):
            CanonicalResolutionRegistry(connection).register(resolution, prepared)
    connection.execute(
        """INSERT INTO football.resolution_decisions(
             decision_key,subject_type,provider_id,provider_entity_id,evidence_refs,
             candidate_canonical_ids,rule_version,confidence,status,actor,reason,created_at,
             supersedes_decision_id)
           SELECT %s,subject_type,provider_id,provider_entity_id,evidence_refs,
             candidate_canonical_ids,rule_version,confidence,'MANUALLY_REJECTED',actor,
             'Identity correction',created_at,id FROM football.resolution_decisions""",
        ("b" * 64,),
    )
    with pytest.raises(CanonicalResolutionError, match="unregistered, superseded or changed"):
        CanonicalResolutionRegistry(connection).register(resolution, prepared)


def test_database_constraints_reject_root_and_revision_forks(connection, tmp_path):
    from psycopg.errors import UniqueViolation

    resolution = _resolution(connection, tmp_path)
    registry = CanonicalResolutionRegistry(connection)
    first = registry.register(resolution, prepare_canonical_resolution(tmp_path, resolution))
    query = """INSERT INTO football.canonical_resource_resolutions(
        decision_id,resource_type,canonical_subject_id,context_sha256,disposition,
        predecessor_decision_id,knowledge_cutoff,decided_at,registered_at,known_at,
        decision_contract_version,schema_sha256,artifact_path,artifact_sha256)
        SELECT %s,resource_type,canonical_subject_id,context_sha256,'REVIEW_REQUIRED',
        %s,knowledge_cutoff,decided_at,registered_at,known_at,decision_contract_version,
        schema_sha256,artifact_path,artifact_sha256
        FROM football.canonical_resource_resolutions WHERE decision_id=%s"""
    with pytest.raises(UniqueViolation), connection.transaction():
        connection.execute(query, (UUID(int=9001), None, first))
    connection.execute(query, (UUID(int=9002), first, first))
    with pytest.raises(UniqueViolation), connection.transaction():
        connection.execute(query, (UUID(int=9003), first, first))


def test_changed_prepared_file_is_rejected_before_database_publication(connection, tmp_path):
    resolution = _resolution(connection, tmp_path)
    prepared = prepare_canonical_resolution(tmp_path, resolution)
    prepared.artifact.path.write_bytes(b"changed")
    with pytest.raises(CanonicalResolutionError, match="artifact bytes"):
        CanonicalResolutionRegistry(connection).register(resolution, prepared)
    assert connection.execute(
        "SELECT count(*) FROM football.canonical_resource_resolutions"
    ).fetchone() == (0,)


def test_every_supporting_and_conflicting_observation_is_registered(connection, tmp_path):
    original = _resolution(connection, tmp_path)
    first = original.candidates[0]
    supporting = replace(
        first,
        observation=replace(
            first.observation,
            versions=replace(first.observation.versions, normalizer_version="independent-review"),
        ),
    )
    conflicting = replace(first, observation=replace(first.observation, home_goals=1))
    for candidate in (supporting, conflicting):
        ObservationArtifactStore(connection, tmp_path).publish(candidate.observation)
    candidates = (first, supporting, conflicting)
    choice = replace(
        original.selection,
        observation_refs=tuple(str(item.observation.observation_id) for item in candidates),
    )
    resolution = resolve_canonical_resource(candidates, choice, knowledge_cutoff=NOW)
    CanonicalResolutionRegistry(connection).register(
        resolution, prepare_canonical_resolution(tmp_path, resolution)
    )
    rows = connection.execute(
        "SELECT observation_id,role FROM football.canonical_resolution_evidence"
    ).fetchall()
    assert dict(rows) == {
        first.observation.observation_id: "SUPPORTING",
        supporting.observation.observation_id: "SUPPORTING",
        conflicting.observation.observation_id: "CONFLICTING",
    }
