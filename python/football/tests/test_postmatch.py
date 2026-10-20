import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from football.forecasting.pitchapi_v3 import _poisson_forecast
from football.forecasting.postmatch import evaluate_postmatch, summarize_postmatch
from football.forecasting.runtime_models import CURRENT_CHAMPION_HASH

KICKOFF = datetime(2026, 10, 1, 15, tzinfo=UTC)


def sample() -> tuple[dict[str, Any], dict[str, Any]]:
    goal = _poisson_forecast(1.4, 1.0)
    source = {
        "forecast_id": str(UUID(int=1)),
        "payload_sha256": "a" * 64,
        "model_artifact_sha256": CURRENT_CHAMPION_HASH,
        "model_algorithm_version": "transferable-rolling-goals-poisson-v1",
        "expected_home_goals": 1.4,
        "expected_away_goals": 1.0,
        "probabilities": {
            "home": goal.markets.home_win,
            "draw": goal.markets.draw,
            "away": goal.markets.away_win,
        },
        "score_matrix": [
            {"home_goals": h, "away_goals": a, "probability": p}
            for h, row in enumerate(goal.score_matrix.probabilities)
            for a, p in enumerate(row)
        ],
        "score_matrix_version": "compact-buckets-v2",
    }
    inputs = {
        "contract": "PostMatchEvaluationInput",
        "policy_version": "postmatch-monitoring-v1",
        "code_commit_sha": "f" * 40,
        "dependency_lock_sha256": "d" * 64,
        "model_artifact_sha256": CURRENT_CHAMPION_HASH,
        "fixture_id": str(UUID(int=2)),
        "forecast_id": source["forecast_id"],
        "forecast_payload_sha256": source["payload_sha256"],
        "kickoff_at": KICKOFF.isoformat(),
        "issued_at": (KICKOFF - timedelta(hours=24)).isoformat(),
        "football_cutoff": (KICKOFF - timedelta(hours=24)).isoformat(),
        "knowledge_cutoff": (KICKOFF - timedelta(hours=24)).isoformat(),
        "outcome_known_at": (KICKOFF + timedelta(hours=2)).isoformat(),
        "home_goals": 7,
        "away_goals": 0,
        "model_id": source["model_algorithm_version"],
        "competition_id": str(UUID(int=3)),
        "season": "2026",
        "horizon": "LATEST",
        "data_quality_tier": "UNKNOWN",
    }
    return inputs, source


def test_monitoring_uses_existing_scores_and_full_poisson_support() -> None:
    inputs, source = sample()
    result = evaluate_postmatch(inputs, source)
    assert result["contract"] == "PostMatchEvaluation"
    assert result["status"] == "COMPLETE"
    p = source["probabilities"]
    assert result["metrics"]["log_loss"] == pytest.approx(-math.log(p["home"]))
    assert result["metrics"]["brier"] == pytest.approx(
        (p["home"] - 1) ** 2 + p["draw"] ** 2 + p["away"] ** 2
    )
    from scipy.stats import poisson

    # Independent CDF reference: seven observed goals stay outside the 5+ display bucket.
    expected_crps = sum((poisson.cdf(count, 2.4) - float(count >= 7)) ** 2 for count in range(80))
    assert result["metrics"]["crps"] == pytest.approx(expected_crps, abs=1e-12)
    assert result["metrics"]["sharpness_entropy"] > 0
    assert result["probabilities"] == [p["home"], p["draw"], p["away"]]
    assert result["outcome"] == "HOME"
    assert source["score_matrix"][-1]["home_goals"] == 5


@pytest.mark.parametrize("field", ["issued_at", "football_cutoff", "knowledge_cutoff"])
def test_post_kickoff_forecasts_are_never_scored(field: str) -> None:
    inputs, source = sample()
    inputs[field] = KICKOFF.isoformat()
    with pytest.raises(ValueError, match="pre-match"):
        evaluate_postmatch(inputs, source)


