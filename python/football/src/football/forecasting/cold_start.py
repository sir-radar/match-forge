from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from football.forecasting.model_contracts import ForecastInputSnapshot, HistoricalMatch

_EPSILON = 0.05
_FULL_HISTORY_MATCHES = 10


class ColdStartError(ValueError):
    """Cold-start input or configuration cannot produce a safe strength estimate."""


class ArtifactTeamState(StrEnum):
    FITTED = "FITTED"
    UNSEEN_TEAM = "UNSEEN_TEAM"


class HistoryTeamState(StrEnum):
    ZERO_HISTORY = "ZERO_HISTORY"
    PARTIAL_HISTORY = "PARTIAL_HISTORY"
    TRANSFER_HISTORY = "TRANSFER_HISTORY"
    FULL_HISTORY = "FULL_HISTORY"


class PromotionStatus(StrEnum):
    PROMOTED_TEAM = "PROMOTED_TEAM"
    NOT_PROMOTED = "NOT_PROMOTED"
    PROMOTION_STATUS_UNKNOWN = "PROMOTION_STATUS_UNKNOWN"


@dataclass(frozen=True, slots=True)
class ColdStartConfig:
    shrinkage_k: float
    competition_transfer_weights: tuple[tuple[UUID, UUID, float], ...] = ()
    rating_reference: float = 1500.0
    rating_scale: float = 400.0
    rating_coefficient: float = 0.0
    recent_5_coefficient: float = 0.0
    recent_10_coefficient: float = 0.0
    home_away_coefficient: float = 0.0
    league_form_coefficient: float = 0.0
    opponent_adjusted_coefficient: float = 0.0
    xg_coefficient: float = 0.0
    l2_regularization: float = 1.0
    home_rate_coefficients: tuple[float, ...] = ()
    away_rate_coefficients: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.shrinkage_k) or self.shrinkage_k <= 0:
            raise ValueError("shrinkage_k must be finite and positive")
        if not math.isfinite(self.rating_scale) or self.rating_scale <= 0:
            raise ValueError("rating_scale must be finite and positive")
        if self.l2_regularization not in (0.01, 0.1, 1.0, 10.0):
            raise ValueError("l2_regularization must use the frozen candidate grid")
        for name, values in (
            ("home_rate_coefficients", self.home_rate_coefficients),
            ("away_rate_coefficients", self.away_rate_coefficients),
        ):
            if values and len(values) != 10:
                raise ValueError(f"{name} must contain exactly ten coefficients")
            if any(not math.isfinite(value) for value in values):
                raise ValueError(f"{name} must be finite")
        relationships: set[tuple[UUID, UUID]] = set()
        for source, target, weight in self.competition_transfer_weights:
            if (source, target) in relationships:
                raise ValueError("competition transfer relationships must be unique")
            relationships.add((source, target))
            if weight not in (0.25, 0.5, 0.75, 1.0):
                raise ValueError("competition transfer weight must use the frozen candidate grid")


@dataclass(frozen=True, slots=True)
class ColdStartStrength:
    attack_log_strength: float
    defence_log_strength: float
    effective_history_matches: float
    competition_prior_attack: float
    competition_prior_defence: float
    competition_goal_mean: float
    history_weight: float
    rating_adjustment: float
    goal_signal: tuple[float, float] | None
    xg_signal: tuple[float, float] | None
    home_away_adjustment: float
    source_competition_context: tuple[str, ...]
    cold_start_confidence: float
    missingness: tuple[str, ...]
    history_state: HistoryTeamState
    promotion_status: PromotionStatus


def shrinkage_weight(n: float, k: float) -> float:
    if not math.isfinite(n) or n < 0:
        raise ValueError("history count must be finite and non-negative")
    if not math.isfinite(k) or k <= 0:
        raise ValueError("shrinkage strength must be finite and positive")
    return n / (n + k)


