from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from uuid import UUID

from scipy.signal import fftconvolve

from football.forecasting.contracts import (
    CornerForecastPayloadV1,
    GoalForecastPayloadV1,
    MatchResultProbabilitiesV1,
)
from football.forecasting.dataset import EvaluationMatchOutcomeV1
from football.forecasting.evaluation import (
    EvaluatedMatchResultV1,
    MatchOutcome,
    MatchResultMetricsV1,
    evaluate_match_results,
)
from football.forecasting.execution import Sprint2RawForecastV1
from football.forecasting.uncertainty import PairedMetricSeriesV1

# Bound support expansion so overdispersed tails are captured without unbounded scoring work.
_MAX_COUNT_LIMIT = 1_000_000


class Sprint2ScoringError(RuntimeError):
    """Sprint 2 predictions and governed outcomes cannot be scored safely."""


@dataclass(frozen=True, slots=True)
class CountMetricsV1:
    sample_count: int
    negative_log_likelihood: float
    crps: float
    mae: float
    rmse: float

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "negative_log_likelihood": self.negative_log_likelihood,
            "crps": self.crps,
            "mae": self.mae,
            "rmse": self.rmse,
        }


@dataclass(frozen=True, slots=True)
class GoalMetricsV1:
    sample_count: int
    joint_score_nll: float
    total: CountMetricsV1
    poisson_deviance: float

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "joint_score_nll": self.joint_score_nll,
            "total": self.total.to_dict(),
            "poisson_deviance": self.poisson_deviance,
        }


