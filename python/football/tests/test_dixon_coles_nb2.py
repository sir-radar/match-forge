from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import football.forecasting.dixon_coles_nb2 as nb2_module
import pytest
from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.artifacts import (
    ArtifactPublicationError,
    PortableModelArtifactStore,
    PublishedModelArtifactV1,
    deserialize_dixon_coles_nb2_fit,
    serialize_dixon_coles_nb2_fit,
)
from football.forecasting.contracts import ModelFitSpecV1, PointInTimeScopeV1
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesContractError,
    DixonColesFitError,
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


def _low_dispersion_matches() -> tuple[GoalMatch, ...]:
    return tuple(
        GoalMatch(
            match_id=UUID(int=200 + index),
            kickoff_at=KICKOFF + timedelta(days=index),
            home_team_id=TEAM_A if index % 2 == 0 else TEAM_B,
            away_team_id=TEAM_B if index % 2 == 0 else TEAM_A,
            home_goals=1,
            away_goals=1,
        )
        for index in range(24)
    )


def _overdispersed_matches() -> tuple[GoalMatch, ...]:
    results = ((0, 0), (6, 0), (0, 5), (5, 5), (1, 0), (0, 1))
    return tuple(
        GoalMatch(
            match_id=UUID(int=300 + index),
            kickoff_at=KICKOFF + timedelta(days=index),
            home_team_id=TEAM_A if index % 2 == 0 else TEAM_B,
            away_team_id=TEAM_B if index % 2 == 0 else TEAM_A,
            home_goals=results[index % len(results)][0],
            away_goals=results[index % len(results)][1],
        )
        for index in range(36)
    )


def _parameters_for_means(home_mean: float, away_mean: float, rho: float) -> DixonColesParameters:
    return DixonColesParameters(
        attack_strengths={TEAM_A: math.log(home_mean), TEAM_B: math.log(away_mean)},
        defense_strengths={TEAM_A: 0.0, TEAM_B: 0.0},
        home_advantage=0.0,
        low_score_correlation=rho,
    )


def _assert_valid_forecast(forecast: DixonColesNB2GoalForecast) -> None:
    assert sum(sum(row) for row in forecast.score_matrix.probabilities) == pytest.approx(1.0)
    assert all(
        math.isfinite(probability) and probability >= 0.0
        for row in forecast.score_matrix.probabilities
        for probability in row
    )
    assert (
        forecast.markets.home_win + forecast.markets.draw + forecast.markets.away_win
        == pytest.approx(1.0, abs=1e-12)
    )
    assert all(
        0.0 <= probability <= 1.0
        for probability in (
            forecast.markets.over_1_5,
            forecast.markets.over_2_5,
            forecast.markets.over_3_5,
            forecast.markets.both_teams_to_score,
            forecast.markets.home_clean_sheet,
            forecast.markets.away_clean_sheet,
        )
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


def test_synthetic_low_dispersion_fit_accepts_the_poisson_boundary_deterministically() -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())

    first = model.fit(_low_dispersion_matches())
    second = model.fit(_low_dispersion_matches())

    assert first == second
    assert first.alpha <= 1e-6
    assert first.conditional_joint_nll >= 0.0


def test_synthetic_overdispersion_identifies_a_positive_alpha_deterministically() -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())

    first = model.fit(_overdispersed_matches())
    second = model.fit(_overdispersed_matches())

    assert first == second
    assert 0.0 < first.alpha < 100.0
    forecast = model.forecast(first.base_fit.parameters, first.alpha, TEAM_A, TEAM_B)
    assert isinstance(forecast, DixonColesNB2GoalForecast)
    _assert_valid_forecast(forecast)


@pytest.mark.parametrize(
    ("home_mean", "away_mean"),
    ((0.05, 1.2), (1.2, 0.05), (20.0, 1.2), (1.2, 20.0), (20.0, 20.0)),
)
def test_extreme_legal_means_produce_valid_positive_alpha_forecasts(
    home_mean: float, away_mean: float
) -> None:
    forecast = DixonColesNB2ResidualDispersionModel(_config()).forecast(
        _parameters_for_means(home_mean, away_mean, rho=0.0), 0.4, TEAM_A, TEAM_B
    )

    assert isinstance(forecast, DixonColesNB2GoalForecast)
    _assert_valid_forecast(forecast)
    assert sum(forecast._home_probabilities) >= 1.0 - 1e-12
    assert sum(forecast._away_probabilities) >= 1.0 - 1e-12


