from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes
from football.ingestion.resolution_policy import (
    DataResolutionPolicyV1,
    ValidationStatusV1,
)

ConflictDispositionV1 = Literal["RESOLVED", "REVIEW_REQUIRED", "QUARANTINED"]
FieldReconciliationStatusV1 = Literal["CORROBORATED", "REVIEW_REQUIRED", "QUARANTINED"]
_DISPOSITIONS = frozenset(("RESOLVED", "REVIEW_REQUIRED", "QUARANTINED"))
_VALIDATION_STATUSES = frozenset(("passed", "warnings"))


class ConflictRecordError(ValueError):
    """A provider reconciliation conflict violates its contract."""


@dataclass(frozen=True, slots=True)
class FieldObservationV1:
    """One validated, provider-scoped integer field observation."""

    observation_ref: str
    provider_id: str
    value: tuple[int, ...]
    validation_status: ValidationStatusV1

    def __post_init__(self) -> None:
        if not self.observation_ref or not PROVIDER_PATTERN.fullmatch(self.provider_id):
            raise ConflictRecordError("field observation identity is required")
        if not self.value or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in self.value
        ):
            raise ConflictRecordError("field observation values must be non-negative")
        if self.validation_status not in _VALIDATION_STATUSES:
            raise ConflictRecordError("field observation validation status is unsupported")


@dataclass(frozen=True, slots=True)
class FieldReconciliationV1:
    """The retained outcome of reconciling one field under one policy."""

    status: FieldReconciliationStatusV1
    observation_refs: tuple[str, ...]
    conflict: ConflictRecordV1 | None
    reason: str


def reconcile_field_observations(
    policy: DataResolutionPolicyV1,
    observations: tuple[FieldObservationV1, ...],
    *,
    conflict_id: str,
    created_at: datetime,
) -> FieldReconciliationV1:
    """Retain every observation; discrepancies escalate without an automatic winner."""

    if not conflict_id or created_at.tzinfo is None:
        raise ConflictRecordError("conflict identity and timezone-aware timestamp are required")
    if len(observations) < 2:
        raise ConflictRecordError("field reconciliation requires multiple observations")
    observation_refs = tuple(observation.observation_ref for observation in observations)
    if len(observation_refs) != len(set(observation_refs)):
        raise ConflictRecordError("field observations must be unique")
    if len({observation.provider_id for observation in observations}) < 2:
        raise ConflictRecordError("field reconciliation requires multiple providers")
    _validate_policy_eligibility(policy, observations)

    if _within_tolerance(observations, policy.conflict_tolerance):
        return FieldReconciliationV1(
            status="CORROBORATED",
            observation_refs=observation_refs,
            conflict=None,
            reason="provider observations agree within the field policy tolerance",
        )

    if policy.escalation == "review":
        disposition: ConflictDispositionV1 = "REVIEW_REQUIRED"
        status: FieldReconciliationStatusV1 = "REVIEW_REQUIRED"
    else:
        disposition = "QUARANTINED"
        status = "QUARANTINED"
    conflict = ConflictRecordV1(
        conflict_id=conflict_id,
        subject_type=f"{policy.domain}:{policy.resource}:{policy.field}",
        observation_refs=observation_refs,
        policy_version=policy.policy_version,
        disposition=disposition,
        selected_observation_ref=None,
        reason="field observations disagree; the policy does not auto-select a winner",
        created_at=created_at,
    )
    return FieldReconciliationV1(
        status=status,
        observation_refs=observation_refs,
        conflict=conflict,
        reason="provider observations disagree and remain preserved",
    )


def _validate_policy_eligibility(
    policy: DataResolutionPolicyV1,
    observations: tuple[FieldObservationV1, ...],
) -> None:
    for observation in observations:
        if observation.provider_id not in policy.eligible_providers:
            raise ConflictRecordError("field observation provider is ineligible under the policy")
        if observation.validation_status not in policy.required_validation_statuses:
            raise ConflictRecordError("field observation validation status is ineligible")


def _within_tolerance(
    observations: tuple[FieldObservationV1, ...],
    tolerance: float,
) -> bool:
    expected = observations[0].value
    return all(
        len(observation.value) == len(expected)
        and all(
            abs(actual - target) <= tolerance
            for actual, target in zip(observation.value, expected, strict=True)
        )
        for observation in observations[1:]
    )


@dataclass(frozen=True, slots=True)
class ConflictRecordV1:
    conflict_id: str
    subject_type: str
    observation_refs: tuple[str, ...]
    policy_version: str
    disposition: ConflictDispositionV1
    selected_observation_ref: str | None
    reason: str
    created_at: datetime
    contract: str = "ConflictRecordV1"

    def __post_init__(self) -> None:
        if self.contract != "ConflictRecordV1":
            raise ConflictRecordError("unsupported conflict record contract")
        if not self.conflict_id or not self.subject_type or not self.policy_version:
            raise ConflictRecordError("conflict identity and policy are required")
        if not self.observation_refs:
            raise ConflictRecordError("conflict observations are required")
        if len(self.observation_refs) != len(set(self.observation_refs)):
            raise ConflictRecordError("conflict observations must be unique")
        if self.disposition not in _DISPOSITIONS:
            raise ConflictRecordError("conflict disposition is unsupported")
        if (
            self.selected_observation_ref not in self.observation_refs
            and self.selected_observation_ref
        ):
            raise ConflictRecordError("selected observation is not part of conflict")
        if self.disposition == "RESOLVED" and not self.selected_observation_ref:
            raise ConflictRecordError("resolved conflict requires selected observation")
        if not self.reason or self.created_at.tzinfo is None:
            raise ConflictRecordError("conflict reason and timezone-aware timestamp are required")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "conflict_id": self.conflict_id,
            "subject_type": self.subject_type,
            "observation_refs": list(self.observation_refs),
            "policy_version": self.policy_version,
            "disposition": self.disposition,
            "selected_observation_ref": self.selected_observation_ref,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }
