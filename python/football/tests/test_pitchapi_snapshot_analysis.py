from __future__ import annotations

import numpy as np
import pytest

from scripts.analyze_pitchapi_snapshot_v1 import _ks, _logistic_fit, _normalized_shot


def test_normalized_shot_maps_goal_and_rejects_unknown_semantics() -> None:
    shot = {
        "id": "s_1",
        "team_id": "t_1",
        "expected_goals": 0.25,
        "situation": "RegularPlay",
        "event_type": "Goal",
    }

    row = _normalized_shot(shot, "FirstHalf")

    assert row == {
        "shot_id": "s_1",
        "team_id": "t_1",
        "period": "FirstHalf",
        "xg": 0.25,
        "situation": "RegularPlay",
        "goal": True,
    }
    with pytest.raises(RuntimeError, match="unknown shot outcome semantics"):
        _normalized_shot({**shot, "event_type": "Unknown"}, "FirstHalf")


def test_logistic_fit_recovers_constructed_intercept_and_slope() -> None:
    xg = np.linspace(0.02, 0.98, 2000)
    predictor = np.log(xg / (1 - xg))
    probabilities = 1 / (1 + np.exp(-(-0.2 + 0.9 * predictor)))
    goals = (np.mod(np.arange(len(xg)) * 0.61803398875, 1.0) < probabilities).astype(float)

    fit = _logistic_fit(xg, goals, clip=1e-6)

    assert fit is not None
    assert fit[0] == pytest.approx(-0.2, abs=0.08)
    assert fit[1] == pytest.approx(0.9, abs=0.08)


def test_ks_comparison_records_effect_size_and_sample_counts() -> None:
    left: list[dict[str, object]] = [{"xg": value} for value in (0.1, 0.2, 0.3, 0.4)]
    right: list[dict[str, object]] = [{"xg": value} for value in (0.6, 0.7, 0.8, 0.9)]

    comparison = _ks("left", "right", "ALL_SHOTS", left, right)

    assert comparison.statistic == 1.0
    assert comparison.left_shot_count == 4
    assert comparison.right_shot_count == 4
