from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from football.contracts.source import canonical_json_bytes
from football.providers.football_data_uk import (
    FootballDataUkResourceTypeV1,
    FootballDataUkSourceResourceV1,
)
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

    @classmethod
    def from_bytes(cls, payload: bytes) -> FootballDataUkAcquisitionEvidenceV1:
        """Read the published canonical bundle without changing its logical digest."""
        try:
            value = json.loads(payload)
            if not isinstance(value, dict) or not isinstance(value.get("receipts"), list):
                raise FootballDataUkAcquisitionEvidenceError("invalid acquisition evidence object")
            evidence = cls(
                receipts=tuple(_receipt(item) for item in value["receipts"]),
                contract=_text(value, "contract"),
            )
            if evidence.to_bytes() != payload:
                raise FootballDataUkAcquisitionEvidenceError(
                    "acquisition evidence differs from its canonical receipt metadata"
                )
            return evidence
        except (UnicodeDecodeError, ValueError) as error:
            raise FootballDataUkAcquisitionEvidenceError(str(error)) from error


def _receipt(value: object) -> FootballDataUkSourceResourceV1:
    if not isinstance(value, dict):
        raise FootballDataUkAcquisitionEvidenceError("source receipt must be an object")
    data = cast(dict[str, object], value)
    return FootballDataUkSourceResourceV1(
        contract=_text(data, "contract"),
        resource_type=cast(FootballDataUkResourceTypeV1, _text(data, "resource_type")),
        source_path=_text(data, "source_path"),
        observed_by_matchforge_at=datetime.fromisoformat(_text(data, "observed_by_matchforge_at")),
        request_started_at=datetime.fromisoformat(_text(data, "request_started_at")),
        http_status=_integer(data, "http_status"),
        content_type=_text(data, "content_type"),
        raw_byte_size=_integer(data, "raw_byte_size"),
        raw_sha256=_text(data, "raw_sha256"),
        http_etag=_optional_text(data, "http_etag"),
        http_last_modified=_optional_text(data, "http_last_modified"),
    )


def _text(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise FootballDataUkAcquisitionEvidenceError(f"receipt {field} must be text")
    return item


def _integer(value: dict[str, object], field: str) -> int:
    item = value.get(field)
    if type(item) is not int:
        raise FootballDataUkAcquisitionEvidenceError(f"receipt {field} must be an integer")
    return item


def _optional_text(value: dict[str, object], field: str) -> str | None:
    item = value.get(field)
    if item is not None and not isinstance(item, str):
        raise FootballDataUkAcquisitionEvidenceError(f"receipt {field} must be text or null")
    return item


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
