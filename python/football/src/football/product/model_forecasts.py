from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection

from football.forecasting.model_contracts import (
    FittedModelArtifact,
    ModelForecast,
    ModelRole,
    ModelRunResult,
    ModelStatus,
)
from football.product.domain import canonical_json, sha256_json, stable_id


def persist_model_artifact(connection: Connection[Any], artifact: FittedModelArtifact) -> int:
    configuration_sha = sha256_json(artifact.configuration)
    manifest = {
        "model_id": artifact.model_id,
        "model_family": artifact.model_family,
        "model_version": artifact.model_version,
        "artifact_sha256": artifact.artifact_sha256,
        "dataset_sha256": artifact.dataset_sha256,
        "configuration": artifact.configuration,
        "dependency_version": artifact.dependency_version,
        "feature_contract": artifact.feature_contract,
        "diagnostics": artifact.diagnostics,
        "persistence": "TRUSTED_LOCAL_RESEARCH_CACHE_ONLY",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.product_model_artifacts (
                artifact_sha256, model_id, model_family, model_version,
                dependency_name, dependency_version, training_start, training_cutoff,
                dataset_sha256, configuration_sha256, feature_contract,
                code_commit_sha, random_seed, manifest, created_at
            ) VALUES (%s, %s, %s, %s, 'penaltyblog', %s, %s, %s,
                %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (artifact_sha256) DO NOTHING
            """,
            (
                artifact.artifact_sha256,
                artifact.model_id,
                artifact.model_family,
                artifact.model_version,
                artifact.dependency_version,
                artifact.training_start,
                artifact.training_cutoff,
                artifact.dataset_sha256,
                configuration_sha,
                artifact.feature_contract,
                artifact.code_commit_sha,
                artifact.random_seed,
                json.dumps(manifest),
                datetime.now(UTC),
            ),
        )
        return cursor.rowcount


def persist_model_run(
    connection: Connection[Any],
    result: ModelRunResult,
    *,
    roles: dict[str, ModelRole],
    fixture_id: object,
    football_cutoff: datetime,
    knowledge_cutoff: datetime,
    knowledge_mode: str,
    input_snapshot_sha256: str,
    created_at: datetime | None = None,
) -> int:
    observed_at = created_at or datetime.now(UTC)
    forecasts = {item.model_id: item for item in result.forecasts}
    count = 0
    for availability in result.availability:
        forecast = forecasts.get(availability.model_id)
        payload = model_forecast_payload(forecast) if forecast is not None else None
        payload_sha = hashlib.sha256(canonical_json(payload)).hexdigest() if payload else None
        artifact_sha = forecast.model_artifact_sha256 if forecast else None
        semantic_sha = sha256_json(
            {
                "fixture_id": str(fixture_id),
                "model_id": availability.model_id,
                "artifact_sha256": artifact_sha,
                "input_snapshot_sha256": input_snapshot_sha256,
                "status": availability.status,
                "payload_sha256": payload_sha,
            }
        )
        role = roles.get(availability.model_id, ModelRole.RESEARCH)
        stored_role = "SHADOW" if role is ModelRole.CHALLENGER else role.value
        model_family = forecast.model_family if forecast else "UNAVAILABLE"
        model_version = forecast.model_version if forecast else availability.model_id
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.product_model_forecasts (
                    model_forecast_id, semantic_sha256, fixture_id, model_id,
                    model_family, model_version, model_artifact_sha256, forecast_role,
                    status, football_cutoff, knowledge_cutoff, knowledge_mode,
                    input_snapshot_sha256, payload, payload_sha256, warnings,
                    failure_reason, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s::jsonb, %s, %s::jsonb, %s, %s)
                ON CONFLICT (semantic_sha256) DO NOTHING
                """,
                (
                    stable_id("product-model-forecast", semantic_sha),
                    semantic_sha,
                    fixture_id,
                    availability.model_id,
                    model_family,
                    model_version,
                    artifact_sha,
                    stored_role,
                    availability.status.value,
                    football_cutoff,
                    knowledge_cutoff,
                    knowledge_mode,
                    input_snapshot_sha256,
                    json.dumps(payload) if payload else None,
                    payload_sha,
                    json.dumps(list(forecast.warnings) if forecast else []),
                    availability.reason,
                    observed_at,
                ),
            )
            count += cursor.rowcount
    return count


def model_forecast_payload(forecast: ModelForecast | None) -> dict[str, object] | None:
    if forecast is None or forecast.status is not ModelStatus.SUCCESS:
        return None
    cells = [
        {
            "home_goals": forecast.score_labels[home],
            "away_goals": forecast.score_labels[away],
            "probability": probability,
        }
        for home, row in enumerate(forecast.score_matrix)
        for away, probability in enumerate(row)
    ]
    return {
        "expected_home_goals": forecast.expected_home_goals,
        "expected_away_goals": forecast.expected_away_goals,
        "probabilities": {
            "home": forecast.home_probability,
            "draw": forecast.draw_probability,
            "away": forecast.away_probability,
            "btts_yes": forecast.btts_yes,
            "btts_no": forecast.btts_no,
            "total_over_2_5": forecast.total_over_2_5,
            "total_under_2_5": forecast.total_under_2_5,
            "home_clean_sheet": forecast.home_clean_sheet,
            "away_clean_sheet": forecast.away_clean_sheet,
        },
        "score_matrix": cells,
        "home_goal_distribution": list(forecast.home_goal_distribution),
        "away_goal_distribution": list(forecast.away_goal_distribution),
        "total_goal_distribution": list(forecast.total_goal_distribution),
        "component_weights": dict(forecast.component_weights),
        "lineage": (
            {
                "forecast_mode": forecast.lineage.forecast_mode.value,
                "primary_model_id": forecast.lineage.primary_model_id,
                "primary_model_artifact_sha256": (forecast.lineage.primary_model_artifact_sha256),
                "fallback_model_id": forecast.lineage.fallback_model_id,
                "fallback_model_artifact_sha256": (forecast.lineage.fallback_model_artifact_sha256),
                "fallback_reason": forecast.lineage.fallback_reason.value,
                "home_artifact_state": forecast.lineage.home_artifact_state,
                "away_artifact_state": forecast.lineage.away_artifact_state,
                "home_history_state": forecast.lineage.home_history_state,
                "away_history_state": forecast.lineage.away_history_state,
                "home_promoted": forecast.lineage.home_promoted,
                "away_promoted": forecast.lineage.away_promoted,
                "native_component_used": forecast.lineage.native_component_used,
                "cold_start_component_used": forecast.lineage.cold_start_component_used,
                "champion_fallback_used": forecast.lineage.champion_fallback_used,
                "ensemble_mode": forecast.lineage.ensemble_mode,
            }
            if forecast.lineage is not None
            else None
        ),
    }
