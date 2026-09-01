from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import football.forecasting.dixon_coles as dixon_coles_module
import pytest
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesContractError,
    DixonColesFitError,
    DixonColesModel,
    DixonColesParameters,
    GoalMatch,
)

TEAM_A = UUID("10000000-0000-4000-8000-000000000001")
TEAM_B = UUID("10000000-0000-4000-8000-000000000002")
TEAM_C = UUID("10000000-0000-4000-8000-000000000003")
TEAM_D = UUID("10000000-0000-4000-8000-000000000004")
UNKNOWN_TEAM = UUID("10000000-0000-4000-8000-000000000099")
KICKOFF = datetime(2026, 1, 1, 15, 0, tzinfo=UTC)


def test_configuration_identity_and_time_decay_are_deterministic() -> None:
    config = DixonColesConfig(model_version="dc-v1", time_decay_half_life_days=100.0)
    same = DixonColesConfig(model_version="dc-v1", time_decay_half_life_days=100.0)

    assert config.sha256 == same.sha256
    assert config.match_weight(0.0) == 1.0
    assert config.match_weight(100.0) == pytest.approx(0.5)
    assert config.match_weight(200.0) == pytest.approx(0.25)

    with pytest.raises(DixonColesContractError, match="model_version"):
        DixonColesConfig(model_version="Invalid Version")
    with pytest.raises(DixonColesContractError, match="half-life"):
        DixonColesConfig(model_version="dc-v2", time_decay_half_life_days=0.0)
    with pytest.raises(DixonColesContractError, match="optimizer"):
        DixonColesConfig(model_version="dc-v2", optimizer="unsupported")  # type: ignore[arg-type]
    with pytest.raises(DixonColesContractError, match="gradient tolerance"):
        DixonColesConfig(model_version="dc-v2", gradient_tolerance=0.0)


def test_forecast_uses_team_strengths_home_advantage_and_low_score_correction() -> None:
    parameters = DixonColesParameters(
        attack_strengths={TEAM_A: 0.2, TEAM_B: -0.2},
        defense_strengths={TEAM_A: -0.1, TEAM_B: 0.1},
        home_advantage=0.25,
        low_score_correlation=-0.1,
    )
    forecast = DixonColesModel(DixonColesConfig(model_version="dc-v1")).forecast(
        parameters, TEAM_A, TEAM_B
    )

    expected_home = math.exp(0.2 + 0.1 + 0.25)
    expected_away = math.exp(-0.2 - 0.1)
    assert forecast.lambda_home == pytest.approx(expected_home)
    assert forecast.lambda_away == pytest.approx(expected_away)
    independent_zero_zero = math.exp(-expected_home) * math.exp(-expected_away)
    assert forecast.exact_score_probability(0, 0) == pytest.approx(
        independent_zero_zero * (1.0 - expected_home * expected_away * -0.1)
    )
    assert forecast.exact_score_probability(2, 1) == pytest.approx(
        _poisson(2, expected_home) * _poisson(1, expected_away)
    )
    assert sum(sum(row) for row in forecast.score_matrix.probabilities) == pytest.approx(1.0)
    assert (
        forecast.markets.home_win + forecast.markets.draw + forecast.markets.away_win
    ) == pytest.approx(1.0)


def test_score_matrix_and_market_probabilities_are_coherent() -> None:
    parameters = DixonColesParameters(
        attack_strengths={TEAM_A: 0.0, TEAM_B: 0.0},
        defense_strengths={TEAM_A: 0.0, TEAM_B: 0.0},
        home_advantage=0.0,
        low_score_correlation=0.0,
    )
    forecast = DixonColesModel(DixonColesConfig(model_version="dc-market-v1")).forecast(
        parameters, TEAM_A, TEAM_B
    )

    assert forecast.score_matrix.labels == ("0", "1", "2", "3", "4", "5+")
    assert sum(sum(row) for row in forecast.score_matrix.probabilities) == pytest.approx(1.0)
    assert forecast.score_matrix.probability("5+", "5+") > 0.0
    assert (
        forecast.markets.home_win + forecast.markets.draw + forecast.markets.away_win
    ) == pytest.approx(1.0)
    assert forecast.markets.home_win == pytest.approx(forecast.markets.away_win)
    assert forecast.markets.over_1_5 > forecast.markets.over_2_5
    assert forecast.markets.over_2_5 > forecast.markets.over_3_5
    assert forecast.markets.both_teams_to_score == pytest.approx((1.0 - math.exp(-1.0)) ** 2)
    assert forecast.markets.home_clean_sheet == pytest.approx(math.exp(-1.0))
    assert forecast.markets.away_clean_sheet == pytest.approx(math.exp(-1.0))


def test_fit_estimates_identifiable_finite_parameters() -> None:
    matches = _balanced_training_matches()
    model = DixonColesModel(
        DixonColesConfig(
            model_version="dc-fit-v1",
            time_decay_half_life_days=None,
            max_iterations=400,
        )
    )

    fitted = model.fit(matches)
    repeated = model.fit(matches)

    assert fitted.converged
    assert fitted.training_match_count == len(matches)
    assert fitted.training_cutoff == matches[-1].kickoff_at
    assert set(fitted.parameters.attack_strengths) == {TEAM_A, TEAM_B, TEAM_C, TEAM_D}
    assert sum(fitted.parameters.attack_strengths.values()) == pytest.approx(0.0, abs=1e-8)
    assert all(math.isfinite(value) for value in fitted.parameters.attack_strengths.values())
    assert all(math.isfinite(value) for value in fitted.parameters.defense_strengths.values())
    assert math.isfinite(fitted.negative_log_likelihood)
    assert repeated == fitted
    forecast = model.forecast(fitted.parameters, TEAM_A, TEAM_D)
    assert forecast.lambda_home > 0.0
    assert forecast.lambda_away > 0.0


