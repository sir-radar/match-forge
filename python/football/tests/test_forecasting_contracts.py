from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.forecasting.contracts import (
    ArtifactCompatibilityV1,
    ArtifactFileV1,
    BaselineForecastV1,
    ForecastContractError,
    MatchResultProbabilitiesV1,
    ModelArtifactManifestV1,
    ModelFitSpecV1,
    PointInTimeScopeV1,
    forecast_payload_sha256,
)
from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_ID = UUID("10000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-4000-8000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-4000-8000-000000000001")
CALIBRATOR_ID = UUID("30000000-0000-4000-8000-000000000002")
FORECAST_ID = UUID("40000000-0000-4000-8000-000000000001")
MATCH_ID = UUID("50000000-0000-4000-8000-000000000001")
CUTOFF = datetime(2026, 1, 1, 15, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
GIT_SHA = "d" * 40


def test_fit_spec_identity_is_canonical_and_binds_point_in_time_lineage() -> None:
    scope = _scope()
    first = ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="dixon-coles-v1",
        config_sha256=SHA_A,
        scope=scope,
        code_commit_sha=GIT_SHA,
        dependency_lock_sha256=SHA_B,
        random_seed=7,
    )
    same_in_another_timezone = ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="dixon-coles-v1",
        config_sha256=SHA_A,
        scope=PointInTimeScopeV1(
            dataset_version_id=DATASET_ID,
            source_snapshot_id=SNAPSHOT_ID,
            feature_set_version="sprint2-features-v1",
            football_cutoff=CUTOFF.astimezone(UTC) + timedelta(hours=0),
            knowledge_cutoff=CUTOFF.astimezone(UTC) + timedelta(hours=0),
            knowledge_mode="bitemporal",
            quality_policy_sha256=SHA_B,
            target_set_sha256=SHA_C,
        ),
        code_commit_sha=GIT_SHA,
        dependency_lock_sha256=SHA_B,
        random_seed=7,
    )

    assert first.sha256 == same_in_another_timezone.sha256
    assert first.to_dict()["scope"] == scope.to_dict()
    assert first.to_dict()["model_family"] == "DIXON_COLES_GOALS"


def test_point_in_time_scope_rejects_unversioned_or_naive_inputs() -> None:
    with pytest.raises(ForecastContractError, match="timezone"):
        PointInTimeScopeV1(
            dataset_version_id=DATASET_ID,
            source_snapshot_id=SNAPSHOT_ID,
            feature_set_version="sprint2-features-v1",
            football_cutoff=datetime(2026, 1, 1),
            knowledge_cutoff=CUTOFF,
            knowledge_mode="bitemporal",
            quality_policy_sha256=SHA_A,
            target_set_sha256=SHA_B,
        )
    with pytest.raises(ForecastContractError, match="feature_set_version"):
        PointInTimeScopeV1(
            dataset_version_id=DATASET_ID,
            source_snapshot_id=SNAPSHOT_ID,
            feature_set_version="Invalid Version",
            football_cutoff=CUTOFF,
            knowledge_cutoff=CUTOFF,
            knowledge_mode="bitemporal",
            quality_policy_sha256=SHA_A,
            target_set_sha256=SHA_B,
        )


def test_artifact_manifest_is_portable_canonical_and_schema_valid() -> None:
    manifest = _manifest()

    assert manifest.to_bytes().endswith(b"\n")
    assert len(manifest.sha256) == 64
    _validate_schema("model-artifact-manifest-v1.schema.json", manifest.to_dict())

    duplicate = ArtifactFileV1(
        relative_path="models/dixon-coles/parameters.json",
        media_type="application/json",
        size_bytes=12,
        physical_sha256=SHA_B,
    )
    with pytest.raises(ForecastContractError, match="paths must be unique"):
        ModelArtifactManifestV1(
            model_artifact_id=ARTIFACT_ID,
            model_family="DIXON_COLES_GOALS",
            fit_spec_sha256=SHA_A,
            schema_version="model-artifact-v1",
            algorithm_version="dixon-coles-v1",
            serializer_version="canonical-json-v1",
            compatibility=_compatibility(),
            logical_model_state_sha256=SHA_C,
            created_at=CUTOFF,
            files=(duplicate, duplicate),
        )


def test_match_result_probabilities_are_coherent() -> None:
    probabilities = MatchResultProbabilitiesV1(home=0.45, draw=0.30, away=0.25)

    assert probabilities.to_dict() == {
        "contract": "MatchResultProbabilitiesV1",
        "home": 0.45,
        "draw": 0.30,
        "away": 0.25,
    }
    with pytest.raises(ForecastContractError, match="sum to one"):
        MatchResultProbabilitiesV1(home=0.45, draw=0.30, away=0.20)
    with pytest.raises(ForecastContractError, match=r"finite in \[0, 1\]"):
        MatchResultProbabilitiesV1(home=float("nan"), draw=0.5, away=0.5)


