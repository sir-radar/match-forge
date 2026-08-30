from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from football.forecasting.contracts import (
    BaselineForecastV1,
    ForecastContractError,
    MatchResultProbabilitiesV1,
    PointInTimeScopeV1,
    forecast_payload_dict,
    forecast_payload_sha256,
)
from football.forecasting.publication import ForecastPublicationError, ImmutableForecastStore
from football.storage.raw import ImmutableFileConflict

DATASET_ID = UUID("10000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-4000-8000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-4000-8000-000000000001")
CALIBRATOR_ID = UUID("30000000-0000-4000-8000-000000000002")
FORECAST_ID = UUID("40000000-0000-4000-8000-000000000001")
MATCH_ID = UUID("50000000-0000-4000-8000-000000000001")
CUTOFF = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 8, 30, 12, 1, tzinfo=UTC)


def test_forecast_store_publishes_canonical_bytes_and_verifies_retry(tmp_path: Path) -> None:
    store = ImmutableForecastStore(tmp_path)
    forecast = _forecast()

    first = store.publish(forecast, PUBLISHED_AT)
    retry = store.publish(forecast, PUBLISHED_AT)

    assert first.status == "published"
    assert retry.status == "verified_existing"
    assert retry.physical_sha256 == first.physical_sha256
    payload = json.loads((tmp_path / first.relative_path).read_text(encoding="utf-8"))
    assert payload == forecast_payload_dict(forecast.match_result)
    assert first.physical_sha256 == forecast.payload_sha256
    assert "20260830T120000.000000Z" in first.relative_path


def test_forecast_store_rejects_mutation_at_immutable_identity(tmp_path: Path) -> None:
    store = ImmutableForecastStore(tmp_path)
    forecast = _forecast()
    store.publish(forecast, PUBLISHED_AT)
    changed_probabilities = MatchResultProbabilitiesV1(home=0.5, draw=0.3, away=0.2)
    changed = BaselineForecastV1(
        forecast_id=forecast.forecast_id,
        match_id=forecast.match_id,
        prediction_cutoff=forecast.prediction_cutoff,
        scope=forecast.scope,
        probability_variant="MODEL_RAW",
        model_artifact_ids=forecast.model_artifact_ids,
        forecast_context_sha256=forecast.forecast_context_sha256,
        payload_sha256=forecast_payload_sha256(changed_probabilities),
        match_result=changed_probabilities,
    )

    with pytest.raises(ImmutableFileConflict, match="immutable file conflict"):
        store.publish(changed, PUBLISHED_AT)
    with pytest.raises(ForecastPublicationError, match="timezone"):
        ImmutableForecastStore(tmp_path / "other").publish(forecast, datetime(2026, 8, 30, 12, 1))


def test_forecast_contract_rejects_payload_hash_or_reused_calibrator() -> None:
    probabilities = MatchResultProbabilitiesV1(home=0.45, draw=0.3, away=0.25)
    with pytest.raises(ForecastContractError, match="does not match"):
        BaselineForecastV1(
            forecast_id=FORECAST_ID,
            match_id=MATCH_ID,
            prediction_cutoff=CUTOFF,
            scope=_scope(),
            probability_variant="MODEL_RAW",
            model_artifact_ids=(ARTIFACT_ID,),
            forecast_context_sha256="d" * 64,
            payload_sha256="a" * 64,
            match_result=probabilities,
        )
    with pytest.raises(ForecastContractError, match="must be distinct"):
        BaselineForecastV1(
            forecast_id=FORECAST_ID,
            match_id=MATCH_ID,
            prediction_cutoff=CUTOFF,
            scope=_scope(),
            probability_variant="MODEL_CALIBRATED",
            model_artifact_ids=(CALIBRATOR_ID,),
            forecast_context_sha256="d" * 64,
            calibrator_artifact_id=CALIBRATOR_ID,
            payload_sha256=forecast_payload_sha256(probabilities),
            match_result=probabilities,
        )


def _forecast() -> BaselineForecastV1:
    probabilities = MatchResultProbabilitiesV1(home=0.45, draw=0.3, away=0.25)
    return BaselineForecastV1(
        forecast_id=FORECAST_ID,
        match_id=MATCH_ID,
        prediction_cutoff=CUTOFF,
        scope=_scope(),
        probability_variant="MODEL_RAW",
        model_artifact_ids=(ARTIFACT_ID,),
        forecast_context_sha256="d" * 64,
        payload_sha256=forecast_payload_sha256(probabilities),
        match_result=probabilities,
    )


def _scope() -> PointInTimeScopeV1:
    return PointInTimeScopeV1(
        dataset_version_id=DATASET_ID,
        source_snapshot_id=SNAPSHOT_ID,
        feature_set_version="sprint2-features-v1",
        football_cutoff=CUTOFF,
        knowledge_cutoff=CUTOFF,
        knowledge_mode="bitemporal",
        quality_policy_sha256="b" * 64,
        target_set_sha256="c" * 64,
    )
