from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from football.contracts.source import canonical_json_bytes
from football.providers.football_data_uk import FootballDataUkSourceResourceV1
from football.storage.raw import ImmutableFileConflict, ImmutableFileStore, ImmutableWrite

_FROZEN_RECEIPTS = (
    ("schema_semantics_and_attribution", "notes.txt"),
    ("historical_league_csv", "mmz4281/2526/E0.csv"),
    ("historical_league_csv", "mmz4281/1516/E0.csv"),
)


class FootballDataUkAcquisitionEvidenceError(ValueError):
    """The bounded acquisition receipts cannot form immutable source evidence."""


@dataclass(frozen=True, slots=True)
class FootballDataUkAcquisitionEvidenceV1:
    """Immutable receipt bundle for exactly one frozen Football-Data capture."""

    receipts: tuple[FootballDataUkSourceResourceV1, ...]
    contract: str = "FootballDataUkAcquisitionEvidenceV1"

    def __post_init__(self) -> None:
        if self.contract != "FootballDataUkAcquisitionEvidenceV1":
            raise FootballDataUkAcquisitionEvidenceError(
                "unsupported acquisition evidence contract"
            )
        actual = tuple((receipt.resource_type, receipt.source_path) for receipt in self.receipts)
        if actual != _FROZEN_RECEIPTS:
            raise FootballDataUkAcquisitionEvidenceError(
                "acquisition evidence receipts must match the frozen resource order"
            )
        identities = tuple(receipt.resource_identity for receipt in self.receipts)
        if len(identities) != len(set(identities)):
            raise FootballDataUkAcquisitionEvidenceError(
                "acquisition evidence receipts must be unique"
            )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "receipts": [receipt.to_dict() for receipt in self.receipts],
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"


class FootballDataUkAcquisitionEvidenceStoreV1:
    """Publish receipt evidence without copying or mutating provider raw bytes."""

    def __init__(self, data_root: Path) -> None:
        self._files = ImmutableFileStore(data_root)

    def publish(self, evidence: FootballDataUkAcquisitionEvidenceV1) -> ImmutableWrite:
        try:
            return self._files.publish(self.relative_path(evidence), evidence.to_bytes())
        except ImmutableFileConflict as error:
            raise FootballDataUkAcquisitionEvidenceError(
                "immutable acquisition evidence conflicts with its identity"
            ) from error

    @staticmethod
    def relative_path(evidence: FootballDataUkAcquisitionEvidenceV1) -> str:
        return (
            "manifests/provider=football_data_uk/"
            f"acquisition_sha256={evidence.sha256}/acquisition-evidence-v1.json"
        )