def test_raw_forecast_identity_is_stable_and_contains_no_outcome() -> None:
    probabilities = MatchResultProbabilitiesV1(home=0.45, draw=0.30, away=0.25)
    forecast = BaselineForecastV1(
        forecast_id=FORECAST_ID,
        match_id=MATCH_ID,
        prediction_cutoff=CUTOFF,
        scope=_scope(),
        probability_variant="MODEL_RAW",
        model_artifact_ids=(ARTIFACT_ID,),
        forecast_context_sha256=SHA_C,
        payload_sha256=forecast_payload_sha256(probabilities),
        match_result=probabilities,
    )
    same_semantics = BaselineForecastV1(
        forecast_id=UUID("40000000-0000-4000-8000-000000000099"),
        match_id=MATCH_ID,
        prediction_cutoff=CUTOFF,
        scope=_scope(),
        probability_variant="MODEL_RAW",
        model_artifact_ids=(ARTIFACT_ID,),
        forecast_context_sha256=SHA_C,
        payload_sha256=forecast_payload_sha256(probabilities),
        match_result=probabilities,
    )

    assert forecast.semantic_sha256 == same_semantics.semantic_sha256
    assert "outcome" not in forecast.to_dict()
    assert "home_score" not in forecast.to_dict()
    _validate_schema("baseline-forecast-v1.schema.json", forecast.to_dict())


def test_calibrated_forecasts_require_a_distinct_calibrator_artifact() -> None:
    with pytest.raises(ForecastContractError, match="requires a calibrator"):
        BaselineForecastV1(
            forecast_id=FORECAST_ID,
            match_id=MATCH_ID,
            prediction_cutoff=CUTOFF,
            scope=_scope(),
            probability_variant="MODEL_CALIBRATED",
            model_artifact_ids=(ARTIFACT_ID,),
            forecast_context_sha256=SHA_C,
            payload_sha256=forecast_payload_sha256(None),
        )

    calibrated = BaselineForecastV1(
        forecast_id=FORECAST_ID,
        match_id=MATCH_ID,
        prediction_cutoff=CUTOFF,
        scope=_scope(),
        probability_variant="MODEL_CALIBRATED",
        model_artifact_ids=(ARTIFACT_ID,),
        forecast_context_sha256=SHA_C,
        calibrator_artifact_id=CALIBRATOR_ID,
        payload_sha256=forecast_payload_sha256(None),
    )

    assert calibrated.to_dict()["calibrator_artifact_id"] == str(CALIBRATOR_ID)


def test_sprint2_artifact_migration_is_additive_and_forward_only() -> None:
    migration = (
        PROJECT_ROOT / "infrastructure/migrations/202608292100_sprint2_artifacts.sql"
    ).read_text(encoding="utf-8")

    assert "-- +goose Up" in migration
    assert "-- +goose Down" not in migration
    for table in (
        "model_fit_runs",
        "model_artifacts",
        "model_artifact_files",
        "model_artifact_inputs",
        "baseline_forecasts",
        "forecast_artifacts",
        "sprint2_evaluation_runs",
        "model_promotion_events",
    ):
        assert f"CREATE TABLE football.{table}" in migration
    assert "DROP TABLE" not in migration
    assert "ALTER TABLE football.team_elo_history" not in migration

    role_migration = (
        PROJECT_ROOT / "infrastructure/migrations/202608300100_sprint2_forecast_artifact_roles.sql"
    ).read_text(encoding="utf-8")
    assert "-- +goose Up" in role_migration
    assert "-- +goose Down" not in role_migration
    assert "DROP CONSTRAINT forecast_artifacts_forecast_id_artifact_role_key" in role_migration
    assert "WHERE artifact_role = 'CALIBRATOR'" in role_migration
    assert "DROP TABLE" not in role_migration

    identity_migration = (
        PROJECT_ROOT / "infrastructure/migrations/202608300200_sprint2_identity_hardening.sql"
    ).read_text(encoding="utf-8")
    assert "knowledge_mode" in identity_migration
    assert "forecast_context_sha256" in identity_migration
    assert "probability_contract_version" in identity_migration
    assert "output_version" in identity_migration
    assert "-- +goose Down" not in identity_migration
    assert "DROP TABLE" not in identity_migration


def _scope() -> PointInTimeScopeV1:
    return PointInTimeScopeV1(
        dataset_version_id=DATASET_ID,
        source_snapshot_id=SNAPSHOT_ID,
        feature_set_version="sprint2-features-v1",
        football_cutoff=CUTOFF,
        knowledge_cutoff=CUTOFF,
        knowledge_mode="bitemporal",
        quality_policy_sha256=SHA_B,
        target_set_sha256=SHA_C,
    )


def _manifest() -> ModelArtifactManifestV1:
    return ModelArtifactManifestV1(
        model_artifact_id=ARTIFACT_ID,
        model_family="DIXON_COLES_GOALS",
        fit_spec_sha256=SHA_A,
        schema_version="model-artifact-v1",
        algorithm_version="dixon-coles-v1",
        serializer_version="canonical-json-v1",
        compatibility=_compatibility(),
        logical_model_state_sha256=SHA_C,
        created_at=CUTOFF,
        files=(
            ArtifactFileV1(
                relative_path="models/dixon-coles/parameters.json",
                media_type="application/json",
                size_bytes=12,
                physical_sha256=SHA_B,
            ),
        ),
    )


def _compatibility() -> ArtifactCompatibilityV1:
    return ArtifactCompatibilityV1(
        runtime="python",
        runtime_version=">=3.13,<3.14",
        loader_version="canonical-json-loader-v1",
        feature_contract_version="sprint2-features-v1",
    )


def _validate_schema(name: str, value: object) -> None:
    schema = json.loads((PROJECT_ROOT / "schemas/contracts" / name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
