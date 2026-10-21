from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
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
from football.contracts.observations_v2 import CompetitionObservationV2
from football.contracts.source import canonical_json_bytes
from football.identity.repository import IdentityRepository
from football.ingestion.conflicts import ConflictRecordV1
from football.ingestion.resolution import ResolutionDecisionV1
from football.ingestion.resolution_storage import PostgresResolutionDecisionStoreV1
from football.observations.storage import ObservationArtifactStore
from football.product.identity_admission import admit_provider_mappings
from football.providers.normalization.cli import registered_resource
from football.providers.normalization.pipeline import normalize_resource
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


def _r2_competition_candidate(connection, root):
    from test_product_identity_admission import _cutoff, _history

    _history(connection, root)
    admit_provider_mappings(connection, root, "football_data_uk")
    cutoff = _cutoff(connection)
    mapping, canonical = connection.execute(
        "SELECT mapping_id,canonical_id FROM football.product_identity_admissions "
        "WHERE entity_type='competition' AND disposition IN ('ORIGIN_ANCHOR','CROSSWALK') "
        "ORDER BY decided_at DESC,decision_id DESC LIMIT 1"
    ).fetchone()
    proof = IdentityRepository(connection).admission_proof_at("competition", mapping, cutoff)
    assert proof is not None
    resource = connection.execute(
        "SELECT r.id FROM football.source_resources r "
        "JOIN football.source_snapshots s ON s.id=r.source_snapshot_id "
        "JOIN football.providers p ON p.id=s.provider_id "
        "WHERE p.code='football_data_uk' AND r.provider_path='test/season.csv'"
    ).fetchone()[0]
    context, raw = registered_resource(connection, root, resource)
    result = normalize_resource(context, "results", raw)
    observation = next(
        item for item in result.observations if isinstance(item, CompetitionObservationV2)
    )
    ObservationArtifactStore(connection, root).publish(observation)
    candidate = CanonicalCandidate(
        observation=observation,
        canonical_subject_id=canonical,
        subject_identity=proof,
        bindings=(CanonicalBinding("/competition", canonical, proof),),
    )
    selection = ConflictRecordV1(
        conflict_id="explicit-r2-competition-review",
        subject_type=f"CompetitionObservation:{canonical}",
        observation_refs=(str(observation.observation_id),),
        policy_version="operator-review",
        disposition="RESOLVED",
        selected_observation_ref=str(observation.observation_id),
        reason="Reviewed exact admitted competition reference",
        created_at=cutoff,
    )
    return candidate, selection, cutoff, mapping


def test_r2_admission_proof_publishes_and_rejects_changed_proof(connection, tmp_path):
    candidate, selection, cutoff, _ = _r2_competition_candidate(connection, tmp_path)
    resolution = resolve_canonical_resource((candidate,), selection, knowledge_cutoff=cutoff)
    registry = CanonicalResolutionRegistry(connection)
    prepared = prepare_canonical_resolution(tmp_path, resolution)
    assert registry.register(resolution, prepared) == resolution.decision.decision_id
    changed = replace(candidate.subject_identity, reason="asserted replacement reason")
    forged = replace(
        candidate,
        subject_identity=changed,
        bindings=(CanonicalBinding("/competition", candidate.canonical_subject_id, changed),),
    )
    invalid = resolve_canonical_resource((forged,), selection, knowledge_cutoff=cutoff)
    with pytest.raises(CanonicalResolutionError, match="admission"):
        registry.register(invalid, prepare_canonical_resolution(tmp_path, invalid))


def test_r2_revocation_blocks_new_resolution_and_preserves_earlier_knowledge(connection, tmp_path):
    from test_product_identity_admission import _cutoff

    candidate, selection, cutoff, mapping = _r2_competition_candidate(connection, tmp_path)
    old = resolve_canonical_resource((candidate,), selection, knowledge_cutoff=cutoff)
    registry = CanonicalResolutionRegistry(connection)
    prepared = prepare_canonical_resolution(tmp_path, old)
    registry.register(old, prepared)
    connection.execute(
        """INSERT INTO football.product_identity_admissions(
            entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,
            disposition,reason,source_snapshot_id,source_observed_at,evidence,evidence_sha256)
           SELECT entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,
                  'REVOKED','operator_revocation',source_snapshot_id,source_observed_at,
                  evidence,evidence_sha256 FROM football.product_identity_admissions
           WHERE mapping_id=%s ORDER BY decided_at DESC,decision_id DESC LIMIT 1""",
        (mapping,),
    )
    later = _cutoff(connection)
    stale = resolve_canonical_resource(
        (candidate,), replace(selection, created_at=later), knowledge_cutoff=later
    )
    with pytest.raises(CanonicalResolutionError, match="admission"):
        registry.register(stale, prepare_canonical_resolution(tmp_path, stale))
    assert registry.register(old, prepared) == old.decision.decision_id


@pytest.mark.parametrize("mapping", [None, "not-a-uuid", str(UUID(int=404))])
def test_r2_proof_rejects_rehashed_mapping_forgery(connection, tmp_path, mapping):
    candidate, selection, cutoff, _ = _r2_competition_candidate(connection, tmp_path)
    evidence = candidate.subject_identity.to_dict()["evidence"]
    source = evidence["source_contract"]
    source["mapping_id"] = mapping
    evidence["source_sha256"] = hashlib.sha256(canonical_json_bytes(source)).hexdigest()
    proof = replace(candidate.subject_identity, evidence=evidence)
    forged = replace(
        candidate,
        subject_identity=proof,
        bindings=(CanonicalBinding("/competition", candidate.canonical_subject_id, proof),),
    )
    resolution = resolve_canonical_resource((forged,), selection, knowledge_cutoff=cutoff)
    with pytest.raises(CanonicalResolutionError, match="admission"):
        CanonicalResolutionRegistry(connection).register(
            resolution, prepare_canonical_resolution(tmp_path, resolution)
        )


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


@pytest.mark.parametrize("method", ["register", "register_prepared"])
def test_invalid_prepared_metadata_rolls_back_before_publication(connection, tmp_path, method):
    resolution = _resolution(connection, tmp_path)
    prepared = prepare_canonical_resolution(tmp_path, resolution)
    prepared = replace(prepared, artifact=replace(prepared.artifact, sha256="f" * 64))
    with pytest.raises(CanonicalResolutionError, match="prepared"):
        getattr(CanonicalResolutionRegistry(connection), method)(resolution, prepared)
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


def test_prepared_canonical_registration_performs_no_filesystem_access(
    connection, tmp_path, monkeypatch
):
    resolution = _resolution(connection, tmp_path)
    prepared = prepare_canonical_resolution(tmp_path, resolution)

    def reject_filesystem(*args: object, **kwargs: object) -> None:
        raise AssertionError("filesystem access during canonical metadata registration")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", reject_filesystem)
        patch.setattr(Path, "is_symlink", reject_filesystem)
        registry = CanonicalResolutionRegistry(connection)
        assert registry.register_prepared(resolution, prepared) == resolution.decision.decision_id
        assert registry.register_prepared(resolution, prepared) == resolution.decision.decision_id
    assert connection.execute(
        "SELECT count(*) FROM football.canonical_resource_resolutions WHERE decision_id=%s",
        (resolution.decision.decision_id,),
    ).fetchone() == (1,)
