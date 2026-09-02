from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from football.ingestion import ResolutionDecisionError, ResolutionDecisionV1, ResolutionStatusV1


def test_resolution_decision_is_auditable_and_canonical() -> None:
    decision = _decision()

    assert decision.to_dict()["contract"] == "ResolutionDecisionV1"
    assert decision.to_dict()["selected_canonical_id"] == "canonical-team-1"
    assert len(decision.sha256) == 64


def test_resolution_decision_requires_evidence_and_selected_acceptance() -> None:
    with pytest.raises(ResolutionDecisionError, match="evidence"):
        _decision(evidence_refs=())
    with pytest.raises(ResolutionDecisionError, match="selected"):
        _decision(status="AUTO_ACCEPTED", selected_canonical_id=None)


def test_resolution_decision_rejects_naive_time_and_invalid_confidence() -> None:
    with pytest.raises(ResolutionDecisionError, match="confidence"):
        _decision(confidence=1.1)
    with pytest.raises(ResolutionDecisionError, match="timezone-aware"):
        _decision(created_at=datetime(2026, 1, 1))


def _decision(
    *,
    evidence_refs: tuple[str, ...] = ("source:1", "rule:team-context-v1"),
    status: str = "MANUALLY_APPROVED",
    selected_canonical_id: str | None = "canonical-team-1",
    confidence: float = 0.98,
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> ResolutionDecisionV1:
    return ResolutionDecisionV1(
        decision_id="decision-1",
        subject_type="team",
        provider_id="totalcorner_api",
        provider_entity_id="team-123",
        evidence_refs=evidence_refs,
        candidate_canonical_ids=("canonical-team-1", "canonical-team-2"),
        rule_version="team-resolution-v1",
        confidence=confidence,
        status=cast(ResolutionStatusV1, status),
        selected_canonical_id=selected_canonical_id,
        actor="operator@example.test",
        reason="reviewed crosswalk and competition context",
        created_at=created_at,
    )
