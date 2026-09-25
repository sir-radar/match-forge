from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from football.forecasting.dixon_coles import DixonColesConfig, DixonColesModel, GoalMatch
from football.forecasting.phase3a_xg import (
    Phase3AXgForModelV1,
    XgFeatureMatchV1,
    _objective,
    deserialize_phase3a_fit,
    serialize_phase3a_fit,
)

TEAMS = tuple(UUID(f"10000000-0000-4000-8000-{index:012d}") for index in range(1, 5))


def rows() -> tuple[XgFeatureMatchV1, ...]:
    results = (
        (0, 1, 2, 0),
        (2, 3, 1, 0),
        (1, 2, 1, 1),
        (3, 0, 0, 1),
        (0, 2, 3, 1),
        (1, 3, 2, 1),
        (2, 0, 1, 1),
        (3, 1, 0, 2),
    ) * 3
    start = datetime(2025, 1, 1, tzinfo=UTC)
    return tuple(
        XgFeatureMatchV1(
            match=GoalMatch(UUID(int=i + 1), start + timedelta(days=i), TEAMS[h], TEAMS[a], hg, ag),
            home_signal=(-0.2, 0.1, 0.3, -0.1)[h],
            away_signal=(-0.2, 0.1, 0.3, -0.1)[a],
        )
        for i, (h, a, hg, ag) in enumerate(results)
    )


def test_zero_beta_exactly_recovers_reference_forecast() -> None:
    training = rows()
    config = DixonColesConfig(model_version="phase3a-test", time_decay_half_life_days=None)
    fit = Phase3AXgForModelV1(config).fit(training)
    zero = type(fit.parameters)(fit.parameters.reference, 0.0)
    actual = Phase3AXgForModelV1(config).forecast(zero, TEAMS[0], TEAMS[1], 0.4, -0.2)
    expected = DixonColesModel(config).forecast(fit.parameters.reference, TEAMS[0], TEAMS[1])
    assert actual == expected


def test_challenger_fit_is_deterministic_and_round_trips() -> None:
    config = DixonColesConfig(model_version="phase3a-test", time_decay_half_life_days=None)
    model = Phase3AXgForModelV1(config)
    first = model.fit(rows())
    second = model.fit(rows())
    assert first == second
    restored = deserialize_phase3a_fit(serialize_phase3a_fit(first))
    assert restored == first
    assert 0.0 <= first.parameters.beta_xg_for <= 1.0


def test_analytic_gradient_matches_central_difference() -> None:
    training = rows()
    team_ids = tuple(sorted(TEAMS, key=str))
    indexes = {team: i for i, team in enumerate(team_ids)}
    config = DixonColesConfig(model_version="phase3a-gradient", time_decay_half_life_days=None)
    values = [0.05, -0.03, 0.02, 0.1, -0.05, 0.03, 0.08, 0.12, -0.04, 0.25]
    weights = tuple(config.match_weight(0.0) for _ in training)
    _, gradient = _objective(values, training, weights, indexes, len(team_ids))
    for index, derivative in enumerate(gradient):
        lower = list(values)
        upper = list(values)
        lower[index] -= 1e-6
        upper[index] += 1e-6
        numerical = (
            _objective(upper, training, weights, indexes, len(team_ids))[0]
            - _objective(lower, training, weights, indexes, len(team_ids))[0]
        ) / (2e-6)
        assert derivative == pytest.approx(numerical, abs=1e-6)
