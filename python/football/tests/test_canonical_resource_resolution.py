import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.canonical_resources.resolution import (
    CanonicalBinding,
    CanonicalCandidate,
    CanonicalResolutionError,
    resolve_canonical_resource,
)
from football.contracts.decisions import DecisionRecordV1
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.contracts.observations_v2 import (
    EntityReferenceV2,
    ObservationVersionsV2,
    ResultObservationV2,
)
from football.contracts.source import canonical_json_bytes
from football.ingestion.conflicts import ConflictDispositionV1, ConflictRecordV1

NOW = datetime(2026, 10, 18, tzinfo=UTC)
SUBJECT = UUID(int=100)


def identity(
    canonical: UUID = SUBJECT, provider: str = "fotmob", native: str = "1"
) -> DecisionRecordV1:
    source = {
        "contract": "ResolutionDecisionV1",
        "selected_canonical_id": str(canonical),
        "provider_id": provider,
        "provider_entity_id": native,
        "status": "AUTO_ACCEPTED",
        "evidence_refs": ["retained-source"],
    }
    return DecisionRecordV1(
        decision_type="identity_resolution",
        subject_type="match",
        subject_id=str(canonical),
        decided_at=NOW - timedelta(days=1),
        disposition="AUTO_ACCEPTED",
        reason="Verified fixture identity",
        evidence={
            "source_contract": source,
            "source_sha256": hashlib.sha256(canonical_json_bytes(source)).hexdigest(),
        },
    )


def candidate(
    provider: str, ordinal: int, home: int = 2, away: int = 1
) -> CanonicalCandidate[ResultObservationV2]:
    item = ResultObservationV2(
        provenance=ObservationProvenance(
            provider, str(ordinal), UUID(int=ordinal), UUID(int=ordinal + 10), "a" * 64
        ),
        time=ObservationTime(
            observed_at=NOW - timedelta(hours=2),
            acquired_at=NOW - timedelta(hours=2),
            known_at=NOW - timedelta(hours=2),
        ),
        versions=ObservationVersionsV2(adapter_version="test", normalizer_version="test"),
        fixture=EntityReferenceV2(str(ordinal)),
        status="FINISHED",
        score_basis="REGULATION_90",
        home_goals=home,
        away_goals=away,
    )
    return CanonicalCandidate(
        observation=item,
        canonical_subject_id=SUBJECT,
        subject_identity=identity(provider=provider, native=str(ordinal)),
        bindings=(
            CanonicalBinding("/fixture", SUBJECT, identity(provider=provider, native=str(ordinal))),
        ),
    )


def selection(
    items: tuple[CanonicalCandidate[ResultObservationV2], ...],
    selected: int | None = 0,
    disposition: ConflictDispositionV1 = "RESOLVED",
) -> ConflictRecordV1:
    return ConflictRecordV1(
        conflict_id="explicit-review",
        subject_type=f"ResultObservation:{SUBJECT}",
        observation_refs=tuple(str(item.observation.observation_id) for item in items),
        policy_version="operator-reviewed-result",
        disposition=disposition,
        selected_observation_ref=str(items[selected].observation.observation_id)
        if selected is not None
        else None,
        reason="Explicit source review",
        created_at=NOW,
    )


def test_canonical_result_retains_support_conflict_and_original_source_bytes() -> None:
    items = (candidate("fotmob", 1), candidate("api_football", 2), candidate("pitchapi", 3, 1, 1))
    before = tuple(item.observation.to_bytes() for item in items)
    result = resolve_canonical_resource(items, selection(items), knowledge_cutoff=NOW)
    assert result.selected is not None
    assert (result.selected.observation.home_goals, result.selected.observation.away_goals) == (
        2,
        1,
    )
    assert set(result.supporting) == {item.observation.observation_id for item in items[:2]}
    assert result.conflicting == (items[2].observation.observation_id,)
    assert tuple(item.observation.to_bytes() for item in items) == before
    assert result.decision.disposition == "RESOLVED"
    assert result.decision.evidence["selection_sha256"] == selection(items).sha256


def test_explicit_selection_is_preserved_instead_of_inventing_a_majority_rule() -> None:
    items = (candidate("fotmob", 1), candidate("api_football", 2), candidate("pitchapi", 3, 1, 1))
    result = resolve_canonical_resource(items, selection(items, 2), knowledge_cutoff=NOW)
    assert result.selected is not None and result.selected.observation.home_goals == 1
    assert result.supporting == (items[2].observation.observation_id,)
    assert set(result.conflicting) == {item.observation.observation_id for item in items[:2]}


