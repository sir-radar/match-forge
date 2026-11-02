"""Read-only score products; count/player models retain their own contracts."""

import math
from collections.abc import Callable
from fractions import Fraction
from functools import partial
from typing import Any

from football.forecasting.model_contracts import (
    PROBABILITY_TOLERANCE,
    ModelForecast,
    ModelStatus,
    validate_model_forecast,
)


def score_products(
    forecast: ModelForecast,
    *,
    goal_lines: tuple[float, ...] = (),
    asian_handicaps: tuple[float, ...] = (),
    european_handicaps: tuple[int, ...] = (),
    goal_ranges: tuple[tuple[int, int], ...] = (),
) -> dict[str, Any]:
    """Project validated probabilities without fitting, sampling or changing mass.

    A legacy grid can contain censored score buckets. Those buckets are never
    presented as exact scores or an exact total-goal distribution.
    """
    if forecast.status is not ModelStatus.SUCCESS:
        raise ValueError("score products require a successful forecast")
    validate_model_forecast(forecast)
    size = len(forecast.score_labels)
    exact_labels = tuple(str(index) for index in range(size))
    censored_labels = exact_labels[:-1] + (f"{size - 1}+",)
    if forecast.score_labels not in (exact_labels, censored_labels):
        raise ValueError("score product labels require integer scores or a final censored bucket")
    exact = forecast.score_labels == exact_labels
    limit = size if exact else size - 1
    return {
        "derived_goals": _derived_goals(
            forecast, exact, goal_lines, asian_handicaps, european_handicaps, goal_ranges
        ),
        "product_family": "SCORE_DISTRIBUTION",
        "fixture_id": str(forecast.fixture_id),
        "model_id": forecast.model_id,
        "model_artifact_sha256": forecast.model_artifact_sha256,
        "input_snapshot_sha256": forecast.input_snapshot_sha256,
        "football_cutoff": forecast.football_cutoff.isoformat(),
        "knowledge_cutoff": forecast.knowledge_cutoff.isoformat(),
        "numerical_contract_version": forecast.numerical_contract_version,
        "one_x_two": {
            "home": forecast.home_probability,
            "draw": forecast.draw_probability,
            "away": forecast.away_probability,
        },
        "double_chance": {
            "home_or_draw": forecast.home_probability + forecast.draw_probability,
            "away_or_draw": forecast.away_probability + forecast.draw_probability,
            "home_or_away": forecast.home_probability + forecast.away_probability,
        },
        "btts": {"yes": forecast.btts_yes, "no": forecast.btts_no},
        "totals": {
            "over_2_5": forecast.total_over_2_5,
            "under_2_5": forecast.total_under_2_5,
            "distribution": list(forecast.total_goal_distribution),
            "distribution_semantics": (
                "EXACT_RESOLVED_TOTALS" if exact else "SUM_OF_SCORE_BUCKET_INDICES"
            ),
        },
        "exact_scores": [
            {
                "home_goals": home,
                "away_goals": away,
                "probability": forecast.score_matrix[home][away],
            }
            for home in range(limit)
            for away in range(limit)
        ],
        "score_distribution": {
            "support": "EXACT_SCORES" if exact else "CENSORED_BUCKETS",
            "labels": list(forecast.score_labels),
            "matrix": [list(row) for row in forecast.score_matrix],
            "unresolved_tail_probability": forecast.unresolved_tail_probability,
        },
        "team_goals": {
            "labels": list(forecast.score_labels),
            "home": list(forecast.home_goal_distribution),
            "away": list(forecast.away_goal_distribution),
        },
        "clean_sheet": {"home": forecast.home_clean_sheet, "away": forecast.away_clean_sheet},
    }


_SETTLEMENTS = ("FULL_LOSS", "HALF_LOSS", "PUSH", "HALF_WIN", "FULL_WIN")
_RESULTS = ("HOME", "DRAW", "AWAY")
_COUNTS: dict[str, Callable[[int, int], int]] = {
    "total": lambda home, away: home + away,
    "home": lambda home, away: home,
    "away": lambda home, away: away,
}


def _quarter_units(line: float) -> int:
    if isinstance(line, bool) or not isinstance(line, (int, float)):
        raise ValueError("goal lines must be finite numbers in quarter-goal increments")
    if isinstance(line, float) and not math.isfinite(line):
        raise ValueError("goal lines must be finite")
    value = Fraction(line) * 4
    if value.denominator != 1:
        raise ValueError("goal lines must use quarter-goal increments")
    return value.numerator


def _validated_parameters(
    goal_lines: tuple[float, ...],
    asian: tuple[float, ...],
    european: tuple[int, ...],
    ranges: tuple[tuple[int, int], ...],
) -> None:
    for line in goal_lines:
        if _quarter_units(line) < 0:
            raise ValueError("goal-total lines must be non-negative")
    for line in asian:
        _quarter_units(line)
    for line in european:
        if _quarter_units(line) % 4:
            raise ValueError("European handicaps require whole goals")
    for low, high in ranges:
        _validate_range(low, high)


def _validate_range(low: int, high: int) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (low, high)):
        raise ValueError("goal ranges require integer bounds")
    if low < 0 or high < low:
        raise ValueError("goal ranges require 0 <= minimum <= maximum")


