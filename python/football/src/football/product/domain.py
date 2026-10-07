"""Pure MVP product rules shared by ingestion jobs and tests."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid5

from football.forecasting.pitchapi_v3 import (
    MatchHistoryFeaturesV1,
    TeamHistoryFeaturesV1,
    TransferableGoalModelV1,
    TransferableParametersV1,
)

PRODUCT_NAMESPACE = UUID("4944b082-913a-4b04-9c42-76374ff3d840")
MODEL_ARTIFACT_PATH = Path("docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json")
MODEL_LABEL = "MVP_FORECAST"
MINIMUM_HISTORY_MATCHES = 10


class ForecastAvailability(StrEnum):
    AVAILABLE = "FORECAST_AVAILABLE"
    NOT_ENOUGH_HISTORY = "NOT_ENOUGH_HISTORY"
    INCOMPLETE = "SOURCE_DATA_INCOMPLETE"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"


class Agreement(StrEnum):
    AGREES = "AGREES"
    WEAK_SUPPORT = "WEAK_SUPPORT"
    DISAGREES = "DISAGREES"
    UNABLE_TO_EVALUATE = "UNABLE_TO_EVALUATE"


class LeagueRating(StrEnum):
    UNRATED = "UNRATED"
    WATCH = "WATCH"
    GOOD = "GOOD"
    STRONG = "STRONG"


@dataclass(frozen=True, slots=True)
class FinishedMatch:
    fixture_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_goals: int
    away_goals: int
    home_xg: float | None = None
    away_xg: float | None = None


@dataclass(frozen=True, slots=True)
class ProductForecast:
    expected_home_goals: float
    expected_away_goals: float
    home_probability: float
    draw_probability: float
    away_probability: float
    score_matrix: tuple[dict[str, int | float], ...]
    home_goal_distribution: tuple[float, ...]
    away_goal_distribution: tuple[float, ...]
    total_goal_distribution: tuple[float, ...]
    btts_yes: float
    home_clean_sheet: float
    away_clean_sheet: float


def stable_id(kind: str, *parts: object) -> UUID:
    normalized = "|".join(_normalize_identity_part(str(part)) for part in parts)
    return uuid5(PRODUCT_NAMESPACE, f"{kind}|{normalized}")


def normalize_team_name(value: str) -> str:
    normalized = re.sub(r"\b(fc|cf|afc|sc|club)\b", " ", value.casefold())
    normalized = normalized.replace("utd", "united")
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())
    aliases = {
        "inter": "internazionale",
        "inter milan": "internazionale",
        "paris saint germain": "psg",
    }
    return aliases.get(normalized, normalized)


def fixture_identity(
    competition_id: UUID,
    season_label: str,
    kickoff_at: datetime,
    home_team_id: UUID,
    away_team_id: UUID,
) -> UUID:
    _aware(kickoff_at)
    return stable_id(
        "fixture",
        competition_id,
        season_label,
        kickoff_at.astimezone(UTC).isoformat(),
        home_team_id,
        away_team_id,
    )


def forecast_from_history(
    *,
    artifact_path: Path,
    target_kickoff: datetime,
    home_team_id: UUID,
    away_team_id: UUID,
    history: Iterable[FinishedMatch],
) -> ProductForecast | None:
    _aware(target_kickoff)
    eligible = sorted(
        (match for match in history if match.kickoff_at < target_kickoff),
        key=lambda match: (match.kickoff_at, str(match.fixture_id)),
    )
    home_history = _team_history(eligible, home_team_id)
    away_history = _team_history(eligible, away_team_id)
    if len(home_history) < MINIMUM_HISTORY_MATCHES or len(away_history) < MINIMUM_HISTORY_MATCHES:
        return None
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    parameters = TransferableParametersV1(**artifact["parameters"])
    features = MatchHistoryFeaturesV1(
        home=_team_features(home_history[-MINIMUM_HISTORY_MATCHES:]),
        away=_team_features(away_history[-MINIMUM_HISTORY_MATCHES:]),
    )
    goal_forecast = TransferableGoalModelV1(parameters).forecast_features(features)
    score_cells = tuple(
        {
            "home_goals": home_index,
            "away_goals": away_index,
            "probability": probability,
        }
        for home_index, row in enumerate(goal_forecast.score_matrix.probabilities)
        for away_index, probability in enumerate(row)
    )
    home_goals = tuple(sum(row) for row in goal_forecast.score_matrix.probabilities)
    away_goals = tuple(
        sum(row[index] for row in goal_forecast.score_matrix.probabilities)
        for index in range(len(goal_forecast.score_matrix.labels))
    )
    total_goals = _total_goal_distribution(home_goals, away_goals)
    return ProductForecast(
        expected_home_goals=goal_forecast.lambda_home,
        expected_away_goals=goal_forecast.lambda_away,
        home_probability=goal_forecast.markets.home_win,
        draw_probability=goal_forecast.markets.draw,
        away_probability=goal_forecast.markets.away_win,
        score_matrix=score_cells,
        home_goal_distribution=home_goals,
        away_goal_distribution=away_goals,
        total_goal_distribution=total_goals,
        btts_yes=goal_forecast.markets.both_teams_to_score,
        home_clean_sheet=goal_forecast.markets.home_clean_sheet,
        away_clean_sheet=goal_forecast.markets.away_clean_sheet,
    )


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def forecast_payload(forecast: ProductForecast) -> dict[str, object]:
    return asdict(forecast)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def map_external_market(value: str) -> tuple[str, str] | None:
    key = re.sub(r"\s+", " ", value.strip().casefold())
    aliases = {
        "1": ("RESULT_1X2", "HOME_WIN"),
        "home": ("RESULT_1X2", "HOME_WIN"),
        "home win": ("RESULT_1X2", "HOME_WIN"),
        "home(1)": ("RESULT_1X2", "HOME_WIN"),
        "x": ("RESULT_1X2", "DRAW"),
        "draw": ("RESULT_1X2", "DRAW"),
        "draw(x)": ("RESULT_1X2", "DRAW"),
        "2": ("RESULT_1X2", "AWAY_WIN"),
        "away": ("RESULT_1X2", "AWAY_WIN"),
        "away win": ("RESULT_1X2", "AWAY_WIN"),
        "away(2)": ("RESULT_1X2", "AWAY_WIN"),
        "1x": ("DOUBLE_CHANCE", "HOME_OR_DRAW"),
        "home win or draw(1x)": ("DOUBLE_CHANCE", "HOME_OR_DRAW"),
        "x2": ("DOUBLE_CHANCE", "DRAW_OR_AWAY"),
        "away win or draw(x2)": ("DOUBLE_CHANCE", "DRAW_OR_AWAY"),
        "gg": ("BTTS", "BTTS_YES"),
        "btts": ("BTTS", "BTTS_YES"),
        "over 1.5": ("TOTAL_GOALS", "TOTAL_OVER_1_5"),
        "over 2.5": ("TOTAL_GOALS", "TOTAL_OVER_2_5"),
        "ov2.5": ("TOTAL_GOALS", "TOTAL_OVER_2_5"),
        "under 2.5": ("TOTAL_GOALS", "TOTAL_UNDER_2_5"),
        "under 3.5": ("TOTAL_GOALS", "TOTAL_UNDER_3_5"),
    }
    return aliases.get(key)


def agreement_for_selection(
    market: str,
    selection: str,
    probabilities: Mapping[str, float],
) -> Agreement:
    probability = _selection_probability(market, selection, probabilities)
    if probability is None or not math.isfinite(probability):
        return Agreement.UNABLE_TO_EVALUATE
    alternatives = _market_alternatives(market, probabilities)
    if probability >= 0.5 and (not alternatives or probability == max(alternatives)):
        return Agreement.AGREES
    if probability >= 0.4:
        return Agreement.WEAK_SUPPORT
    return Agreement.DISAGREES


def external_selection_correct(
    market: str,
    selection: str,
    home_goals: int,
    away_goals: int,
) -> bool | None:
    outcomes = {
        ("RESULT_1X2", "HOME_WIN"): home_goals > away_goals,
        ("RESULT_1X2", "DRAW"): home_goals == away_goals,
        ("RESULT_1X2", "AWAY_WIN"): away_goals > home_goals,
        ("DOUBLE_CHANCE", "HOME_OR_DRAW"): home_goals >= away_goals,
        ("DOUBLE_CHANCE", "DRAW_OR_AWAY"): away_goals >= home_goals,
        ("BTTS", "BTTS_YES"): home_goals > 0 and away_goals > 0,
        ("TOTAL_GOALS", "TOTAL_OVER_1_5"): home_goals + away_goals > 1,
        ("TOTAL_GOALS", "TOTAL_OVER_2_5"): home_goals + away_goals > 2,
        ("TOTAL_GOALS", "TOTAL_UNDER_2_5"): home_goals + away_goals <= 2,
        ("TOTAL_GOALS", "TOTAL_UNDER_3_5"): home_goals + away_goals <= 3,
    }
    return outcomes.get((market, selection))


def league_rating(
    *,
    total_forecasts: int,
    brier: float | None,
    log_loss: float | None,
    baseline_brier: float | None,
    baseline_log_loss: float | None,
    recent_brier: float | None,
    recent_log_loss: float | None,
    recent_baseline_brier: float | None,
    recent_baseline_log_loss: float | None,
) -> LeagueRating:
    if total_forecasts < 50:
        return LeagueRating.UNRATED
    values = (brier, log_loss, baseline_brier, baseline_log_loss)
    if any(value is None or not math.isfinite(value) for value in values):
        return LeagueRating.WATCH
    full_better = brier < baseline_brier and log_loss < baseline_log_loss  # type: ignore[operator]
    if not full_better:
        return LeagueRating.WATCH
    if total_forecasts < 100:
        return LeagueRating.GOOD
    recent_values = (
        recent_brier,
        recent_log_loss,
        recent_baseline_brier,
        recent_baseline_log_loss,
    )
    if any(value is None or not math.isfinite(value) for value in recent_values):
        return LeagueRating.GOOD
    recent_better = (
        recent_brier < recent_baseline_brier  # type: ignore[operator]
        and recent_log_loss < recent_baseline_log_loss  # type: ignore[operator]
    )
    return LeagueRating.STRONG if recent_better else LeagueRating.GOOD


def _team_history(
    matches: Sequence[FinishedMatch], team_id: UUID
) -> list[tuple[int, int, float | None]]:
    rows: list[tuple[int, int, float | None]] = []
    for match in matches:
        if match.home_team_id == team_id:
            rows.append((match.home_goals, match.away_goals, match.home_xg))
        elif match.away_team_id == team_id:
            rows.append((match.away_goals, match.home_goals, match.away_xg))
    return rows


def _team_features(rows: Sequence[tuple[int, int, float | None]]) -> TeamHistoryFeaturesV1:
    xg_values = tuple(row[2] for row in rows if row[2] is not None)
    return TeamHistoryFeaturesV1(
        appearances=len(rows),
        goals_for_mean=sum(row[0] for row in rows) / len(rows),
        goals_against_mean=sum(row[1] for row in rows) / len(rows),
        # The production control has beta_xg_for=0.0. Keep missing xG explicit until this
        # boundary; the ignored value is only materialized to satisfy its frozen contract.
        npxg_for_mean=(sum(xg_values) / len(xg_values) if xg_values else 0.0),
    )


def _total_goal_distribution(home: Sequence[float], away: Sequence[float]) -> tuple[float, ...]:
    exact_limit = len(home) - 1
    values = [0.0] * (exact_limit * 2 + 1)
    tail = 0.0
    for home_goals, home_probability in enumerate(home):
        for away_goals, away_probability in enumerate(away):
            probability = home_probability * away_probability
            if home_goals == exact_limit or away_goals == exact_limit:
                tail += probability
            else:
                values[home_goals + away_goals] += probability
    values.append(tail)
    return tuple(values)


def _selection_probability(
    market: str, selection: str, values: Mapping[str, float]
) -> float | None:
    keys = {
        ("RESULT_1X2", "HOME_WIN"): "home",
        ("RESULT_1X2", "DRAW"): "draw",
        ("RESULT_1X2", "AWAY_WIN"): "away",
        ("BTTS", "BTTS_YES"): "btts_yes",
        ("TOTAL_GOALS", "TOTAL_OVER_1_5"): "total_over_1_5",
        ("TOTAL_GOALS", "TOTAL_OVER_2_5"): "total_over_2_5",
        ("TOTAL_GOALS", "TOTAL_UNDER_2_5"): "total_under_2_5",
        ("TOTAL_GOALS", "TOTAL_UNDER_3_5"): "total_under_3_5",
    }
    if selection == "HOME_OR_DRAW":
        return values.get("home", 0.0) + values.get("draw", 0.0)
    if selection == "DRAW_OR_AWAY":
        return values.get("draw", 0.0) + values.get("away", 0.0)
    key = keys.get((market, selection))
    return values.get(key) if key is not None else None


def _market_alternatives(market: str, values: Mapping[str, float]) -> tuple[float, ...]:
    if market == "RESULT_1X2":
        return tuple(values[key] for key in ("home", "draw", "away") if key in values)
    return ()


def _normalize_identity_part(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
