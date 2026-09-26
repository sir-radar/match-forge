from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from football.forecasting.pitchapi_v3 import (
    HistoryObservationV1,
    RollingHistoryV1,
    TransferableForecastContextV1,
    TransferableGoalModelV1,
    TransferableParametersV1,
    parameter_payload,
)


def _observation(
    *,
    match_id: UUID | None = None,
    kickoff_at: datetime,
    home_team_id: UUID,
    away_team_id: UUID,
    home_goals: int = 1,
    away_goals: int = 0,
    home_npxg: float = 1.2,
    away_npxg: float = 0.8,
) -> HistoryObservationV1:
    return HistoryObservationV1(
        match_id=match_id or uuid4(),
        kickoff_at=kickoff_at,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_goals=home_goals,
        away_goals=away_goals,
        home_npxg=home_npxg,
        away_npxg=away_npxg,
    )


def test_transferable_model_forecasts_completely_unseen_team_ids() -> None:
    home = uuid4()
    away = uuid4()
    history = RollingHistoryV1(window=10)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(10):
        history.update_batch(
            (
                _observation(
                    kickoff_at=start + timedelta(days=index),
                    home_team_id=home,
                    away_team_id=away,
                    home_goals=index % 3,
                    away_goals=(index + 1) % 2,
                ),
            )
        )
    context = TransferableForecastContextV1(
        match_id=uuid4(),
        scope_key="synthetic",
        kickoff_at=start + timedelta(days=10),
        home_team_id=home,
        away_team_id=away,
    )
    parameters = TransferableParametersV1(
        home_intercept=0.2,
        away_intercept=-0.1,
        attack_goals_weight=0.5,
        defense_goals_weight=0.5,
        beta_xg_for=0.1,
        population_goal_mean=1.2,
        population_npxg_mean=1.1,
    )

    forecast = TransferableGoalModelV1(parameters).forecast(context, history)

    assert forecast.lambda_home > 0
    assert forecast.lambda_away > 0
    assert sum(sum(row) for row in forecast.score_matrix.probabilities) == pytest.approx(1.0)


def test_same_kickoff_batch_cannot_observe_peer_outcome() -> None:
    home = uuid4()
    away = uuid4()
    third = uuid4()
    history = RollingHistoryV1(window=10)
    kickoff = datetime(2026, 2, 1, tzinfo=UTC)
    for index in range(10):
        history.update_batch(
            (
                _observation(
                    kickoff_at=kickoff - timedelta(days=10 - index),
                    home_team_id=home,
                    away_team_id=away,
                ),
            )
        )
    before = history.features(home, away, cutoff=kickoff)
    peer = _observation(
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=third,
        home_goals=9,
        home_npxg=8.0,
    )

    with pytest.raises(ValueError, match="strictly precede"):
        history.update_batch((peer,), next_cutoff=kickoff)

    assert history.features(home, away, cutoff=kickoff) == before


def test_history_requires_exactly_ten_prior_appearances() -> None:
    home = uuid4()
    away = uuid4()
    history = RollingHistoryV1(window=10)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(9):
        history.update_batch(
            (
                _observation(
                    kickoff_at=start + timedelta(days=index),
                    home_team_id=home,
                    away_team_id=away,
                ),
            )
        )

    with pytest.raises(ValueError, match="10 prior appearances"):
        history.features(home, away, cutoff=start + timedelta(days=10))


def test_transferable_artifact_and_forecast_are_roster_independent_and_deterministic() -> None:
    parameters = TransferableParametersV1(0.2, -0.1, 0.4, 0.3, 0.1, 1.2, 1.1)
    payload = parameter_payload(parameters, model_role="REFERENCE")
    assert payload["team_id_parameters"] is False
    artifact_parameters = payload["parameters"]
    assert isinstance(artifact_parameters, dict)
    assert not any("team" in key for key in artifact_parameters)

    history = RollingHistoryV1()
    home, away = uuid4(), uuid4()
    start = datetime(2026, 3, 1, tzinfo=UTC)
    for index in range(12):
        history.update_batch(
            (
                _observation(
                    kickoff_at=start + timedelta(days=index),
                    home_team_id=home,
                    away_team_id=away,
                    home_npxg=0.0 if index == 0 else 1.2,
                ),
            )
        )
    context = TransferableForecastContextV1(
        uuid4(), "new_competition", start + timedelta(days=12), home, away
    )
    model = TransferableGoalModelV1(parameters)
    assert model.forecast(context, history) == model.forecast(context, history)
