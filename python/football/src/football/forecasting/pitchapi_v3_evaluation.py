"""Frozen domain aggregation and uncertainty rules for PitchAPI V3."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from football.forecasting.dixon_coles import GoalForecast

EXPECTED_TARGETS = {
    "bundesliga_2022_23": 216,
    "bundesliga_2023_24": 216,
    "ligue1_2022_23": 280,
}
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20_260_924
BLOCK_LENGTH = 10


class PitchApiV3EvaluationError(ValueError):
    """Evaluation input violates frozen V3 metric rules."""


@dataclass(frozen=True, slots=True)
class DomainMetricSeriesV1:
    reference: tuple[float, ...]
    challenger: tuple[float, ...]
    kickoff_batches: tuple[int, ...]

    def __post_init__(self) -> None:
        count = len(self.reference)
        if count == 0 or len(self.challenger) != count or len(self.kickoff_batches) != count:
            raise PitchApiV3EvaluationError("paired domain metric series is misaligned")
        if any(not math.isfinite(value) for value in (*self.reference, *self.challenger)):
            raise PitchApiV3EvaluationError("domain metric values must be finite")
        if tuple(sorted(self.kickoff_batches)) != self.kickoff_batches:
            raise PitchApiV3EvaluationError("kickoff batches must be chronological")

    @classmethod
    def synthetic(cls, count: int, delta: float) -> DomainMetricSeriesV1:
        return cls(
            reference=(1.0,) * count,
            challenger=(1.0 + delta,) * count,
            kickoff_batches=tuple(range(count)),
        )

    @property
    def point_delta(self) -> float:
        return sum(
            challenger - reference
            for reference, challenger in zip(self.reference, self.challenger, strict=True)
        ) / len(self.reference)


@dataclass(frozen=True, slots=True)
class AggregateDomainMetricV1:
    macro_delta: float
    weighted_delta: float


@dataclass(frozen=True, slots=True)
class DomainBootstrapV1:
    domain_replicates: dict[str, tuple[float, ...]]
    macro_replicates: tuple[float, ...]
    weighted_replicates: tuple[float, ...]
    domain_intervals: dict[str, tuple[float, float]]
    macro_interval: tuple[float, float]
    weighted_interval: tuple[float, float]


@dataclass(frozen=True, slots=True)
class ExactScoreDistributionV1:
    atoms: tuple[tuple[int, int, float], ...]
    unresolved_tail: float

    def __post_init__(self) -> None:
        probabilities = tuple(atom[2] for atom in self.atoms)
        if not self.atoms or any(
            not math.isfinite(value) or value < 0.0
            for value in (*probabilities, self.unresolved_tail)
        ):
            raise PitchApiV3EvaluationError("score distribution contains invalid probabilities")
        if self.unresolved_tail > 1e-12:
            raise PitchApiV3EvaluationError("score distribution tail exceeds 1e-12")
        if abs(sum(probabilities) + self.unresolved_tail - 1.0) > 1e-12:
            raise PitchApiV3EvaluationError("score distribution does not normalize")


@dataclass(frozen=True, slots=True)
class TargetScoresV1:
    joint_score_log_loss: float
    one_x_two_log_loss: float
    one_x_two_brier: float
    one_x_two_rps: float
    total_goal_crps: float
    expected_total_goal_mae: float
    exact_score_top_1: float
    exact_score_top_3: float
    exact_score_top_5: float

    def to_dict(self) -> dict[str, float]:
        return {
            "exact_score_top_1": self.exact_score_top_1,
            "exact_score_top_3": self.exact_score_top_3,
            "exact_score_top_5": self.exact_score_top_5,
            "expected_total_goal_mae": self.expected_total_goal_mae,
            "joint_score_log_loss": self.joint_score_log_loss,
            "one_x_two_brier": self.one_x_two_brier,
            "one_x_two_log_loss": self.one_x_two_log_loss,
            "one_x_two_rps": self.one_x_two_rps,
            "total_goal_crps": self.total_goal_crps,
        }


@dataclass(frozen=True, slots=True)
class CalibrationFitV1:
    intercept: float
    slope: float
    intercept_standard_error: float
    slope_standard_error: float
    converged: bool


def exact_distribution(forecast: GoalForecast) -> ExactScoreDistributionV1:
    atoms: list[tuple[int, int, float]] = []
    support = 8
    while support <= 100:
        atoms = [
            (home, away, forecast.exact_score_probability(home, away))
            for home in range(support + 1)
            for away in range(support + 1)
        ]
        tail = 1.0 - sum(atom[2] for atom in atoms)
        if -1e-12 <= tail <= 1e-12:
            return ExactScoreDistributionV1(tuple(atoms), max(0.0, tail))
        support += 4
    raise PitchApiV3EvaluationError("exact score support did not reach tail tolerance")


def score_target(
    distribution: ExactScoreDistributionV1, *, home_goals: int, away_goals: int
) -> TargetScoresV1:
    lookup = {(home, away): probability for home, away, probability in distribution.atoms}
    observed = lookup.get((home_goals, away_goals), 0.0)
    if observed <= 0.0:
        raise PitchApiV3EvaluationError("observed exact score has zero probability")
    one_x_two = _one_x_two(distribution)
    actual_class = 2 if home_goals > away_goals else 1 if home_goals == away_goals else 0
    actual = tuple(float(index == actual_class) for index in range(3))
    one_x_two_probability = one_x_two[actual_class]
    if one_x_two_probability <= 0.0:
        raise PitchApiV3EvaluationError("observed 1X2 class has zero probability")
    cumulative_forecast = (one_x_two[0], one_x_two[0] + one_x_two[1])
    cumulative_actual = (actual[0], actual[0] + actual[1])
    total_probabilities = _total_probabilities(distribution)
    observed_total = home_goals + away_goals
    crps = 0.0
    cumulative = 0.0
    for total, probability in enumerate(total_probabilities):
        cumulative += probability
        crps += (cumulative - float(observed_total <= total)) ** 2
    ranked = sorted(distribution.atoms, key=lambda atom: (-atom[2], atom[0], atom[1]))
    observed_score = (home_goals, away_goals)
    return TargetScoresV1(
        joint_score_log_loss=-math.log(observed),
        one_x_two_log_loss=-math.log(one_x_two_probability),
        one_x_two_brier=sum(
            (probability - target) ** 2
            for probability, target in zip(one_x_two, actual, strict=True)
        ),
        one_x_two_rps=sum(
            (forecast_value - actual_value) ** 2
            for forecast_value, actual_value in zip(
                cumulative_forecast, cumulative_actual, strict=True
            )
        )
        / 2.0,
        total_goal_crps=crps,
        expected_total_goal_mae=abs(
            sum(total * probability for total, probability in enumerate(total_probabilities))
            - observed_total
        ),
        exact_score_top_1=float(observed_score in {(row[0], row[1]) for row in ranked[:1]}),
        exact_score_top_3=float(observed_score in {(row[0], row[1]) for row in ranked[:3]}),
        exact_score_top_5=float(observed_score in {(row[0], row[1]) for row in ranked[:5]}),
    )


def calibration_fit(
    probabilities: tuple[float, ...], outcomes: tuple[int, ...]
) -> CalibrationFitV1:
    if not probabilities or len(probabilities) != len(outcomes):
        raise PitchApiV3EvaluationError("calibration inputs are empty or misaligned")
    if any(not 0.0 < value < 1.0 for value in probabilities):
        raise PitchApiV3EvaluationError("calibration probabilities must be inside (0,1)")
    if set(outcomes) != {0, 1}:
        raise PitchApiV3EvaluationError("calibration outcome must contain both classes")
    logits = np.asarray([math.log(value / (1.0 - value)) for value in probabilities])
    targets = np.asarray(outcomes, dtype=float)

    def objective(values: np.ndarray) -> tuple[float, np.ndarray]:
        linear = values[0] + values[1] * logits
        fitted = 1.0 / (1.0 + np.exp(-linear))
        loss = float(np.sum(np.logaddexp(0.0, linear) - targets * linear))
        gradient = np.asarray([np.sum(fitted - targets), np.sum((fitted - targets) * logits)])
        return loss, gradient

    result = minimize(objective, np.asarray([0.0, 1.0]), jac=True, method="BFGS")
    if not result.success or not np.all(np.isfinite(result.x)):
        raise PitchApiV3EvaluationError("calibration fit did not converge")
    covariance = np.asarray(result.hess_inv)
    standard_errors = np.sqrt(np.diag(covariance))
    if not np.all(np.isfinite(standard_errors)):
        raise PitchApiV3EvaluationError("calibration standard errors are invalid")
    return CalibrationFitV1(
        intercept=float(result.x[0]),
        slope=float(result.x[1]),
        intercept_standard_error=float(standard_errors[0]),
        slope_standard_error=float(standard_errors[1]),
        converged=True,
    )


def reliability_diagram(
    probabilities: tuple[float, ...], outcomes: tuple[int, ...]
) -> tuple[dict[str, float | int | None], ...]:
    if len(probabilities) != len(outcomes):
        raise PitchApiV3EvaluationError("reliability inputs are misaligned")
    bins: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        if not 0.0 <= probability <= 1.0 or outcome not in (0, 1):
            raise PitchApiV3EvaluationError("reliability input is invalid")
        bins[min(int(probability * 10), 9)].append((probability, outcome))
    return tuple(
        {
            "lower": index / 10.0,
            "mean_forecast": (sum(row[0] for row in values) / len(values) if values else None),
            "observed_rate": (sum(row[1] for row in values) / len(values) if values else None),
            "target_count": len(values),
            "upper": (index + 1) / 10.0,
        }
        for index, values in enumerate(bins)
    )


def descriptive_target_metrics(
    distribution: ExactScoreDistributionV1, *, home_goals: int, away_goals: int
) -> dict[str, object]:
    total = home_goals + away_goals
    binary: dict[str, object] = {}
    events = {
        "btts": (
            sum(value for home, away, value in distribution.atoms if home > 0 and away > 0),
            int(home_goals > 0 and away_goals > 0),
        ),
        **{
            name: values
            for threshold in range(5)
            for name, values in (
                (
                    f"over_{threshold}.5",
                    (
                        sum(
                            value
                            for home, away, value in distribution.atoms
                            if home + away > threshold
                        ),
                        int(total > threshold),
                    ),
                ),
                (
                    f"under_{threshold}.5",
                    (
                        sum(
                            value
                            for home, away, value in distribution.atoms
                            if home + away <= threshold
                        ),
                        int(total <= threshold),
                    ),
                ),
            )
        },
    }
    for name, (probability, outcome) in events.items():
        if not 0.0 < probability < 1.0:
            raise PitchApiV3EvaluationError("binary market probability must be inside (0,1)")
        binary[name] = {
            "brier": (probability - outcome) ** 2,
            "log_loss": -(
                outcome * math.log(probability) + (1 - outcome) * math.log(1.0 - probability)
            ),
            "outcome": outcome,
            "probability": probability,
        }
    totals = _total_probabilities(distribution)
    return {
        "binary_markets": binary,
        "prediction_intervals": {
            "50": _prediction_interval(totals, total, 0.5),
            "90": _prediction_interval(totals, total, 0.9),
        },
        "score_support_maximum": max(home + away for home, away, _ in distribution.atoms),
        "unresolved_tail": distribution.unresolved_tail,
    }


def binary_auc(probabilities: tuple[float, ...], outcomes: tuple[int, ...]) -> float | None:
    positives = [value for value, outcome in zip(probabilities, outcomes, strict=True) if outcome]
    negatives = [
        value for value, outcome in zip(probabilities, outcomes, strict=True) if not outcome
    ]
    if not positives or not negatives:
        return None
    favourable = 0.0
    for positive in positives:
        for negative in negatives:
            favourable += float(positive > negative) + 0.5 * float(positive == negative)
    return favourable / (len(positives) * len(negatives))


def _one_x_two(distribution: ExactScoreDistributionV1) -> tuple[float, float, float]:
    away = sum(probability for home, goals, probability in distribution.atoms if home < goals)
    draw = sum(probability for home, goals, probability in distribution.atoms if home == goals)
    home = sum(
        probability for goals, away_goals, probability in distribution.atoms if goals > away_goals
    )
    return away, draw, home


def _total_probabilities(distribution: ExactScoreDistributionV1) -> tuple[float, ...]:
    maximum = max(home + away for home, away, _ in distribution.atoms)
    totals = [0.0] * (maximum + 1)
    for home, away, probability in distribution.atoms:
        totals[home + away] += probability
    return tuple(totals)


def _prediction_interval(
    probabilities: tuple[float, ...], observed: int, level: float
) -> dict[str, float | int]:
    lower_probability = (1.0 - level) / 2.0
    upper_probability = 1.0 - lower_probability
    cumulative = 0.0
    lower: int | None = None
    upper: int | None = None
    for value, probability in enumerate(probabilities):
        cumulative += probability
        if lower is None and cumulative >= lower_probability:
            lower = value
        if cumulative >= upper_probability:
            upper = value
            break
    if lower is None or upper is None:
        raise PitchApiV3EvaluationError("prediction interval support is incomplete")
    return {
        "covered": int(lower <= observed <= upper),
        "lower": lower,
        "upper": upper,
        "width": upper - lower + 1,
    }


def aggregate_domain_series(domains: dict[str, DomainMetricSeriesV1]) -> AggregateDomainMetricV1:
    _validate_domains(domains)
    deltas = {name: series.point_delta for name, series in domains.items()}
    return AggregateDomainMetricV1(
        macro_delta=sum(deltas.values()) / 3.0,
        weighted_delta=sum(deltas[name] * EXPECTED_TARGETS[name] for name in EXPECTED_TARGETS)
        / 712.0,
    )


def paired_domain_bootstrap(domains: dict[str, DomainMetricSeriesV1]) -> DomainBootstrapV1:
    _validate_domains(domains)
    domain_replicates: dict[str, tuple[float, ...]] = {}
    for domain_index, name in enumerate(EXPECTED_TARGETS):
        domain_replicates[name] = _domain_replicates(
            domains[name],
            seed=BOOTSTRAP_SEED + domain_index,
        )
    macro = tuple(
        sum(domain_replicates[name][index] for name in EXPECTED_TARGETS) / 3.0
        for index in range(BOOTSTRAP_REPLICATES)
    )
    weighted = tuple(
        sum(domain_replicates[name][index] * EXPECTED_TARGETS[name] for name in EXPECTED_TARGETS)
        / 712.0
        for index in range(BOOTSTRAP_REPLICATES)
    )
    return DomainBootstrapV1(
        domain_replicates=domain_replicates,
        macro_replicates=macro,
        weighted_replicates=weighted,
        domain_intervals={name: _interval(values) for name, values in domain_replicates.items()},
        macro_interval=_interval(macro),
        weighted_interval=_interval(weighted),
    )


def _domain_replicates(series: DomainMetricSeriesV1, *, seed: int) -> tuple[float, ...]:
    batches: list[list[int]] = []
    for index, batch_id in enumerate(series.kickoff_batches):
        if not batches or series.kickoff_batches[batches[-1][0]] != batch_id:
            batches.append([index])
        else:
            batches[-1].append(index)
    if len(batches) < BLOCK_LENGTH:
        raise PitchApiV3EvaluationError("domain has fewer than 10 kickoff batches")
    randomizer = random.Random(seed)
    maximum_start = len(batches) - BLOCK_LENGTH
    output: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        indexes: list[int] = []
        while len(indexes) < len(series.reference):
            start = randomizer.randrange(maximum_start + 1)
            for batch in batches[start : start + BLOCK_LENGTH]:
                indexes.extend(batch)
                if len(indexes) >= len(series.reference):
                    break
        indexes = indexes[: len(series.reference)]
        output.append(
            sum(series.challenger[index] - series.reference[index] for index in indexes)
            / len(indexes)
        )
    return tuple(output)


def _interval(values: tuple[float, ...]) -> tuple[float, float]:
    ordered = tuple(sorted(values))
    return _quantile(ordered, 0.025), _quantile(ordered, 0.975)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _validate_domains(domains: dict[str, DomainMetricSeriesV1]) -> None:
    if set(domains) != set(EXPECTED_TARGETS):
        raise PitchApiV3EvaluationError("metrics must contain exactly the three V3 domains")
    for name, expected in EXPECTED_TARGETS.items():
        if len(domains[name].reference) != expected:
            raise PitchApiV3EvaluationError(f"unexpected target count for {name}")
