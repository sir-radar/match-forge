from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from football.forecasting.context_research import (
    ContextEvaluationRow,
    adjusted_rates,
    evaluate_rest_development,
)
from football.forecasting.contextual_goal import ALLOWED_L2, FittedContextFeature

from scripts.run_context_feature_evaluation_rerun import _rest_values, _verify_frozen_inputs

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _rows() -> tuple[ContextEvaluationRow, ...]:
    start = datetime(2022, 8, 1, tzinfo=UTC)
    rows = []
    for index in range(150):
        rest = float(2 + index % 6)
        rows.append(
            ContextEvaluationRow(
                UUID(int=index + 1),
                start + timedelta(days=index),
                f"domain-{index % 4}",
                1.4,
                1.1,
                3 if rest >= 6.0 else index % 2,
                (index // 2) % 2,
                {
                    "home_days_since_last_match": rest,
                    "away_days_since_last_match": float(2 + (index + 2) % 6),
                    "days_since_last_match_difference": rest - float(2 + (index + 2) % 6),
                },
            )
        )
    return tuple(rows)


def test_rest_development_uses_frozen_grid_and_chronological_split() -> None:
    result = evaluate_rest_development(_rows())

    assert tuple(value for value, _score in result.validation_joint_log_loss) == ALLOWED_L2
    assert set(dict(result.partition_counts).values()) == {90, 30}
    assert sum(dict(result.partition_counts).values()) == 150
    assert result.holdout_result.coverage.forecasted_targets == 150
    assert result.holdout_result.coverage.context_qualified_targets == 150
    assert len(result.domain_results) == 4


def test_adjusted_rates_are_neutral_for_mean_imputed_missing_value() -> None:
    row = ContextEvaluationRow(
        UUID(int=1),
        datetime(2022, 8, 1, tzinfo=UTC),
        "domain",
        1.4,
        1.1,
        1,
        0,
        {},
    )
    coefficients = (FittedContextFeature("home_days_since_last_match", 0.4, -0.2, 5.0, 2.0),)

    assert adjusted_rates(row, coefficients) == (1.4, 1.1)


def test_rerun_inputs_verify_before_outcomes_are_loaded() -> None:
    inputs = _verify_frozen_inputs(REPOSITORY_ROOT)

    assert len(inputs["targets"]) == 4316
    assert len(inputs["snapshots"]) == 4316
    assert inputs["manifest"]["target_manifest_outcome_blind"] is True
    assert inputs["rest"]["status"] == "QUALIFIED"


def test_rest_values_preserve_sides_and_home_away_difference() -> None:
    values = _rest_values(
        {
            "rest_context": {
                "home": {"days_since_last_match": 3.0, "matches_last_7_days": 2.0},
                "away": {"days_since_last_match": 5.0, "matches_last_7_days": 1.0},
            }
        }
    )

    assert values["home_days_since_last_match"] == 3.0
    assert values["away_days_since_last_match"] == 5.0
    assert values["days_since_last_match_difference"] == -2.0
    assert values["matches_last_7_days_difference"] == 1.0
    assert values["days_to_next_match_difference"] is None