@pytest.mark.parametrize("rho", (-0.05, 0.05))
@pytest.mark.parametrize("alpha", (0.0, 0.4))
def test_both_legal_rho_signs_preserve_marginals_and_mass(alpha: float, rho: float) -> None:
    parameters = _parameters_for_means(1.2, 0.9, rho)
    challenger = DixonColesNB2ResidualDispersionModel(_config())
    forecast = challenger.forecast(parameters, alpha, TEAM_A, TEAM_B)

    if alpha == 0.0:
        expected = DixonColesModel(_config()).forecast(parameters, TEAM_A, TEAM_B)
        assert forecast == expected
        return

    assert isinstance(forecast, DixonColesNB2GoalForecast)
    _assert_valid_forecast(forecast)
    delta = rho * forecast.home_marginal(1) * forecast.away_marginal(1)
    assert forecast.exact_score_probability(0, 0) == pytest.approx(
        forecast.home_marginal(0) * forecast.away_marginal(0) - delta
    )
    assert forecast.exact_score_probability(0, 1) == pytest.approx(
        forecast.home_marginal(0) * forecast.away_marginal(1) + delta
    )
    assert forecast.exact_score_probability(1, 0) == pytest.approx(
        forecast.home_marginal(1) * forecast.away_marginal(0) + delta
    )
    assert forecast.exact_score_probability(1, 1) == pytest.approx(
        forecast.home_marginal(1) * forecast.away_marginal(1) - delta
    )


def test_near_poisson_alpha_remains_finite_normalized_and_round_trips() -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())
    forecast = model.forecast(_parameters(), 1e-10, TEAM_A, TEAM_B)

    assert isinstance(forecast, DixonColesNB2GoalForecast)
    _assert_valid_forecast(forecast)
    fit = replace(model.fit(_matches()), alpha=1e-10)
    restored = deserialize_dixon_coles_nb2_fit(serialize_dixon_coles_nb2_fit(fit))
    assert restored.alpha == 1e-10


def test_input_order_does_not_change_fit_identity_or_predictions() -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())
    first = model.fit(_overdispersed_matches())
    second = model.fit(tuple(reversed(_overdispersed_matches())))

    assert first == second
    assert sha256_bytes(canonical_json_bytes(serialize_dixon_coles_nb2_fit(first))) == sha256_bytes(
        canonical_json_bytes(serialize_dixon_coles_nb2_fit(second))
    )
    assert model.forecast(first.base_fit.parameters, first.alpha, TEAM_A, TEAM_B) == model.forecast(
        second.base_fit.parameters, second.alpha, TEAM_A, TEAM_B
    )


def test_alpha_ceiling_and_optimizer_failure_fail_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())

    monkeypatch.setattr(
        nb2_module,
        "minimize_scalar",
        lambda *_args, **_kwargs: SimpleNamespace(
            success=True, fun=1.0, x=100.0, message="ceiling"
        ),
    )
    with pytest.raises(DixonColesFitError, match="ALPHA_NOT_IDENTIFIED_WITHIN_NUMERICAL_DOMAIN"):
        model.fit(_matches())

    monkeypatch.setattr(
        nb2_module,
        "minimize_scalar",
        lambda *_args, **_kwargs: SimpleNamespace(
            success=False, fun=math.inf, x=0.0, message="forced failure"
        ),
    )
    with pytest.raises(DixonColesFitError, match="optimizer did not converge"):
        model.fit(_matches())

    monkeypatch.setattr(
        nb2_module,
        "minimize_scalar",
        lambda *_args, **_kwargs: SimpleNamespace(success=True, fun=1.0, x=0.0, message="boundary"),
    )
    assert model.fit(_matches()).alpha == 0.0


def test_stationarity_invalid_probability_and_tail_exhaustion_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(DixonColesFitError, match="ALPHA_OPTIMIZER_STATIONARITY_FAILURE"):
        nb2_module._verify_local_minimum(lambda value: 0.0 if value != 0.5 else 1.0, 0.5, 1.0)
    with pytest.raises(DixonColesFitError, match="invalid probability"):
        nb2_module._joint_probability(0, 0, 1.0, 1.0, 0.4, 10.0)
    with pytest.raises(DixonColesFitError, match="invalid probability"):
        nb2_module._probability(math.nan)
    with pytest.raises(DixonColesFitError, match="invalid probability"):
        nb2_module._probability(math.inf)
    monkeypatch.setattr(nb2_module, "_HARD_SUPPORT_LIMIT", 1)
    with pytest.raises(DixonColesFitError, match="tail support exhausted"):
        nb2_module._support(10.0, 0.4)
    monkeypatch.setattr(nb2_module, "_joint_bucket_probability", lambda *_args: 0.2)
    with pytest.raises(DixonColesFitError, match="score matrix is not normalized"):
        nb2_module._score_matrix(1.0, 1.0, 0.4, 0.0, 2)


