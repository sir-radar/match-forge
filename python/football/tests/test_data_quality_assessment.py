from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

import pytest
from football.canonical_resources.resolution import CanonicalBinding, CanonicalResolutionError
from football.contracts.decisions import DecisionRecordV1
from football.validation.quality import (
    QUALITY_DIMENSIONS,
    DataQualityAssessment,
    DataQualityError,
    QualityDimension,
)

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def dimension(**changes: Any) -> QualityDimension:
    values = dict(
        state="UNKNOWN",
        reason_codes=("MF_IDENTITY_NOT_ASSESSED",),
        action="resolve_identity_with_existing_owner",
        evidence_refs=("retained-input:sha256:abc",),
    )
    return QualityDimension(**(values | changes))


def assessment(**changes: Any) -> DataQualityAssessment:
    values: dict[str, Any] = dict(
        subject="provider:fixture:one",
        resource="results",
        knowledge_cutoff=NOW,
        assessed_at=NOW + timedelta(seconds=1),
        **{name: dimension() for name in QUALITY_DIMENSIONS},
    )
    return DataQualityAssessment(**(values | changes))


def test_all_dimensions_round_trip_independently_in_common_decision_evidence() -> None:
    item = assessment(
        completeness=dimension(
            state="COMPLETE", reason_codes=("EXPECTED_FIELDS_PRESENT",), action="none"
        ),
        conflict_state=dimension(
            state="REVIEW_REQUIRED",
            reason_codes=("CONFLICT_UNRESOLVED",),
            action="review_preserved_observations",
        ),
    )
    record = item.to_decision_record()
    restored = DataQualityAssessment.from_decision_record(
        DecisionRecordV1.from_bytes(record.to_bytes())
    )
    assert restored == item
    assert record.decision_type == "data_quality_assessment"
    assert record.disposition == "ASSESSED"
    assert item.identity_state.state == "UNKNOWN"
    assert item.completeness.state == "COMPLETE"
    assert item.conflict_state.action == "review_preserved_observations"
    assert set(cast(dict[str, Any], record.to_dict()["evidence"])["dimensions"]) == set(
        QUALITY_DIMENSIONS
    )
    assert "confidence" not in record.to_bytes().decode()


def test_quality_cannot_be_used_as_identity_proof_even_with_a_positive_state() -> None:
    item = assessment(subject=str(UUID(int=1)), identity_state=dimension(state="UNIQUE"))
    with pytest.raises(CanonicalResolutionError, match="identity"):
        CanonicalBinding("/fixture", UUID(int=1), item.to_decision_record())


def test_unknown_state_requires_explicit_reason_action_and_evidence() -> None:
    for field, value in (
        ("state", " "),
        ("reason_codes", ()),
        ("action", ""),
        ("evidence_refs", ()),
    ):
        with pytest.raises(DataQualityError):
            dimension(**{field: value})


@pytest.mark.parametrize("field", ["reason_codes", "evidence_refs"])
def test_dimension_copies_mutable_inputs_and_rejects_duplicates(field: str) -> None:
    source = ["one"]
    item = dimension(**{field: source})
    source.append("two")
    assert getattr(item, field) == ("one",)
    with pytest.raises(DataQualityError):
        dimension(**{field: ("one", "one")})
    with pytest.raises(DataQualityError):
        dimension(**{field: (" ",)})
    with pytest.raises(FrozenInstanceError):
        cast(Any, item).state = "COMPLETE"


def test_clocks_are_explicit_and_equivalent_timezones_have_identical_bytes() -> None:
    item = assessment()
    local = timezone(timedelta(hours=1))
    same = replace(
        item, knowledge_cutoff=NOW.astimezone(local), assessed_at=item.assessed_at.astimezone(local)
    )
    assert item.to_decision_record().to_bytes() == same.to_decision_record().to_bytes()
    with pytest.raises(DataQualityError, match="knowledge"):
        assessment(assessed_at=NOW - timedelta(seconds=1))
    for field in ("knowledge_cutoff", "assessed_at"):
        with pytest.raises(DataQualityError, match="timezone"):
            assessment(**{field: NOW.replace(tzinfo=None)})


@pytest.mark.parametrize("field", ["subject", "resource"])
def test_scope_is_required(field: str) -> None:
    with pytest.raises(DataQualityError):
        assessment(**{field: " "})


@pytest.mark.parametrize(
    "change",
    ["type", "disposition", "version", "dimension", "extra", "resource", "effective", "clock"],
)
def test_decoder_rejects_wrong_or_incomplete_assessment_evidence(change: str) -> None:
    record = assessment().to_decision_record()
    evidence = cast(dict[str, Any], record.to_dict()["evidence"])
    if change == "type":
        record = replace(record, decision_type="identity_resolution")
    elif change == "disposition":
        record = replace(record, disposition="APPROVED")
    elif change == "version":
        evidence["contract_version"] = "2"
    elif change == "dimension":
        del evidence["dimensions"]["freshness"]
    elif change == "extra":
        evidence["dimensions"]["confidence"] = {"score": 1}
    elif change == "resource":
        evidence["resource"] = None
    elif change == "effective":
        record = replace(record, effective_at=NOW)
    else:
        evidence["knowledge_cutoff"] = "not-a-time"
    if change not in ("type", "disposition", "effective"):
        record = replace(record, evidence=evidence)
    with pytest.raises(DataQualityError):
        DataQualityAssessment.from_decision_record(record)


def test_dimension_decoder_rejects_unknown_fields_without_silent_coercion() -> None:
    record = assessment().to_decision_record()
    evidence = cast(dict[str, Any], record.to_dict()["evidence"])
    evidence["dimensions"]["precision"]["score"] = 1
    with pytest.raises(DataQualityError):
        DataQualityAssessment.from_decision_record(replace(record, evidence=evidence))


@pytest.mark.parametrize(
    ("field", "value"),
    [("state", None), ("reason_codes", "CODE"), ("action", 1), ("evidence_refs", (1,))],
)
def test_quality_values_are_not_silently_coerced(field: str, value: Any) -> None:
    with pytest.raises(DataQualityError):
        dimension(**{field: value})


def test_unassessed_dimension_cannot_be_omitted_or_replaced_with_a_score() -> None:
    with pytest.raises(DataQualityError, match="explicit quality dimension"):
        assessment(identity_state=1)
