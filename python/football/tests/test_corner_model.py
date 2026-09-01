from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from football.forecasting.corner import (
    CornerContractError,
    CornerFeatures,
    CornerFit,
    CornerFixture,
    CornerMatch,
    CornerModelConfig,
    CornerModels,
    CornerParameters,
)

TEAM_A = UUID("10000000-0000-4000-8000-000000000001")
TEAM_B = UUID("10000000-0000-4000-8000-000000000002")
COMPETITION = UUID("20000000-0000-4000-8000-000000000001")
KICKOFF = datetime(2026, 1, 1, 15, 0, tzinfo=UTC)
FEATURES = CornerFeatures(
    possession_tendency=0.5,
    shot_rate=12.0,
    cross_rate=16.0,
    recent_corners=5.0,
)


def test_fit_compares_poisson_and_negative_binomial_on_overdispersed_counts() -> None:
    model = CornerModels(
        CornerModelConfig(
            model_version="corners-v1",
            time_decay_half_life_days=None,
            max_iterations=500,
        )
    )

    comparison = model.fit(_overdispersed_matches())

    assert comparison.observed_variance > comparison.observed_mean
    assert comparison.overdispersed
    assert comparison.negative_binomial.parameters.dispersion is not None
    assert comparison.negative_binomial.parameters.dispersion > 0.0
    assert comparison.negative_binomial.aic < comparison.poisson.aic
    assert comparison.preferred_distribution == "negative_binomial"
    assert comparison.poisson.training_sha256 == comparison.negative_binomial.training_sha256
    assert comparison.poisson.parameters.feature_scales.shot_rate == 1.0


def test_forecast_exposes_coherent_poisson_and_negative_binomial_distributions() -> None:
    model = CornerModels(
        CornerModelConfig(
            model_version="corners-forecast-v1",
            time_decay_half_life_days=None,
            max_iterations=500,
        )
    )
    comparison = model.fit(_overdispersed_matches())
    fixture = CornerFixture(
        competition_id=COMPETITION,
        home_team_id=TEAM_A,
        away_team_id=TEAM_B,
        home_features=FEATURES,
        away_features=FEATURES,
    )

    poisson = model.forecast(comparison.poisson, fixture)
    negative_binomial = model.forecast(comparison.negative_binomial, fixture)

    assert poisson.lambda_home > 0.0
    assert poisson.lambda_away > 0.0
    assert poisson.home_variance == pytest.approx(poisson.lambda_home)
    assert negative_binomial.home_variance > negative_binomial.lambda_home
    assert sum(poisson.home_probability(value) for value in range(40)) == pytest.approx(
        1.0, abs=1e-8
    )
    negative_binomial_mass = sum(negative_binomial.home_probability(value) for value in range(80))
    assert 0.999 < negative_binomial_mass <= 1.0


def test_time_decay_and_configuration_identity_are_deterministic() -> None:
    config = CornerModelConfig(model_version="corners-config-v1", time_decay_half_life_days=50.0)

    assert (
        config.sha256
        == CornerModelConfig(
            model_version="corners-config-v1", time_decay_half_life_days=50.0
        ).sha256
    )
    assert config.match_weight(0.0) == 1.0
    assert config.match_weight(50.0) == pytest.approx(0.5)
    assert config.match_weight(100.0) == pytest.approx(0.25)


def test_effect_regularization_is_versioned_and_shrinks_team_effects() -> None:
    unregularized_config = CornerModelConfig(
        model_version="corners-shrinkage-v2",
        time_decay_half_life_days=None,
        effect_regularization=0.0,
    )
    regularized_config = CornerModelConfig(
        model_version="corners-shrinkage-v2",
        time_decay_half_life_days=None,
        effect_regularization=4.0,
    )

    unregularized = CornerModels(unregularized_config).fit(_asymmetric_matches()).poisson
    regularized = CornerModels(regularized_config).fit(_asymmetric_matches()).poisson

    assert unregularized_config.sha256 != regularized_config.sha256
    assert regularized.config.effect_regularization == 4.0
    assert _effect_energy(regularized) < _effect_energy(unregularized)


