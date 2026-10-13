from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from football.forecasting.champion_adapter import (
    TransferableRollingGoalsChampion,
    load_champion_artifact,
)
from football.forecasting.ensemble import EnsembleWeights, build_ensemble_forecast
from football.forecasting.model_contracts import (
    CompetitionContext,
    HistoricalMatch,
    derive_markets,
    distributions,
    rust_score_atoms,
)
from football.forecasting.multimodel_cli import _forecast_dict, _forecast_from_dict
from football.forecasting.pitchapi_v3 import _poisson_forecast
from football.forecasting.snapshot import build_forecast_snapshot
from football.product.domain import MODEL_ARTIFACT_PATH


@pytest.mark.parametrize("means", [(0.1, 0.2), (2.5, 2.0), (8.0, 6.0), (12.0, 9.0)])
def test_champion_adapter_preserves_analytic_control_and_exact_support(
    monkeypatch: pytest.MonkeyPatch, means: tuple[float, float]
) -> None:
    home, away, competition, target = [UUID(int=index) for index in range(1, 5)]
    kickoff = datetime(2026, 10, 20, 14, tzinfo=UTC)
    history = tuple(
        HistoricalMatch(
            fixture_id=UUID(int=100 + side * 20 + index),
            competition_id=competition,
            competition_context=CompetitionContext.LEAGUE,
            kickoff_at=kickoff - timedelta(days=20 - index),
            known_at=kickoff - timedelta(days=19 - index),
            home_team_id=team,
            away_team_id=UUID(int=1000 + side * 20 + index),
            home_goals=2,
            away_goals=1,
        )
        for side, team in enumerate((home, away))
        for index in range(10)
    )
    snapshot = build_forecast_snapshot(
        fixture_id=target,
        competition_id=competition,
        competition_context=CompetitionContext.LEAGUE,
        season_label="2026",
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        football_cutoff=kickoff - timedelta(hours=1),
        knowledge_cutoff=kickoff - timedelta(hours=1),
        knowledge_mode="bitemporal",
        history=history,
    )
    canonical = _poisson_forecast(*means)
    monkeypatch.setattr(
        "football.product.domain.TransferableGoalModelV1.forecast_features",
        lambda _model, _features: canonical,
    )
    artifact = load_champion_artifact(MODEL_ARTIFACT_PATH, history)
    forecast = TransferableRollingGoalsChampion().predict(artifact, snapshot)
    assert forecast.expected_home_goals == means[0]
    assert forecast.expected_away_goals == means[1]
    assert forecast.home_probability == canonical.markets.home_win
    assert forecast.draw_probability == canonical.markets.draw
    assert forecast.away_probability == canonical.markets.away_win
    assert forecast.numerical_contract_version == "exact-support-with-tail-v2"
    assert all(label == str(index) for index, label in enumerate(forecast.score_labels))
    assert forecast.display_score_labels[-1] == "5+"
    assert forecast.score_matrix[6][5] > 0 and forecast.score_matrix[5][6] > 0
    assert forecast.display_score_matrix[5][5] >= (
        forecast.score_matrix[5][5] + forecast.score_matrix[6][5] + forecast.score_matrix[5][6]
    )
    assert sum(
        map(sum, forecast.score_matrix)
    ) + forecast.unresolved_tail_probability == pytest.approx(1.0, abs=1e-10)
    atoms = rust_score_atoms(forecast)
    assert sum(cast(float, atom["probability"]) for atom in atoms) == pytest.approx(1.0, abs=1e-10)
    assert any(atom["kind"] == "UNRESOLVED_TAIL" for atom in atoms)
    assert _forecast_from_dict(_forecast_dict(forecast)) == forecast
    partner = replace(forecast, model_id="compatible-exact-component")
    pooled = build_ensemble_forecast(
        forecasts=(forecast, partner),
        weights=EnsembleWeights(((forecast.model_id, 0.5), (partner.model_id, 0.5)), ()),
        model_artifact_sha256="a" * 64,
    )
    assert pooled is not None
    assert pooled.expected_home_goals == means[0]
    assert pooled.expected_away_goals == means[1]
    assert pooled.draw_probability == canonical.markets.draw
    assert pooled.unresolved_tail_probability == forecast.unresolved_tail_probability
    legacy_home, legacy_away, legacy_total = distributions(forecast.display_score_matrix)
    legacy = replace(
        forecast,
        model_id="legacy-compact-component",
        numerical_contract_version="legacy-score-grid-v1",
        score_labels=forecast.display_score_labels,
        score_matrix=forecast.display_score_matrix,
        home_goal_distribution=legacy_home,
        away_goal_distribution=legacy_away,
        total_goal_distribution=legacy_total,
        expected_home_goals=sum(index * value for index, value in enumerate(legacy_home)),
        expected_away_goals=sum(index * value for index, value in enumerate(legacy_away)),
        unresolved_tail_probability=0,
        unresolved_tail_home_expectation=0,
        unresolved_tail_away_expectation=0,
        display_score_labels=(),
        display_score_matrix=(),
        **derive_markets(forecast.display_score_matrix),
    )
    legacy_payload = _forecast_dict(legacy)
    assert "numerical_contract_version" not in legacy_payload
    assert _forecast_dict(_forecast_from_dict(legacy_payload)) == legacy_payload
    with pytest.raises(ValueError, match="unresolved tail exceeds"):
        build_ensemble_forecast(
            forecasts=(forecast, legacy),
            weights=EnsembleWeights(((forecast.model_id, 0.5), (legacy.model_id, 0.5)), ()),
            model_artifact_sha256="a" * 64,
        )
    with pytest.raises(ValueError, match="exact integer score labels"):
        replace(
            forecast,
            score_labels=forecast.display_score_labels,
            score_matrix=forecast.display_score_matrix,
        )
    with pytest.raises(ValueError, match="expected_away_goals"):
        replace(forecast, expected_away_goals=forecast.expected_away_goals + 0.1)
    with pytest.raises(ValueError, match="unresolved tail exceeds"):
        replace(forecast, unresolved_tail_probability=0.01)