def test_serialized_state_preserves_required_training_and_fit_fields() -> None:
    fit = DixonColesNB2ResidualDispersionModel(_config()).fit(_overdispersed_matches())
    state = serialize_dixon_coles_nb2_fit(fit)

    assert state["training_match_count"] == fit.base_fit.training_match_count
    assert state["training_cutoff"] == fit.base_fit.training_cutoff.isoformat()
    assert state["conditional_joint_nll"] == fit.conditional_joint_nll
    assert state["base_dcv3_state_sha256"] == sha256_bytes(canonical_json_bytes(state["base_dcv3"]))


def test_logical_state_identity_changes_for_material_semantic_changes() -> None:
    fit = DixonColesNB2ResidualDispersionModel(_config()).fit(_overdispersed_matches())
    state = serialize_dixon_coles_nb2_fit(fit)
    logical_sha = sha256_bytes(canonical_json_bytes(state))

    assert logical_sha == sha256_bytes(canonical_json_bytes(serialize_dixon_coles_nb2_fit(fit)))
    assert logical_sha != sha256_bytes(
        canonical_json_bytes(serialize_dixon_coles_nb2_fit(replace(fit, alpha=0.0)))
    )
    changed_rho = replace(
        fit.base_fit,
        parameters=replace(fit.base_fit.parameters, low_score_correlation=0.01),
    )
    assert logical_sha != sha256_bytes(
        canonical_json_bytes(serialize_dixon_coles_nb2_fit(replace(fit, base_fit=changed_rho)))
    )
    assert logical_sha != sha256_bytes(
        canonical_json_bytes(serialize_dixon_coles_nb2_fit(replace(fit, training_sha256="e" * 64)))
    )
    different_algorithm = dict(state)
    different_algorithm["algorithm_version"] = "dcv3-nb2-residual-dispersion-v2"
    assert logical_sha != sha256_bytes(canonical_json_bytes(different_algorithm))


def test_logical_artifact_identity_does_not_depend_on_storage_location(tmp_path: Path) -> None:
    fit = DixonColesNB2ResidualDispersionModel(_config()).fit(_overdispersed_matches())
    fit_spec = _fit_spec(fit.config_sha256, 200)
    first = PortableModelArtifactStore(tmp_path / "first").publish(
        model_artifact_id=UUID(int=201),
        fit_spec=fit_spec,
        state=serialize_dixon_coles_nb2_fit(fit),
        created_at=KICKOFF,
    )
    second = PortableModelArtifactStore(tmp_path / "second").publish(
        model_artifact_id=UUID(int=202),
        fit_spec=fit_spec,
        state=serialize_dixon_coles_nb2_fit(fit),
        created_at=KICKOFF,
    )

    assert first.manifest.logical_model_state_sha256 == second.manifest.logical_model_state_sha256


def test_deserializer_rejects_base_state_and_checksum_corruption() -> None:
    fit = DixonColesNB2ResidualDispersionModel(_config()).fit(_overdispersed_matches())
    state = serialize_dixon_coles_nb2_fit(fit)
    broken_base = dict(state)
    base_state = state["base_dcv3"]
    assert isinstance(base_state, dict)
    broken_embedded_base = dict(base_state)
    broken_embedded_base["training_sha256"] = "f" * 64
    broken_base["base_dcv3"] = broken_embedded_base
    with pytest.raises(ArtifactPublicationError, match="base Dixon-Coles checksum mismatch"):
        deserialize_dixon_coles_nb2_fit(broken_base)
    broken_checksum = dict(state)
    broken_checksum["base_dcv3_state_sha256"] = "0" * 64
    with pytest.raises(ArtifactPublicationError, match="base Dixon-Coles checksum mismatch"):
        deserialize_dixon_coles_nb2_fit(broken_checksum)
    wrong_count = dict(state)
    wrong_count["training_match_count"] = 0
    with pytest.raises(ArtifactPublicationError, match="training count does not match"):
        deserialize_dixon_coles_nb2_fit(wrong_count)
    wrong_algorithm = dict(state)
    wrong_algorithm["algorithm_version"] = "dcv3-nb2-residual-dispersion-v2"
    with pytest.raises(ArtifactPublicationError, match="unsupported DCv3-NB2 algorithm version"):
        deserialize_dixon_coles_nb2_fit(wrong_algorithm)


def _fit_spec(fit_config_sha256: str, identifier: int) -> ModelFitSpecV1:
    scope = PointInTimeScopeV1(
        dataset_version_id=UUID(int=identifier),
        source_snapshot_id=UUID(int=identifier + 1),
        feature_set_version="sprint2-features-v1",
        football_cutoff=KICKOFF,
        knowledge_cutoff=KICKOFF,
        knowledge_mode="bitemporal",
        quality_policy_sha256="a" * 64,
        target_set_sha256="b" * 64,
    )
    return ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="dcv3-nb2-residual-dispersion-v1",
        config_sha256=fit_config_sha256,
        scope=scope,
        code_commit_sha="c" * 40,
        dependency_lock_sha256="d" * 64,
    )


