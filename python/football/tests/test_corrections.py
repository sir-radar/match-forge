from __future__ import annotations

from datetime import UTC, datetime

import pytest
from football.ingestion import BitemporalCorrectionV1, CorrectionRecordError


def test_correction_binds_prior_and_replacement_lineage() -> None:
    correction = _correction()

    assert correction.to_dict()["prior_observation_ref"] == "observation:old"
    assert len(correction.sha256) == 64


def test_correction_rejects_same_observation_or_reversed_range() -> None:
    with pytest.raises(CorrectionRecordError, match="must differ"):
        _correction(replacement_observation_ref="observation:old")
    with pytest.raises(CorrectionRecordError, match="reversed"):
        _correction(
            football_valid_from=datetime(2026, 2, 1, tzinfo=UTC),
            football_valid_to=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_correction_requires_timezone_aware_knowledge_time() -> None:
    with pytest.raises(CorrectionRecordError, match="timezone-aware"):
        _correction(known_from=datetime(2026, 1, 1))


def _correction(
    *,
    replacement_observation_ref: str = "observation:new",
    football_valid_from: datetime | None = datetime(2026, 1, 1, tzinfo=UTC),
    football_valid_to: datetime | None = None,
    known_from: datetime = datetime(2026, 1, 2, tzinfo=UTC),
) -> BitemporalCorrectionV1:
    return BitemporalCorrectionV1(
        correction_id="correction-1",
        canonical_entity_id="match-1",
        prior_observation_ref="observation:old",
        replacement_observation_ref=replacement_observation_ref,
        source_snapshot_ref="snapshot:1",
        source_resource_ref="resource:1",
        football_valid_from=football_valid_from,
        football_valid_to=football_valid_to,
        known_from=known_from,
        reason="provider supplied a corrected regulation-time score",
    )
