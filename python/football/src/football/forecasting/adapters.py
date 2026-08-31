from __future__ import annotations

import math
from dataclasses import dataclass

from football.forecasting.contracts import (
    CornerForecastPayloadV1,
    GoalForecastPayloadV1,
    MatchResultProbabilitiesV1,
)
from football.forecasting.corner import CornerForecast
from football.forecasting.dixon_coles import GoalForecast

_ELO_SCALE = 400.0


class ForecastAdapterError(ValueError):
    """A retained model output cannot be projected into a shared forecast contract."""


@dataclass(frozen=True, slots=True)
class EloOneXTwoAdapterV1:
    """Davidson-style draw-aware projection of pre-match Elo ratings."""

    draw_propensity: float
    home_advantage: float = 0.0
    algorithm_version: str = "elo-davidson-1x2-v1"

    def __post_init__(self) -> None:
        _finite(self.draw_propensity, "draw_propensity")
        _finite(self.home_advantage, "home_advantage")
        if self.draw_propensity <= 0.0:
            raise ForecastAdapterError("draw_propensity must be positive")

    def forecast(self, home_rating: float, away_rating: float) -> MatchResultProbabilitiesV1:
        _finite(home_rating, "home_rating")
        _finite(away_rating, "away_rating")
        coefficient = math.log(10.0) / _ELO_SCALE
        log_home = coefficient * (home_rating + self.home_advantage)
        log_away = coefficient * away_rating
        log_draw = math.log(self.draw_propensity) + 0.5 * (log_home + log_away)
        maximum = max(log_home, log_draw, log_away)
        weights = tuple(math.exp(value - maximum) for value in (log_home, log_draw, log_away))
        total = sum(weights)
        return MatchResultProbabilitiesV1(
            home=weights[0] / total,
            draw=weights[1] / total,
            away=weights[2] / total,
        )


def dixon_coles_result_probabilities(forecast: GoalForecast) -> MatchResultProbabilitiesV1:
    return MatchResultProbabilitiesV1(
        home=forecast.markets.home_win,
        draw=forecast.markets.draw,
        away=forecast.markets.away_win,
    )


def goal_forecast_payload(forecast: GoalForecast) -> GoalForecastPayloadV1:
    under_4_5 = sum(
        forecast.exact_score_probability(home_goals, away_goals)
        for home_goals in range(5)
        for away_goals in range(5 - home_goals)
    )
    return GoalForecastPayloadV1(
        lambda_home=forecast.lambda_home,
        lambda_away=forecast.lambda_away,
        score_labels=forecast.score_matrix.labels,
        score_probabilities=forecast.score_matrix.probabilities,
        over_0_5=_bounded_probability(1.0 - forecast.exact_score_probability(0, 0), "over_0_5"),
        over_1_5=forecast.markets.over_1_5,
        over_2_5=forecast.markets.over_2_5,
        over_3_5=forecast.markets.over_3_5,
        over_4_5=_bounded_probability(1.0 - under_4_5, "over_4_5"),
        btts_yes=forecast.markets.both_teams_to_score,
        home_clean_sheet=forecast.markets.home_clean_sheet,
        away_clean_sheet=forecast.markets.away_clean_sheet,
        low_score_correlation=forecast.low_score_correlation,
    )


def corner_forecast_payload(forecast: CornerForecast) -> CornerForecastPayloadV1:
    return CornerForecastPayloadV1(
        distribution=forecast.distribution,
        lambda_home=forecast.lambda_home,
        lambda_away=forecast.lambda_away,
        home_variance=forecast.home_variance,
        away_variance=forecast.away_variance,
        dispersion=forecast.dispersion,
    )


@dataclass(frozen=True, slots=True)
class CountDistributionSummaryV1:
    median: int
    interval_80: tuple[int, int]
    interval_95: tuple[int, int]


@dataclass(frozen=True, slots=True)
class CornerTotalDistributionV1:
    forecast: CornerForecast

    def probability(self, total_corners: int) -> float:
        if isinstance(total_corners, bool) or not isinstance(total_corners, int):
            raise ForecastAdapterError("total_corners must be a non-negative integer")
        if total_corners < 0:
            raise ForecastAdapterError("total_corners must be a non-negative integer")
        return sum(
            self.forecast.home_probability(home)
            * self.forecast.away_probability(total_corners - home)
            for home in range(total_corners + 1)
        )

    def summary(self, max_count: int = 200) -> CountDistributionSummaryV1:
        if isinstance(max_count, bool) or not isinstance(max_count, int) or max_count <= 0:
            raise ForecastAdapterError("max_count must be a positive integer")
        cumulative = 0.0
        quantiles: dict[float, int] = {}
        thresholds = (0.025, 0.10, 0.50, 0.90, 0.975)
        for value in range(max_count + 1):
            cumulative += self.probability(value)
            for threshold in thresholds:
                if threshold not in quantiles and cumulative >= threshold:
                    quantiles[threshold] = value
            if cumulative >= 1.0 - 1e-12:
                break
        if len(quantiles) != len(thresholds):
            raise ForecastAdapterError("max_count does not capture required probability mass")
        return CountDistributionSummaryV1(
            median=quantiles[0.50],
            interval_80=(quantiles[0.10], quantiles[0.90]),
            interval_95=(quantiles[0.025], quantiles[0.975]),
        )


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ForecastAdapterError(f"{field_name} must be finite")


def _bounded_probability(value: float, field_name: str) -> float:
    if not math.isfinite(value) or value < -1e-12 or value > 1.0 + 1e-12:
        raise ForecastAdapterError(f"{field_name} calculation produced an invalid probability")
    return min(max(value, 0.0), 1.0)