def test_portable_artifact_rejects_physical_logical_and_identity_corruption(tmp_path: Path) -> None:
    fit = DixonColesNB2ResidualDispersionModel(_config()).fit(_overdispersed_matches())

    def publish(root: Path, identifier: int) -> PublishedModelArtifactV1:
        return PortableModelArtifactStore(root).publish(
            model_artifact_id=UUID(int=identifier),
            fit_spec=_fit_spec(fit.config_sha256, identifier),
            state=serialize_dixon_coles_nb2_fit(fit),
            created_at=KICKOFF,
        )

    physical_root = tmp_path / "physical"
    physical_root.mkdir()
    publication = publish(physical_root, 203)
    original_file = publication.manifest.files[0]
    bad_physical = replace(
        publication,
        manifest=replace(
            publication.manifest,
            files=(replace(original_file, physical_sha256="0" * 64),),
        ),
    )
    manifest_path = physical_root / publication.manifest_path
    manifest_path.write_bytes(bad_physical.manifest.to_bytes())
    bad_physical = replace(
        bad_physical, manifest_sha256=sha256_bytes(bad_physical.manifest.to_bytes())
    )
    with pytest.raises(ArtifactPublicationError, match="state checksum mismatch"):
        PortableModelArtifactStore(physical_root).load(
            bad_physical, expected_feature_contract_version="sprint2-features-v1"
        )

    logical_root = tmp_path / "logical"
    logical_root.mkdir()
    publication = publish(logical_root, 204)
    bad_logical = replace(
        publication,
        manifest=replace(publication.manifest, logical_model_state_sha256="0" * 64),
    )
    manifest_path = logical_root / publication.manifest_path
    manifest_path.write_bytes(bad_logical.manifest.to_bytes())
    bad_logical = replace(
        bad_logical, manifest_sha256=sha256_bytes(bad_logical.manifest.to_bytes())
    )
    with pytest.raises(ArtifactPublicationError, match="logical model state checksum mismatch"):
        PortableModelArtifactStore(logical_root).load(
            bad_logical, expected_feature_contract_version="sprint2-features-v1"
        )

    identity_root = tmp_path / "identity"
    identity_root.mkdir()
    publication = publish(identity_root, 205)
    original_file = publication.manifest.files[0]
    state_path = identity_root / original_file.relative_path
    envelope = json.loads(state_path.read_text(encoding="utf-8"))
    envelope["algorithm_version"] = "dcv3-nb2-residual-dispersion-v2"
    payload = canonical_json_bytes(envelope) + b"\n"
    state_path.write_bytes(payload)
    conflicting = replace(
        publication,
        manifest=replace(
            publication.manifest,
            logical_model_state_sha256=sha256_bytes(canonical_json_bytes(envelope)),
            files=(
                replace(
                    original_file,
                    size_bytes=len(payload),
                    physical_sha256=sha256_bytes(payload),
                ),
            ),
        ),
    )
    manifest_path = identity_root / publication.manifest_path
    manifest_path.write_bytes(conflicting.manifest.to_bytes())
    conflicting = replace(
        conflicting, manifest_sha256=sha256_bytes(conflicting.manifest.to_bytes())
    )
    with pytest.raises(ArtifactPublicationError, match="envelope conflicts with manifest"):
        PortableModelArtifactStore(identity_root).load(
            conflicting, expected_feature_contract_version="sprint2-features-v1"
        )


@pytest.mark.parametrize("alpha", (0.0, 0.4))
def test_reloaded_artifact_reproduces_all_prediction_outputs(tmp_path: Path, alpha: float) -> None:
    model = DixonColesNB2ResidualDispersionModel(_config())
    fit = replace(model.fit(_overdispersed_matches()), alpha=alpha)
    publication = PortableModelArtifactStore(tmp_path).publish(
        model_artifact_id=UUID(int=302 + int(alpha * 10)),
        fit_spec=_fit_spec(fit.config_sha256, 300 + int(alpha * 10)),
        state=serialize_dixon_coles_nb2_fit(fit),
        created_at=KICKOFF,
    )
    loaded = PortableModelArtifactStore(tmp_path).load(
        publication, expected_feature_contract_version="sprint2-features-v1"
    )
    reloaded = deserialize_dixon_coles_nb2_fit(loaded.state)
    original_forecast = model.forecast(fit.base_fit.parameters, fit.alpha, TEAM_A, TEAM_B)
    restored_forecast = DixonColesNB2ResidualDispersionModel(reloaded.base_fit.config).forecast(
        reloaded.base_fit.parameters, reloaded.alpha, TEAM_A, TEAM_B
    )

    assert restored_forecast == original_forecast
