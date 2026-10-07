from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from football.forecasting.cold_start import (
    ColdStartConfig,
    ColdStartError,
    ColdStartStrengthV1,
    transferable_context_features,
)
from football.forecasting.model_contracts import ForecastInputSnapshot

SHRINKAGE_GRID = (2.0, 5.0, 10.0, 20.0, 40.0)
TRANSFER_WEIGHT_GRID = (0.25, 0.5, 0.75, 1.0)
L2_GRID = (0.01, 0.1, 1.0, 10.0)


@dataclass(frozen=True, slots=True)
class ColdStartDevelopmentObservation:
    snapshot: ForecastInputSnapshot
    home_goals: int
    away_goals: int

    def __post_init__(self) -> None:
        for name, value in (("home_goals", self.home_goals), ("away_goals", self.away_goals)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.snapshot.football_cutoff > self.snapshot.kickoff_at:
            raise ValueError("training cutoff must not follow target kickoff")
        if any(
            row.kickoff_at >= self.snapshot.football_cutoff
            or row.known_at > self.snapshot.knowledge_cutoff
            for row in self.snapshot.qualified_history
        ):
            raise ValueError("development observation contains ineligible history")


@dataclass(frozen=True, slots=True)
class ChronologicalDevelopmentSplit:
    train: tuple[ColdStartDevelopmentObservation, ...]
    validation: tuple[ColdStartDevelopmentObservation, ...]
    development_holdout: tuple[ColdStartDevelopmentObservation, ...]
    train_end: datetime
    validation_end: datetime


@dataclass(frozen=True, slots=True)
class ColdStartDevelopmentMetrics:
    target_count: int
    joint_score_log_loss: float
    result_log_loss: float
    multiclass_brier: float


@dataclass(frozen=True, slots=True)
class ColdStartSelectionResult:
    config: ColdStartConfig
    selected_transfer_weight: float
    split: ChronologicalDevelopmentSplit
    validation_metrics: ColdStartDevelopmentMetrics
    development_holdout_metrics: ColdStartDevelopmentMetrics
    candidate_count: int


def chronological_development_split(
    observations: tuple[ColdStartDevelopmentObservation, ...],
) -> ChronologicalDevelopmentSplit:
    if len(observations) < 5:
        raise ValueError("development selection requires at least five observations")
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (item.snapshot.kickoff_at, str(item.snapshot.fixture_id)),
        )
    )
    batches = tuple(sorted({item.snapshot.kickoff_at for item in ordered}))
    if len(batches) < 5:
        raise ValueError("development selection requires at least five kickoff batches")
    train_batches = max(1, math.floor(len(batches) * 0.6))
    validation_batches = max(train_batches + 1, math.floor(len(batches) * 0.8))
    if validation_batches >= len(batches):
        validation_batches = len(batches) - 1
    train_end = batches[train_batches - 1]
    validation_end = batches[validation_batches - 1]
    train = tuple(item for item in ordered if item.snapshot.kickoff_at <= train_end)
    validation = tuple(
        item for item in ordered if train_end < item.snapshot.kickoff_at <= validation_end
    )
    holdout = tuple(item for item in ordered if item.snapshot.kickoff_at > validation_end)
    if not train or not validation or not holdout:
        raise ValueError("chronological development split produced an empty partition")
    return ChronologicalDevelopmentSplit(train, validation, holdout, train_end, validation_end)


def select_cold_start_config(
    observations: tuple[ColdStartDevelopmentObservation, ...],
    *,
    competition_relationships: tuple[tuple[UUID, UUID], ...] = (),
) -> ColdStartSelectionResult:
    split = chronological_development_split(observations)
    transfer_grid = TRANSFER_WEIGHT_GRID if competition_relationships else (0.0,)
    candidates: list[tuple[tuple[float, float, float, int, float], ColdStartConfig, float]] = []
    for shrinkage_k in SHRINKAGE_GRID:
        for transfer_weight in transfer_grid:
            relationships = tuple(
                (source, target, transfer_weight) for source, target in competition_relationships
            )
            for l2 in L2_GRID:
                initial = ColdStartConfig(
                    shrinkage_k=shrinkage_k,
                    competition_transfer_weights=relationships,
                    l2_regularization=l2,
                )
                fitted = _fit_coefficients(split.train, initial)
                metrics = _evaluate(split.validation, fitted)
                complexity = sum(
                    abs(value) > 1e-12
                    for value in fitted.home_rate_coefficients + fitted.away_rate_coefficients
                )
                key = (
                    metrics.joint_score_log_loss,
                    metrics.result_log_loss,
                    metrics.multiclass_brier,
                    complexity,
                    -shrinkage_k,
                )
                candidates.append((key, fitted, transfer_weight))
    _, selected, transfer_weight = min(candidates, key=lambda item: item[0])
    validation_metrics = _evaluate(split.validation, selected)
    holdout_metrics = _evaluate(split.development_holdout, selected)
    return ColdStartSelectionResult(
        config=selected,
        selected_transfer_weight=transfer_weight,
        split=split,
        validation_metrics=validation_metrics,
        development_holdout_metrics=holdout_metrics,
        candidate_count=len(candidates),
    )


