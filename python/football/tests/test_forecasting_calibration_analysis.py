from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from football.forecasting.calibration_analysis import (
    Sprint2CalibrationAnalyzerV1,
    Sprint2CalibrationPolicyV1,
)
from football.forecasting.contracts import (
    CornerForecastPayloadV1,
    GoalForecastPayloadV1,
    MatchResultProbabilitiesV1,
)
from football.forecasting.dataset import EvaluationMatchOutcomeV1, ForecastMatchContextV1
from football.forecasting.execution import Sprint2RawForecastV1

COMPETITION = UUID(int=1)
SEASON = UUID(int=2)
HOME = UUID(int=3)
AWAY = UUID(int=4)
START = datetime(2015, 8, 1, 15, 0, tzinfo=UTC)


def test_calibration_uses_prior_oos_batches_and_preserves_raw_probabilities() -> None:
    forecasts, outcomes = _observations(36)
    raw_before = tuple(forecast.to_dict() for forecast in forecasts)
    policy = Sprint2CalibrationPolicyV1(
        binary_platt_minimum=20,
        binary_platt_minimum_events=5,
        binary_isotonic_minimum=30,
        binary_isotonic_minimum_events=5,
        binary_isotonic_minimum_distinct=10,
        multiclass_minimum=30,
        multiclass_minimum_class_events=5,
    )
    analyzer = Sprint2CalibrationAnalyzerV1(policy)

    first = analyzer.analyze(forecasts, outcomes)
    repeated = analyzer.analyze(forecasts, outcomes)

    assert first == repeated
    assert tuple(forecast.to_dict() for forecast in forecasts) == raw_before
    available = [row for row in first.predictions if row.status == "AVAILABLE"]
    assert available
    multiclass = next(row for row in available if row.product == "1x2")
    assert multiclass.calibrated_home is not None
    assert multiclass.calibrated_draw is not None
    assert multiclass.calibrated_away is not None
    assert (
        multiclass.calibrated_home + multiclass.calibrated_draw + multiclass.calibrated_away == 1.0
    )
    assert first.metrics
    assert first.bins


def test_same_kickoff_predictions_cannot_train_each_other() -> None:
    forecasts, outcomes = _observations(34, same_kickoff_tail=True)
    policy = Sprint2CalibrationPolicyV1(
        binary_platt_minimum=20,
        binary_platt_minimum_events=5,
        binary_isotonic_minimum=30,
        binary_isotonic_minimum_events=5,
        binary_isotonic_minimum_distinct=10,
        multiclass_minimum=30,
        multiclass_minimum_class_events=5,
    )

    result = Sprint2CalibrationAnalyzerV1(policy).analyze(forecasts, outcomes)
    tail_ids = {forecasts[-1].context.match_id, forecasts[-2].context.match_id}
    rows = [
        row
        for row in result.predictions
        if row.match_id in tail_ids and row.product == "1x2" and row.base_model == "dixon_coles"
    ]

    assert len(rows) == 2
    assert {row.training_sample_count for row in rows} == {32}


def _observations(
    count: int, *, same_kickoff_tail: bool = False
) -> tuple[tuple[Sprint2RawForecastV1, ...], tuple[EvaluationMatchOutcomeV1, ...]]:
    forecasts: list[Sprint2RawForecastV1] = []
    outcomes: list[EvaluationMatchOutcomeV1] = []
    for index in range(count):
        kickoff = START + timedelta(days=index)
        if same_kickoff_tail and index == count - 1:
            kickoff = START + timedelta(days=index - 1)
        probability = 0.12 + (index % 25) / 100.0
        result = MatchResultProbabilitiesV1(
            home=0.25 + probability / 2.0,
            draw=0.25,
            away=0.50 - probability / 2.0,
        )
        goal = GoalForecastPayloadV1(
            lambda_home=1.4,
            lambda_away=1.1,
            score_labels=("0", "1", "2+"),
            score_probabilities=((0.1, 0.1, 0.1), (0.1, 0.2, 0.1), (0.1, 0.1, 0.1)),
            over_0_5=0.9,
            over_1_5=0.75,
            over_2_5=probability + 0.2,
            over_3_5=0.2,
            over_4_5=0.1,
            btts_yes=probability + 0.1,
            home_clean_sheet=0.3,
            away_clean_sheet=0.25,
        )
        corners = CornerForecastPayloadV1("poisson", 5.0, 4.0, 5.0, 4.0, None)
        context = ForecastMatchContextV1(
            UUID(int=100 + index), COMPETITION, SEASON, kickoff, HOME, AWAY
        )
        forecasts.append(
            Sprint2RawForecastV1(
                context=context,
                elo_result=result,
                dixon_coles_result=result,
                goal=goal,
                corner_poisson=corners,
                corner_negative_binomial=CornerForecastPayloadV1(
                    "negative_binomial", 5.0, 4.0, 7.5, 6.0, 0.1
                ),
                result_reference=MatchResultProbabilitiesV1(0.4, 0.3, 0.3),
                goal_reference=goal,
                corner_reference=corners,
            )
        )
        outcome_class = index % 3
        scores = ((2, 0), (1, 1), (0, 2))[outcome_class]
        outcomes.append(
            EvaluationMatchOutcomeV1(
                context.match_id,
                kickoff,
                scores[0],
                scores[1],
                5,
                4,
                kickoff + timedelta(hours=2),
            )
        )
    return tuple(forecasts), tuple(outcomes)
