from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.forecasting.artifacts import (
    ArtifactPublicationError,
    PortableModelArtifactStore,
    deserialize_dixon_coles_nb2_fit,
    serialize_dixon_coles_nb2_fit,
)
from football.forecasting.contracts import ModelFitSpecV1, PointInTimeScopeV1
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesContractError,
    DixonColesModel,
    DixonColesParameters,
    GoalMatch,
)
from football.forecasting.dixon_coles_nb2 import (
    DixonColesNB2GoalForecast,
    DixonColesNB2ResidualDispersionModel,
)

TEAM_A = UUID("10000000-0000-4000-8000-000000000001")
TEAM_B = UUID("10000000-0000-4000-8000-000000000002")
KICKOFF = datetime(2025, 1, 1, tzinfo=UTC)


def _parameters() -> DixonColesParameters:
    return DixonColesParameters(
        attack_strengths={TEAM_A: 0.2, TEAM_B: -0.1},
        defense_strengths={TEAM_A: -0.1, TEAM_B: 0.15},
        home_advantage=0.1,
        low_score_correlation=-0.08,
    )


def _config() -> DixonColesConfig:
    return DixonColesConfig(
        model_version="dixon-coles-v3",
        time_decay_half_life_days=None,
        effect_regularization=16.0,
    )


def _matches() -> tuple[GoalMatch, ...]:
    results = ((0, 0), (4, 1), (0, 3), (3, 3), (1, 0), (2, 2), (5, 0), (0, 2))
    return tuple(
        GoalMatch(
            match_id=UUID(int=index + 1),
            kickoff_at=KICKOFF + timedelta(days=index),
            home_team_id=TEAM_A if index % 2 == 0 else TEAM_B,
            away_team_id=TEAM_B if index % 2 == 0 else TEAM_A,
            home_goals=home_goals,
            away_goals=away_goals,
        )
        for index, (home_goals, away_goals) in enumerate(results)
    )


def test_alpha_zero_exactly_reproduces_dixon_coles_v3() -> None:
    base = DixonColesModel(_config())
    parameters = _parameters()
    expected = base.forecast(parameters, TEAM_A, TEAM_B)
    challenger = DixonColesNB2ResidualDispersionModel(_config())

    actual = challenger.forecast(parameters, 0.0, TEAM_A, TEAM_B)

    assert actual.lambda_home == expected.lambda_home
    assert actual.lambda_away == expected.lambda_away
    assert actual.score_matrix == expected.score_matrix
    assert actual.markets == expected.markets
    for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1), (3, 2)):
        assert actual.exact_score_probability(home_goals, away_goals) == pytest.approx(
            expected.exact_score_probability(home_goals, away_goals), abs=1e-12
        )


def test_challenger_rejects_a_non_frozen_base_configuration() -> None:
    with pytest.raises(DixonColesContractError, match="dixon-coles-v3"):
        DixonColesNB2ResidualDispersionModel(DixonColesConfig(model_version="dixon-coles-v2"))
    with pytest.raises(DixonColesContractError, match="regularization"):
        DixonColesNB2ResidualDispersionModel(
            DixonColesConfig(model_version="dixon-coles-v3", effect_regularization=0.0)
        )


def test_nb2_forecast_preserves_marginals_and_four_cell_rho_mass_transfer() -> None:
    forecast = DixonColesNB2ResidualDispersionModel(_config()).forecast(
        _parameters(), 0.4, TEAM_A, TEAM_B
    )
    assert isinstance(forecast, DixonColesNB2GoalForecast)

    assert sum(sum(row) for row in forecast.score_matrix.probabilities) == pytest.approx(1.0)
    assert all(
        probability >= 0.0 for row in forecast.score_matrix.probabilities for probability in row
    )
    assert (
        forecast.markets.home_win + forecast.markets.draw + forecast.markets.away_win
    ) == pytest.approx(1.0, abs=1e-12)
    assert forecast.markets.home_clean_sheet == pytest.approx(forecast.away_marginal(0))
    assert forecast.markets.away_clean_sheet == pytest.approx(forecast.home_marginal(0))
    assert forecast.markets.both_teams_to_score == pytest.approx(
        (1.0 - forecast.home_marginal(0)) * (1.0 - forecast.away_marginal(0))
        - forecast.low_score_mass_transfer
    )


def test_conditional_alpha_fit_is_deterministic_and_round_trips() -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())
    first = model.fit(_matches())
    second = model.fit(_matches())

    assert first == second
    assert 0.0 <= first.alpha < 100.0
    restored = deserialize_dixon_coles_nb2_fit(serialize_dixon_coles_nb2_fit(first))
    original_forecast = model.forecast(first.base_fit.parameters, first.alpha, TEAM_A, TEAM_B)
    restored_forecast = DixonColesNB2ResidualDispersionModel(restored.base_fit.config).forecast(
        restored.base_fit.parameters, restored.alpha, TEAM_A, TEAM_B
    )
    assert restored_forecast == original_forecast


def test_portable_state_round_trip_rejects_a_physical_mutation(tmp_path: Path) -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())
    fit = model.fit(_matches())
    scope = PointInTimeScopeV1(
        dataset_version_id=UUID(int=101),
        source_snapshot_id=UUID(int=102),
        feature_set_version="sprint2-features-v1",
        football_cutoff=KICKOFF,
        knowledge_cutoff=KICKOFF,
        knowledge_mode="bitemporal",
        quality_policy_sha256="a" * 64,
        target_set_sha256="b" * 64,
    )
    fit_spec = ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="dcv3-nb2-residual-dispersion-v1",
        config_sha256=fit.config_sha256,
        scope=scope,
        code_commit_sha="c" * 40,
        dependency_lock_sha256="d" * 64,
    )
    publication = PortableModelArtifactStore(tmp_path).publish(
        model_artifact_id=UUID(int=103),
        fit_spec=fit_spec,
        state=serialize_dixon_coles_nb2_fit(fit),
        created_at=KICKOFF,
    )

    loaded = PortableModelArtifactStore(tmp_path).load(
        publication, expected_feature_contract_version="sprint2-features-v1"
    )
    assert deserialize_dixon_coles_nb2_fit(loaded.state) == fit
    (tmp_path / publication.manifest.files[0].relative_path).write_bytes(b"{}")
    with pytest.raises(ArtifactPublicationError, match="state checksum mismatch"):
        PortableModelArtifactStore(tmp_path).load(
            publication, expected_feature_contract_version="sprint2-features-v1"
        )
