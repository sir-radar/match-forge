from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import numpy as np
import pytest
from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ModelParametersV2,
    ResearchObservationV2,
    ResearchRowV2,
    RollingFeaturesV2,
    dixon_coles_tau,
    fit_model,
    forecast,
    research_rows,
)


def _observation(
    day: int,
    home: UUID,
    away: UUID,
    *,
    match_id: UUID | None = None,
    home_goals: int = 1,
    away_goals: int = 0,
) -> ResearchObservationV2:
    return ResearchObservationV2(
        match_id=match_id or uuid4(),
        scope_key="test_2025_26",
        competition="Test League",
        kickoff_at=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=day),
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
        home_npxg=1.2,
        away_npxg=0.8,
    )


def test_dixon_coles_tau_exact_cells_and_ordinary_cell() -> None:
    assert dixon_coles_tau(0, 0, 1.4, 1.1, -0.05) == pytest.approx(1.077)
    assert dixon_coles_tau(0, 1, 1.4, 1.1, -0.05) == pytest.approx(0.93)
    assert dixon_coles_tau(1, 0, 1.4, 1.1, -0.05) == pytest.approx(0.945)
    assert dixon_coles_tau(1, 1, 1.4, 1.1, -0.05) == pytest.approx(1.05)
    assert dixon_coles_tau(2, 1, 1.4, 1.1, -0.05) == 1.0


@pytest.mark.parametrize("rho", [-0.15, 0.15])
def test_score_matrix_is_normalized_at_rho_boundary(rho: float) -> None:
    parameters = ModelParametersV2(
        global_intercept=math.log(1.1),
        global_home_advantage=math.log(1.2 / 1.1),
        goals_for_weight=0.0,
        goals_against_weight=0.0,
        npxg_for_weight=0.0,
        npxg_against_weight=0.0,
        rho=rho,
        competition_baseline_deviations={},
        competition_home_advantage_deviations={},
        regularization=(25.0, 25.0, 100.0),
    )
    prediction = forecast(parameters, _features())
    assert sum(sum(row) for row in prediction.score_matrix) == pytest.approx(1.0, abs=1e-12)
    assert all(value >= 0.0 for row in prediction.score_matrix for value in row)


def test_rolling_features_are_prior_only_and_same_kickoff_sealed() -> None:
    home, away, third = uuid4(), uuid4(), uuid4()
    observations = [_observation(day, home, away) for day in range(10)]
    kickoff_match = uuid4()
    observations.extend(
        (
            _observation(10, home, away, match_id=kickoff_match, home_goals=9),
            _observation(10, third, home, home_goals=0, away_goals=8),
        )
    )
    rows = research_rows(tuple(observations))
    target = next(row for row in rows if row.match_id == kickoff_match)
    assert target.features.home_goals_for == pytest.approx(math.log(1.05 / 0.55))
    assert target.features.home_npxg_for == pytest.approx(math.log(1.25 / 1.05))


def test_candidate_fit_is_deterministic_and_roster_independent() -> None:
    teams = tuple(uuid4() for _ in range(4))
    rows: list[ResearchRowV2] = []
    for index in range(40):
        rows.append(
            ResearchRowV2(
                match_id=uuid4(),
                scope_key="test_2025_26",
                competition="Test League",
                kickoff_at=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index),
                home_team_id=teams[index % 4],
                away_team_id=teams[(index + 1) % 4],
                features=_features(),
                home_goals=index % 3,
                away_goals=(index + 1) % 2,
            )
        )
    first = fit_model(tuple(rows), model_role="candidate", regularization=(25.0, 25.0, 100.0))
    second = fit_model(tuple(rows), model_role="candidate", regularization=(25.0, 25.0, 100.0))
    assert first == second
    assert not any("team" in key for key in first.to_dict())
    assert ModelParametersV2.from_dict(first.to_dict()) == first


def test_analytic_gradient_matches_finite_difference() -> None:
    from football.forecasting import transferable_npxg_dixon_coles_v2 as model

    teams = tuple(uuid4() for _ in range(4))
    rows = tuple(
        ResearchRowV2(
            match_id=uuid4(),
            scope_key="test",
            competition="Test League",
            kickoff_at=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index),
            home_team_id=teams[index % 4],
            away_team_id=teams[(index + 1) % 4],
            features=_features(),
            home_goals=index % 3,
            away_goals=(index + 1) % 2,
        )
        for index in range(12)
    )
    layout = model._Layout(("Test League",), "candidate")
    values = layout.initial(rows)
    _, analytic = model._objective_and_gradient(values, rows, layout, (25.0, 25.0, 100.0))
    epsilon = 1e-6
    finite = np.zeros(layout.size)
    for index in range(layout.size):
        plus, minus = values.copy(), values.copy()
        plus[index] += epsilon
        minus[index] -= epsilon
        upper = model._objective_and_gradient(plus, rows, layout, (25.0, 25.0, 100.0))[0]
        lower = model._objective_and_gradient(minus, rows, layout, (25.0, 25.0, 100.0))[0]
        finite[index] = (upper - lower) / (2.0 * epsilon)
    assert analytic == pytest.approx(finite, abs=1e-6)


def test_domain_and_team_folds_exclude_future_and_held_out_identity() -> None:
    from scripts.run_transferable_npxg_dixon_coles_v2_research import (
        _domain_training_rows,
        _team_training_rows,
    )

    team = uuid4()
    opponent = uuid4()
    third = uuid4()
    cutoff = datetime(2025, 2, 1, tzinfo=UTC)
    rows = (
        ResearchRowV2(
            uuid4(), "held", "A", cutoff - timedelta(days=2), team, opponent, _features(), 1, 0
        ),
        ResearchRowV2(
            uuid4(), "other", "B", cutoff - timedelta(days=1), team, third, _features(), 1, 1
        ),
        ResearchRowV2(
            uuid4(), "other", "B", cutoff - timedelta(days=1), opponent, third, _features(), 0, 1
        ),
        ResearchRowV2(uuid4(), "other", "B", cutoff, opponent, third, _features(), 2, 1),
    )
    domain_rows = _domain_training_rows(rows, held_out_scope="held", cutoff=cutoff)
    assert len(domain_rows) == 2
    assert all(row.scope_key != "held" and row.kickoff_at < cutoff for row in domain_rows)
    team_rows = _team_training_rows(rows, held_out_team=team, cutoff=cutoff)
    assert len(team_rows) == 1
    assert all(team not in (row.home_team_id, row.away_team_id) for row in team_rows)


def _features() -> RollingFeaturesV2:
    return RollingFeaturesV2(
        home_goals_for=0.1,
        home_goals_against=-0.1,
        home_npxg_for=0.12,
        home_npxg_against=-0.08,
        away_goals_for=-0.05,
        away_goals_against=0.05,
        away_npxg_for=-0.02,
        away_npxg_against=0.03,
    )