class ColdStartStrengthV1:
    def __init__(self, config: ColdStartConfig) -> None:
        self.config = config

    def estimate(self, snapshot: ForecastInputSnapshot, team_id: UUID) -> ColdStartStrength:
        if team_id not in (snapshot.home_team_id, snapshot.away_team_id):
            raise ColdStartError("team is not part of forecast fixture")
        competition_rows = tuple(
            row
            for row in snapshot.qualified_history
            if row.competition_id == snapshot.competition_id
        )
        if not competition_rows:
            raise ColdStartError("target competition has no eligible prior scoring environment")
        competition_goal_mean = sum(row.home_goals + row.away_goals for row in competition_rows) / (
            2.0 * len(competition_rows)
        )
        weights = self._eligible_team_rows(snapshot, team_id)
        effective_matches = sum(weight for _, weight in weights)
        history_state = _history_state(snapshot, team_id, weights)
        promotion_status = _promotion_status(snapshot, team_id)
        history_weight = shrinkage_weight(effective_matches, self.config.shrinkage_k)
        missingness: list[str] = []

        if effective_matches:
            goals_for_mean = (
                sum(weight * _team_goals(row, team_id)[0] for row, weight in weights)
                / effective_matches
            )
            goals_against_mean = (
                sum(weight * _team_goals(row, team_id)[1] for row, weight in weights)
                / effective_matches
            )
            attack_observed = math.log(
                (goals_for_mean + _EPSILON) / (competition_goal_mean + _EPSILON)
            )
            defence_observed = math.log(
                (goals_against_mean + _EPSILON) / (competition_goal_mean + _EPSILON)
            )
            goal_signal: tuple[float, float] | None = (
                attack_observed,
                defence_observed,
            )
        else:
            attack_observed = defence_observed = 0.0
            goal_signal = None

        form = snapshot.home_form_10 if team_id == snapshot.home_team_id else snapshot.away_form_10
        xg_signal = _xg_signal(form.xg_for, form.xg_against, competition_goal_mean)
        if xg_signal is None:
            missingness.append("XG_UNAVAILABLE")
        rating_adjustment = self._rating_adjustment(snapshot, team_id, missingness)
        context_adjustment = self._context_adjustment(snapshot, team_id)
        xg_adjustment = (
            self.config.xg_coefficient * (xg_signal[0] - xg_signal[1])
            if xg_signal is not None
            else 0.0
        )
        attack = history_weight * attack_observed + rating_adjustment + context_adjustment
        defence = history_weight * defence_observed - rating_adjustment - context_adjustment
        attack += xg_adjustment
        defence -= xg_adjustment
        source_competitions = tuple(
            sorted({str(row.competition_id) for row, weight in weights if weight < 1.0})
        )
        return ColdStartStrength(
            attack_log_strength=attack,
            defence_log_strength=defence,
            effective_history_matches=effective_matches,
            competition_prior_attack=0.0,
            competition_prior_defence=0.0,
            competition_goal_mean=competition_goal_mean,
            history_weight=history_weight,
            rating_adjustment=rating_adjustment,
            goal_signal=goal_signal,
            xg_signal=xg_signal,
            home_away_adjustment=self._home_away_adjustment(snapshot, team_id),
            source_competition_context=source_competitions,
            cold_start_confidence=history_weight,
            missingness=tuple(missingness),
            history_state=history_state,
            promotion_status=promotion_status,
        )

    def classify_history(self, snapshot: ForecastInputSnapshot, team_id: UUID) -> HistoryTeamState:
        return _history_state(snapshot, team_id, self._eligible_team_rows(snapshot, team_id))

    def _eligible_team_rows(
        self, snapshot: ForecastInputSnapshot, team_id: UUID
    ) -> tuple[tuple[HistoricalMatch, float], ...]:
        transfer = {
            (source, target): weight
            for source, target, weight in self.config.competition_transfer_weights
        }
        rows: list[tuple[HistoricalMatch, float]] = []
        for row in snapshot.qualified_history:
            if team_id not in (row.home_team_id, row.away_team_id):
                continue
            weight = (
                1.0
                if row.competition_id == snapshot.competition_id
                else transfer.get((row.competition_id, snapshot.competition_id), 0.0)
            )
            if weight > 0:
                rows.append((row, weight))
        return tuple(rows)

    def _rating_adjustment(
        self, snapshot: ForecastInputSnapshot, team_id: UUID, missingness: list[str]
    ) -> float:
        home = team_id == snapshot.home_team_id
        marker = "HOME_RATING_UNAVAILABLE" if home else "AWAY_RATING_UNAVAILABLE"
        if marker in snapshot.missingness:
            missingness.append("RATING_UNAVAILABLE")
            return 0.0
        rating = snapshot.rating.home_rating if home else snapshot.rating.away_rating
        return (
            self.config.rating_coefficient
            * (rating - self.config.rating_reference)
            / self.config.rating_scale
        )

    def _context_adjustment(self, snapshot: ForecastInputSnapshot, team_id: UUID) -> float:
        home = team_id == snapshot.home_team_id
        form_5 = snapshot.home_form_5 if home else snapshot.away_form_5
        form_10 = snapshot.home_form_10 if home else snapshot.away_form_10
        split = snapshot.home_home_form_10 if home else snapshot.away_away_form_10
        league = snapshot.home_league_form_10 if home else snapshot.away_league_form_10
        return sum(
            (
                self.config.recent_5_coefficient * (form_5.goal_difference or 0.0),
                self.config.recent_10_coefficient * (form_10.goal_difference or 0.0),
                self.config.home_away_coefficient * (split.goal_difference or 0.0),
                self.config.league_form_coefficient * (league.goal_difference or 0.0),
                self.config.opponent_adjusted_coefficient
                * (form_10.opponent_adjusted_points or 0.0),
            )
        )

    def _home_away_adjustment(self, snapshot: ForecastInputSnapshot, team_id: UUID) -> float:
        form = (
            snapshot.home_home_form_10
            if team_id == snapshot.home_team_id
            else snapshot.away_away_form_10
        )
        return self.config.home_away_coefficient * (form.goal_difference or 0.0)


