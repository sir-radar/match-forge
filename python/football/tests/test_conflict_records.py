from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from football.ingestion import ConflictDispositionV1, ConflictRecordError, ConflictRecordV1


def test_conflict_record_preserves_observations_and_hashes() -> None:
    record = _record()

    assert record.to_dict()["observation_refs"] == ["obs:statsbomb", "obs:totalcorner"]
    assert len(record.sha256) == 64


def test_conflict_record_requires_selected_observation_for_resolution() -> None:
    with pytest.raises(ConflictRecordError, match="selected observation"):
        _record(disposition="RESOLVED", selected_observation_ref=None)
    with pytest.raises(ConflictRecordError, match="part of conflict"):
        _record(selected_observation_ref="obs:other")


def test_conflict_record_rejects_duplicate_observations_and_naive_time() -> None:
    with pytest.raises(ConflictRecordError, match="must be unique"):
        _record(observation_refs=("obs:one", "obs:one"))
    with pytest.raises(ConflictRecordError, match="timezone-aware"):
        _record(created_at=datetime(2026, 1, 1))


def _record(
    *,
    observation_refs: tuple[str, ...] = ("obs:statsbomb", "obs:totalcorner"),
    disposition: str = "RESOLVED",
    selected_observation_ref: str | None = "obs:statsbomb",
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> ConflictRecordV1:
    return ConflictRecordV1(
        conflict_id="conflict-1",
        subject_type="match_score",
        observation_refs=observation_refs,
        policy_version="score-v1",
        disposition=cast(ConflictDispositionV1, disposition),
        selected_observation_ref=selected_observation_ref,
        reason="field policy precedence selected the reviewed observation",
        created_at=created_at,
    )
