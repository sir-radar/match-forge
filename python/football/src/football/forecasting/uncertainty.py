from __future__ import annotations

import math
import random
from dataclasses import dataclass


class BootstrapContractError(ValueError):
    """Paired bootstrap configuration or metric series is invalid."""


@dataclass(frozen=True, slots=True)
class BootstrapPolicyV1:
    replicates: int = 2_000
    block_size: int = 10
    confidence_level: float = 0.95
    seed: int = 20_260_831
    method: str = "paired-chronological-moving-block-v1"

    def __post_init__(self) -> None:
        if self.method != "paired-chronological-moving-block-v1":
            raise BootstrapContractError("unsupported bootstrap method")
        for field_name, value in (
            ("replicates", self.replicates),
            ("block_size", self.block_size),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise BootstrapContractError(f"{field_name} must be a positive integer")
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or not 0.0 < self.confidence_level < 1.0
        ):
            raise BootstrapContractError("bootstrap seed and confidence level are invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "replicates": self.replicates,
            "block_size": self.block_size,
            "confidence_level": self.confidence_level,
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class PairedMetricSeriesV1:
    comparison: str
    metric: str
    candidate: tuple[float, ...]
    reference: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.comparison or not self.metric:
            raise BootstrapContractError("bootstrap comparison and metric must not be empty")
        if not self.candidate or len(self.candidate) != len(self.reference):
            raise BootstrapContractError("bootstrap candidate and reference must be aligned")
        if any(not math.isfinite(value) for value in (*self.candidate, *self.reference)):
            raise BootstrapContractError("bootstrap metric values must be finite")


@dataclass(frozen=True, slots=True)
class MetricDeltaIntervalV1:
    comparison: str
    metric: str
    point_delta: float
    lower_bound: float
    upper_bound: float
    replicate_deltas: tuple[float, ...]

    def to_dict(self, *, include_replicates: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "comparison": self.comparison,
            "metric": self.metric,
            "point_delta": self.point_delta,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
        }
        if include_replicates:
            payload["replicate_deltas"] = list(self.replicate_deltas)
        return payload


@dataclass(frozen=True, slots=True)
class Sprint2BootstrapResultV1:
    policy: BootstrapPolicyV1
    sample_count: int
    intervals: tuple[MetricDeltaIntervalV1, ...]
    contract: str = "Sprint2BootstrapResultV1"

    def __post_init__(self) -> None:
        if self.contract != "Sprint2BootstrapResultV1":
            raise BootstrapContractError("unsupported bootstrap result contract")
        if self.sample_count <= 0 or not self.intervals:
            raise BootstrapContractError("bootstrap result requires samples and intervals")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "policy": self.policy.to_dict(),
            "sample_count": self.sample_count,
            "intervals": [interval.to_dict() for interval in self.intervals],
        }


def paired_moving_block_bootstrap(
    series: tuple[PairedMetricSeriesV1, ...],
    policy: BootstrapPolicyV1 | None = None,
) -> Sprint2BootstrapResultV1:
    if not series:
        raise BootstrapContractError("paired bootstrap requires metric series")
    resolved = policy or BootstrapPolicyV1()
    sample_count = len(series[0].candidate)
    if any(len(item.candidate) != sample_count for item in series):
        raise BootstrapContractError("paired bootstrap series must share one target population")
    if resolved.block_size > sample_count:
        raise BootstrapContractError("bootstrap block size exceeds sample count")
    samples = _resamples(sample_count, resolved)
    tail = (1.0 - resolved.confidence_level) / 2.0
    intervals = tuple(_interval(item, samples, tail) for item in series)
    return Sprint2BootstrapResultV1(resolved, sample_count, intervals)


def _resamples(sample_count: int, policy: BootstrapPolicyV1) -> tuple[tuple[int, ...], ...]:
    randomizer = random.Random(policy.seed)
    maximum_start = sample_count - policy.block_size
    samples: list[tuple[int, ...]] = []
    for _ in range(policy.replicates):
        indices: list[int] = []
        while len(indices) < sample_count:
            start = randomizer.randrange(maximum_start + 1)
            indices.extend(range(start, start + policy.block_size))
        samples.append(tuple(indices[:sample_count]))
    return tuple(samples)


def _interval(
    series: PairedMetricSeriesV1,
    samples: tuple[tuple[int, ...], ...],
    tail: float,
) -> MetricDeltaIntervalV1:
    deltas = tuple(
        sum(series.candidate[index] - series.reference[index] for index in sample) / len(sample)
        for sample in samples
    )
    ordered = tuple(sorted(deltas))
    return MetricDeltaIntervalV1(
        comparison=series.comparison,
        metric=series.metric,
        point_delta=sum(
            candidate - reference
            for candidate, reference in zip(series.candidate, series.reference, strict=True)
        )
        / len(series.candidate),
        lower_bound=_quantile(ordered, tail),
        upper_bound=_quantile(ordered, 1.0 - tail),
        replicate_deltas=deltas,
    )


def _quantile(ordered: tuple[float, ...], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