def test_review_required_never_produces_a_canonical_winner() -> None:
    items = (candidate("fotmob", 1), candidate("pitchapi", 2, 1, 1))
    result = resolve_canonical_resource(
        items, selection(items, None, "REVIEW_REQUIRED"), knowledge_cutoff=NOW
    )
    assert result.selected is None and result.supporting == () and result.conflicting == ()
    assert result.decision.disposition == "REVIEW_REQUIRED"


def test_candidate_order_does_not_change_the_canonical_decision_identity() -> None:
    items = (candidate("fotmob", 1), candidate("api_football", 2))
    chosen = selection(items)
    first = resolve_canonical_resource(items, chosen, knowledge_cutoff=NOW)
    second = resolve_canonical_resource(tuple(reversed(items)), chosen, knowledge_cutoff=NOW)
    assert first.decision.to_bytes() == second.decision.to_bytes()


def test_source_or_identity_from_future_knowledge_is_blocking() -> None:
    item = candidate("fotmob", 1)
    future = replace(
        item.observation, time=replace(item.observation.time, known_at=NOW + timedelta(days=1))
    )
    changed = replace(item, observation=future)
    with pytest.raises(CanonicalResolutionError, match="knowledge"):
        resolve_canonical_resource((changed,), selection((changed,)), knowledge_cutoff=NOW)
    later = replace(identity(), decided_at=NOW + timedelta(days=1))
    changed = replace(
        item, subject_identity=later, bindings=(CanonicalBinding("/fixture", SUBJECT, later),)
    )
    with pytest.raises(CanonicalResolutionError, match="knowledge"):
        resolve_canonical_resource((changed,), selection((changed,)), knowledge_cutoff=NOW)


def test_incomplete_or_unapproved_identity_cannot_be_substituted_by_provider_trust() -> None:
    item = candidate("fotmob", 1)
    with pytest.raises(CanonicalResolutionError, match="reference"):
        replace(item, bindings=())
    with pytest.raises(CanonicalResolutionError, match="identity"):
        replace(item, subject_identity=replace(identity(), disposition="REVIEW_REQUIRED"))
    with pytest.raises(CanonicalResolutionError, match="identity"):
        replace(item, subject_identity=replace(identity(), decision_type="provider_authority"))


def test_another_subject_or_unretained_evidence_cannot_be_silently_merged() -> None:
    first = candidate("fotmob", 1)
    proof = identity(UUID(int=101), "pitchapi", "2")
    other = replace(
        candidate("pitchapi", 2),
        canonical_subject_id=UUID(int=101),
        subject_identity=proof,
        bindings=(CanonicalBinding("/fixture", UUID(int=101), proof),),
    )
    with pytest.raises(CanonicalResolutionError, match="subject"):
        resolve_canonical_resource((first, other), selection((first, other)), knowledge_cutoff=NOW)
    with pytest.raises(CanonicalResolutionError, match="evidence"):
        resolve_canonical_resource(
            (first,), selection((first, candidate("pitchapi", 2))), knowledge_cutoff=NOW
        )


def test_mixed_fixtures_and_score_bases_are_different_resource_contexts() -> None:
    first = candidate("fotmob", 1)
    second = candidate("api_football", 2)
    other = UUID(int=101)
    proof = identity(other, "api_football", "2")
    changed = replace(
        second,
        canonical_subject_id=other,
        subject_identity=proof,
        bindings=(CanonicalBinding("/fixture", other, proof),),
    )
    with pytest.raises(CanonicalResolutionError, match="resource and subject"):
        resolve_canonical_resource(
            (first, changed), selection((first, changed)), knowledge_cutoff=NOW
        )
    changed = replace(second, observation=replace(second.observation, score_basis="EXTRA_TIME"))
    with pytest.raises(CanonicalResolutionError, match="resource and subject"):
        resolve_canonical_resource(
            (first, changed), selection((first, changed)), knowledge_cutoff=NOW
        )


def test_identity_binding_cannot_be_reused_for_another_provider_or_native_id() -> None:
    first = candidate("fotmob", 1)
    for provider, native in [("pitchapi", "1"), ("fotmob", "other")]:
        proof = identity(provider=provider, native=native)
        with pytest.raises(CanonicalResolutionError, match="another provider or reference"):
            replace(
                first,
                subject_identity=proof,
                bindings=(CanonicalBinding("/fixture", SUBJECT, proof),),
            )


