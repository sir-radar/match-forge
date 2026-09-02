from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import canonical_json_bytes

ProviderAcceptanceStatusV1 = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL", "NOT_RUN"]
_STATUSES = frozenset(("PASS", "PASS_WITH_WARNINGS", "FAIL", "NOT_RUN"))
_CHECK_FIELDS = (
    "schema_contract_status",
    "runtime_safety_status",
    "secret_boundary_status",
    "resolution_ledger_status",
    "quarantine_reprocessing_status",
    "conflict_reconciliation_status",
    "change_set_publication_status",
)


class ProviderAcceptanceError(ValueError):
    """Provider-platform acceptance evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class ProviderPlatformAcceptanceReportV1:
    """Immutable evidence for the Phase 1B multi-source acceptance gate."""

    report_id: str
    policy_version: str
    created_at: datetime
    approved_provider_refs: tuple[str, ...]
    end_to_end_status: ProviderAcceptanceStatusV1
    schema_contract_status: ProviderAcceptanceStatusV1
    runtime_safety_status: ProviderAcceptanceStatusV1
    secret_boundary_status: ProviderAcceptanceStatusV1
    resolution_ledger_status: ProviderAcceptanceStatusV1
    quarantine_reprocessing_status: ProviderAcceptanceStatusV1
    conflict_reconciliation_status: ProviderAcceptanceStatusV1
    change_set_publication_status: ProviderAcceptanceStatusV1
    evidence_refs: tuple[str, ...]
    contract: str = "ProviderPlatformAcceptanceReportV1"

    def __post_init__(self) -> None:
        if self.contract != "ProviderPlatformAcceptanceReportV1":
            raise ProviderAcceptanceError("unsupported provider acceptance contract")
        if not self.report_id or not self.policy_version:
            raise ProviderAcceptanceError("provider acceptance identity and policy are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ProviderAcceptanceError("provider acceptance timestamp must include a timezone")
        _validate_provider_refs(self.approved_provider_refs)
        _validate_refs(self.evidence_refs, "evidence")
        if any(
            getattr(self, name) not in _STATUSES for name in ("end_to_end_status", *_CHECK_FIELDS)
        ):
            raise ProviderAcceptanceError("provider acceptance status is unsupported")

    @property
    def status(self) -> ProviderAcceptanceStatusV1:
        statuses = [self.end_to_end_status, *(getattr(self, name) for name in _CHECK_FIELDS)]
        if "FAIL" in statuses or 0 < len(self.approved_provider_refs) < 2:
            return "FAIL"
        if "NOT_RUN" in statuses or not self.approved_provider_refs:
            return "NOT_RUN"
        if "PASS_WITH_WARNINGS" in statuses:
            return "PASS_WITH_WARNINGS"
        return "PASS"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "report_id": self.report_id,
            "policy_version": self.policy_version,
            "created_at": self.created_at.isoformat(),
            "approved_provider_refs": list(self.approved_provider_refs),
            "end_to_end_status": self.end_to_end_status,
            **{name: getattr(self, name) for name in _CHECK_FIELDS},
            "evidence_refs": list(self.evidence_refs),
            "status": self.status,
        }


def _validate_refs(values: tuple[str, ...], label: str) -> None:
    if not values or any(not value for value in values):
        raise ProviderAcceptanceError(f"{label} references are required")
    if len(values) != len(set(values)):
        raise ProviderAcceptanceError(f"{label} references must be unique")


def _validate_provider_refs(values: tuple[str, ...]) -> None:
    if any(not value for value in values):
        raise ProviderAcceptanceError("approved provider references must not be empty")
    if len(values) != len(set(values)):
        raise ProviderAcceptanceError("approved provider references must be unique")
