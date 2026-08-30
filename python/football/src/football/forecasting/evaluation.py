from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from football.forecasting.contracts import MatchResultProbabilitiesV1

MatchOutcome = Literal["HOME", "DRAW", "AWAY"]
_OUTCOMES: tuple[MatchOutcome, ...] = ("HOME", "DRAW", "AWAY")
_EPSILON = 1e-15


class EvaluationContractError(ValueError):
    """Evaluation input, chronology, or policy is invalid."""


@dataclass(frozen=True, slots=True)
class EvaluatedMatchResultV1:
    kickoff_at: datetime
    prediction_cutoff: datetime
    outcome_known_at: datetime
    probabilities: MatchResultProbabilitiesV1
    outcome: MatchOutcome

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        _aware(self.prediction_cutoff, "prediction_cutoff")
        _aware(self.outcome_known_at, "outcome_known_at")
        if self.prediction_cutoff > self.kickoff_at:
            raise EvaluationContractError("prediction_cutoff must not follow kickoff_at")
        if self.outcome_known_at < self.kickoff_at:
            raise EvaluationContractError("outcome_known_at must not precede kickoff_at")
        if self.outcome not in _OUTCOMES:
            raise EvaluationContractError("unsupported match outcome")


@dataclass(frozen=True, slots=True)
class ReliabilityBinV1:
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_probability: float | None
    observed_frequency: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "sample_count": self.sample_count,
            "mean_probability": self.mean_probability,
            "observed_frequency": self.observed_frequency,
        }


@dataclass(frozen=True, slots=True)
class BrierDecompositionV1:
    uncertainty: float
    resolution: float
    reliability: float

    def to_dict(self) -> dict[str, float]:
        return {
            "uncertainty": self.uncertainty,
            "resolution": self.resolution,
            "reliability": self.reliability,
        }


@dataclass(frozen=True, slots=True)
class MatchResultMetricsV1:
    sample_count: int
    log_loss: float
    brier_score: float
    ranked_probability_score: float
    accuracy: float
    expected_calibration_error: float
    brier_decomposition: BrierDecompositionV1
    reliability_bins: tuple[ReliabilityBinV1, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "log_loss": self.log_loss,
            "brier_score": self.brier_score,
            "ranked_probability_score": self.ranked_probability_score,
            "accuracy": self.accuracy,
            "expected_calibration_error": self.expected_calibration_error,
            "brier_decomposition": self.brier_decomposition.to_dict(),
            "reliability_bins": [bin.to_dict() for bin in self.reliability_bins],
        }


@dataclass(frozen=True, slots=True)
class WalkForwardWindowV1:
    training_start: datetime
    training_end: datetime
    evaluation_start: datetime
    evaluation_end: datetime

    def __post_init__(self) -> None:
        for field_name, value in (
            ("training_start", self.training_start),
            ("training_end", self.training_end),
            ("evaluation_start", self.evaluation_start),
            ("evaluation_end", self.evaluation_end),
        ):
            _aware(value, field_name)
        if not self.training_start < self.training_end <= self.evaluation_start:
            raise EvaluationContractError("training window must end before evaluation starts")
        if self.evaluation_start >= self.evaluation_end:
            raise EvaluationContractError("evaluation window must be non-empty")


@dataclass(frozen=True, slots=True)
class WalkForwardPolicyV1:
    initial_training_duration: timedelta
    evaluation_duration: timedelta
    retraining_frequency: timedelta
    rolling_training_duration: timedelta | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("initial_training_duration", self.initial_training_duration),
            ("evaluation_duration", self.evaluation_duration),
            ("retraining_frequency", self.retraining_frequency),
        ):
            if value <= timedelta(0):
                raise EvaluationContractError(f"{field_name} must be positive")
        if (
            self.rolling_training_duration is not None
            and self.rolling_training_duration <= timedelta(0)
        ):
            raise EvaluationContractError("rolling_training_duration must be positive")


class WalkForwardEvaluator:
    def __init__(self, policy: WalkForwardPolicyV1) -> None:
        self.policy = policy

    def windows(self, start: datetime, end: datetime) -> tuple[WalkForwardWindowV1, ...]:
        _aware(start, "start")
        _aware(end, "end")
        if start >= end:
            raise EvaluationContractError("walk-forward range must be non-empty")
        evaluation_start = start + self.policy.initial_training_duration
        windows: list[WalkForwardWindowV1] = []
        while evaluation_start < end:
            evaluation_end = min(evaluation_start + self.policy.evaluation_duration, end)
            training_start = start
            if self.policy.rolling_training_duration is not None:
                training_start = max(
                    start, evaluation_start - self.policy.rolling_training_duration
                )
            windows.append(
                WalkForwardWindowV1(
                    training_start=training_start,
                    training_end=evaluation_start,
                    evaluation_start=evaluation_start,
                    evaluation_end=evaluation_end,
                )
            )
            evaluation_start += self.policy.retraining_frequency
        return tuple(windows)

    @staticmethod
    def chronological_batches(
        observations: tuple[EvaluatedMatchResultV1, ...],
    ) -> tuple[tuple[EvaluatedMatchResultV1, ...], ...]:
        ordered = sorted(observations, key=lambda item: item.kickoff_at)
        batches: list[list[EvaluatedMatchResultV1]] = []
        for observation in ordered:
            if not batches or batches[-1][0].kickoff_at != observation.kickoff_at:
                batches.append([observation])
            else:
                batches[-1].append(observation)
        return tuple(tuple(batch) for batch in batches)