def test_forecast_uses_team_opponent_home_competition_and_pre_match_features() -> None:
    config = CornerModelConfig(model_version="corners-formula-v1")
    parameters = CornerParameters(
        intercept=1.0,
        team_corner_strengths={TEAM_A: 0.2, TEAM_B: -0.2},
        opponent_concession_strengths={TEAM_A: -0.1, TEAM_B: 0.1},
        competition_effects={COMPETITION: 0.05},
        home_advantage=0.15,
        shot_coefficient=0.2,
        feature_means=CornerFeatures(0.5, 10.0, 15.0, 5.0),
        feature_scales=CornerFeatures(0.1, 2.0, 5.0, 1.0),
    )
    fit = CornerFit(
        model_version=config.model_version,
        config=config,
        config_sha256=config.sha256,
        training_sha256="a" * 64,
        training_match_count=10,
        training_cutoff=KICKOFF,
        distribution="poisson",
        parameters=parameters,
        negative_log_likelihood=10.0,
        aic=30.0,
        converged=True,
    )
    fixture = CornerFixture(
        competition_id=COMPETITION,
        home_team_id=TEAM_A,
        away_team_id=TEAM_B,
        home_features=CornerFeatures(0.5, 12.0, 15.0, 5.0),
        away_features=CornerFeatures(0.5, 10.0, 15.0, 5.0),
    )

    forecast = CornerModels(config).forecast(fit, fixture)

    assert forecast.lambda_home == pytest.approx(math.exp(1.0 + 0.2 + 0.1 + 0.05 + 0.15 + 0.2))
    assert forecast.lambda_away == pytest.approx(math.exp(1.0 - 0.2 - 0.1 + 0.05))


def test_rejects_leaky_or_invalid_feature_and_match_inputs() -> None:
    with pytest.raises(CornerContractError, match="possession"):
        CornerFeatures(
            possession_tendency=1.1,
            shot_rate=12.0,
            cross_rate=16.0,
            recent_corners=5.0,
        )
    with pytest.raises(CornerContractError, match="timezone"):
        CornerMatch(
            match_id=UUID(int=1),
            competition_id=COMPETITION,
            kickoff_at=datetime(2026, 1, 1),
            home_team_id=TEAM_A,
            away_team_id=TEAM_B,
            home_corners=5,
            away_corners=4,
            home_features=FEATURES,
            away_features=FEATURES,
        )
    with pytest.raises(CornerContractError, match="non-negative integer"):
        _match(1, -1, 4)
    with pytest.raises(CornerContractError, match="at least one match"):
        CornerModels(CornerModelConfig(model_version="corners-empty-v1")).fit(())
    with pytest.raises(CornerContractError, match="effect regularization"):
        CornerModelConfig(model_version="corners-invalid-v2", effect_regularization=-1.0)


def _overdispersed_matches() -> tuple[CornerMatch, ...]:
    corner_pairs = (
        (0, 0),
        (1, 0),
        (12, 10),
        (0, 1),
        (0, 0),
        (10, 12),
        (1, 1),
        (0, 0),
        (14, 11),
        (0, 1),
        (0, 0),
        (11, 14),
        (1, 0),
        (0, 0),
        (13, 9),
        (0, 1),
    )
    return tuple(
        _match(index, home_corners, away_corners)
        for index, (home_corners, away_corners) in enumerate(corner_pairs, start=1)
    )


def _asymmetric_matches() -> tuple[CornerMatch, ...]:
    return tuple(
        CornerMatch(
            match_id=UUID(int=index),
            competition_id=COMPETITION,
            kickoff_at=KICKOFF + timedelta(days=index),
            home_team_id=TEAM_A if index % 2 else TEAM_B,
            away_team_id=TEAM_B if index % 2 else TEAM_A,
            home_corners=9 if index % 2 else 2,
            away_corners=2 if index % 2 else 8,
            home_features=FEATURES,
            away_features=FEATURES,
        )
        for index in range(1, 25)
    )


def _effect_energy(fit: CornerFit) -> float:
    return sum(value * value for value in fit.parameters.team_corner_strengths.values()) + sum(
        value * value for value in fit.parameters.opponent_concession_strengths.values()
    )


def _match(index: int, home_corners: int, away_corners: int) -> CornerMatch:
    home_team_id, away_team_id = (TEAM_A, TEAM_B) if index % 2 else (TEAM_B, TEAM_A)
    return CornerMatch(
        match_id=UUID(int=index),
        competition_id=COMPETITION,
        kickoff_at=KICKOFF + timedelta(days=index),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_corners=home_corners,
        away_corners=away_corners,
        home_features=FEATURES,
        away_features=FEATURES,
    )
