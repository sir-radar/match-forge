from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from football.contracts.source import canonical_json_bytes

ArtifactRetirementObjectKindV1 = Literal["FORECAST", "EVALUATION"]
ArtifactRetirementScopeV1 = Literal["TEST_ONLY_HARD_GATE_EXCLUSION"]
ArtifactRetirementReasonV1 = Literal["SYNTHETIC_TEST_LINEAGE"]


class ArtifactRetirementContractError(ValueError):
    """An append-only artifact retirement event is invalid."""


@dataclass(frozen=True, slots=True)
class ArtifactRetirementEventV1:
    retirement_event_id: UUID
    object_kind: ArtifactRetirementObjectKindV1
    object_id: UUID
    retirement_scope: ArtifactRetirementScopeV1
    reason: ArtifactRetirementReasonV1
    evidence_reference: str
    recorded_at: datetime
    code_commit_sha: str
    contract_version: str = "artifact-retirement-event-v1"
    contract: str = "ArtifactRetirementEventV1"

    def __post_init__(self) -> None:
        if self.contract != "ArtifactRetirementEventV1":
            raise ArtifactRetirementContractError("unsupported artifact retirement contract")
        if self.object_kind not in {"FORECAST", "EVALUATION"}:
            raise ArtifactRetirementContractError("artifact retirement object kind is unsupported")
        if self.retirement_scope != "TEST_ONLY_HARD_GATE_EXCLUSION":
            raise ArtifactRetirementContractError("artifact retirement scope is unsupported")
        if self.reason != "SYNTHETIC_TEST_LINEAGE":
            raise ArtifactRetirementContractError("artifact retirement reason is unsupported")
        if not self.evidence_reference:
            raise ArtifactRetirementContractError(
                "artifact retirement evidence reference is required"
            )
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ArtifactRetirementContractError(
                "artifact retirement timestamp must include a timezone"
            )
        if len(self.code_commit_sha) != 40 or any(
            character not in "0123456789abcdef" for character in self.code_commit_sha
        ):
            raise ArtifactRetirementContractError(
                "code_commit_sha must be a 40-character lowercase Git SHA"
            )
        if self.contract_version != "artifact-retirement-event-v1":
            raise ArtifactRetirementContractError(
                "artifact retirement contract version is unsupported"
            )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "retirement_event_id": str(self.retirement_event_id),
            "object_kind": self.object_kind,
            "object_id": str(self.object_id),
            "retirement_scope": self.retirement_scope,
            "reason": self.reason,
            "evidence_reference": self.evidence_reference,
            "recorded_at": self.recorded_at.isoformat(),
            "code_commit_sha": self.code_commit_sha,
            "contract_version": self.contract_version,
        }
