from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from football.contracts.source import canonical_json_bytes


class CorrectionRecordError(ValueError):
    """A bitemporal correction record violates its append-only contract."""


@dataclass(frozen=True, slots=True)
class BitemporalCorrectionV1:
    correction_id: str
    canonical_entity_id: str
    prior_observation_ref: str
    replacement_observation_ref: str
    source_snapshot_ref: str
    source_resource_ref: str
    football_valid_from: datetime | None
    football_valid_to: datetime | None
    known_from: datetime
    reason: str
    contract: str = "BitemporalCorrectionV1"

    def __post_init__(self) -> None:
        if self.contract != "BitemporalCorrectionV1":
            raise CorrectionRecordError("unsupported bitemporal correction contract")
        if any(
            not value
            for value in (
                self.correction_id,
                self.canonical_entity_id,
                self.prior_observation_ref,
                self.replacement_observation_ref,
                self.source_snapshot_ref,
                self.source_resource_ref,
                self.reason,
            )
        ):
            raise CorrectionRecordError("correction identity and lineage are required")
        if self.prior_observation_ref == self.replacement_observation_ref:
            raise CorrectionRecordError("correction observations must differ")
        for value in (self.known_from, self.football_valid_from, self.football_valid_to):
            if value is not None and value.tzinfo is None:
                raise CorrectionRecordError("correction timestamps must be timezone-aware")
        if (
            self.football_valid_from is not None
            and self.football_valid_to is not None
            and self.football_valid_to < self.football_valid_from
        ):
            raise CorrectionRecordError("football correction range is reversed")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "correction_id": self.correction_id,
            "canonical_entity_id": self.canonical_entity_id,
            "prior_observation_ref": self.prior_observation_ref,
            "replacement_observation_ref": self.replacement_observation_ref,
            "source_snapshot_ref": self.source_snapshot_ref,
            "source_resource_ref": self.source_resource_ref,
            "football_valid_from": _iso(self.football_valid_from),
            "football_valid_to": _iso(self.football_valid_to),
            "known_from": self.known_from.isoformat(),
            "reason": self.reason,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
