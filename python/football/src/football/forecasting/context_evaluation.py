"""Frozen development evaluation rules for contextual feature families."""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import numpy as np

from football.context.live import (
    AvailabilityState,
    LineupObservation,
    LineupRole,
    PredictedLineupV1,
    PredictionConfidence,
)
from football.forecasting.contextual_goal import (
    BOOTSTRAP_BLOCK_LENGTH,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    FamilyDisposition,
    FeatureFamily,
)


class DevelopmentPartition(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    DEVELOPMENT_HOLDOUT = "DEVELOPMENT_HOLDOUT"


@dataclass(frozen=True, slots=True)
class LineupValidationCase:
    fixture_id: UUID
    predicted: PredictedLineupV1
    naive_previous_starters: tuple[UUID, ...]
    confirmed: LineupObservation
    unavailable_previous_starters: Mapping[UUID, AvailabilityState]


@dataclass(frozen=True, slots=True)
class LineupPredictorReport:
    sample_count: int
    mean_correct_starters: float
    median_correct_starters: float
    exact_xi_rate: float
    formation_accuracy: float
    injured_starter_removal_accuracy: float | None
    suspended_starter_removal_accuracy: float | None
    replacement_player_accuracy: float | None
    exact_position_replacement_accuracy: float | None
    naive_mean_correct_starters: float
    naive_replacement_player_accuracy: float
    coverage_by_confidence: tuple[tuple[PredictionConfidence, int], ...]
    admitted: bool


@dataclass(frozen=True, slots=True)
class TargetDelta:
    fixture_id: UUID
    kickoff_at: datetime
    domain: str
    joint_log_loss: float
    one_x_two_log_loss: float
    brier: float
    rps: float
    crps: float


@dataclass(frozen=True, slots=True)
class MetricDelta:
    point: float
    confidence_interval_95: tuple[float, float]


@dataclass(frozen=True, slots=True)
class CoverageReport:
    baseline_eligible_targets: int
    context_qualified_targets: int
    missing_context_targets: int
    forecasted_targets: int

    @property
    def coverage(self) -> float:
        if self.baseline_eligible_targets == 0:
            return 0.0
        return self.context_qualified_targets / self.baseline_eligible_targets

    def __post_init__(self) -> None:
        if self.forecasted_targets != self.baseline_eligible_targets:
            raise ValueError("context missingness must not reduce baseline forecast coverage")
        if (
            self.context_qualified_targets + self.missing_context_targets
            != self.baseline_eligible_targets
        ):
            raise ValueError("context coverage counts must partition baseline targets")


@dataclass(frozen=True, slots=True)
class FamilyDevelopmentResult:
    family: FeatureFamily
    disposition: FamilyDisposition
    coverage: CoverageReport
    metrics: tuple[tuple[str, MetricDelta], ...] = ()
    domain_joint_log_loss: tuple[tuple[str, float], ...] = ()
    reason: str | None = None


def validate_lineup_predictor(cases: tuple[LineupValidationCase, ...]) -> LineupPredictorReport:
    if not cases:
        raise ValueError("lineup predictor validation requires qualified cases")
    correct: list[int] = []
    naive_correct: list[int] = []
    formations: list[bool] = []
    replacement_hits: list[bool] = []
    exact_position_hits: list[bool] = []
    injury_removals: list[bool] = []
    suspension_removals: list[bool] = []
    confidence = {level: 0 for level in PredictionConfidence}
    for case in cases:
        predicted_ids = {row.player_id for row in case.predicted.starters}
        confirmed_ids = {
            row.canonical_player_id
            for row in case.confirmed.players
            if row.role is LineupRole.STARTER
        }
        naive_ids = set(case.naive_previous_starters)
        correct.append(len(predicted_ids & confirmed_ids))
        naive_correct.append(len(naive_ids & confirmed_ids))
        formations.append(case.predicted.formation == case.confirmed.formation)
        confidence[case.predicted.confidence] += 1
        for player_id, state in case.unavailable_previous_starters.items():
            removed = player_id not in predicted_ids
            if state is AvailabilityState.UNAVAILABLE_INJURY:
                injury_removals.append(removed)
            elif state is AvailabilityState.UNAVAILABLE_SUSPENSION:
                suspension_removals.append(removed)
        for starter in case.predicted.starters:
            if starter.replaced_player_id is None:
                continue
            replacement_hits.append(starter.player_id in confirmed_ids)
            if starter.normalized_position:
                actual_positions = {
                    row.normalized_position
                    for row in case.confirmed.players
                    if row.role is LineupRole.STARTER
                    and row.canonical_player_id == starter.player_id
                }
                exact_position_hits.append(starter.normalized_position in actual_positions)
    replacement_accuracy = _mean_bool(replacement_hits)
    mean_correct = statistics.fmean(correct)
    naive_mean = statistics.fmean(naive_correct)
    return LineupPredictorReport(
        sample_count=len(cases),
        mean_correct_starters=mean_correct,
        median_correct_starters=float(statistics.median(correct)),
        exact_xi_rate=statistics.fmean(value == 11 for value in correct),
        formation_accuracy=statistics.fmean(formations),
        injured_starter_removal_accuracy=_mean_bool(injury_removals),
        suspended_starter_removal_accuracy=_mean_bool(suspension_removals),
        replacement_player_accuracy=replacement_accuracy,
        exact_position_replacement_accuracy=_mean_bool(exact_position_hits),
        naive_mean_correct_starters=naive_mean,
        naive_replacement_player_accuracy=0.0,
        coverage_by_confidence=tuple((level, confidence[level]) for level in PredictionConfidence),
        admitted=(
            mean_correct > naive_mean
            and replacement_accuracy is not None
            and replacement_accuracy > 0.0
        ),
    )


def chronological_partitions(
    values: tuple[tuple[UUID, datetime], ...],
) -> dict[UUID, DevelopmentPartition]:
    """Split 60/20/20 while keeping every same-kickoff batch intact."""
    if not values:
        raise ValueError("development split requires targets")
    batches: dict[datetime, list[UUID]] = defaultdict(list)
    for fixture_id, kickoff_at in values:
        if kickoff_at.tzinfo is None or kickoff_at.utcoffset() is None:
            raise ValueError("kickoff_at must include a timezone")
        batches[kickoff_at].append(fixture_id)
    ordered = tuple(
        (kickoff, tuple(sorted(ids, key=str))) for kickoff, ids in sorted(batches.items())
    )
    train_boundary = len(values) * 0.6
    validation_boundary = len(values) * 0.8
    result: dict[UUID, DevelopmentPartition] = {}
    count = 0
    for _kickoff, identifiers in ordered:
        partition = (
            DevelopmentPartition.TRAIN
            if count < train_boundary
            else DevelopmentPartition.VALIDATION
            if count < validation_boundary
            else DevelopmentPartition.DEVELOPMENT_HOLDOUT
        )
        result.update({identifier: partition for identifier in identifiers})
        count += len(identifiers)
    return result


def evaluate_family_admission(
    family: FeatureFamily,
    deltas: tuple[TargetDelta, ...],
    coverage: CoverageReport,
) -> FamilyDevelopmentResult:
    if not deltas:
        return FamilyDevelopmentResult(
            family,
            FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE,
            coverage,
            reason="no qualified development-holdout targets",
        )
    metric_names = ("joint_log_loss", "one_x_two_log_loss", "brier", "rps", "crps")
    metrics = tuple((name, _metric_delta(deltas, name)) for name in metric_names)
    by_name = dict(metrics)
    domains = tuple(
        (domain, statistics.fmean(row.joint_log_loss for row in deltas if row.domain == domain))
        for domain in sorted({row.domain for row in deltas})
    )
    negative_domains = sum(value < 0.0 for _domain, value in domains)
    domain_gate = all(value <= 0.02 for _domain, value in domains)
    if len(domains) >= 3:
        domain_gate = domain_gate and negative_domains >= 3
    accepted = (
        by_name["joint_log_loss"].point <= -0.003
        and by_name["joint_log_loss"].confidence_interval_95[1] < 0.0
        and by_name["one_x_two_log_loss"].point <= 0.0
        and by_name["brier"].confidence_interval_95[1] <= 0.01
        and by_name["rps"].confidence_interval_95[1] <= 0.01
        and by_name["crps"].confidence_interval_95[1] <= 0.02
        and domain_gate
    )
    return FamilyDevelopmentResult(
        family,
        (
            FamilyDisposition.DEVELOPMENT_ACCEPTED
            if accepted
            else FamilyDisposition.DEVELOPMENT_REJECTED
        ),
        coverage,
        metrics,
        domains,
    )


def coverage_gate(
    family: FeatureFamily,
    coverage: CoverageReport,
    *,
    competition_domains: int,
) -> FamilyDisposition | None:
    if family is FeatureFamily.MANAGER and (
        coverage.context_qualified_targets < 300
        or competition_domains < 3
        or coverage.coverage < 0.70
    ):
        return FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE
    if family is FeatureFamily.TRAVEL and (
        coverage.context_qualified_targets < 500
        or competition_domains < 3
        or coverage.coverage < 0.80
    ):
        return FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE
    return None


def _metric_delta(rows: tuple[TargetDelta, ...], name: str) -> MetricDelta:
    values = tuple(float(getattr(row, name)) for row in rows)
    point = statistics.fmean(values)
    return MetricDelta(point, _moving_block_interval(rows, values))


def _moving_block_interval(
    rows: tuple[TargetDelta, ...], values: tuple[float, ...]
) -> tuple[float, float]:
    grouped: dict[datetime, list[float]] = defaultdict(list)
    for row, value in zip(rows, values, strict=True):
        grouped[row.kickoff_at].append(value)
    batches = tuple(tuple(grouped[key]) for key in sorted(grouped))
    if len(batches) < BOOTSTRAP_BLOCK_LENGTH:
        point = statistics.fmean(values)
        return point, point
    blocks = tuple(
        tuple(value for batch in batches[start : start + BOOTSTRAP_BLOCK_LENGTH] for value in batch)
        for start in range(len(batches) - BOOTSTRAP_BLOCK_LENGTH + 1)
    )
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = []
    for _ in range(BOOTSTRAP_REPLICATES):
        selected: list[float] = []
        while len(selected) < len(values):
            selected.extend(blocks[int(rng.integers(0, len(blocks)))])
        samples.append(statistics.fmean(selected[: len(values)]))
    lower, upper = np.quantile(np.array(samples, dtype=float), (0.025, 0.975))
    return float(lower), float(upper)


def _mean_bool(values: list[bool]) -> float | None:
    return statistics.fmean(values) if values else None
