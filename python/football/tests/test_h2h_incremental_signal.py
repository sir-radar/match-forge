from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.forecasting.h2h_incremental_signal import (
    H2HResearchError,
    independent_poisson_prediction,
    kickoff_batches,
    verify_firewall,
)
from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ResearchRowV2,
    RollingFeaturesV2,
)


def row(identifier: int, kickoff: datetime) -> ResearchRowV2:
    return ResearchRowV2(
        UUID(int=identifier),
        "premier_league_2024_25",
        "Premier League",
        kickoff,
        UUID(int=10 + identifier),
        UUID(int=20 + identifier),
        RollingFeaturesV2(*(0.0 for _ in range(8))),
        1,
        0,
    )


def test_same_kickoff_rows_are_one_sorted_sealed_batch() -> None:
    first = datetime(2025, 1, 1, 15, tzinfo=UTC)
    second = datetime(2025, 1, 1, 17, tzinfo=UTC)
    batches = kickoff_batches((row(3, second), row(2, first), row(1, first)))
    assert [[item.match_id.int for item in batch] for batch in batches] == [[1, 2], [3]]


def test_firewall_fails_closed_on_any_intersection() -> None:
    verify_firewall({"status": "PASS", "intersections": {"spent_intersections": 0}})
    with pytest.raises(H2HResearchError, match="FAIL_CLOSED_PROTOCOL_VIOLATION"):
        verify_firewall({"status": "PASS", "intersections": {"spent_intersections": 1}})


def test_independent_poisson_score_distribution_is_valid() -> None:
    prediction = independent_poisson_prediction(1.4, 1.1)
    assert sum(sum(row) for row in prediction.score_matrix) == pytest.approx(1.0)
    assert sum(prediction.one_x_two) == pytest.approx(1.0)
    assert all(value >= 0.0 for row in prediction.score_matrix for value in row)
