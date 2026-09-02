from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

QuarantineReasonV1 = Literal[
    "SCHEMA_INVALID",
    "CONTENT_INVALID",
    "IDENTITY_UNRESOLVED",
    "MATCH_UNRESOLVED",
    "CONFLICT_UNRESOLVED",
    "QUALITY_POLICY_FAILED",
    "LICENSE_OR_POLICY_BLOCKED",
    "PUBLISH_RECONCILIATION_REQUIRED",
]
QuarantineStatusV1 = Literal["OPEN", "RETRYABLE", "NEEDS_REVIEW", "RESOLVED", "SUPERSEDED"]
_REASONS = frozenset(
    (
        "SCHEMA_INVALID",
        "CONTENT_INVALID",
        "IDENTITY_UNRESOLVED",
        "MATCH_UNRESOLVED",
        "CONFLICT_UNRESOLVED",
        "QUALITY_POLICY_FAILED",
        "LICENSE_OR_POLICY_BLOCKED",
        "PUBLISH_RECONCILIATION_REQUIRED",
    )
)
_STATUSES = frozenset(("OPEN", "RETRYABLE", "NEEDS_REVIEW", "RESOLVED", "SUPERSEDED"))


class QuarantineRecordError(ValueError):
    """A quarantine record violates its versioned contract."""


@dataclass(frozen=True, slots=True)
class QuarantineRecordV1:
    quarantine_id: str
    provider_id: str
    resource_identity: str
    source_snapshot_sha256: str
    source_resource_sha256: str
    canonical_candidate_id: str | None
    reason_code: QuarantineReasonV1
    details: Mapping[str, object]
    policy_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    attempt_count: int
    status: QuarantineStatusV1
    reviewer: str | None = None
    resolution_ref: str | None = None
    contract: str = "QuarantineRecordV1"

    def __post_init__(self) -> None:
        if self.contract != "QuarantineRecordV1":
            raise QuarantineRecordError("unsupported quarantine record contract")
        if not self.quarantine_id or not PROVIDER_PATTERN.fullmatch(self.provider_id):
            raise QuarantineRecordError("quarantine and provider identifiers are required")
        if not self.resource_identity or not self.policy_version:
            raise QuarantineRecordError("resource identity and policy version are required")
        if len(self.source_snapshot_sha256) != 64 or len(self.source_resource_sha256) != 64:
            raise QuarantineRecordError("source checksums must be SHA-256")
        if self.reason_code not in _REASONS or self.status not in _STATUSES:
            raise QuarantineRecordError("quarantine reason or status is unsupported")
        if not isinstance(self.details, Mapping):
            raise QuarantineRecordError("quarantine details must be an object")
        if self.attempt_count < 0:
            raise QuarantineRecordError("quarantine attempt count must not be negative")
        if self.first_seen_at.tzinfo is None or self.last_seen_at.tzinfo is None:
            raise QuarantineRecordError("quarantine timestamps must be timezone-aware")
        if self.last_seen_at < self.first_seen_at:
            raise QuarantineRecordError("quarantine last_seen_at precedes first_seen_at")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "quarantine_id": self.quarantine_id,
            "provider_id": self.provider_id,
            "resource_identity": self.resource_identity,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_resource_sha256": self.source_resource_sha256,
            "canonical_candidate_id": self.canonical_candidate_id,
            "reason_code": self.reason_code,
            "details": dict(self.details),
            "policy_version": self.policy_version,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "attempt_count": self.attempt_count,
            "status": self.status,
            "reviewer": self.reviewer,
            "resolution_ref": self.resolution_ref,
        }
