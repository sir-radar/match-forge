from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

ValidationStatusV1 = Literal["passed", "warnings"]
EscalationActionV1 = Literal["review", "quarantine", "reject"]
_VALIDATION_STATUSES = frozenset(("passed", "warnings"))
_ESCALATION_ACTIONS = frozenset(("review", "quarantine", "reject"))


class ResolutionPolicyError(ValueError):
    """A field-level data-resolution policy violates its contract."""


@dataclass(frozen=True, slots=True)
class DataResolutionPolicyV1:
    policy_version: str
    domain: str
    resource: str
    field: str
    eligible_providers: tuple[str, ...]
    source_precedence: tuple[str, ...]
    freshness_window_seconds: int | None
    require_complete: bool
    required_validation_statuses: tuple[ValidationStatusV1, ...]
    conflict_tolerance: float
    escalation: EscalationActionV1
    contract: str = "DataResolutionPolicyV1"

    def __post_init__(self) -> None:
        if self.contract != "DataResolutionPolicyV1":
            raise ResolutionPolicyError("unsupported data resolution policy contract")
        if not self.policy_version or not self.domain or not self.resource or not self.field:
            raise ResolutionPolicyError("policy version and field scope are required")
        _validate_providers(self.eligible_providers, "eligible providers")
        _validate_providers(self.source_precedence, "source precedence")
        if not set(self.source_precedence) <= set(self.eligible_providers):
            raise ResolutionPolicyError("source precedence contains ineligible provider")
        if self.freshness_window_seconds is not None and self.freshness_window_seconds <= 0:
            raise ResolutionPolicyError("freshness window must be positive")
        if not self.required_validation_statuses or any(
            value not in _VALIDATION_STATUSES for value in self.required_validation_statuses
        ):
            raise ResolutionPolicyError("validation status is unsupported")
        if self.conflict_tolerance < 0.0:
            raise ResolutionPolicyError("conflict tolerance must not be negative")
        if self.escalation not in _ESCALATION_ACTIONS:
            raise ResolutionPolicyError("escalation action is unsupported")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "policy_version": self.policy_version,
            "domain": self.domain,
            "resource": self.resource,
            "field": self.field,
            "eligible_providers": list(self.eligible_providers),
            "source_precedence": list(self.source_precedence),
            "freshness_window_seconds": self.freshness_window_seconds,
            "require_complete": self.require_complete,
            "required_validation_statuses": list(self.required_validation_statuses),
            "conflict_tolerance": self.conflict_tolerance,
            "escalation": self.escalation,
        }


def _validate_providers(providers: tuple[str, ...], label: str) -> None:
    if not providers or any(not PROVIDER_PATTERN.fullmatch(provider) for provider in providers):
        raise ResolutionPolicyError(f"{label} must use lowercase snake_case")
    if len(providers) != len(set(providers)):
        raise ResolutionPolicyError(f"{label} must be unique")