def test_result_clocks_and_forecast_identity_are_verified() -> None:
    inputs, source = sample()
    inputs["outcome_known_at"] = KICKOFF.isoformat()
    with pytest.raises(ValueError, match="final result"):
        evaluate_postmatch(inputs, source)
    inputs, source = sample()
    source["payload_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="identity"):
        evaluate_postmatch(inputs, source)


@pytest.mark.parametrize("change", [{"home": 2.0}, {"home": float("nan")}, {"home": True}])
def test_invalid_probabilities_are_recorded_without_clipping(change: dict[str, Any]) -> None:
    inputs, source = sample()
    source["probabilities"].update(change)
    result = evaluate_postmatch(inputs, source)
    assert result["status"] == "UNSCORABLE"
    assert result["metrics"] is None
    assert result["reasons"] == ["INVALID_FORECAST"]


def test_unknown_or_inconsistent_count_models_have_explicit_missing_crps() -> None:
    inputs, source = sample()
    source["model_artifact_sha256"] = "f" * 64
    inputs["model_artifact_sha256"] = source["model_artifact_sha256"]
    result = evaluate_postmatch(inputs, source)
    assert result["status"] == "PARTIAL"
    assert result["metrics"]["crps"] is None
    assert result["reasons"] == ["COUNT_DISTRIBUTION_UNAVAILABLE"]
    inputs, source = sample()
    source["score_matrix"][0]["probability"] = 0.9
    assert evaluate_postmatch(inputs, source)["metrics"]["crps"] is None


def test_rolling_metrics_keep_missingness_and_review_only_limits() -> None:
    inputs, source = sample()
    good = evaluate_postmatch(inputs, source)
    bad = {
        **good,
        "status": "UNSCORABLE",
        "metrics": None,
        "probabilities": None,
        "reasons": ["INVALID_FORECAST"],
    }
    report = summarize_postmatch((good, bad), review_limits={})
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["coverage"] == {"selected": 2, "scored": 1, "ratio": 0.5, "crps_scored": 1}
    assert report["calibration"]["sample_count"] == 1
    assert report["metrics"]["log_loss"] == good["metrics"]["log_loss"]
    assert not {"AUTO_RETRAIN", "AUTO_RECALIBRATE", "AUTO_PROMOTE"}.intersection(
        str(report).split()
    )
    report = summarize_postmatch((good,), review_limits={"log_loss": 0.0})
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["review_reasons"] == ["log_loss_LIMIT_EXCEEDED"]
    assert summarize_postmatch((), review_limits={})["coverage"]["ratio"] is None


@pytest.mark.parametrize("limits", [{"arbitrary": 1.0}, {"brier": -1.0}, {"crps": float("nan")}])
def test_review_limits_are_explicit_validated_inputs(limits: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="review limits"):
        summarize_postmatch((), review_limits=limits)


@pytest.mark.parametrize("goals", [-1, True])
def test_invalid_final_counts_are_rejected(goals: object) -> None:
    inputs, source = sample()
    inputs["home_goals"] = goals
    with pytest.raises(ValueError, match="integer goals"):
        evaluate_postmatch(inputs, source)


def test_projection_capture_normalizes_database_timezone() -> None:
    from datetime import timezone

    from football.forecasting.postmatch_storage import _inputs

    inputs, source = sample()
    source.update(
        fixture_id=inputs["fixture_id"],
        competition_id=inputs["competition_id"],
        season_label=inputs["season"],
        home_score=7,
        away_score=0,
    )
    clocks = ("kickoff_at", "issued_at", "football_cutoff", "knowledge_cutoff", "outcome_known_at")
    source.update({key: datetime.fromisoformat(inputs[key]) for key in clocks})
    first = _inputs(source, "LATEST", "f" * 40, "d" * 64)
    source.update({key: source[key].astimezone(timezone(timedelta(hours=1))) for key in clocks})
    assert _inputs(source, "LATEST", "f" * 40, "d" * 64) == first


def test_postmatch_schema_is_frozen_and_binds_the_input_checksum() -> None:
    import json
    from pathlib import Path

    from football.forecasting.postmatch_contract import postmatch_schema, validate_postmatch_record

    assert (
        json.loads(Path("schemas/contracts/post-match-evaluation.schema.json").read_text())
        == postmatch_schema()
    )
    inputs, source = sample()
    record = evaluate_postmatch(inputs, source)
    validate_postmatch_record(record)
    record["input_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="checksum"):
        validate_postmatch_record(record)


@pytest.mark.parametrize(
    "change", [{"status": "AUTO_PROMOTE"}, {"extra_field": True}, {"metrics": None}]
)
def test_invalid_durable_monitoring_records_are_rejected(change: dict[str, Any]) -> None:
    from football.forecasting.postmatch_contract import validate_postmatch_record

    inputs, source = sample()
    record = evaluate_postmatch(inputs, source)
    record.update(change)
    with pytest.raises(ValueError, match="invalid post-match evaluation"):
        validate_postmatch_record(record)


@pytest.mark.parametrize("field", ["code_commit_sha", "dependency_lock_sha256"])
def test_scoring_provenance_requires_full_hashes(field: str) -> None:
    from football.forecasting.postmatch_contract import validate_postmatch_record

    inputs, source = sample()
    inputs[field] = "unknown"
    record = evaluate_postmatch(inputs, source)
    with pytest.raises(ValueError, match="invalid post-match evaluation"):
        validate_postmatch_record(record)
