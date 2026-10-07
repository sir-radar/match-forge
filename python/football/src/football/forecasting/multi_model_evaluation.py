from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from scipy.optimize import minimize

from football.forecasting.contracts import MatchResultProbabilitiesV1
from football.forecasting.evaluation import (
    EvaluatedMatchResultV1,
    MatchOutcome,
    ReliabilityBinV1,
    evaluate_match_results,
)
from football.forecasting.model_contracts import ModelForecast


@dataclass(frozen=True, slots=True)
class ScoredModelForecast:
    forecast: ModelForecast
    kickoff_at: datetime
    outcome_known_at: datetime
    home_goals: int
    away_goals: int
    competition_id: str
    season_label: str


@dataclass(frozen=True, slots=True)
class ClassCalibration:
    outcome: str
    intercept: float | None
    slope: float | None
    reliability_bins: tuple[ReliabilityBinV1, ...]


@dataclass(frozen=True, slots=True)
class ModelEvaluationMetrics:
    model_id: str
    target_count: int
    joint_score_log_loss: float
    result_log_loss: float
    multiclass_brier: float
    ranked_probability_score: float
    total_goal_crps: float
    calibration: tuple[ClassCalibration, ...]


@dataclass(frozen=True, slots=True)
class PairedDelta:
    candidate_model_id: str
    champion_model_id: str
    metric: str
    target_count: int
    delta: float
    confidence_interval_95: tuple[float, float]
    conclusion: str


@dataclass(frozen=True, slots=True)
class ForecastLosses:
    joint_score_log_loss: float
    result_log_loss: float
    multiclass_brier: float
    ranked_probability_score: float
    total_goal_crps: float


def forecast_losses(item: ScoredModelForecast) -> ForecastLosses:
    probabilities = (
        item.forecast.home_probability,
        item.forecast.draw_probability,
        item.forecast.away_probability,
    )
    outcome_index = (
        0 if item.home_goals > item.away_goals else 1 if item.home_goals == item.away_goals else 2
    )
    actual = tuple(float(index == outcome_index) for index in range(3))
    return ForecastLosses(
        joint_score_log_loss=_joint_loss(item),
        result_log_loss=_result_loss(item),
        multiclass_brier=sum(
            (probability - target) ** 2
            for probability, target in zip(probabilities, actual, strict=True)
        ),
        ranked_probability_score=(
            (probabilities[0] - actual[0]) ** 2
            + (probabilities[0] + probabilities[1] - actual[0] - actual[1]) ** 2
        )
        / 2.0,
        total_goal_crps=_total_crps(item),
    )


def evaluate_model_forecasts(
    observations: tuple[ScoredModelForecast, ...],
) -> ModelEvaluationMetrics:
    if not observations:
        raise ValueError("model evaluation requires observations")
    model_ids = {item.forecast.model_id for item in observations}
    if len(model_ids) != 1:
        raise ValueError("one evaluation row set must contain exactly one model")
    evaluated = tuple(
        EvaluatedMatchResultV1(
            kickoff_at=item.kickoff_at,
            prediction_cutoff=item.forecast.football_cutoff,
            outcome_known_at=item.outcome_known_at,
            probabilities=MatchResultProbabilitiesV1(
                home=item.forecast.home_probability,
                draw=item.forecast.draw_probability,
                away=item.forecast.away_probability,
            ),
            outcome=_outcome(item.home_goals, item.away_goals),
        )
        for item in observations
    )
    result_metrics = evaluate_match_results(evaluated)
    joint = tuple(_joint_loss(item) for item in observations)
    crps = tuple(_total_crps(item) for item in observations)
    calibrations = tuple(
        _class_calibration(observations, index, name)
        for index, name in enumerate(("HOME", "DRAW", "AWAY"))
    )
    return ModelEvaluationMetrics(
        model_id=next(iter(model_ids)),
        target_count=len(observations),
        joint_score_log_loss=sum(joint) / len(joint),
        result_log_loss=result_metrics.log_loss,
        multiclass_brier=result_metrics.brier_score,
        ranked_probability_score=result_metrics.ranked_probability_score,
        total_goal_crps=sum(crps) / len(crps),
        calibration=calibrations,
    )