def _history_state(
    snapshot: ForecastInputSnapshot,
    team_id: UUID,
    weighted_rows: tuple[tuple[HistoricalMatch, float], ...],
) -> HistoryTeamState:
    same_competition = sum(
        row.competition_id == snapshot.competition_id for row, _ in weighted_rows
    )
    if same_competition >= _FULL_HISTORY_MATCHES:
        return HistoryTeamState.FULL_HISTORY
    if same_competition:
        return HistoryTeamState.PARTIAL_HISTORY
    if weighted_rows:
        return HistoryTeamState.TRANSFER_HISTORY
    return HistoryTeamState.ZERO_HISTORY


def _promotion_status(snapshot: ForecastInputSnapshot, team_id: UUID) -> PromotionStatus:
    promoted = (
        snapshot.home_promoted if team_id == snapshot.home_team_id else snapshot.away_promoted
    )
    if promoted is True:
        return PromotionStatus.PROMOTED_TEAM
    if promoted is False:
        return PromotionStatus.NOT_PROMOTED
    return PromotionStatus.PROMOTION_STATUS_UNKNOWN


def _team_goals(row: HistoricalMatch, team_id: UUID) -> tuple[int, int]:
    if row.home_team_id == team_id:
        return row.home_goals, row.away_goals
    return row.away_goals, row.home_goals


def _xg_signal(
    xg_for: float | None, xg_against: float | None, competition_goal_mean: float
) -> tuple[float, float] | None:
    if xg_for is None or xg_against is None:
        return None
    return (
        math.log((xg_for + _EPSILON) / (competition_goal_mean + _EPSILON)),
        math.log((xg_against + _EPSILON) / (competition_goal_mean + _EPSILON)),
    )


def transferable_context_features(snapshot: ForecastInputSnapshot) -> tuple[float, ...]:
    home_xg = snapshot.home_form_10.xg_difference
    away_xg = snapshot.away_form_10.xg_difference
    xg_missing = home_xg is None or away_xg is None
    competition_rows = tuple(
        row for row in snapshot.qualified_history if row.competition_id == snapshot.competition_id
    )
    competition_mean = (
        sum(row.home_goals + row.away_goals for row in competition_rows)
        / (2.0 * len(competition_rows))
        if competition_rows
        else 1.0
    )
    return (
        1.0,
        snapshot.rating.rating_difference / 400.0,
        _difference(snapshot.home_form_5.goal_difference, snapshot.away_form_5.goal_difference),
        _difference(snapshot.home_form_10.goal_difference, snapshot.away_form_10.goal_difference),
        _difference(
            snapshot.home_home_form_10.goal_difference,
            snapshot.away_away_form_10.goal_difference,
        ),
        _difference(
            snapshot.home_league_form_10.goal_difference,
            snapshot.away_league_form_10.goal_difference,
        ),
        _difference(
            snapshot.home_form_10.opponent_adjusted_points,
            snapshot.away_form_10.opponent_adjusted_points,
        ),
        _difference(home_xg, away_xg),
        float(xg_missing),
        math.log(competition_mean + _EPSILON),
    )


def rate_context_adjustments(
    config: ColdStartConfig, snapshot: ForecastInputSnapshot
) -> tuple[float, float]:
    features = transferable_context_features(snapshot)
    home = (
        sum(
            value * coefficient
            for value, coefficient in zip(features, config.home_rate_coefficients, strict=True)
        )
        if config.home_rate_coefficients
        else 0.0
    )
    away = (
        sum(
            value * coefficient
            for value, coefficient in zip(features, config.away_rate_coefficients, strict=True)
        )
        if config.away_rate_coefficients
        else 0.0
    )
    return home, away


def _difference(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0
    return left - right
