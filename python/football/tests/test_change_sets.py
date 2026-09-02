from __future__ import annotations

from datetime import UTC, datetime

import pytest
from football.ingestion import CanonicalChangeSetV1, ChangeSetError


def test_change_set_is_immutable_and_binds_lineage() -> None:
    change_set = _change_set()

    assert change_set.to_dict()["source_resources"] == [
        {"resource_ref": "resource:1", "sha256": "a" * 64}
    ]
    assert len(change_set.sha256) == 64


def test_change_set_requires_trusted_observation_and_valid_ranges() -> None:
    with pytest.raises(ChangeSetError, match="observations"):
        _change_set(added_observation_refs=())
    with pytest.raises(ChangeSetError, match="football time range"):
        _change_set(
            football_time_start=datetime(2026, 2, 1, tzinfo=UTC),
            football_time_end=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_change_set_rejects_invalid_source_checksum() -> None:
    with pytest.raises(ChangeSetError, match="SHA-256"):
        _change_set(source_resources=(("resource:1", "bad"),))


def _change_set(
    *,
    source_resources: tuple[tuple[str, str], ...] = (("resource:1", "a" * 64),),
    added_observation_refs: tuple[str, ...] = ("observation:1",),
    football_time_start: datetime | None = None,
    football_time_end: datetime | None = None,
) -> CanonicalChangeSetV1:
    return CanonicalChangeSetV1(
        change_set_id="change-set-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        sync_run_ids=("run-1",),
        source_resources=source_resources,
        affected_canonical_ids=("match-1",),
        added_observation_refs=added_observation_refs,
        superseding_observation_refs=(),
        affected_partitions=("match=match-1",),
        football_time_start=football_time_start,
        football_time_end=football_time_end,
        knowledge_time_start=None,
        knowledge_time_end=None,
        resolution_policy_version="resolution-v1",
        quality_policy_version="quality-v1",
    )
