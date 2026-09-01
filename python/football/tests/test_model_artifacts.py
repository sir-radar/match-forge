from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from football.forecasting.artifacts import (
    ArtifactPublicationError,
    PortableModelArtifactStore,
    deserialize_corner_fit,
    deserialize_dixon_coles_fit,
    deserialize_elo_run,
    serialize_corner_fit,
    serialize_dixon_coles_fit,
    serialize_elo_run,
)
from football.forecasting.contracts import ModelFamily, ModelFitSpecV1, PointInTimeScopeV1
from football.forecasting.corner import (
    CornerFeatures,
    CornerFit,
    CornerFixture,
    CornerModelConfig,
    CornerModels,
    CornerParameters,
)
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesFit,
    DixonColesModel,
    DixonColesParameters,
)
from football.forecasting.elo import EloConfig, EloMatch, TeamEloModel
from football.storage.raw import ImmutableFileConflict

DATASET_ID = UUID("10000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-4000-8000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-4000-8000-000000000001")
TEAM_A = UUID("40000000-0000-4000-8000-000000000002")
TEAM_B = UUID("40000000-0000-4000-8000-000000000001")
COMPETITION_ID = UUID("50000000-0000-4000-8000-000000000001")
CUTOFF = datetime(2026, 8, 29, 16, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def test_portable_artifact_publication_is_canonical_and_idempotent(tmp_path: Path) -> None:
    store = PortableModelArtifactStore(tmp_path)
    fit_spec = _fit_spec("DIXON_COLES_GOALS")
    state = serialize_dixon_coles_fit(_dixon_coles_fit())

    first = store.publish(
        model_artifact_id=ARTIFACT_ID,
        fit_spec=fit_spec,
        state=state,
        created_at=CUTOFF,
    )
    retry = store.publish(
        model_artifact_id=ARTIFACT_ID,
        fit_spec=fit_spec,
        state=state,
        created_at=CUTOFF,
    )

    assert first.status == "published"
    assert retry.status == "verified_existing"
    assert retry.manifest == first.manifest
    assert retry.manifest_sha256 == first.manifest_sha256
    state_file = tmp_path / first.manifest.files[0].relative_path
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["contract"] == "PortableModelStateV1"
    assert payload["fit_spec_sha256"] == fit_spec.sha256
    assert payload["state"]["parameters"]["attack_strengths"] == {
        str(TEAM_B): -0.1,
        str(TEAM_A): 0.1,
    }
    loaded = store.load(first, expected_feature_contract_version="sprint2-features-v1")
    restored = deserialize_dixon_coles_fit(loaded.state)
    original = _dixon_coles_fit()
    original_forecast = DixonColesModel(original.config).forecast(
        original.parameters, TEAM_A, TEAM_B
    )
    restored_forecast = DixonColesModel(restored.config).forecast(
        restored.parameters, TEAM_A, TEAM_B
    )
    assert restored_forecast.lambda_home == pytest.approx(original_forecast.lambda_home)
    assert restored_forecast.lambda_away == pytest.approx(original_forecast.lambda_away)
    assert restored_forecast.markets == original_forecast.markets


def test_portable_artifact_recovers_created_at_for_orphan_manifest(tmp_path: Path) -> None:
    store = PortableModelArtifactStore(tmp_path)
    fit_spec = _fit_spec("DIXON_COLES_GOALS")
    store.publish(
        model_artifact_id=ARTIFACT_ID,
        fit_spec=fit_spec,
        state=serialize_dixon_coles_fit(_dixon_coles_fit()),
        created_at=CUTOFF,
    )

    assert store.existing_created_at(ARTIFACT_ID, fit_spec) == CUTOFF
    assert store.existing_created_at(UUID(int=999), fit_spec) is None


def test_portable_artifact_rejects_mutation_and_non_finite_state(tmp_path: Path) -> None:
    store = PortableModelArtifactStore(tmp_path)
    fit_spec = _fit_spec("DIXON_COLES_GOALS")
    state = serialize_dixon_coles_fit(_dixon_coles_fit())
    store.publish(
        model_artifact_id=ARTIFACT_ID,
        fit_spec=fit_spec,
        state=state,
        created_at=CUTOFF,
    )

    with pytest.raises(ImmutableFileConflict, match="immutable file conflict"):
        store.publish(
            model_artifact_id=ARTIFACT_ID,
            fit_spec=fit_spec,
            state={**state, "training_match_count": 99},
            created_at=CUTOFF,
        )


def test_artifact_loader_rejects_corrupt_missing_or_incompatible_files(tmp_path: Path) -> None:
    store = PortableModelArtifactStore(tmp_path)
    fit_spec = _fit_spec("DIXON_COLES_GOALS")
    publication = store.publish(
        model_artifact_id=ARTIFACT_ID,
        fit_spec=fit_spec,
        state=serialize_dixon_coles_fit(_dixon_coles_fit()),
        created_at=CUTOFF,
    )

    with pytest.raises(ArtifactPublicationError, match="feature contract"):
        store.load(publication, expected_feature_contract_version="other-features-v1")
    unsupported = replace(
        publication,
        manifest=replace(publication.manifest, schema_version="model-artifact-v2"),
    )
    with pytest.raises(ArtifactPublicationError, match="schema version"):
        store.load(unsupported, expected_feature_contract_version="sprint2-features-v1")
    state_path = tmp_path / publication.manifest.files[0].relative_path
    state_path.write_bytes(b"{}")
    with pytest.raises(ArtifactPublicationError, match="state checksum mismatch"):
        store.load(publication, expected_feature_contract_version="sprint2-features-v1")
    state_path.unlink()
    with pytest.raises(ArtifactPublicationError, match="state file is missing"):
        store.load(publication, expected_feature_contract_version="sprint2-features-v1")
    with pytest.raises(ArtifactPublicationError, match="non-finite"):
        PortableModelArtifactStore(tmp_path / "other").publish(
            model_artifact_id=ARTIFACT_ID,
            fit_spec=fit_spec,
            state={"coefficient": float("nan")},
            created_at=CUTOFF,
        )


def test_corner_serializer_preserves_distribution_and_sorted_effects() -> None:
    config = CornerModelConfig(model_version="corner-v1")
    original_fit = CornerFit(
        model_version="corner-v1",
        config=config,
        config_sha256=config.sha256,
        training_sha256=SHA_B,
        training_match_count=12,
        training_cutoff=CUTOFF,
        distribution="negative_binomial",
        parameters=CornerParameters(
            intercept=1.0,
            team_corner_strengths={TEAM_A: 0.1, TEAM_B: -0.1},
            opponent_concession_strengths={TEAM_A: -0.2, TEAM_B: 0.2},
            competition_effects={COMPETITION_ID: 0.0},
            feature_means=CornerFeatures(0.5, 10.0, 4.0, 5.0),
            feature_scales=CornerFeatures(0.1, 2.0, 1.0, 1.5),
            dispersion=4.0,
        ),
        negative_log_likelihood=20.0,
        aic=60.0,
        converged=True,
    )
    state = serialize_corner_fit(original_fit)

    parameters = state["parameters"]
    assert isinstance(parameters, dict)
    assert state["distribution"] == "negative_binomial"
    assert list(parameters["team_corner_strengths"]) == [str(TEAM_B), str(TEAM_A)]
    assert parameters["feature_scales"] == {
        "possession_tendency": 0.1,
        "shot_rate": 2.0,
        "cross_rate": 1.0,
        "recent_corners": 1.5,
    }
    restored = deserialize_corner_fit(state)
    fixture = CornerFixture(
        competition_id=COMPETITION_ID,
        home_team_id=TEAM_A,
        away_team_id=TEAM_B,
        home_features=CornerFeatures(0.5, 10.0, 4.0, 5.0),
        away_features=CornerFeatures(0.5, 10.0, 4.0, 5.0),
    )
    original_forecast = CornerModels(config).forecast(original_fit, fixture)
    restored_forecast = CornerModels(restored.config).forecast(restored, fixture)
    assert restored_forecast == original_forecast


def test_elo_serializer_round_trip_preserves_forecast_state() -> None:
    config = EloConfig(model_version="elo-v1", time_decay_half_life_days=None)
    original = TeamEloModel(config).rate(
        (
            EloMatch(
                match_id=UUID(int=1),
                competition_id=COMPETITION_ID,
                kickoff_at=CUTOFF,
                home_team_id=TEAM_A,
                away_team_id=TEAM_B,
                home_score=2,
                away_score=0,
            ),
        )
    )

    restored = deserialize_elo_run(serialize_elo_run(original))

    assert restored == original
    next_cutoff = CUTOFF.replace(day=30)
    assert TeamEloModel(restored.config).rating_before(
        restored, TEAM_A, next_cutoff
    ) == pytest.approx(TeamEloModel(config).rating_before(original, TEAM_A, next_cutoff))


def _fit_spec(model_family: ModelFamily) -> ModelFitSpecV1:
    return ModelFitSpecV1(
        model_family=model_family,
        algorithm_version="baseline-v1",
        config_sha256=SHA_A,
        scope=PointInTimeScopeV1(
            dataset_version_id=DATASET_ID,
            source_snapshot_id=SNAPSHOT_ID,
            feature_set_version="sprint2-features-v1",
            football_cutoff=CUTOFF,
            knowledge_cutoff=CUTOFF,
            knowledge_mode="bitemporal",
            quality_policy_sha256=SHA_B,
            target_set_sha256=SHA_C,
        ),
        code_commit_sha="d" * 40,
        dependency_lock_sha256=SHA_C,
        random_seed=7,
    )


def _dixon_coles_fit() -> DixonColesFit:
    config = DixonColesConfig(model_version="dixon-coles-v1")
    return DixonColesFit(
        model_version="dixon-coles-v1",
        config=config,
        config_sha256=config.sha256,
        training_sha256=SHA_B,
        training_match_count=12,
        training_cutoff=CUTOFF,
        parameters=DixonColesParameters(
            attack_strengths={TEAM_A: 0.1, TEAM_B: -0.1},
            defense_strengths={TEAM_A: -0.2, TEAM_B: 0.2},
            home_advantage=0.15,
            low_score_correlation=-0.05,
        ),
        negative_log_likelihood=10.0,
        converged=True,
    )
