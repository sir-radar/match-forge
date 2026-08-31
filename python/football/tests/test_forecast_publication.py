from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from football.forecasting.contracts import (
    BaselineForecastV1,
    CornerForecastPayloadV1,
    ForecastContractError,
    GoalForecastPayloadV1,
    MatchResultProbabilitiesV1,
    PointInTimeScopeV1,
    forecast_payload_dict,
    forecast_payload_sha256,
)
from football.forecasting.publication import ForecastPublicationError, ImmutableForecastStore
from football.storage.raw import ImmutableFileConflict
from jsonschema import Draft202012Validator, FormatChecker

DATASET_ID = UUID("10000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-4000-8000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-4000-8000-000000000001")
CALIBRATOR_ID = UUID("30000000-0000-4000-8000-000000000002")
FORECAST_ID = UUID("40000000-0000-4000-8000-000000000001")
MATCH_ID = UUID("50000000-0000-4000-8000-000000000001")
CUTOFF = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 8, 30, 12, 1, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


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


def test_forecast_store_preserves_full_goal_and_corner_probability_payloads(
    tmp_path: Path,
) -> None:
    match_result = MatchResultProbabilitiesV1(home=0.45, draw=0.30, away=0.25)
    goal = GoalForecastPayloadV1(
        lambda_home=1.4,
        lambda_away=1.0,
        score_labels=("0", "1", "2+"),
        score_probabilities=(
            (0.12, 0.10, 0.08),
            (0.11, 0.14, 0.10),
            (0.09, 0.12, 0.14),
        ),
        over_0_5=0.9,
        over_1_5=0.7,
        over_2_5=0.5,
        over_3_5=0.3,
        over_4_5=0.1,
        btts_yes=0.55,
        home_clean_sheet=0.35,
        away_clean_sheet=0.25,
    )
    corners = CornerForecastPayloadV1(
        distribution="negative_binomial",
        lambda_home=5.4,
        lambda_away=4.6,
        home_variance=8.0,
        away_variance=6.5,
        dispersion=0.1,
    )
    forecast = BaselineForecastV1(
        forecast_id=FORECAST_ID,
        match_id=MATCH_ID,
        prediction_cutoff=CUTOFF,
        scope=_scope(),
        probability_variant="MODEL_RAW",
        model_artifact_ids=(ARTIFACT_ID,),
        forecast_context_sha256="d" * 64,
        payload_sha256=forecast_payload_sha256(match_result, goal=goal, corners=corners),
        match_result=match_result,
        goal=goal,
        corners=corners,
        probability_contract_version="sprint2-probability-products-v1",
    )

    published = ImmutableForecastStore(tmp_path).publish(forecast, PUBLISHED_AT)
    payload = json.loads((tmp_path / published.relative_path).read_text(encoding="utf-8"))

    assert payload == forecast_payload_dict(match_result, goal=goal, corners=corners)
    assert payload["goal"]["score_probabilities"][2][2] == pytest.approx(0.14)
    assert payload["corners"]["distribution"] == "negative_binomial"
    assert published.physical_sha256 == forecast.payload_sha256
    schema = json.loads(
        (PROJECT_ROOT / "schemas/contracts/baseline-forecast-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(forecast.to_dict())


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