def evaluate_match_results(
    observations: tuple[EvaluatedMatchResultV1, ...], *, bin_count: int = 10
) -> MatchResultMetricsV1:
    if not observations:
        raise EvaluationContractError("match-result evaluation requires observations")
    if isinstance(bin_count, bool) or not isinstance(bin_count, int) or bin_count < 2:
        raise EvaluationContractError("bin_count must be an integer of at least 2")
    losses: list[float] = []
    brier_scores: list[float] = []
    ranked_scores: list[float] = []
    correct = 0
    samples: list[tuple[float, float, int]] = []
    base_counts = {outcome: 0 for outcome in _OUTCOMES}
    for observation in observations:
        probabilities = _probabilities(observation.probabilities)
        actual = _actual(observation.outcome)
        outcome_index = _OUTCOMES.index(observation.outcome)
        losses.append(-math.log(max(probabilities[outcome_index], _EPSILON)))
        brier_scores.append(
            sum(
                (probability - target) ** 2
                for probability, target in zip(probabilities, actual, strict=True)
            )
        )
        ranked_scores.append(
            sum((sum(probabilities[:index]) - sum(actual[:index])) ** 2 for index in (1, 2)) / 2.0
        )
        predicted_index = max(range(3), key=probabilities.__getitem__)
        correct += int(predicted_index == outcome_index)
        base_counts[observation.outcome] += 1
        samples.extend(
            (probability, target, class_index)
            for class_index, (probability, target) in enumerate(
                zip(probabilities, actual, strict=True)
            )
        )
    reliability_bins = _reliability_bins(samples, bin_count)
    ece = sum(
        bin.sample_count
        / len(samples)
        * abs((bin.mean_probability or 0.0) - (bin.observed_frequency or 0.0))
        for bin in reliability_bins
    )
    decomposition = _brier_decomposition(samples, base_counts, len(observations), bin_count)
    count = len(observations)
    return MatchResultMetricsV1(
        sample_count=count,
        log_loss=sum(losses) / count,
        brier_score=sum(brier_scores) / count,
        ranked_probability_score=sum(ranked_scores) / count,
        accuracy=correct / count,
        expected_calibration_error=ece,
        brier_decomposition=decomposition,
        reliability_bins=reliability_bins,
    )


def _reliability_bins(
    samples: list[tuple[float, float, int]], bin_count: int
) -> tuple[ReliabilityBinV1, ...]:
    grouped: list[list[tuple[float, float]]] = [[] for _ in range(bin_count)]
    for probability, target, _class_index in samples:
        index = min(int(probability * bin_count), bin_count - 1)
        grouped[index].append((probability, target))
    return tuple(
        ReliabilityBinV1(
            lower_bound=index / bin_count,
            upper_bound=(index + 1) / bin_count,
            sample_count=len(values),
            mean_probability=(sum(value[0] for value in values) / len(values) if values else None),
            observed_frequency=(
                sum(value[1] for value in values) / len(values) if values else None
            ),
        )
        for index, values in enumerate(grouped)
    )


def _brier_decomposition(
    samples: list[tuple[float, float, int]],
    base_counts: dict[MatchOutcome, int],
    observation_count: int,
    bin_count: int,
) -> BrierDecompositionV1:
    base_rates = tuple(base_counts[outcome] / observation_count for outcome in _OUTCOMES)
    uncertainty = sum(rate * (1.0 - rate) for rate in base_rates)
    reliability = 0.0
    resolution = 0.0
    for class_index, base_rate in enumerate(base_rates):
        class_samples = [sample for sample in samples if sample[2] == class_index]
        bins = _reliability_bins(class_samples, bin_count)
        for bin in bins:
            if bin.sample_count == 0:
                continue
            weight = bin.sample_count / observation_count
            mean_probability = bin.mean_probability or 0.0
            observed_frequency = bin.observed_frequency or 0.0
            reliability += weight * (mean_probability - observed_frequency) ** 2
            resolution += weight * (observed_frequency - base_rate) ** 2
    return BrierDecompositionV1(
        uncertainty=uncertainty,
        resolution=resolution,
        reliability=reliability,
    )


def _probabilities(value: MatchResultProbabilitiesV1) -> tuple[float, float, float]:
    return value.home, value.draw, value.away


def _actual(outcome: MatchOutcome) -> tuple[float, float, float]:
    if outcome == "HOME":
        return 1.0, 0.0, 0.0
    if outcome == "DRAW":
        return 0.0, 1.0, 0.0
    return 0.0, 0.0, 1.0


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvaluationContractError(f"{field_name} must include a timezone")