def _partition(
    forecast: ModelForecast, outcomes: tuple[str, ...], classify: Callable[[int, int], str]
) -> dict[str, Any]:
    groups: dict[str, list[float]] = {key: [] for key in outcomes}
    for home, row in enumerate(forecast.score_matrix):
        for away, probability in enumerate(row):
            groups[classify(home, away)].append(probability)
    resolved = {key: math.fsum(values) for key, values in groups.items()}
    if any(not 0 <= value <= 1 for value in resolved.values()):
        raise ValueError("derived probability is outside [0,1]")
    tail = forecast.unresolved_tail_probability
    return {
        "resolved": resolved,
        "unresolved_probability": tail,
        "bounds": {
            key: {"lower": probability, "upper": min(1.0, probability + tail)}
            for key, probability in resolved.items()
        },
    }


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _settlement(difference: int, quarter: int) -> str:
    parts = (quarter - 1, quarter + 1) if quarter % 2 else (quarter, quarter)
    return _SETTLEMENTS[2 + sum(_sign(4 * difference + part) for part in parts)]


def _handicap(forecast: ModelForecast, line: float) -> dict[str, Any]:
    quarter = _quarter_units(line)
    return {
        "home_handicap": line,
        "home": _partition(forecast, _SETTLEMENTS, lambda h, a: _settlement(h - a, quarter)),
        "away": _partition(forecast, _SETTLEMENTS, lambda h, a: _settlement(a - h, -quarter)),
    }


def _result(difference: int) -> str:
    return {1: "HOME", 0: "DRAW", -1: "AWAY"}[_sign(difference)]


def _european(forecast: ModelForecast, line: int) -> dict[str, Any]:
    return {
        "home_handicap": line,
        **_partition(forecast, _RESULTS, lambda h, a: _result(h - a + line)),
    }


def _count_outcome(
    home: int, away: int, *, count: Callable[[int, int], int], quarter: int, direction: int
) -> str:
    return _settlement(direction * count(home, away), -direction * quarter)


def _range_outcome(
    home: int, away: int, *, count: Callable[[int, int], int], low: int, high: int
) -> str:
    return "INSIDE" if low <= count(home, away) <= high else "OUTSIDE"


def _totals(forecast: ModelForecast, line: float) -> dict[str, Any]:
    quarter = _quarter_units(line)
    return {
        "line": line,
        **{
            axis: {
                "over": _partition(
                    forecast,
                    _SETTLEMENTS,
                    partial(_count_outcome, count=count, quarter=quarter, direction=1),
                ),
                "under": _partition(
                    forecast,
                    _SETTLEMENTS,
                    partial(_count_outcome, count=count, quarter=quarter, direction=-1),
                ),
            }
            for axis, count in _COUNTS.items()
        },
    }


def _result_totals(forecast: ModelForecast, line: float) -> dict[str, Any]:
    quarter = _quarter_units(line)
    conditions = {-1: "UNDER", 0: "EQUAL", 1: "OVER"}
    return {
        "line": line,
        "condition": "STRICT_TOTAL_COMPARISON_WITHOUT_SPLIT_STAKE",
        **_partition(
            forecast,
            tuple(
                f"{result}_{condition}" for result in _RESULTS for condition in conditions.values()
            ),
            lambda h, a: f"{_result(h - a)}_{conditions[_sign(4 * (h + a) - quarter)]}",
        ),
    }


def _ranges(forecast: ModelForecast, low: int, high: int) -> dict[str, Any]:
    return {
        "minimum": low,
        "maximum": high,
        **{
            axis: _partition(
                forecast,
                ("INSIDE", "OUTSIDE"),
                partial(_range_outcome, count=count, low=low, high=high),
            )
            for axis, count in _COUNTS.items()
        },
    }


def _derived_goals(
    forecast: ModelForecast,
    exact: bool,
    goal_lines: tuple[float, ...],
    asian: tuple[float, ...],
    european: tuple[int, ...],
    ranges: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    _validated_parameters(goal_lines, asian, european, ranges)
    if not exact:
        return {
            "status": "UNSUPPORTED_CENSORED_SUPPORT",
            "reason": (
                "Censored bucket indices do not identify exact handicap, margin or joint outcomes."
            ),
        }
    size = len(forecast.score_labels)
    return {
        "status": "COMPUTED",
        "semantics": "EXACT_RESOLVED_SCORE_ATOMS_WITH_UNRESOLVED_TAIL_BOUNDS",
        "numerical_tolerance": PROBABILITY_TOLERANCE,
        "draw_no_bet": _handicap(forecast, 0),
        "winning_margin": _partition(
            forecast, tuple(str(value) for value in range(1 - size, size)), lambda h, a: str(h - a)
        ),
        "result_btts": _partition(
            forecast,
            tuple(f"{result}_{condition}" for result in _RESULTS for condition in ("YES", "NO")),
            lambda h, a: f"{_result(h - a)}_{'YES' if h > 0 and a > 0 else 'NO'}",
        ),
        "asian_handicaps": [_handicap(forecast, line) for line in sorted(set(asian))],
        "european_handicaps": [_european(forecast, line) for line in sorted(set(european))],
        "totals": [_totals(forecast, line) for line in sorted(set(goal_lines))],
        "result_totals": [_result_totals(forecast, line) for line in sorted(set(goal_lines))],
        "goal_ranges": [_ranges(forecast, low, high) for low, high in sorted(set(ranges))],
    }