def _fit_coefficients(
    observations: tuple[ColdStartDevelopmentObservation, ...], config: ColdStartConfig
) -> ColdStartConfig:
    rows = tuple(_design_row(item, config) for item in observations)
    if not rows:
        raise ValueError("no eligible training rows for cold-start coefficient fit")
    features = np.asarray([row[0] for row in rows], dtype=float)
    home_offsets = np.asarray([row[1] for row in rows], dtype=float)
    away_offsets = np.asarray([row[2] for row in rows], dtype=float)
    home_goals = np.asarray([row[3] for row in rows], dtype=float)
    away_goals = np.asarray([row[4] for row in rows], dtype=float)
    home = _fit_poisson(features, home_offsets, home_goals, config.l2_regularization)
    away = _fit_poisson(features, away_offsets, away_goals, config.l2_regularization)
    return replace(
        config,
        home_rate_coefficients=tuple(float(value) for value in home),
        away_rate_coefficients=tuple(float(value) for value in away),
    )


def _fit_poisson(
    features: np.ndarray,
    offsets: np.ndarray,
    outcomes: np.ndarray,
    l2: float,
) -> np.ndarray:
    def objective(values: np.ndarray) -> float:
        eta = np.clip(offsets + features @ values, -10.0, 10.0)
        likelihood = np.exp(eta) - outcomes * eta
        return float(np.mean(likelihood) + l2 * np.sum(values[1:] ** 2))

    result = minimize(
        objective,
        np.zeros(features.shape[1], dtype=float),
        method="L-BFGS-B",
    )
    if not result.success or not math.isfinite(float(result.fun)):
        raise ValueError(f"cold-start coefficient optimizer failed: {result.message}")
    return np.asarray(result.x, dtype=float)


def _evaluate(
    observations: tuple[ColdStartDevelopmentObservation, ...], config: ColdStartConfig
) -> ColdStartDevelopmentMetrics:
    losses: list[tuple[float, float, float]] = []
    for item in observations:
        try:
            features, home_offset, away_offset, home_goals, away_goals = _design_row(item, config)
        except ColdStartError:
            continue
        home_lambda = math.exp(
            max(-10.0, min(10.0, home_offset + _dot(features, config.home_rate_coefficients)))
        )
        away_lambda = math.exp(
            max(-10.0, min(10.0, away_offset + _dot(features, config.away_rate_coefficients)))
        )
        joint_probability = float(poisson.pmf(home_goals, home_lambda)) * float(
            poisson.pmf(away_goals, away_lambda)
        )
        result_probabilities = _result_probabilities(home_lambda, away_lambda)
        outcome = 0 if home_goals > away_goals else 1 if home_goals == away_goals else 2
        one_hot = tuple(float(index == outcome) for index in range(3))
        losses.append(
            (
                -math.log(max(joint_probability, 1e-15)),
                -math.log(max(result_probabilities[outcome], 1e-15)),
                sum(
                    (probability - actual) ** 2
                    for probability, actual in zip(result_probabilities, one_hot, strict=True)
                ),
            )
        )
    if not losses:
        raise ValueError("no eligible rows for cold-start evaluation")
    return ColdStartDevelopmentMetrics(
        target_count=len(losses),
        joint_score_log_loss=sum(item[0] for item in losses) / len(losses),
        result_log_loss=sum(item[1] for item in losses) / len(losses),
        multiclass_brier=sum(item[2] for item in losses) / len(losses),
    )


def _design_row(
    observation: ColdStartDevelopmentObservation, config: ColdStartConfig
) -> tuple[tuple[float, ...], float, float, int, int]:
    snapshot = observation.snapshot
    estimator = ColdStartStrengthV1(config)
    home = estimator.estimate(snapshot, snapshot.home_team_id)
    away = estimator.estimate(snapshot, snapshot.away_team_id)
    mean = (home.competition_goal_mean + away.competition_goal_mean) / 2.0
    return (
        transferable_context_features(snapshot),
        math.log(mean + 0.05) + home.attack_log_strength + away.defence_log_strength,
        math.log(mean + 0.05) + away.attack_log_strength + home.defence_log_strength,
        observation.home_goals,
        observation.away_goals,
    )


def _dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True)) if right else 0.0


def _result_probabilities(home_lambda: float, away_lambda: float) -> tuple[float, float, float]:
    support = 20
    home = draw = away = 0.0
    for home_goals in range(support):
        for away_goals in range(support):
            probability = float(poisson.pmf(home_goals, home_lambda)) * float(
                poisson.pmf(away_goals, away_lambda)
            )
            if home_goals > away_goals:
                home += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away += probability
    total = home + draw + away
    if total <= 0 or not math.isfinite(total):
        raise ValueError("invalid development result distribution")
    return home / total, draw / total, away / total
