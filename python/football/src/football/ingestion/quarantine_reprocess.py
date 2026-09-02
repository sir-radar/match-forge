from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import canonical_json_bytes

ReprocessTriggerV1 = Literal[
    "MAPPING_REVIEWED",
    "SCHEMA_FIXED",
    "PROVIDER_CORRECTION",
    "POLICY_VERSIONED",
]
_TRIGGERS = frozenset(
    ("MAPPING_REVIEWED", "SCHEMA_FIXED", "PROVIDER_CORRECTION", "POLICY_VERSIONED")
)


class QuarantineReprocessError(ValueError):
    """A quarantine reprocessing request violates its contract."""


@dataclass(frozen=True, slots=True)
class QuarantineReprocessRequestV1:
    request_id: str
    source_quarantine_id: str
    trigger: ReprocessTriggerV1
    trigger_ref: str
    policy_version: str
    scheduled_at: datetime
    contract: str = "QuarantineReprocessRequestV1"

    def __post_init__(self) -> None:
        if self.contract != "QuarantineReprocessRequestV1":
            raise QuarantineReprocessError("unsupported quarantine reprocess contract")
        if not self.request_id or not self.source_quarantine_id:
            raise QuarantineReprocessError("reprocess and source quarantine IDs are required")
        if self.trigger not in _TRIGGERS or not self.trigger_ref:
            raise QuarantineReprocessError("reprocess trigger and reference are required")
        if not self.policy_version:
            raise QuarantineReprocessError("reprocess policy version is required")
        if self.scheduled_at.tzinfo is None:
            raise QuarantineReprocessError("reprocess scheduled_at must be timezone-aware")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "request_id": self.request_id,
            "source_quarantine_id": self.source_quarantine_id,
            "trigger": self.trigger,
            "trigger_ref": self.trigger_ref,
            "policy_version": self.policy_version,
            "scheduled_at": self.scheduled_at.isoformat(),
        }