def test_quarantined_selection_cannot_leak_a_provisional_winner() -> None:
    items = (candidate("fotmob", 1),)
    result = resolve_canonical_resource(
        items, selection(items, 0, "QUARANTINED"), knowledge_cutoff=NOW
    )
    assert result.selected is None
    assert result.supporting == result.conflicting == ()


def test_v1_and_v2_results_compare_by_canonical_value() -> None:
    from football.contracts.observations import (
        EntityReference,
        ObservationVersions,
        ResultObservationV1,
    )

    first = candidate("fotmob", 1)
    second = candidate("api_football", 2)
    item = second.observation
    v1 = ResultObservationV1(
        provenance=item.provenance,
        time=item.time,
        versions=ObservationVersions(adapter_version="test", normalizer_version="test"),
        fixture=EntityReference("2"),
        status=item.status,
        score_basis=item.score_basis,
        home_goals=item.home_goals,
        away_goals=item.away_goals,
    )
    older = CanonicalCandidate(
        observation=v1,
        canonical_subject_id=SUBJECT,
        subject_identity=second.subject_identity,
        bindings=second.bindings,
    )
    assert older.value_sha256 == first.value_sha256
    assert older.context_sha256 == first.context_sha256


def test_canonical_artifact_corruption_and_asserted_conclusions_are_rejected(
    tmp_path: Path,
) -> None:
    from football.canonical_resources.storage import (
        load_canonical_decision,
        prepare_canonical_resolution,
    )

    items = (candidate("fotmob", 1),)
    result = resolve_canonical_resource(items, selection(items), knowledge_cutoff=NOW)
    prepared = prepare_canonical_resolution(tmp_path, result)
    assert (
        load_canonical_decision(tmp_path, result.decision.decision_id, result.decision.sha256)
        == result.decision
    )
    with pytest.raises(CanonicalResolutionError, match="declared evidence"):
        prepare_canonical_resolution(tmp_path, replace(result, supporting=()))
    prepared.artifact.path.write_bytes(b"{}")
    with pytest.raises(ValueError):
        load_canonical_decision(tmp_path, result.decision.decision_id, result.decision.sha256)


@pytest.mark.parametrize(
    "contract",
    [
        "Fixture",
        "Result",
        "Competition",
        "Team",
        "Player",
        "Coach",
        "Lineup",
        "Availability",
        "Formation",
        "Event",
        "Shot",
        "ExpectedGoals",
        "TeamStatistic",
        "PlayerStatistic",
        "Standing",
        "Odds",
    ],
)
@pytest.mark.parametrize("version", [1, 2])
def test_every_typed_resource_retains_its_original_observation(contract: str, version: int) -> None:
    import json

    from football.contracts.observations import observation_from_bytes
    from test_observation_contracts import resource_payload

    payload = resource_payload(contract + "ObservationV1")
    if version == 2:
        payload["contract"] = contract + "ObservationV2"
        versions = payload["versions"]
        assert isinstance(versions, dict)
        versions["observation_contract_version"] = "2"
    observation = observation_from_bytes(json.dumps(payload).encode())
    bindings = _resource_bindings(payload)
    primary = (
        next(binding for binding in bindings if binding.reference_path == "/team")
        if contract == "Coach"
        else bindings[0]
    )
    subject = primary.canonical_id
    proof = primary.identity_decision
    if contract in ("Event", "Shot"):
        subject = UUID(int=999)
        proof = replace(identity(subject), subject_type="event" if contract == "Event" else "shot")
    item = CanonicalCandidate(
        observation=observation,
        canonical_subject_id=subject,
        subject_identity=proof,
        bindings=tuple(bindings),
    )
    choice = ConflictRecordV1(
        conflict_id="typed-resource-test",
        subject_type=f"{item.resource_type}:{subject}",
        observation_refs=(str(observation.observation_id),),
        policy_version="explicit-review",
        disposition="RESOLVED",
        selected_observation_ref=str(observation.observation_id),
        reason="Explicit source review",
        created_at=NOW,
    )
    result = resolve_canonical_resource((item,), choice, knowledge_cutoff=NOW)
    assert result.selected is not None
    assert result.selected.observation.to_bytes() == observation.to_bytes()
    assert result.supporting == (observation.observation_id,)


