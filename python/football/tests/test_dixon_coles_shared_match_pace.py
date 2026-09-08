from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import football.forecasting.dixon_coles_shared_match_pace as shared_pace_module
import pytest
from football.forecasting.artifacts import (
    ArtifactPublicationError,
    PortableModelArtifactStore,
    deserialize_dixon_coles_shared_match_pace_fit,
    serialize_dixon_coles_shared_match_pace_fit,
)
from football.forecasting.contracts import ModelFitSpecV1, PointInTimeScopeV1
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesFitError,
    DixonColesModel,
    DixonColesParameters,
    GoalMatch,
)
from football.forecasting.dixon_coles_shared_match_pace import (
    DixonColesSharedMatchPaceFit,
    DixonColesSharedMatchPaceGoalForecast,
    DixonColesSharedMatchPaceModel,
)

TEAM_A = UUID("10000000-0000-4000-8000-000000000001")
TEAM_B = UUID("10000000-0000-4000-8000-000000000002")
KICKOFF = datetime(2025, 1, 1, tzinfo=UTC)


def _config() -> DixonColesConfig:
    return DixonColesConfig(
        model_version="dixon-coles-v3",
        time_decay_half_life_days=None,
        effect_regularization=16.0,
    )


def _parameters(rho: float = -0.05) -> DixonColesParameters:
    return DixonColesParameters(
        attack_strengths={TEAM_A: math.log(1.4), TEAM_B: math.log(0.9)},
        defense_strengths={TEAM_A: 0.0, TEAM_B: 0.0},
        home_advantage=0.0,
        low_score_correlation=rho,
    )


def _matches() -> tuple[GoalMatch, ...]:
    results = ((0, 0), (5, 1), (0, 4), (4, 4), (1, 0), (0, 1))
    return tuple(
        GoalMatch(
            match_id=UUID(int=index + 1),
            kickoff_at=KICKOFF + timedelta(days=index),
            home_team_id=TEAM_A if index % 2 == 0 else TEAM_B,
            away_team_id=TEAM_B if index % 2 == 0 else TEAM_A,
            home_goals=home_goals,
            away_goals=away_goals,
        )
        for index, (home_goals, away_goals) in enumerate(results * 6)
    )


def _interior_matches() -> tuple[GoalMatch, ...]:
    results = ((0, 0), (4, 0), (0, 3), (3, 3), (1, 0), (0, 1))
    return tuple(
        GoalMatch(
            match_id=UUID(int=index + 501),
            kickoff_at=KICKOFF + timedelta(days=index),
            home_team_id=TEAM_A if index % 2 == 0 else TEAM_B,
            away_team_id=TEAM_B if index % 2 == 0 else TEAM_A,
            home_goals=home_goals,
            away_goals=away_goals,
        )
        for index, (home_goals, away_goals) in enumerate(results * 4)
    )


def test_kappa_zero_is_exact_frozen_dcv3() -> None:
    parameters = _parameters()
    expected = DixonColesModel(_config()).forecast(parameters, TEAM_A, TEAM_B)
    actual = DixonColesSharedMatchPaceModel(_config()).forecast(parameters, 0.0, TEAM_A, TEAM_B)

    assert actual == expected


def test_shared_pace_preserves_means_normalization_and_rho_marginals() -> None:
    model = DixonColesSharedMatchPaceModel(_config())
    forecast = model.forecast(_parameters(), 0.4, TEAM_A, TEAM_B)
    assert isinstance(forecast, DixonColesSharedMatchPaceGoalForecast)

    assert sum(sum(row) for row in forecast.score_matrix.probabilities) == pytest.approx(1.0)
    assert forecast.home_mean() == pytest.approx(forecast.lambda_home, abs=1e-12)
    assert forecast.away_mean() == pytest.approx(forecast.lambda_away, abs=1e-12)
    uncorrected = model.forecast(_parameters(0.0), 0.4, TEAM_A, TEAM_B)
    assert forecast.exact_score_probability(0, 0) + forecast.exact_score_probability(
        0, 1
    ) == pytest.approx(
        uncorrected.exact_score_probability(0, 0) + uncorrected.exact_score_probability(0, 1)
    )
    assert forecast.exact_score_probability(0, 0) + forecast.exact_score_probability(
        1, 0
    ) == pytest.approx(
        uncorrected.exact_score_probability(0, 0) + uncorrected.exact_score_probability(1, 0)
    )


