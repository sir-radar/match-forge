"""Existing public descriptive analytics, owned by Python rather than the HTTP server."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, cast

from football.forecasting.model_contracts import PROBABILITY_TOLERANCE

POLICY_VERSION = "pre-match-revisions-v2"
_OUTCOMES = ("home", "draw", "away")
_METRICS = (
    "outcome_hit_rate",
    "brier",
    "log_loss",
    "baseline_brier",
    "baseline_log_loss",
    "exact_score_rate",
    "top_three_score_rate",
    "top_five_score_rate",
    "total_goals_hit_rate",
    "btts_hit_rate",
)
_CHAMPION_ALGORITHMS = (
    "transferable-rolling-goals-poisson-v1",
    "transferable-rolling-goals-poisson-v1-rolling10-v2",
)


def _valid_probability(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    number = cast(int | float, value)
    return math.isfinite(number) and 0 <= number <= 1


def _clock(value: str | datetime) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if result.utcoffset() is None:
        raise ValueError("public analytics clocks require timezones")
    return result


@dataclass(frozen=True, slots=True)
class ScoreCell:
    home_goals: int
    away_goals: int
    probability: float
    home_kind: str
    away_kind: str

    def matches(self, home: int, away: int) -> bool:
        return (
            home >= self.home_goals if self.home_kind == "AT_LEAST" else home == self.home_goals
        ) and (away >= self.away_goals if self.away_kind == "AT_LEAST" else away == self.away_goals)


def _bucket(cell: Mapping[str, Any], side: str, version: str) -> tuple[int, str]:
    goals = cell[side + "_goals"]
    if type(goals) is not int or goals < 0:
        raise ValueError("invalid score bucket")
    if version == "legacy-compact-index-v1":
        if goals > 5:
            raise ValueError("invalid legacy score bucket")
        return goals, "AT_LEAST" if goals == 5 else "EXACT"
    kind, label = cell[side + "_bucket_kind"], cell[side + "_bucket_label"]
    if kind not in ("EXACT", "AT_LEAST") or label != str(goals) + (
        "+" if kind == "AT_LEAST" else ""
    ):
        raise ValueError("inconsistent score bucket label")
    return goals, kind


def score_cells(cells: list[dict[str, Any]], version: str, algorithm: str) -> tuple[ScoreCell, ...]:
    if version not in ("legacy-compact-index-v1", "compact-buckets-v2"):
        raise ValueError("unsupported score matrix version")
    if version == "legacy-compact-index-v1" and algorithm not in _CHAMPION_ALGORITHMS:
        raise ValueError("unsupported legacy score interpretation")
    result = []
    for cell in cells:
        home, home_kind = _bucket(cell, "home", version)
        away, away_kind = _bucket(cell, "away", version)
        if not _valid_probability(cell["probability"]):
            raise ValueError("invalid score cell probability")
        result.append(ScoreCell(home, away, cell["probability"], home_kind, away_kind))
    return tuple(result)


def _performance_probabilities(raw: Mapping[str, Any]) -> Mapping[str, float]:
    values = dict(raw)
    if any(
        type(value) not in (int, float) or not math.isfinite(value) for value in values.values()
    ):
        raise ValueError("invalid stored performance probabilities")
    if any(
        not _valid_probability(values.get(key))
        for key in (*_OUTCOMES, "total_over_2_5", "btts_yes")
    ):
        raise ValueError("invalid stored performance probabilities")
    if abs(sum(values[key] for key in _OUTCOMES) - 1) > PROBABILITY_TOLERANCE:
        raise ValueError("invalid stored outcome probability sum")
    return MappingProxyType(values)


@dataclass(frozen=True, slots=True)
class PerformanceObservation:
    probabilities: Mapping[str, float]
    scores: tuple[ScoreCell, ...]
    home_goals: int
    away_goals: int
    kickoff_at: datetime
    knowledge_cutoff: datetime
    outcome_known_at: datetime | None

    @classmethod
    def from_source(cls, row: Mapping[str, Any]) -> PerformanceObservation:
        values = _performance_probabilities(row["probabilities"])
        if any(type(row[key]) is not int or row[key] < 0 for key in ("home_score", "away_score")):
            raise ValueError("invalid final scores")
        kickoff, cutoff = _clock(row["kickoff_at"]), _clock(row["knowledge_cutoff"])
        if cutoff >= kickoff:
            raise ValueError("public analytics requires pre-match forecast knowledge")
        return cls(
            values,
            score_cells(
                row["score_matrix"], row["score_matrix_version"], row["model_algorithm_version"]
            ),
            row["home_score"],
            row["away_score"],
            kickoff,
            cutoff,
            _clock(row["outcome_known_at"]) if row["outcome_known_at"] is not None else None,
        )


def _outcome(home: int, away: int) -> str:
    return "home" if home > away else "away" if away > home else "draw"


def _max_outcome(values: Mapping[str, float]) -> str:
    return max(_OUTCOMES, key=lambda key: values.get(key, 0))


def performance_baselines(
    records: tuple[PerformanceObservation, ...],
) -> tuple[dict[str, float], ...]:
    """Preserve the existing known-outcome sweep and inclusive knowledge boundary."""
    events = sorted(
        (
            row
            for row in records
            if row.outcome_known_at is not None and row.outcome_known_at > row.kickoff_at
        ),
        key=lambda row: row.outcome_known_at or row.kickoff_at,
    )
    counts = dict.fromkeys(_OUTCOMES, 1.0)
    baselines: list[dict[str, float]] = [{} for _ in records]
    event, total = 0, 3.0
    for index in sorted(range(len(records)), key=lambda i: records[i].knowledge_cutoff):
        while event < len(events):
            prior = events[event]
            if (
                prior.outcome_known_at is None
                or prior.outcome_known_at > records[index].knowledge_cutoff
            ):
                break
            counts[_outcome(prior.home_goals, prior.away_goals)] += 1
            total += 1
            event += 1
        baselines[index] = {key: counts[key] / total for key in _OUTCOMES}
    return tuple(baselines)


def _accumulate_outcome(
    values: dict[str, float], row: PerformanceObservation, baseline: Mapping[str, float]
) -> None:
    outcome = _outcome(row.home_goals, row.away_goals)
    values["outcome_hit_rate"] += float(_max_outcome(row.probabilities) == outcome)
    for key in _OUTCOMES:
        target = float(key == outcome)
        values["brier"] += (row.probabilities[key] - target) ** 2
        values["baseline_brier"] += (baseline[key] - target) ** 2
    values["log_loss"] -= math.log(max(row.probabilities[outcome], 1e-15))
    values["baseline_log_loss"] -= math.log(max(baseline[outcome], 1e-15))


def _accumulate_scores(values: dict[str, float], row: PerformanceObservation) -> None:
    ranked = sorted(
        row.scores, key=lambda cell: (-cell.probability, cell.home_goals, cell.away_goals)
    )
    position = next(
        (i for i, cell in enumerate(ranked) if cell.matches(row.home_goals, row.away_goals)), -1
    )
    values["exact_score_rate"] += float(
        position == 0 and ranked[0].home_kind != "AT_LEAST" and ranked[0].away_kind != "AT_LEAST"
    )
    values["top_three_score_rate"] += float(0 <= position < 3)
    values["top_five_score_rate"] += float(0 <= position < 5)
    values["total_goals_hit_rate"] += float(
        (row.probabilities["total_over_2_5"] >= 0.5) == (row.home_goals + row.away_goals > 2)
    )
    values["btts_hit_rate"] += float(
        (row.probabilities["btts_yes"] >= 0.5) == (row.home_goals > 0 and row.away_goals > 0)
    )


def _window(
    records: tuple[PerformanceObservation, ...], baselines: tuple[dict[str, float], ...], start: int
) -> dict[str, float]:
    values = dict.fromkeys(_METRICS, 0.0)
    for index in range(start, len(records)):
        _accumulate_outcome(values, records[index], baselines[index])
        _accumulate_scores(values, records[index])
    return {key: value / (len(records) - start) for key, value in values.items()}


def performance_report(
    competition_id: str, records: tuple[PerformanceObservation, ...], *, horizon: str
) -> dict[str, Any]:
    result = {
        "competition_id": competition_id,
        "analytics_policy_version": POLICY_VERSION,
        "analytics_horizon": horizon or "LATEST",
        "rating": "UNRATED",
        "forecasts": len(records),
        **dict.fromkeys(
            (
                *_METRICS,
                "latest_fifty_brier",
                "latest_fifty_log_loss",
                "latest_fifty_baseline_brier",
                "latest_fifty_baseline_log_loss",
            )
        ),
    }
    if not records:
        return result
    baselines = performance_baselines(records)
    all_records = _window(records, baselines, 0)
    latest = _window(records, baselines, max(0, len(records) - 50))
    result.update(all_records)
    result.update(
        latest_fifty_brier=latest["brier"],
        latest_fifty_log_loss=latest["log_loss"],
        latest_fifty_baseline_brier=latest["baseline_brier"],
        latest_fifty_baseline_log_loss=latest["baseline_log_loss"],
    )
    beats_all = (
        all_records["brier"] < all_records["baseline_brier"]
        and all_records["log_loss"] < all_records["baseline_log_loss"]
    )
    beats_latest = (
        latest["brier"] < latest["baseline_brier"]
        and latest["log_loss"] < latest["baseline_log_loss"]
    )
    if len(records) >= 50:
        result["rating"] = "GOOD" if beats_all else "WATCH"
    if len(records) >= 100 and beats_all and beats_latest:
        result["rating"] = "STRONG"
    return result


_SELECTIONS = {
    "HOME_WIN": "home",
    "DRAW": "draw",
    "AWAY_WIN": "away",
    "BTTS_YES": "btts_yes",
    "TOTAL_OVER_1_5": "total_over_1_5",
    "TOTAL_OVER_2_5": "total_over_2_5",
    "TOTAL_UNDER_2_5": "total_under_2_5",
    "TOTAL_UNDER_3_5": "total_under_3_5",
}


def selection_agreement(
    market: str, selection: str, values: Mapping[str, float]
) -> tuple[float | None, str]:
    selection = selection.strip().upper()
    if selection in ("HOME_OR_DRAW", "DRAW_OR_AWAY"):
        first, second = ("home", "draw") if selection == "HOME_OR_DRAW" else ("draw", "away")
        probability = (
            values[first] + values[second] if first in values and second in values else None
        )
    else:
        probability = values.get(_SELECTIONS.get(selection, ""))
    if not _valid_probability(probability):
        return None, "UNABLE_TO_EVALUATE"
    assert probability is not None
    if probability >= 0.5 and (
        market != "RESULT_1X2" or probability >= values.get(_max_outcome(values), 0)
    ):
        return probability, "AGREES"
    return probability, "WEAK_SUPPORT" if probability >= 0.4 else "DISAGREES"


def summarize_form(matches: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    if not matches:
        return None
    goals_for = sum(row["goals_for"] for row in matches)
    goals_against = sum(row["goals_against"] for row in matches)
    return {
        "recent_matches": len(matches),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "average_goals_for": goals_for / len(matches),
        "average_goals_against": goals_against / len(matches),
    }


def summarize_h2h(matches: tuple[dict[str, Any], ...]) -> dict[str, int]:
    return {
        "meetings": len(matches),
        "home_wins": sum(row["home_goals"] > row["away_goals"] for row in matches),
        "draws": sum(row["home_goals"] == row["away_goals"] for row in matches),
        "away_wins": sum(row["home_goals"] < row["away_goals"] for row in matches),
        "home_goals": sum(row["home_goals"] for row in matches),
        "away_goals": sum(row["away_goals"] for row in matches),
    }