@dataclass(frozen=True, slots=True)
class CornerMetricsV1:
    home: CountMetricsV1
    away: CountMetricsV1
    total: CountMetricsV1

    def to_dict(self) -> dict[str, object]:
        return {
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
            "total": self.total.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Sprint2RawMetricsV1:
    elo_result: MatchResultMetricsV1
    dixon_coles_result: MatchResultMetricsV1
    result_reference: MatchResultMetricsV1
    goals: GoalMetricsV1
    goal_reference: GoalMetricsV1
    corner_poisson: CornerMetricsV1
    corner_negative_binomial: CornerMetricsV1
    corner_reference: CornerMetricsV1

    def to_dict(self) -> dict[str, object]:
        return {
            "elo_result": self.elo_result.to_dict(),
            "dixon_coles_result": self.dixon_coles_result.to_dict(),
            "result_reference": self.result_reference.to_dict(),
            "goals": self.goals.to_dict(),
            "goal_reference": self.goal_reference.to_dict(),
            "corner_poisson": self.corner_poisson.to_dict(),
            "corner_negative_binomial": self.corner_negative_binomial.to_dict(),
            "corner_reference": self.corner_reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Sprint2ComparisonRowV1:
    match_id: UUID
    kickoff_at: datetime
    elo_log_loss: float
    elo_rps: float
    dixon_coles_log_loss: float
    dixon_coles_rps: float
    result_reference_log_loss: float
    result_reference_rps: float
    goal_joint_nll: float
    goal_total_crps: float
    goal_total_absolute_error: float
    goal_reference_joint_nll: float
    goal_reference_total_crps: float
    goal_reference_total_absolute_error: float
    corner_poisson_total_nll: float
    corner_poisson_total_crps: float
    corner_poisson_total_absolute_error: float
    corner_negative_binomial_total_nll: float
    corner_negative_binomial_total_crps: float
    corner_negative_binomial_total_absolute_error: float
    corner_reference_total_nll: float
    corner_reference_total_crps: float
    corner_reference_total_absolute_error: float

    def to_dict(self) -> dict[str, object]:
        return {
            "match_id": str(self.match_id),
            "kickoff_at": self.kickoff_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            **{
                field: getattr(self, field)
                for field in self.__dataclass_fields__
                if field not in ("match_id", "kickoff_at")
            },
        }


class Sprint2Scorer:
    def evaluate(
        self,
        forecasts: tuple[Sprint2RawForecastV1, ...],
        outcomes: tuple[EvaluationMatchOutcomeV1, ...],
    ) -> Sprint2RawMetricsV1:
        aligned = _align(forecasts, outcomes)
        return Sprint2RawMetricsV1(
            elo_result=_result_metrics(aligned, lambda forecast: forecast.elo_result),
            dixon_coles_result=_result_metrics(
                aligned, lambda forecast: forecast.dixon_coles_result
            ),
            result_reference=_result_metrics(aligned, lambda forecast: forecast.result_reference),
            goals=_goal_metrics(aligned, lambda forecast: forecast.goal),
            goal_reference=_goal_metrics(aligned, lambda forecast: forecast.goal_reference),
            corner_poisson=_corner_metrics(aligned, lambda forecast: forecast.corner_poisson),
            corner_negative_binomial=_corner_metrics(
                aligned, lambda forecast: forecast.corner_negative_binomial
            ),
            corner_reference=_corner_metrics(aligned, lambda forecast: forecast.corner_reference),
        )

    def comparison_rows(
        self,
        forecasts: tuple[Sprint2RawForecastV1, ...],
        outcomes: tuple[EvaluationMatchOutcomeV1, ...],
    ) -> tuple[Sprint2ComparisonRowV1, ...]:
        return tuple(
            _comparison_row(forecast, outcome) for forecast, outcome in _align(forecasts, outcomes)
        )

    @staticmethod
    def paired_metric_series(
        rows: tuple[Sprint2ComparisonRowV1, ...],
    ) -> tuple[PairedMetricSeriesV1, ...]:
        if not rows:
            raise Sprint2ScoringError("paired comparison requires target scores")
        definitions = (
            ("elo_vs_result_reference", "log_loss", "elo_log_loss", "result_reference_log_loss"),
            (
                "elo_vs_result_reference",
                "ranked_probability_score",
                "elo_rps",
                "result_reference_rps",
            ),
            (
                "dixon_coles_vs_result_reference",
                "log_loss",
                "dixon_coles_log_loss",
                "result_reference_log_loss",
            ),
            (
                "dixon_coles_vs_result_reference",
                "ranked_probability_score",
                "dixon_coles_rps",
                "result_reference_rps",
            ),
            (
                "dixon_coles_goals_vs_goal_reference",
                "joint_score_nll",
                "goal_joint_nll",
                "goal_reference_joint_nll",
            ),
            (
                "dixon_coles_goals_vs_goal_reference",
                "total_crps",
                "goal_total_crps",
                "goal_reference_total_crps",
            ),
            (
                "dixon_coles_goals_vs_goal_reference",
                "total_mae",
                "goal_total_absolute_error",
                "goal_reference_total_absolute_error",
            ),
            (
                "corner_poisson_vs_corner_reference",
                "total_nll",
                "corner_poisson_total_nll",
                "corner_reference_total_nll",
            ),
            (
                "corner_poisson_vs_corner_reference",
                "total_crps",
                "corner_poisson_total_crps",
                "corner_reference_total_crps",
            ),
            (
                "corner_poisson_vs_corner_reference",
                "total_mae",
                "corner_poisson_total_absolute_error",
                "corner_reference_total_absolute_error",
            ),
            (
                "corner_negative_binomial_vs_corner_poisson",
                "total_nll",
                "corner_negative_binomial_total_nll",
                "corner_poisson_total_nll",
            ),
            (
                "corner_negative_binomial_vs_corner_poisson",
                "total_crps",
                "corner_negative_binomial_total_crps",
                "corner_poisson_total_crps",
            ),
        )
        return tuple(
            PairedMetricSeriesV1(
                comparison=comparison,
                metric=metric,
                candidate=tuple(float(getattr(row, candidate)) for row in rows),
                reference=tuple(float(getattr(row, reference)) for row in rows),
            )
            for comparison, metric, candidate, reference in definitions
        )


def _comparison_row(
    forecast: Sprint2RawForecastV1, outcome: EvaluationMatchOutcomeV1
) -> Sprint2ComparisonRowV1:
    elo = _result_losses(forecast.elo_result, outcome)
    dixon_coles = _result_losses(forecast.dixon_coles_result, outcome)
    result_reference = _result_losses(forecast.result_reference, outcome)
    goal = _goal_losses(forecast.goal, outcome)
    goal_reference = _goal_losses(forecast.goal_reference, outcome)
    corner_poisson = _corner_total_losses(forecast.corner_poisson, outcome)
    corner_negative_binomial = _corner_total_losses(forecast.corner_negative_binomial, outcome)
    corner_reference = _corner_total_losses(forecast.corner_reference, outcome)
    return Sprint2ComparisonRowV1(
        match_id=forecast.context.match_id,
        kickoff_at=forecast.context.kickoff_at,
        elo_log_loss=elo[0],
        elo_rps=elo[1],
        dixon_coles_log_loss=dixon_coles[0],
        dixon_coles_rps=dixon_coles[1],
        result_reference_log_loss=result_reference[0],
        result_reference_rps=result_reference[1],
        goal_joint_nll=goal[0],
        goal_total_crps=goal[1],
        goal_total_absolute_error=goal[2],
        goal_reference_joint_nll=goal_reference[0],
        goal_reference_total_crps=goal_reference[1],
        goal_reference_total_absolute_error=goal_reference[2],
        corner_poisson_total_nll=corner_poisson[0],
        corner_poisson_total_crps=corner_poisson[1],
        corner_poisson_total_absolute_error=corner_poisson[2],
        corner_negative_binomial_total_nll=corner_negative_binomial[0],
        corner_negative_binomial_total_crps=corner_negative_binomial[1],
        corner_negative_binomial_total_absolute_error=corner_negative_binomial[2],
        corner_reference_total_nll=corner_reference[0],
        corner_reference_total_crps=corner_reference[1],
        corner_reference_total_absolute_error=corner_reference[2],
    )


def _result_losses(
    probabilities: MatchResultProbabilitiesV1, outcome: EvaluationMatchOutcomeV1
) -> tuple[float, float]:
    values = (probabilities.home, probabilities.draw, probabilities.away)
    resolved = _outcome(outcome)
    outcome_index = ("HOME", "DRAW", "AWAY").index(resolved)
    actual = tuple(float(index == outcome_index) for index in range(3))
    ranked = sum((sum(values[:index]) - sum(actual[:index])) ** 2 for index in (1, 2)) / 2.0
    return _negative_log(values[outcome_index]), ranked


def _goal_losses(
    payload: GoalForecastPayloadV1, outcome: EvaluationMatchOutcomeV1
) -> tuple[float, float, float]:
    observed_total = outcome.home_score + outcome.away_score
    expected_total = payload.lambda_home + payload.lambda_away
    return (
        _negative_log(_goal_probability(outcome.home_score, outcome.away_score, payload)),
        _crps(partial(_goal_total_probability, payload=payload), observed_total),
        abs(expected_total - observed_total),
    )


def _corner_total_losses(
    payload: CornerForecastPayloadV1, outcome: EvaluationMatchOutcomeV1
) -> tuple[float, float, float]:
    observed_total = outcome.home_corners + outcome.away_corners
    distribution = _corner_total_distribution(payload)
    probability = partial(_stored_probability, values=distribution)
    return (
        _negative_log(probability(observed_total)),
        _crps(probability, observed_total),
        abs(payload.lambda_home + payload.lambda_away - observed_total),
    )


AlignedForecast = tuple[Sprint2RawForecastV1, EvaluationMatchOutcomeV1]


def _align(
    forecasts: tuple[Sprint2RawForecastV1, ...],
    outcomes: tuple[EvaluationMatchOutcomeV1, ...],
) -> tuple[AlignedForecast, ...]:
    if not forecasts:
        raise Sprint2ScoringError("Sprint 2 scoring requires forecasts")
    forecast_ids = [forecast.context.match_id for forecast in forecasts]
    outcome_by_match = {outcome.match_id: outcome for outcome in outcomes}
    if (
        len(forecast_ids) != len(set(forecast_ids))
        or len(outcome_by_match) != len(outcomes)
        or set(forecast_ids) != set(outcome_by_match)
    ):
        raise Sprint2ScoringError("Sprint 2 forecasts and outcomes must align exactly")
    aligned = tuple(
        (forecast, outcome_by_match[forecast.context.match_id]) for forecast in forecasts
    )
    if any(forecast.context.kickoff_at != outcome.kickoff_at for forecast, outcome in aligned):
        raise Sprint2ScoringError("Sprint 2 forecast and outcome kickoffs conflict")
    return aligned


def _result_metrics(
    aligned: tuple[AlignedForecast, ...],
    probabilities: Callable[[Sprint2RawForecastV1], MatchResultProbabilitiesV1],
) -> MatchResultMetricsV1:
    observations = tuple(
        EvaluatedMatchResultV1(
            kickoff_at=forecast.context.kickoff_at,
            prediction_cutoff=forecast.context.kickoff_at,
            outcome_known_at=outcome.outcome_known_at,
            probabilities=probabilities(forecast),
            outcome=_outcome(outcome),
        )
        for forecast, outcome in aligned
    )
    return evaluate_match_results(observations)


def _goal_metrics(
    aligned: tuple[AlignedForecast, ...],
    payload: Callable[[Sprint2RawForecastV1], GoalForecastPayloadV1],
) -> GoalMetricsV1:
    joint_losses: list[float] = []
    total_items: list[_CountItem] = []
    deviances: list[float] = []
    for forecast, outcome in aligned:
        resolved = payload(forecast)
        probability = _goal_probability(
            outcome.home_score,
            outcome.away_score,
            resolved,
        )
        joint_losses.append(_negative_log(probability))
        observed_total = outcome.home_score + outcome.away_score
        expected_total = resolved.lambda_home + resolved.lambda_away
        total_items.append(
            _CountItem(
                expected_total,
                observed_total,
                partial(_goal_total_probability, payload=resolved),
            )
        )
        deviances.append(_poisson_deviance(observed_total, expected_total))
    return GoalMetricsV1(
        sample_count=len(aligned),
        joint_score_nll=sum(joint_losses) / len(joint_losses),
        total=_count_metrics(tuple(total_items)),
        poisson_deviance=sum(deviances) / len(deviances),
    )


def _corner_metrics(
    aligned: tuple[AlignedForecast, ...],
    payload: Callable[[Sprint2RawForecastV1], CornerForecastPayloadV1],
) -> CornerMetricsV1:
    home: list[_CountItem] = []
    away: list[_CountItem] = []
    total: list[_CountItem] = []
    for forecast, outcome in aligned:
        resolved = payload(forecast)
        total_distribution = _corner_total_distribution(resolved)
        home.append(
            _CountItem(
                resolved.lambda_home,
                outcome.home_corners,
                partial(
                    _corner_probability,
                    expected=resolved.lambda_home,
                    dispersion=resolved.dispersion,
                ),
            )
        )
        away.append(
            _CountItem(
                resolved.lambda_away,
                outcome.away_corners,
                partial(
                    _corner_probability,
                    expected=resolved.lambda_away,
                    dispersion=resolved.dispersion,
                ),
            )
        )
        total.append(
            _CountItem(
                resolved.lambda_home + resolved.lambda_away,
                outcome.home_corners + outcome.away_corners,
                partial(_stored_probability, values=total_distribution),
            )
        )
    return CornerMetricsV1(
        home=_count_metrics(tuple(home)),
        away=_count_metrics(tuple(away)),
        total=_count_metrics(tuple(total)),
    )


@dataclass(frozen=True, slots=True)
class _CountItem:
    expected: float
    observed: int
    probability: Callable[[int], float]


def _count_metrics(items: tuple[_CountItem, ...]) -> CountMetricsV1:
    losses: list[float] = []
    crps_values: list[float] = []
    absolute_errors: list[float] = []
    squared_errors: list[float] = []
    for item in items:
        losses.append(_negative_log(item.probability(item.observed)))
        crps_values.append(_crps(item.probability, item.observed))
        error = item.expected - item.observed
        absolute_errors.append(abs(error))
        squared_errors.append(error * error)
    count = len(items)
    return CountMetricsV1(
        sample_count=count,
        negative_log_likelihood=sum(losses) / count,
        crps=sum(crps_values) / count,
        mae=sum(absolute_errors) / count,
        rmse=math.sqrt(sum(squared_errors) / count),
    )


def _crps(probability: Callable[[int], float], observed: int) -> float:
    cumulative = 0.0
    score = 0.0
    for count in range(_MAX_COUNT_LIMIT + 1):
        mass = probability(count)
        if not math.isfinite(mass) or mass < 0.0 or mass > 1.0:
            raise Sprint2ScoringError("count distribution produced invalid probability")
        cumulative += mass
        score += (cumulative - float(observed <= count)) ** 2
        if count >= observed and cumulative >= 1.0 - 1e-12:
            return score
    raise Sprint2ScoringError("count distribution exceeds scoring support")


def _goal_probability(home: int, away: int, payload: GoalForecastPayloadV1) -> float:
    independent = _poisson_probability(home, payload.lambda_home) * _poisson_probability(
        away, payload.lambda_away
    )
    return independent * _tau(
        home,
        away,
        payload.lambda_home,
        payload.lambda_away,
        payload.low_score_correlation,
    )


def _goal_total_probability(total: int, payload: GoalForecastPayloadV1) -> float:
    return sum(_goal_probability(home, total - home, payload) for home in range(total + 1))


def _corner_total_distribution(payload: CornerForecastPayloadV1) -> tuple[float, ...]:
    home = _finite_distribution(
        lambda count: _corner_probability(count, payload.lambda_home, payload.dispersion)
    )
    away = _finite_distribution(
        lambda count: _corner_probability(count, payload.lambda_away, payload.dispersion)
    )
    convolved = tuple(float(value) for value in fftconvolve(home, away))
    if any(value < -1e-12 or not math.isfinite(value) for value in convolved):
        raise Sprint2ScoringError("corner convolution produced invalid probability")
    non_negative = tuple(max(value, 0.0) for value in convolved)
    total = sum(non_negative)
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise Sprint2ScoringError("corner convolution lost probability mass")
    return tuple(value / total for value in non_negative)


def _finite_distribution(probability: Callable[[int], float]) -> tuple[float, ...]:
    values: list[float] = []
    cumulative = 0.0
    for count in range(_MAX_COUNT_LIMIT + 1):
        mass = probability(count)
        if not math.isfinite(mass) or mass < 0.0 or mass > 1.0:
            raise Sprint2ScoringError("count distribution produced invalid probability")
        values.append(mass)
        cumulative += mass
        if cumulative >= 1.0 - 1e-12:
            return tuple(values)
    raise Sprint2ScoringError("count distribution exceeds scoring support")


def _corner_probability(count: int, expected: float, dispersion: float | None) -> float:
    if dispersion is None:
        return _poisson_probability(count, expected)
    shape = 1.0 / dispersion
    return math.exp(
        math.lgamma(count + shape)
        - math.lgamma(shape)
        - math.lgamma(count + 1.0)
        + shape * math.log(shape / (shape + expected))
        + count * math.log(expected / (shape + expected))
    )


def _stored_probability(count: int, values: tuple[float, ...]) -> float:
    return values[count] if count < len(values) else 0.0


def _poisson_probability(count: int, expected: float) -> float:
    return math.exp(count * math.log(expected) - expected - math.lgamma(count + 1.0))


def _tau(home: int, away: int, home_mean: float, away_mean: float, rho: float) -> float:
    if home == 0 and away == 0:
        return 1.0 - home_mean * away_mean * rho
    if home == 0 and away == 1:
        return 1.0 + home_mean * rho
    if home == 1 and away == 0:
        return 1.0 + away_mean * rho
    if home == 1 and away == 1:
        return 1.0 - rho
    return 1.0


def _negative_log(probability: float) -> float:
    if not math.isfinite(probability) or probability <= 0.0 or probability > 1.0 + 1e-12:
        raise Sprint2ScoringError("observed outcome has invalid forecast probability")
    return -math.log(min(probability, 1.0))


def _poisson_deviance(observed: int, expected: float) -> float:
    if observed == 0:
        return 2.0 * expected
    return 2.0 * (observed * math.log(observed / expected) - (observed - expected))


def _outcome(outcome: EvaluationMatchOutcomeV1) -> MatchOutcome:
    if outcome.home_score > outcome.away_score:
        return "HOME"
    if outcome.home_score < outcome.away_score:
        return "AWAY"
    return "DRAW"
