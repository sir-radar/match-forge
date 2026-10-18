import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from football.contracts.decisions import DecisionRecordError, DecisionRecordV1, decision_schema
from football.contracts.source import canonical_json_bytes

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def record(**changes: Any) -> DecisionRecordV1:
    values: dict[str, Any] = dict(
        decision_type="identity_resolution",
        subject_type="team",
        subject_id="00000000-0000-0000-0000-000000000001",
        decided_at=NOW,
        disposition="ORIGIN_ANCHOR",
        reason="Verified retained source",
        evidence={"source_resource_id": "00000000-0000-0000-0000-000000000002", "sha256": "a" * 64},
    )
    return DecisionRecordV1(**(values | changes))


def test_decision_record_round_trip_binds_evidence_and_has_deterministic_identity() -> None:
    item = record()
    restored = DecisionRecordV1.from_bytes(item.to_bytes())
    assert restored.to_bytes() == item.to_bytes()
    assert (
        item.evidence_hash
        == hashlib.sha256(canonical_json_bytes(item.to_dict()["evidence"])).hexdigest()
    )
    assert item.sha256 == hashlib.sha256(item.to_bytes()).hexdigest()
    assert isinstance(item.decision_id, UUID)
    assert item.decision_id == record().decision_id


def test_evidence_is_deeply_immutable_and_never_aliases_input_or_serialized_output() -> None:
    source = {"nested": {"items": [1, 0, False, None]}}
    item = record(evidence=source)
    before = item.to_bytes()
    source["nested"]["items"].append(7)
    output = item.to_dict()
    cast(dict[str, Any], output["evidence"])["nested"]["items"].append(8)
    assert item.to_bytes() == before
    with pytest.raises(TypeError):
        cast(dict[str, object], item.evidence)["changed"] = True
    with pytest.raises(TypeError):
        cast(dict[str, Any], item.evidence["nested"])["changed"] = True
    with pytest.raises(FrozenInstanceError):
        cast(Any, item).reason = "changed"


def test_decision_and_effective_times_are_distinct_and_equivalent_timezones_are_canonical() -> None:
    future = record(effective_at=NOW + timedelta(days=1))
    local = timezone(timedelta(hours=1))
    same = record(
        decided_at=NOW.astimezone(local), effective_at=(NOW + timedelta(days=1)).astimezone(local)
    )
    assert future.to_bytes() == same.to_bytes()
    assert record(effective_at=NOW - timedelta(days=1)).effective_at != future.effective_at
    assert record().effective_at is None


@pytest.mark.parametrize(
    "field", ["decision_type", "subject_type", "subject_id", "disposition", "reason"]
)
def test_decision_identifiers_and_reason_cannot_be_blank(field: str) -> None:
    with pytest.raises(DecisionRecordError):
        record(**{field: " "})


@pytest.mark.parametrize("field", ["decided_at", "effective_at"])
def test_decision_clocks_require_timezones(field: str) -> None:
    with pytest.raises(DecisionRecordError):
        record(**{field: datetime(2026, 1, 1)})


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), b"bytes", {1: "not a JSON key"}, {"nested": set()}]
)
def test_decision_evidence_rejects_non_json_values(value: object) -> None:
    with pytest.raises(DecisionRecordError):
        record(evidence={"value": value})


@pytest.mark.parametrize(
    "change", ["hash", "version", "contract", "extra", "missing", "duplicate", "nonfinite"]
)
def test_decision_decoder_rejects_tampered_or_unsupported_payloads(change: str) -> None:
    payload = record().to_dict()
    if change == "hash":
        payload["evidence_hash"] = "f" * 64
    elif change == "version":
        payload["contract_version"] = "2"
    elif change == "contract":
        payload["contract"] = "DecisionRecordV2"
    elif change == "extra":
        payload["unexpected"] = 1
    elif change == "missing":
        del payload["reason"]
    raw = canonical_json_bytes(payload)
    if change == "duplicate":
        raw = raw.replace(b'{"contract":', b'{"contract":"duplicate","contract":', 1)
    if change == "nonfinite":
        raw = raw.replace(b'"evidence":{', b'"evidence":{"bad":NaN,', 1)
    with pytest.raises(DecisionRecordError):
        DecisionRecordV1.from_bytes(raw)