def test_fit_rejects_false_optimizer_success_with_nonstationary_gradient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def false_success(objective: object, initial: list[float], **_: object) -> object:
        value = objective(initial)  # type: ignore[operator]
        objective_value = value[0] if isinstance(value, tuple) else value
        return SimpleNamespace(
            success=True,
            message="false success",
            fun=objective_value,
            x=initial,
            jac=[1.0] * len(initial),
        )

    monkeypatch.setattr(dixon_coles_module, "minimize", false_success)
    model = DixonColesModel(
        DixonColesConfig(model_version="dc-stationarity-v2", time_decay_half_life_days=None)
    )

    with pytest.raises(DixonColesFitError, match="stationary"):
        model.fit(_balanced_training_matches())


def test_v2_uses_analytic_slsqp_with_strict_function_tolerance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def successful_fit(objective: object, initial: list[float], **kwargs: object) -> object:
        captured.update(kwargs)
        value, gradient = objective(initial)  # type: ignore[operator]
        return SimpleNamespace(
            success=True,
            message="converged",
            fun=value,
            x=initial,
            jac=[0.0] * len(gradient),
        )

    monkeypatch.setattr(dixon_coles_module, "minimize", successful_fit)
    config = DixonColesConfig(
        model_version="dc-analytic-slsqp-v2",
        time_decay_half_life_days=None,
        gradient_tolerance=2e-4,
    )

    DixonColesModel(config).fit(_balanced_training_matches())

    assert config.optimizer == "slsqp-analytic-gradient-v2"
    assert config.tolerance == 1e-12
    assert captured["method"] == "SLSQP"
    assert captured["jac"] is True
    assert captured["options"] == {
        "maxiter": config.max_iterations,
        "ftol": config.tolerance,
    }


def test_analytic_gradient_matches_central_difference() -> None:
    matches = _balanced_training_matches()
    team_ids = tuple(
        sorted({team for match in matches for team in (match.home_team_id, match.away_team_id)})
    )
    team_indexes = {team_id: index for index, team_id in enumerate(team_ids)}
    values = [0.05, -0.03, 0.02, 0.1, -0.05, 0.03, 0.08, 0.12, -0.04]

    _, gradient = dixon_coles_module._negative_log_likelihood_and_gradient(
        values,
        matches,
        (1.0,) * len(matches),
        team_indexes,
        len(team_ids),
    )

    step = 1e-6
    for index, derivative in enumerate(gradient):
        lower = values.copy()
        upper = values.copy()
        lower[index] -= step
        upper[index] += step
        lower_value = dixon_coles_module._negative_log_likelihood_and_gradient(
            lower, matches, (1.0,) * len(matches), team_indexes, len(team_ids)
        )[0]
        upper_value = dixon_coles_module._negative_log_likelihood_and_gradient(
            upper, matches, (1.0,) * len(matches), team_indexes, len(team_ids)
        )[0]
        numerical = (upper_value - lower_value) / (2.0 * step)
        assert derivative == pytest.approx(numerical, abs=1e-6)


def test_rejects_invalid_matches_parameters_and_unknown_teams() -> None:
    with pytest.raises(DixonColesContractError, match="timezone"):
        GoalMatch(
            match_id=UUID(int=1),
            kickoff_at=datetime(2026, 1, 1),
            home_team_id=TEAM_A,
            away_team_id=TEAM_B,
            home_goals=1,
            away_goals=0,
        )
    parameters = DixonColesParameters(
        attack_strengths={TEAM_A: 0.0, TEAM_B: 0.0},
        defense_strengths={TEAM_A: 0.0, TEAM_B: 0.0},
        home_advantage=0.0,
        low_score_correlation=0.0,
    )
    model = DixonColesModel(DixonColesConfig(model_version="dc-errors-v1"))
    with pytest.raises(DixonColesContractError, match="not fitted"):
        model.forecast(parameters, TEAM_A, UNKNOWN_TEAM)
    with pytest.raises(DixonColesContractError, match="attack strength"):
        DixonColesParameters(
            attack_strengths={TEAM_A: 4.0, TEAM_B: 0.0},
            defense_strengths={TEAM_A: 0.0, TEAM_B: 0.0},
        )
    with pytest.raises(DixonColesContractError, match="at least two teams"):
        model.fit(())


def _balanced_training_matches() -> tuple[GoalMatch, ...]:
    results = (
        (TEAM_A, TEAM_B, 2, 0),
        (TEAM_C, TEAM_D, 1, 0),
        (TEAM_B, TEAM_C, 1, 1),
        (TEAM_D, TEAM_A, 0, 1),
        (TEAM_A, TEAM_C, 3, 1),
        (TEAM_B, TEAM_D, 2, 1),
        (TEAM_C, TEAM_A, 1, 1),
        (TEAM_D, TEAM_B, 0, 2),
        (TEAM_A, TEAM_D, 2, 1),
        (TEAM_C, TEAM_B, 0, 0),
        (TEAM_B, TEAM_A, 1, 2),
        (TEAM_D, TEAM_C, 1, 1),
    )
    return tuple(
        GoalMatch(
            match_id=UUID(int=index + 1),
            kickoff_at=KICKOFF + timedelta(days=index * 7),
            home_team_id=home,
            away_team_id=away,
            home_goals=home_goals,
            away_goals=away_goals,
        )
        for index, (home, away, home_goals, away_goals) in enumerate(results)
    )


def _poisson(goals: int, expected_goals: float) -> float:
    return math.exp(-expected_goals) * expected_goals**goals / math.factorial(goals)