def test_rho_is_post_mixture_four_cell_zero_sum_transfer() -> None:
    model = DixonColesSharedMatchPaceModel(_config())
    uncorrected = model.forecast(_parameters(0.0), 0.4, TEAM_A, TEAM_B)
    corrected = model.forecast(_parameters(-0.05), 0.4, TEAM_A, TEAM_B)
    delta = -0.05 * uncorrected.exact_score_probability(1, 1)

    assert corrected.exact_score_probability(0, 0) == pytest.approx(
        uncorrected.exact_score_probability(0, 0) - delta
    )
    assert corrected.exact_score_probability(0, 1) == pytest.approx(
        uncorrected.exact_score_probability(0, 1) + delta
    )
    assert corrected.exact_score_probability(1, 0) == pytest.approx(
        uncorrected.exact_score_probability(1, 0) + delta
    )
    assert corrected.exact_score_probability(1, 1) == pytest.approx(
        uncorrected.exact_score_probability(1, 1) - delta
    )


def test_exact_mixture_means_and_weighted_joint_nll_are_preserved() -> None:
    model = DixonColesSharedMatchPaceModel(_config())
    forecast = model.forecast(_parameters(0.0), 0.4, TEAM_A, TEAM_B)
    assert isinstance(forecast, DixonColesSharedMatchPaceGoalForecast)
    assert sum(goals * forecast.home_marginal(goals) for goals in range(100)) == pytest.approx(
        forecast.lambda_home, abs=1e-12
    )
    assert sum(goals * forecast.away_marginal(goals) for goals in range(100)) == pytest.approx(
        forecast.lambda_away, abs=1e-12
    )

    matches = _matches()[:2]
    means = tuple(
        shared_pace_module._means(_parameters(0.0), match.home_team_id, match.away_team_id)
        for match in matches
    )
    objective = shared_pace_module._objective(matches, (1.0, 3.0), means, 0.0)
    expected = (
        -sum(
            weight
            * math.log(
                shared_pace_module._joint_probability(
                    match.home_goals, match.away_goals, home_mean, away_mean, 0.4, 0.0
                )
            )
            for match, weight, (home_mean, away_mean) in zip(
                matches, (1.0, 3.0), means, strict=True
            )
        )
        / 4.0
    )
    assert objective(0.4) == pytest.approx(expected)


def test_fit_uses_frozen_bounded_optimizer_and_rejects_nonidentified_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def optimizer(objective: object, **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(success=True, fun=0.0, x=0.0, nit=1, message="boundary")

    monkeypatch.setattr(shared_pace_module, "minimize_scalar", optimizer)

    with pytest.raises(DixonColesFitError, match="LOWER_BOUNDARY_DCV3_LIMIT"):
        shared_pace_module._fit_kappa(lambda kappa: kappa)

    assert captured == {
        "method": "bounded",
        "bounds": (0.0, 1.0),
        "options": {"xatol": 1e-10, "maxiter": 500},
    }


def test_synthetic_interior_fit_is_deterministic_and_input_order_independent() -> None:
    model = DixonColesSharedMatchPaceModel(_config())
    matches = _interior_matches()

    first = model.fit(matches)
    second = model.fit(matches)
    reversed_fit = model.fit(tuple(reversed(matches)))

    assert 0.0 < first.kappa < 1.0
    assert first == second == reversed_fit
    assert serialize_dixon_coles_shared_match_pace_fit(
        first
    ) == serialize_dixon_coles_shared_match_pace_fit(second)


def test_stationarity_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shared_pace_module,
        "minimize_scalar",
        lambda *_args, **_kwargs: SimpleNamespace(
            success=True, fun=0.01, x=0.4, nit=1, message="forced"
        ),
    )

    with pytest.raises(DixonColesFitError, match="STATIONARITY_CHECK_FAILED"):
        shared_pace_module._fit_kappa(lambda kappa: (kappa - 0.5) ** 2)


def test_upper_boundary_optimizer_and_ambiguous_profile_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shared_pace_module,
        "minimize_scalar",
        lambda *_args, **_kwargs: SimpleNamespace(
            success=True, fun=0.0, x=1.0, nit=1, message="upper"
        ),
    )
    with pytest.raises(DixonColesFitError, match="UPPER_BOUNDARY_OPTIMUM"):
        shared_pace_module._fit_kappa(lambda kappa: 1.0 - kappa)

    monkeypatch.undo()
    with pytest.raises(DixonColesFitError, match="AMBIGUOUS_OPTIMUM"):
        shared_pace_module._fit_kappa(lambda kappa: min((kappa - 0.25) ** 2, (kappa - 0.75) ** 2))


