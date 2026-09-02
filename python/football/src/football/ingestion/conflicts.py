from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import canonical_json_bytes

ConflictDispositionV1 = Literal["RESOLVED", "REVIEW_REQUIRED", "QUARANTINED"]
_DISPOSITIONS = frozenset(("RESOLVED", "REVIEW_REQUIRED", "QUARANTINED"))


class ConflictRecordError(ValueError):
    """A provider reconciliation conflict violates its contract."""


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
