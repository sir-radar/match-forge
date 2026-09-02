from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

ResolutionSubjectV1 = Literal["competition", "season", "team", "player", "match"]
ResolutionStatusV1 = Literal[
    "AUTO_ACCEPTED",
    "REVIEW_REQUIRED",
    "MANUALLY_APPROVED",
    "MANUALLY_REJECTED",
    "SUPERSEDED",
]
_SUBJECTS = frozenset(("competition", "season", "team", "player", "match"))
_STATUSES = frozenset(
    (
        "AUTO_ACCEPTED",
        "REVIEW_REQUIRED",
        "MANUALLY_APPROVED",
        "MANUALLY_REJECTED",
        "SUPERSEDED",
    )
)


class ResolutionDecisionError(ValueError):
    """A cross-provider resolution decision violates its versioned contract."""


@dataclass(frozen=True, slots=True)
class ResolutionDecisionV1:
    decision_id: str
    subject_type: ResolutionSubjectV1
    provider_id: str
    provider_entity_id: str
    evidence_refs: tuple[str, ...]
    candidate_canonical_ids: tuple[str, ...]
    rule_version: str
    confidence: float
    status: ResolutionStatusV1
    selected_canonical_id: str | None
    actor: str
    reason: str
    created_at: datetime
    supersedes_decision_id: str | None = None
    contract: str = "ResolutionDecisionV1"

    def __post_init__(self) -> None:
        _validate_identity(self)
        _validate_evidence(self)
        _validate_decision(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "decision_id": self.decision_id,
            "subject_type": self.subject_type,
            "provider_id": self.provider_id,
            "provider_entity_id": self.provider_entity_id,
            "evidence_refs": list(self.evidence_refs),
            "candidate_canonical_ids": list(self.candidate_canonical_ids),
            "rule_version": self.rule_version,
            "confidence": self.confidence,
            "status": self.status,
            "selected_canonical_id": self.selected_canonical_id,
            "actor": self.actor,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "supersedes_decision_id": self.supersedes_decision_id,
        }


def _validate_identity(decision: ResolutionDecisionV1) -> None:
    if decision.contract != "ResolutionDecisionV1":
        raise ResolutionDecisionError("unsupported resolution decision contract")
    if not decision.decision_id or not PROVIDER_PATTERN.fullmatch(decision.provider_id):
        raise ResolutionDecisionError("decision and provider identifiers are required")
    if decision.subject_type not in _SUBJECTS or decision.status not in _STATUSES:
        raise ResolutionDecisionError("resolution subject or status is unsupported")
    if not decision.provider_entity_id or not decision.rule_version:
        raise ResolutionDecisionError("provider entity and rule version are required")


def _validate_evidence(decision: ResolutionDecisionV1) -> None:
    if not decision.evidence_refs or any(not value for value in decision.evidence_refs):
        raise ResolutionDecisionError("resolution evidence references are required")
    if len(decision.evidence_refs) != len(set(decision.evidence_refs)):
        raise ResolutionDecisionError("resolution evidence references must be unique")
    if not decision.candidate_canonical_ids:
        raise ResolutionDecisionError("resolution candidates are required")
    if len(decision.candidate_canonical_ids) != len(set(decision.candidate_canonical_ids)):
        raise ResolutionDecisionError("resolution candidates must be unique")


def _validate_decision(decision: ResolutionDecisionV1) -> None:
    if not 0.0 <= decision.confidence <= 1.0:
        raise ResolutionDecisionError("resolution confidence must be 0..1")
    if (
        decision.status in {"AUTO_ACCEPTED", "MANUALLY_APPROVED"}
        and not decision.selected_canonical_id
    ):
        raise ResolutionDecisionError("accepted resolution requires a selected canonical ID")
    if not decision.actor or not decision.reason:
        raise ResolutionDecisionError("resolution actor and reason are required")
    if decision.created_at.tzinfo is None:
        raise ResolutionDecisionError("resolution created_at must be timezone-aware")
