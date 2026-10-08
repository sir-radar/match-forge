"""Frozen development selection and scoring for contextual goal corrections."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import numpy as np
from scipy.stats import poisson, skellam

from football.forecasting.context_evaluation import (
    CoverageReport,
    DevelopmentPartition,
    FamilyDevelopmentResult,
    TargetDelta,
    chronological_partitions,
    evaluate_family_admission,
)
from football.forecasting.contextual_goal import (
    ALLOWED_L2,
    ContextTrainingRow,
    FeatureFamily,
    FittedContextFeature,
    fit_contextual_adjustment,
)
from football.forecasting.pitchapi_v3_evaluation import (
    PitchApiV3EvaluationError,
    calibration_fit,
)


@dataclass(frozen=True, slots=True)
class ContextEvaluationRow:
    fixture_id: UUID
    kickoff_at: datetime
    competition: str
    baseline_home_rate: float
    baseline_away_rate: float
    home_goals: int
    away_goals: int
    values: dict[str, float | None]

    def training_row(self) -> ContextTrainingRow:
        return ContextTrainingRow(
            self.fixture_id,
            self.kickoff_at,
            self.competition,
            self.baseline_home_rate,
            self.baseline_away_rate,
            self.home_goals,
            self.away_goals,
            self.values,
        )


@dataclass(frozen=True, slots=True)
class ScoreMetrics:
    sample_count: int
    joint_log_loss: float
    one_x_two_log_loss: float
    brier: float
    rps: float
    crps: float
    calibration: tuple[tuple[str, float | None, float | None], ...]


@dataclass(frozen=True, slots=True)
class DomainResult:
    domain: str
    baseline: ScoreMetrics
    candidate: ScoreMetrics
    joint_log_loss_delta: float


@dataclass(frozen=True, slots=True)
class RestDevelopmentEvaluation:
    selected_l2: float
    validation_joint_log_loss: tuple[tuple[float, float], ...]
    coefficients: tuple[FittedContextFeature, ...]
    partition_counts: tuple[tuple[DevelopmentPartition, int], ...]
    training_cutoff: datetime
    holdout_result: FamilyDevelopmentResult
    baseline_metrics: ScoreMetrics
    candidate_metrics: ScoreMetrics
    domain_results: tuple[DomainResult, ...]


@dataclass(frozen=True, slots=True)
class _TargetScores:
    joint_log_loss: float
    one_x_two_log_loss: float
    brier: float
    rps: float
    crps: float
    probabilities: tuple[float, float, float]
    outcome_index: int


def evaluate_rest_development(
    rows: tuple[ContextEvaluationRow, ...],
) -> RestDevelopmentEvaluation:
    """Execute the frozen 60/20/20 rest-family development protocol once."""
    if not rows:
        raise ValueError("rest development evaluation requires rows")
    ordered = tuple(sorted(rows, key=lambda row: (row.kickoff_at, str(row.fixture_id))))
    partitions = chronological_partitions(
        tuple((row.fixture_id, row.kickoff_at) for row in ordered)
    )
    grouped = {
        partition: tuple(row for row in ordered if partitions[row.fixture_id] is partition)
        for partition in DevelopmentPartition
    }
    if any(not grouped[partition] for partition in DevelopmentPartition):
        raise ValueError("rest development evaluation requires non-empty 60/20/20 partitions")

    training = tuple(row.training_row() for row in grouped[DevelopmentPartition.TRAIN])
    fitted = tuple(
        (l2, fit_contextual_adjustment(training, FeatureFamily.REST_CONGESTION, l2=l2))
        for l2 in ALLOWED_L2
    )
    validation = grouped[DevelopmentPartition.VALIDATION]
    validation_scores = tuple(
        (l2, _metrics(validation, coefficients).joint_log_loss) for l2, coefficients in fitted
    )
    selected_l2, _score = min(validation_scores, key=lambda item: (item[1], item[0]))
    selected = dict(fitted)[selected_l2]

    holdout = grouped[DevelopmentPartition.DEVELOPMENT_HOLDOUT]
    deltas = tuple(_target_delta(row, selected) for row in holdout)
    qualified = sum(_has_rest_context(row) for row in ordered)
    coverage = CoverageReport(len(ordered), qualified, len(ordered) - qualified, len(ordered))
    result = evaluate_family_admission(FeatureFamily.REST_CONGESTION, deltas, coverage)
    domains = tuple(
        DomainResult(
            domain,
            _metrics(subset, ()),
            _metrics(subset, selected),
            statistics.fmean(_target_delta(row, selected).joint_log_loss for row in subset),
        )
        for domain in sorted({row.competition for row in holdout})
        if (subset := tuple(row for row in holdout if row.competition == domain))
    )
    return RestDevelopmentEvaluation(
        selected_l2,
        validation_scores,
        selected,
        tuple((partition, len(grouped[partition])) for partition in DevelopmentPartition),
        max(row.kickoff_at for row in grouped[DevelopmentPartition.TRAIN]),
        result,
        _metrics(holdout, ()),
        _metrics(holdout, selected),
        domains,
    )


def adjusted_rates(
    row: ContextEvaluationRow, coefficients: tuple[FittedContextFeature, ...]
) -> tuple[float, float]:
    home_delta = 0.0
    away_delta = 0.0
    for item in coefficients:
        raw = _feature_value(item, row.values)
        home_delta += item.home_coefficient * raw
        away_delta += item.away_coefficient * raw
    home = row.baseline_home_rate * math.exp(home_delta)
    away = row.baseline_away_rate * math.exp(away_delta)
    if not math.isfinite(home) or not math.isfinite(away) or home <= 0.0 or away <= 0.0:
        raise ValueError("context adjustment produced invalid rates")
    return home, away


def _metrics(
    rows: tuple[ContextEvaluationRow, ...],
    coefficients: tuple[FittedContextFeature, ...],
) -> ScoreMetrics:
    scores = tuple(_score(row, coefficients) for row in rows)
    calibration = tuple(
        _calibration(scores, index, name) for index, name in enumerate(("HOME", "DRAW", "AWAY"))
    )
    return ScoreMetrics(
        len(rows),
        statistics.fmean(score.joint_log_loss for score in scores),
        statistics.fmean(score.one_x_two_log_loss for score in scores),
        statistics.fmean(score.brier for score in scores),
        statistics.fmean(score.rps for score in scores),
        statistics.fmean(score.crps for score in scores),
        calibration,
    )


def _target_delta(
    row: ContextEvaluationRow, coefficients: tuple[FittedContextFeature, ...]
) -> TargetDelta:
    baseline = _score(row, ())
    candidate = _score(row, coefficients)
    return TargetDelta(
        row.fixture_id,
        row.kickoff_at,
        row.competition,
        candidate.joint_log_loss - baseline.joint_log_loss,
        candidate.one_x_two_log_loss - baseline.one_x_two_log_loss,
        candidate.brier - baseline.brier,
        candidate.rps - baseline.rps,
        candidate.crps - baseline.crps,
    )


def _score(
    row: ContextEvaluationRow, coefficients: tuple[FittedContextFeature, ...]
) -> _TargetScores:
    home_rate, away_rate = adjusted_rates(row, coefficients)
    probabilities = _one_x_two(home_rate, away_rate)
    outcome = 0 if row.home_goals > row.away_goals else 1 if row.home_goals == row.away_goals else 2
    actual = tuple(float(index == outcome) for index in range(3))
    cumulative_forecast = (probabilities[0], probabilities[0] + probabilities[1])
    cumulative_actual = (actual[0], actual[0] + actual[1])
    return _TargetScores(
        _poisson_loss(row.home_goals, home_rate) + _poisson_loss(row.away_goals, away_rate),
        -math.log(max(probabilities[outcome], 1e-15)),
        sum(
            (probability - target) ** 2
            for probability, target in zip(probabilities, actual, strict=True)
        ),
        sum(
            (forecast - target) ** 2
            for forecast, target in zip(cumulative_forecast, cumulative_actual, strict=True)
        )
        / 2.0,
        _total_goal_crps(home_rate + away_rate, row.home_goals + row.away_goals),
        probabilities,
        outcome,
    )


def _calibration(
    scores: tuple[_TargetScores, ...], index: int, name: str
) -> tuple[str, float | None, float | None]:
    probabilities = tuple(score.probabilities[index] for score in scores)
    outcomes = tuple(int(score.outcome_index == index) for score in scores)
    try:
        fit = calibration_fit(probabilities, outcomes)
    except PitchApiV3EvaluationError as error:
        if str(error) != "calibration outcome must contain both classes":
            raise
        return name, None, None
    return name, fit.intercept, fit.slope


def _one_x_two(home_rate: float, away_rate: float) -> tuple[float, float, float]:
    home = float(skellam.sf(0, home_rate, away_rate))
    draw = float(skellam.pmf(0, home_rate, away_rate))
    away = float(skellam.cdf(-1, home_rate, away_rate))
    total = home + draw + away
    return home / total, draw / total, away / total


def _poisson_loss(goals: int, rate: float) -> float:
    return rate - goals * math.log(rate) + math.lgamma(goals + 1)


def _total_goal_crps(rate: float, observed: int) -> float:
    support = max(observed, int(poisson.ppf(1.0 - 1e-12, rate)))
    values = np.arange(support + 1)
    cumulative = poisson.cdf(values, rate)
    actual = (values >= observed).astype(float)
    return float(np.sum((cumulative - actual) ** 2))


def _feature_value(item: FittedContextFeature, values: dict[str, float | None]) -> float:
    name = item.feature_name
    if name.endswith("__coverage"):
        base = name.removesuffix("__coverage")
        raw = float(values.get(base) is not None)
    elif name.endswith("__missing"):
        base = name.removesuffix("__missing")
        raw = float(values.get(base) is None)
    else:
        value = values.get(name)
        if value is None:
            return 0.0
        raw = value
    return (raw - item.mean) / item.scale


def _has_rest_context(row: ContextEvaluationRow) -> bool:
    return (
        row.values.get("home_days_since_last_match") is not None
        and row.values.get("away_days_since_last_match") is not None
    )