def _resource_bindings(payload: dict[str, object]) -> list[CanonicalBinding]:
    kinds = {
        "fixture": "match",
        "competition": "competition",
        "home_team": "team",
        "away_team": "team",
        "team": "team",
        "player": "player",
        "coach": "coach",
        "venue": "venue",
        "shot": "shot",
        "assisting_player": "player",
        "assist_event": "event",
        "referee": "referee",
    }
    bindings: list[CanonicalBinding] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            if "provider_native_id" in value and "canonical_id" in value:
                kind = kinds[path.rsplit("/", 1)[-1]]
                native = value["provider_native_id"]
                assert isinstance(native, str)
                canonical = UUID(
                    int=1 + int(hashlib.sha256((kind + native).encode()).hexdigest()[:30], 16)
                )
                proof = replace(identity(canonical, "fotmob", native), subject_type=kind)
                bindings.append(CanonicalBinding(path, canonical, proof))
            else:
                for key, nested in value.items():
                    visit(nested, path + "/" + key)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, path + "/" + str(index))

    for key, value in payload.items():
        if key not in ("provenance", "time", "versions"):
            visit(value, "/" + key)
    return bindings


def test_resource_subject_cannot_switch_to_another_participant() -> None:
    import json

    from football.contracts.observations import observation_from_bytes
    from test_observation_contracts import resource_payload

    payload = resource_payload("FixtureObservationV1")
    observation = observation_from_bytes(json.dumps(payload).encode())
    bindings = _resource_bindings(payload)
    home = next(binding for binding in bindings if binding.reference_path == "/home_team")
    with pytest.raises(CanonicalResolutionError, match="exact entity binding"):
        CanonicalCandidate(
            observation=observation,
            canonical_subject_id=home.canonical_id,
            subject_identity=home.identity_decision,
            bindings=tuple(bindings),
        )


def test_different_effective_intervals_cannot_be_reconciled_as_one_context() -> None:
    first = candidate("fotmob", 1)
    second = candidate("api_football", 2)
    second = replace(
        second,
        observation=replace(
            second.observation,
            time=replace(second.observation.time, valid_from=NOW - timedelta(days=1)),
        ),
    )
    with pytest.raises(CanonicalResolutionError, match="resource and subject"):
        resolve_canonical_resource(
            (first, second), selection((first, second)), knowledge_cutoff=NOW
        )


@pytest.mark.parametrize("index", range(6))
def test_rich_resources_bind_exact_identities_and_preserve_period_and_rating_context(
    index: int,
) -> None:
    from football.contracts.observations_v2 import EntityReferenceV2
    from football.contracts.observations_v3 import RefereeObservationV3, ShotObservationV3
    from test_observation_contracts_v3 import examples

    observation = examples()[index]
    observation = replace(
        observation, provenance=replace(observation.provenance, provider="fotmob")
    )
    if isinstance(observation, RefereeObservationV3):
        observation = replace(observation, referee=EntityReferenceV2("referee-1"))
    if isinstance(observation, ShotObservationV3):
        observation = replace(
            observation,
            assisting_player=EntityReferenceV2("assist-player"),
            assist_event=EntityReferenceV2("assist-event"),
        )
    bindings = _resource_bindings(observation.to_dict())
    subject, proof = bindings[0].canonical_id, bindings[0].identity_decision
    if isinstance(observation, ShotObservationV3):
        subject = UUID(int=999)
        proof = replace(identity(subject), subject_type="shot")
    item = CanonicalCandidate(
        observation=observation,
        canonical_subject_id=subject,
        subject_identity=proof,
        bindings=tuple(bindings),
    )
    assert item.resource_type == observation.CONTRACT.removesuffix("V3")
    assert len(item.value_sha256) == len(item.context_sha256) == 64
    assert item.observation.to_bytes() == observation.to_bytes()
    changed_semantics = replace(
        item,
        observation=replace(
            observation, versions=replace(observation.versions, semantic_version="reviewed-source")
        ),
    )
    assert changed_semantics.context_sha256 != item.context_sha256
    if index == 3:
        changed = replace(item, observation=replace(observation, period="SECOND_HALF"))
        assert changed.context_sha256 != item.context_sha256
    if index == 5:
        from datetime import date

        changed = replace(item, observation=replace(observation, rating_date=date(2026, 10, 2)))
        assert changed.context_sha256 != item.context_sha256
    with pytest.raises(CanonicalResolutionError, match="reference"):
        replace(item, bindings=tuple(bindings[:-1]))