def test_invalid_probability_optimizer_failure_and_support_tail_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(DixonColesFitError, match="INVALID_PROBABILITY"):
        shared_pace_module._joint_probability(0, 0, 1.0, 1.0, 0.4, 10.0)

    monkeypatch.setattr(
        shared_pace_module,
        "minimize_scalar",
        lambda *_args, **_kwargs: SimpleNamespace(
            success=False, fun=math.inf, x=0.5, nit=501, message="forced"
        ),
    )
    with pytest.raises(DixonColesFitError, match="OPTIMIZER_FAILURE"):
        shared_pace_module._fit_kappa(lambda kappa: (kappa - 0.5) ** 2)

    monkeypatch.setattr(shared_pace_module, "_HARD_SUPPORT_LIMIT", 1)
    with pytest.raises(DixonColesFitError, match="SUPPORT_TAIL_FAILURE"):
        DixonColesSharedMatchPaceModel(_config()).forecast(_parameters(), 0.4, TEAM_A, TEAM_B)


def test_forecast_products_are_one_normalized_joint_distribution() -> None:
    forecast = DixonColesSharedMatchPaceModel(_config()).forecast(
        _parameters(0.05), 0.4, TEAM_A, TEAM_B
    )
    assert isinstance(forecast, DixonColesSharedMatchPaceGoalForecast)
    assert (
        forecast.markets.home_win + forecast.markets.draw + forecast.markets.away_win
        == pytest.approx(1.0, abs=1e-12)
    )
    assert forecast.markets.home_clean_sheet == pytest.approx(forecast.away_marginal(0))
    assert forecast.markets.away_clean_sheet == pytest.approx(forecast.home_marginal(0))
    assert forecast.markets.both_teams_to_score == pytest.approx(
        1.0
        - forecast.home_marginal(0)
        - forecast.away_marginal(0)
        + forecast.exact_score_probability(0, 0)
    )


def test_portable_state_round_trip_rejects_invalid_kappa_and_reproduces_forecasts(
    tmp_path: Path,
) -> None:
    fit = _artifact_fit()
    state = serialize_dixon_coles_shared_match_pace_fit(fit)
    assert deserialize_dixon_coles_shared_match_pace_fit(state) == fit

    store = PortableModelArtifactStore(tmp_path)
    publication = store.publish(
        model_artifact_id=UUID(int=101),
        fit_spec=_fit_spec(fit.config_sha256),
        state=state,
        created_at=KICKOFF,
    )
    loaded = store.load(publication, expected_feature_contract_version="sprint2-features-v1")
    restored = deserialize_dixon_coles_shared_match_pace_fit(loaded.state)
    original_forecast = DixonColesSharedMatchPaceModel(fit.base_fit.config).forecast(
        fit.base_fit.parameters, fit.kappa, TEAM_A, TEAM_B
    )
    restored_forecast = DixonColesSharedMatchPaceModel(restored.base_fit.config).forecast(
        restored.base_fit.parameters, restored.kappa, TEAM_A, TEAM_B
    )
    assert restored_forecast == original_forecast
    state_path = tmp_path / publication.manifest.files[0].relative_path
    state_path.write_bytes(b"{}")
    with pytest.raises(ArtifactPublicationError, match="state checksum mismatch"):
        store.load(publication, expected_feature_contract_version="sprint2-features-v1")

    broken = dict(state)
    pace = state["pace"]
    assert isinstance(pace, dict)
    broken["pace"] = {**pace, "kappa": 0.0}
    with pytest.raises(ArtifactPublicationError, match="accepted fitted domain"):
        deserialize_dixon_coles_shared_match_pace_fit(broken)
    with pytest.raises(ArtifactPublicationError, match="config checksum"):
        deserialize_dixon_coles_shared_match_pace_fit(replace_state(state, config_sha256="0" * 64))


def _artifact_fit() -> DixonColesSharedMatchPaceFit:
    model = DixonColesSharedMatchPaceModel(_config())
    return DixonColesSharedMatchPaceFit(
        base_fit=DixonColesModel(_config()).fit(_matches()),
        kappa=0.4,
        config_sha256=model.config_sha256,
        training_sha256="a" * 64,
        weighted_joint_nll=1.0,
        converged=True,
    )


def _fit_spec(config_sha256: str) -> ModelFitSpecV1:
    return ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="dcv3-shared-match-pace-mixture-v1",
        config_sha256=config_sha256,
        scope=PointInTimeScopeV1(
            dataset_version_id=UUID(int=201),
            source_snapshot_id=UUID(int=202),
            feature_set_version="sprint2-features-v1",
            football_cutoff=KICKOFF,
            knowledge_cutoff=KICKOFF,
            knowledge_mode="bitemporal",
            quality_policy_sha256="b" * 64,
            target_set_sha256="c" * 64,
        ),
        code_commit_sha="d" * 40,
        dependency_lock_sha256="e" * 64,
    )


def replace_state(state: dict[str, object], **changes: object) -> dict[str, object]:
    return {**state, **changes}
