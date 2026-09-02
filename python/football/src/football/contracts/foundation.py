from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import SHA256_PATTERN, canonical_json_bytes

FoundationEvidenceStatusV1 = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL", "NOT_RUN"]
_STATUSES = frozenset(("PASS", "PASS_WITH_WARNINGS", "FAIL", "NOT_RUN"))
_EVIDENCE_FIELDS = (
    "provider_platform_status",
    "dependency_graph_status",
    "rebuild_status",
    "ci_status",
    "observability_status",
    "backup_restore_status",
    "integrity_status",
    "competition_rules_status",
)


class FoundationReportError(ValueError):
    """A foundation-hardening report violates its evidence contract."""


@dataclass(frozen=True, slots=True)
class FoundationHardeningReportV1:
    """Immutable aggregate evidence for the Phase 2B foundation gate."""

    report_id: str
    policy_version: str
    created_at: datetime
    provider_platform_status: FoundationEvidenceStatusV1
    dependency_graph_status: FoundationEvidenceStatusV1
    rebuild_status: FoundationEvidenceStatusV1
    ci_status: FoundationEvidenceStatusV1
    observability_status: FoundationEvidenceStatusV1
    backup_restore_status: FoundationEvidenceStatusV1
    integrity_status: FoundationEvidenceStatusV1
    competition_rules_status: FoundationEvidenceStatusV1
    code_git_sha: str
    dependency_lock_sha256: str
    evidence_refs: tuple[str, ...]
    contract: str = "FoundationHardeningReportV1"

    def __post_init__(self) -> None:
        if self.contract != "FoundationHardeningReportV1":
            raise FoundationReportError("unsupported foundation report contract")
        if not self.report_id or not self.policy_version:
            raise FoundationReportError("foundation report identity and policy are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise FoundationReportError("foundation report timestamp must include a timezone")
        if not self.evidence_refs or len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise FoundationReportError("foundation report evidence references must be unique")
        if any(not value for value in self.evidence_refs):
            raise FoundationReportError("foundation report evidence references must not be empty")
        if any(getattr(self, name) not in _STATUSES for name in _EVIDENCE_FIELDS):
            raise FoundationReportError("foundation evidence status is unsupported")
        if len(self.code_git_sha) != 40 or any(
            character not in "0123456789abcdef" for character in self.code_git_sha
        ):
            raise FoundationReportError("code_git_sha must be a 40-character lowercase Git SHA")
        if not SHA256_PATTERN.fullmatch(self.dependency_lock_sha256):
            raise FoundationReportError("dependency lock must be a SHA-256")

    @property
    def status(self) -> FoundationEvidenceStatusV1:
        statuses = [getattr(self, name) for name in _EVIDENCE_FIELDS]
        if "FAIL" in statuses:
            return "FAIL"
        if "NOT_RUN" in statuses:
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
            **{name: getattr(self, name) for name in _EVIDENCE_FIELDS},
            "code_git_sha": self.code_git_sha,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "evidence_refs": list(self.evidence_refs),
            "status": self.status,
        }
