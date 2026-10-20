"""Descriptive production monitoring; no training, calibration fitting or promotion."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.contracts import MatchResultProbabilitiesV1
from football.forecasting.evaluation import (
    EvaluatedMatchResultV1,
    MatchOutcome,
    evaluate_match_results,
)
from football.forecasting.model_contracts import PROBABILITY_TOLERANCE
from football.forecasting.pitchapi_v3 import _poisson_forecast
from football.forecasting.runtime_models import CURRENT_CHAMPION_HASH
from football.forecasting.scoring import _crps, _poisson_probability

POLICY_VERSION = "postmatch-monitoring-v1"
_METRICS = ("log_loss", "brier", "rps", "crps", "sharpness_entropy")


def evaluate_postmatch(inputs: Mapping[str, Any], forecast: Mapping[str, Any]) -> dict[str, Any]:
    """Score only a bound, published pre-match forecast and a separate final result."""
    _validate_input(inputs, forecast)
    home, away = inputs["home_goals"], inputs["away_goals"]
    outcome: MatchOutcome = "HOME" if home > away else "DRAW" if home == away else "AWAY"
    record: dict[str, Any] = {
        "contract": "PostMatchEvaluation",
        "policy_version": POLICY_VERSION,
        "input_sha256": sha256_bytes(canonical_json_bytes(dict(inputs))),
        "input": dict(inputs),
        "outcome": outcome,
    }
    try:
        raw = forecast["probabilities"]
        probabilities = MatchResultProbabilitiesV1(raw["home"], raw["draw"], raw["away"])
        observation = _observation(inputs, probabilities, outcome)
        scores = evaluate_match_results((observation,))
    except (KeyError, TypeError, ValueError):
        return {
            **record,
            "status": "UNSCORABLE",
            "metrics": None,
            "probabilities": None,
            "reasons": ["INVALID_FORECAST"],
        }
    values = (probabilities.home, probabilities.draw, probabilities.away)
    crps = _count_crps(forecast, home + away)
    return {
        **record,
        "status": "COMPLETE" if crps is not None else "PARTIAL",
        "probabilities": list(values),
        "metrics": {
            "log_loss": scores.log_loss,
            "brier": scores.brier_score,
            "rps": scores.ranked_probability_score,
            "crps": crps,
            "sharpness_entropy": math.fsum(-p * math.log(p) for p in values if p > 0),
        },
        "reasons": [] if crps is not None else ["COUNT_DISTRIBUTION_UNAVAILABLE"],
    }


def _validate_input(inputs: Mapping[str, Any], forecast: Mapping[str, Any]) -> None:
    if (inputs["forecast_id"], inputs["forecast_payload_sha256"]) != (
        str(forecast["forecast_id"]),
        forecast["payload_sha256"],
    ):
        raise ValueError("post-match forecast identity mismatch")
    if (inputs["model_artifact_sha256"], inputs["model_id"]) != (
        forecast["model_artifact_sha256"],
        forecast["model_algorithm_version"],
    ):
        raise ValueError("post-match model identity mismatch")
    clocks = {
        key: datetime.fromisoformat(inputs[key])
        for key in (
            "kickoff_at",
            "issued_at",
            "football_cutoff",
            "knowledge_cutoff",
            "outcome_known_at",
        )
    }
    if any(value.utcoffset() is None for value in clocks.values()):
        raise ValueError("post-match clocks require timezones")
    if not (
        clocks["football_cutoff"] <= clocks["issued_at"] < clocks["kickoff_at"]
        and clocks["knowledge_cutoff"] <= clocks["issued_at"]
    ):
        raise ValueError("only pre-match forecasts can be monitored")
    if clocks["outcome_known_at"] <= clocks["kickoff_at"]:
        raise ValueError("final result knowledge must follow kickoff")
    if any(type(inputs[key]) is not int or inputs[key] < 0 for key in ("home_goals", "away_goals")):
        raise ValueError("final result requires nonnegative integer goals")


def _observation(
    inputs: Mapping[str, Any], probabilities: MatchResultProbabilitiesV1, outcome: MatchOutcome
) -> EvaluatedMatchResultV1:
    return EvaluatedMatchResultV1(
        kickoff_at=datetime.fromisoformat(inputs["kickoff_at"]),
        prediction_cutoff=datetime.fromisoformat(inputs["football_cutoff"]),
        outcome_known_at=datetime.fromisoformat(inputs["outcome_known_at"]),
        probabilities=probabilities,
        outcome=outcome,
    )


def _count_crps(forecast: Mapping[str, Any], observed: int) -> float | None:
    """Decode only the existing champion's published Poisson sufficient parameters.

    Its compact 5+ display bucket is not an exact score. Reuse the existing count
    scorer's support/tolerance, without folding observed totals into that bucket.
    """
    if (
        forecast["model_artifact_sha256"] != CURRENT_CHAMPION_HASH
        or forecast["model_algorithm_version"]
        not in (
            "transferable-rolling-goals-poisson-v1",
            "transferable-rolling-goals-poisson-v1-rolling10-v2",
        )
        or forecast["score_matrix_version"] not in ("legacy-compact-index-v1", "compact-buckets-v2")
    ):
        return None
    try:
        home, away = forecast["expected_home_goals"], forecast["expected_away_goals"]
        if not all(math.isfinite(value) and value > 0 for value in (home, away, home + away)):
            return None
        reference = _poisson_forecast(home, away)
        raw = forecast["probabilities"]
        if any(
            not math.isclose(raw[name], expected, abs_tol=PROBABILITY_TOLERANCE, rel_tol=0)
            for name, expected in (
                ("home", reference.markets.home_win),
                ("draw", reference.markets.draw),
                ("away", reference.markets.away_win),
            )
        ):
            return None
        if not _same_grid(forecast["score_matrix"], reference.score_matrix.probabilities):
            return None
        return _crps(lambda count: _poisson_probability(count, home + away), observed)
    except (ArithmeticError, KeyError, TypeError, ValueError, RuntimeError):
        return None


def _same_grid(cells: list[dict[str, Any]], reference: tuple[tuple[float, ...], ...]) -> bool:
    size = len(reference)
    if len(cells) != size * size:
        return False
    coordinates = set()
    for cell in cells:
        home, away, value = cell["home_goals"], cell["away_goals"], cell["probability"]
        if (
            type(home) is not int
            or type(away) is not int
            or not 0 <= home < size
            or not 0 <= away < size
            or (home, away) in coordinates
        ):
            return False
        coordinates.add((home, away))
        if not math.isclose(value, reference[home][away], abs_tol=PROBABILITY_TOLERANCE, rel_tol=0):
            return False
    return True


def validate_review_limits(limits: Mapping[str, float]) -> None:
    if any(
        key not in _METRICS
        or type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
        for key, value in limits.items()
    ):
        raise ValueError("review limits require named finite nonnegative metric bounds")


def summarize_postmatch(
    records: tuple[dict[str, Any], ...], *, review_limits: Mapping[str, float]
) -> dict[str, Any]:
    validate_review_limits(review_limits)
    scored = [record for record in records if record["metrics"] is not None]
    metrics = {}
    counts = {}
    for name in _METRICS:
        values = [
            record["metrics"][name] for record in scored if record["metrics"][name] is not None
        ]
        counts[name] = len(values)
        metrics[name] = math.fsum(values) / len(values) if values else None
    observations = tuple(
        _observation(
            record["input"],
            MatchResultProbabilitiesV1(*record["probabilities"]),
            cast(MatchOutcome, record["outcome"]),
        )
        for record in scored
    )
    calibration = evaluate_match_results(observations).to_dict() if observations else None
    reasons = []
    for name, limit in review_limits.items():
        value = metrics[name]
        if value is not None and value > limit:
            reasons.append(name + "_LIMIT_EXCEEDED")
    reasons.sort()
    if any(record["status"] != "COMPLETE" for record in records):
        reasons.append("INCOMPLETE_SCORING_COVERAGE")
    return {
        "status": "REVIEW_REQUIRED" if reasons else "MONITORING",
        "review_limits": dict(review_limits),
        "review_reasons": reasons,
        "metrics": metrics,
        "metric_sample_counts": counts,
        "calibration": calibration,
        "coverage": {
            "selected": len(records),
            "scored": len(scored),
            "ratio": len(scored) / len(records) if records else None,
            "crps_scored": counts["crps"],
        },
        "policy_version": POLICY_VERSION,
    }
