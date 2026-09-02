from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from football.contracts.source import canonical_json_bytes


class ChangeSetError(ValueError):
    """A canonical change set violates its publication contract."""


@dataclass(frozen=True, slots=True)
class CanonicalChangeSetV1:
    change_set_id: str
    created_at: datetime
    sync_run_ids: tuple[str, ...]
    source_resources: tuple[tuple[str, str], ...]
    affected_canonical_ids: tuple[str, ...]
    added_observation_refs: tuple[str, ...]
    superseding_observation_refs: tuple[str, ...]
    affected_partitions: tuple[str, ...]
    football_time_start: datetime | None
    football_time_end: datetime | None
    knowledge_time_start: datetime | None
    knowledge_time_end: datetime | None
    resolution_policy_version: str
    quality_policy_version: str
    contract: str = "CanonicalChangeSetV1"

    def __post_init__(self) -> None:
        if self.contract != "CanonicalChangeSetV1":
            raise ChangeSetError("unsupported canonical change-set contract")
        if not self.change_set_id or self.created_at.tzinfo is None:
            raise ChangeSetError(
                "change-set identity and timezone-aware creation time are required"
            )
        if not self.sync_run_ids or not self.source_resources:
            raise ChangeSetError("change set requires sync runs and source resources")
        if any(not value for value in self.sync_run_ids):
            raise ChangeSetError("sync run IDs must not be empty")
        if any(not key or len(checksum) != 64 for key, checksum in self.source_resources):
            raise ChangeSetError("source resources require identity and SHA-256")
        if not self.affected_canonical_ids or not (
            self.added_observation_refs or self.superseding_observation_refs
        ):
            raise ChangeSetError("change set requires affected entities and observations")
        _validate_range(self.football_time_start, self.football_time_end, "football")
        _validate_range(self.knowledge_time_start, self.knowledge_time_end, "knowledge")
        if not self.resolution_policy_version or not self.quality_policy_version:
            raise ChangeSetError("resolution and quality policy versions are required")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "change_set_id": self.change_set_id,
            "created_at": self.created_at.isoformat(),
            "sync_run_ids": list(self.sync_run_ids),
            "source_resources": [
                {"resource_ref": resource, "sha256": checksum}
                for resource, checksum in self.source_resources
            ],
            "affected_canonical_ids": list(self.affected_canonical_ids),
            "added_observation_refs": list(self.added_observation_refs),
            "superseding_observation_refs": list(self.superseding_observation_refs),
            "affected_partitions": list(self.affected_partitions),
            "football_time_start": _iso(self.football_time_start),
            "football_time_end": _iso(self.football_time_end),
            "knowledge_time_start": _iso(self.knowledge_time_start),
            "knowledge_time_end": _iso(self.knowledge_time_end),
            "resolution_policy_version": self.resolution_policy_version,
            "quality_policy_version": self.quality_policy_version,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _validate_range(start: datetime | None, end: datetime | None, label: str) -> None:
    if start is not None and start.tzinfo is None or end is not None and end.tzinfo is None:
        raise ChangeSetError(f"{label} time range must be timezone-aware")
    if start and end and end < start:
        raise ChangeSetError(f"{label} time range is reversed")