def paired_bootstrap_delta(
    *,
    candidate: tuple[ScoredModelForecast, ...],
    champion: tuple[ScoredModelForecast, ...],
    metric: str = "joint_score_log_loss",
    samples: int = 2_000,
    seed: int = 20261004,
) -> PairedDelta:
    candidate_by_fixture = {item.forecast.fixture_id: item for item in candidate}
    champion_by_fixture = {item.forecast.fixture_id: item for item in champion}
    common = tuple(sorted(candidate_by_fixture.keys() & champion_by_fixture.keys(), key=str))
    if not common:
        raise ValueError("paired comparison requires common fixtures")
    scorer = _joint_loss if metric == "joint_score_log_loss" else _result_loss
    differences = np.array(
        [scorer(candidate_by_fixture[key]) - scorer(champion_by_fixture[key]) for key in common],
        dtype=float,
    )
    rng = np.random.default_rng(seed)
    draws = rng.choice(differences, size=(samples, len(differences)), replace=True).mean(axis=1)
    lower, upper = np.quantile(draws, (0.025, 0.975))
    conclusion = "INCONCLUSIVE"
    if upper < 0:
        conclusion = "CHALLENGER_BETTER"
    elif lower > 0:
        conclusion = "CHALLENGER_WORSE"
    return PairedDelta(
        candidate_model_id=candidate[0].forecast.model_id,
        champion_model_id=champion[0].forecast.model_id,
        metric=metric,
        target_count=len(common),
        delta=float(differences.mean()),
        confidence_interval_95=(float(lower), float(upper)),
        conclusion=conclusion,
    )


def _joint_loss(item: ScoredModelForecast) -> float:
    matrix = item.forecast.score_matrix
    home = min(item.home_goals, len(matrix) - 1)
    away = min(item.away_goals, len(matrix) - 1)
    return -math.log(max(matrix[home][away], 1e-15))


def _result_loss(item: ScoredModelForecast) -> float:
    values = (
        item.forecast.home_probability,
        item.forecast.draw_probability,
        item.forecast.away_probability,
    )
    index = (
        0 if item.home_goals > item.away_goals else 1 if item.home_goals == item.away_goals else 2
    )
    return -math.log(max(values[index], 1e-15))


def _total_crps(item: ScoredModelForecast) -> float:
    observed = item.home_goals + item.away_goals
    cumulative = 0.0
    score = 0.0
    for goals, probability in enumerate(item.forecast.total_goal_distribution):
        cumulative += probability
        target = 1.0 if goals >= observed else 0.0
        score += (cumulative - target) ** 2
    return score


def _class_calibration(
    observations: tuple[ScoredModelForecast, ...], class_index: int, name: str
) -> ClassCalibration:
    probabilities = np.array(
        [
            (
                item.forecast.home_probability,
                item.forecast.draw_probability,
                item.forecast.away_probability,
            )[class_index]
            for item in observations
        ],
        dtype=float,
    )
    outcomes = np.array(
        [
            int(
                (class_index == 0 and item.home_goals > item.away_goals)
                or (class_index == 1 and item.home_goals == item.away_goals)
                or (class_index == 2 and item.home_goals < item.away_goals)
            )
            for item in observations
        ],
        dtype=float,
    )
    logits = np.log(np.clip(probabilities, 1e-12, 1 - 1e-12) / np.clip(1 - probabilities, 1e-12, 1))

    def objective(values: np.ndarray[Any, Any]) -> float:
        fitted = 1.0 / (1.0 + np.exp(-(values[0] + values[1] * logits)))
        return float(
            -np.sum(outcomes * np.log(fitted + 1e-15) + (1 - outcomes) * np.log(1 - fitted + 1e-15))
        )

    fit = minimize(objective, np.array([0.0, 1.0]), method="BFGS")
    intercept, slope = (float(value) for value in fit.x) if fit.success else (None, None)
    bins = []
    for index in range(10):
        lower = index / 10
        upper = (index + 1) / 10
        selected = (probabilities >= lower) & (
            probabilities < upper if index < 9 else probabilities <= upper
        )
        count = int(selected.sum())
        bins.append(
            ReliabilityBinV1(
                lower_bound=lower,
                upper_bound=upper,
                sample_count=count,
                mean_probability=float(probabilities[selected].mean()) if count else None,
                observed_frequency=float(outcomes[selected].mean()) if count else None,
            )
        )
    return ClassCalibration(name, intercept, slope, tuple(bins))


def _outcome(home_goals: int, away_goals: int) -> MatchOutcome:
    if home_goals > away_goals:
        return "HOME"
    if home_goals < away_goals:
        return "AWAY"
    return "DRAW"