def test_predecessors_link_new_records_without_mutating_previous_decisions() -> None:
    prior = record()
    before = prior.to_bytes()
    successor = replace(
        prior,
        decided_at=NOW + timedelta(hours=1),
        predecessor=str(prior.decision_id),
        disposition="REVOKED",
    )
    assert successor.decision_id != prior.decision_id
    assert DecisionRecordV1.from_bytes(successor.to_bytes()).predecessor == str(prior.decision_id)
    assert prior.to_bytes() == before


def test_checked_in_schema_matches_the_contract_and_callers_cannot_mutate_its_validator() -> None:
    expected = decision_schema()
    assert (
        json.loads(Path("schemas/contracts/decision-record-v1.schema.json").read_bytes())
        == expected
    )
    expected["properties"] = {}
    with pytest.raises(DecisionRecordError):
        record(subject_id=" ")


def test_v1_schema_and_wire_identity_remain_frozen() -> None:
    assert hashlib.sha256(canonical_json_bytes(decision_schema())).hexdigest() == (
        "dd31aaac6e264c516aca19f4ad175537c447a4153f59dd675ef8973309141ee1"
    )
    assert record().sha256 == "f36c60adc3a5b69375e1decd72a22713d0d5482f967253fbad5cf69a4d48ab15"
    assert record().decision_id == UUID("13bf3fd9-ca03-5a16-bf06-0b2e3df74ea8")


def test_resolution_adapter_retains_source_hash_and_never_changes_the_existing_contract() -> None:
    from football.ingestion.resolution import ResolutionDecisionV1

    original = ResolutionDecisionV1(
        decision_id="existing-decision",
        subject_type="team",
        provider_id="statsbomb_open_data",
        provider_entity_id="42",
        evidence_refs=("source:resource",),
        candidate_canonical_ids=("00000000-0000-0000-0000-000000000001",),
        rule_version="existing-rule",
        confidence=1,
        status="AUTO_ACCEPTED",
        selected_canonical_id="00000000-0000-0000-0000-000000000001",
        actor="existing-owner",
        reason="Verified source",
        created_at=NOW,
        supersedes_decision_id="prior-decision",
    )
    before = original.to_dict(), original.sha256
    common = original.to_decision_record("stable-mapping-id")
    assert common.subject_id == "stable-mapping-id"
    assert common.predecessor == "prior-decision"
    assert common.evidence["source_sha256"] == original.sha256
    evidence = common.to_dict()["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["source_contract"] == before[0]
    assert (original.to_dict(), original.sha256) == before
    assert common.effective_at is None


def test_promotion_adapter_preserves_artifact_evaluation_and_original_event() -> None:
    from dataclasses import asdict

    from football.forecasting.governance import ModelPromotionEventV1

    promotion = ModelPromotionEventV1(
        UUID(int=1), UUID(int=2), UUID(int=3), "baseline", "BASELINE_APPROVED", NOW
    )
    before = asdict(promotion)
    common = promotion.to_decision_record("Approved under the existing evaluation gate")
    assert common.subject_id == str(promotion.model_artifact_id)
    assert common.evidence["evaluation_run_id"] == str(promotion.evaluation_run_id)
    assert common.disposition == promotion.designation
    assert common.effective_at is None
    assert asdict(promotion) == before


def test_cyclic_evidence_is_rejected() -> None:
    evidence: dict[str, object] = {}
    evidence["self"] = evidence
    with pytest.raises(DecisionRecordError, match="acyclic"):
        record(evidence=evidence)
