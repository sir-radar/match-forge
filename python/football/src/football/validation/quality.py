"""Structured quality reports; assessment never grants identity or model eligibility."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from football.contracts.decisions import DecisionRecordV1

QUALITY_DIMENSIONS = (
    "identity_state",
    "completeness",
    "freshness",
    "precision",
    "consistency",
    "temporal_integrity",
    "provenance_state",
    "conflict_state",
)
_REASON = "Structured resource quality assessment; independent identity admission required."


class DataQualityError(ValueError):
    """A quality assessment lacks explicit scope, clocks or actionable evidence."""


@dataclass(frozen=True, slots=True, kw_only=True)
class QualityDimension:
    """An owner-defined state and reasons, without a shared numeric score.

    Evidence references identify the owner's retained findings, checks or
    decisions. The action addresses the supplied reason codes together.
    """

    state: str
    reason_codes: tuple[str, ...]
    action: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.state)
        _text(self.action)
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs))

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "action": self.action,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, value: object) -> QualityDimension:
        data = _object(value, {"state", "reason_codes", "action", "evidence_refs"})
        return cls(
            state=_text(data["state"]),
            reason_codes=_strings(data["reason_codes"]),
            action=_text(data["action"]),
            evidence_refs=_strings(data["evidence_refs"]),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DataQualityAssessment:
    """Explicit independent quality dimensions for one stable resource subject.

    States and reason codes come from the applicable domain policies. Unknown
    dimensions must be supplied explicitly with the reason and required action.
    A positive identity state reports an existing owner's conclusion; consumers
    still require that owner's independently validated identity proof.
    """

    subject: str
    resource: str
    knowledge_cutoff: datetime
    assessed_at: datetime
    identity_state: QualityDimension
    completeness: QualityDimension
    freshness: QualityDimension
    precision: QualityDimension
    consistency: QualityDimension
    temporal_integrity: QualityDimension
    provenance_state: QualityDimension
    conflict_state: QualityDimension

    def __post_init__(self) -> None:
        _text(self.subject)
        _text(self.resource)
        for name in ("knowledge_cutoff", "assessed_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise DataQualityError("quality clocks require a timezone")
            object.__setattr__(self, name, value.astimezone(UTC))
        if self.knowledge_cutoff > self.assessed_at:
            raise DataQualityError("quality assessment cannot use future knowledge")
        for name in QUALITY_DIMENSIONS:
            if not isinstance(getattr(self, name), QualityDimension):
                raise DataQualityError(f"explicit quality dimension required: {name}")

    def to_decision_record(self) -> DecisionRecordV1:
        """Use the common immutable evidence format, without an approval disposition."""
        return DecisionRecordV1(
            decision_type="data_quality_assessment",
            subject_type="resource",
            subject_id=self.subject,
            decided_at=self.assessed_at,
            disposition="ASSESSED",
            reason=_REASON,
            evidence={
                "contract": "DataQualityAssessment",
                "contract_version": "1",
                "resource": self.resource,
                "knowledge_cutoff": self.knowledge_cutoff.isoformat(),
                "dimensions": {name: getattr(self, name).to_dict() for name in QUALITY_DIMENSIONS},
            },
        )

    @classmethod
    def from_decision_record(cls, record: DecisionRecordV1) -> DataQualityAssessment:
        if (
            record.decision_type != "data_quality_assessment"
            or record.subject_type != "resource"
            or record.disposition != "ASSESSED"
            or record.reason != _REASON
            or record.effective_at is not None
            or record.predecessor is not None
        ):
            raise DataQualityError("record is not a resource quality assessment")
        data = _object(
            record.evidence,
            {"contract", "contract_version", "resource", "knowledge_cutoff", "dimensions"},
        )
        if data["contract"] != "DataQualityAssessment" or data["contract_version"] != "1":
            raise DataQualityError("unsupported quality assessment contract")
        dimensions = _object(data["dimensions"], set(QUALITY_DIMENSIONS))
        return cls(
            subject=record.subject_id,
            resource=_text(data["resource"]),
            knowledge_cutoff=_timestamp(data["knowledge_cutoff"]),
            assessed_at=record.decided_at,
            **{name: QualityDimension.from_dict(dimensions[name]) for name in QUALITY_DIMENSIONS},
        )


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataQualityError(
            "quality states, scope, reasons and actions must be nonblank strings"
        )
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not value:
        raise DataQualityError("quality reason codes and evidence references are required")
    result = tuple(_text(item) for item in value)
    if len(set(result)) != len(result):
        raise DataQualityError("quality reason codes and evidence references must be unique")
    return result


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise DataQualityError("quality assessment fields differ from the declared contract")
    return dict(value)


def _timestamp(value: object) -> datetime:
    try:
        return datetime.fromisoformat(_text(value))
    except ValueError as error:
        raise DataQualityError("invalid quality knowledge cutoff") from error
