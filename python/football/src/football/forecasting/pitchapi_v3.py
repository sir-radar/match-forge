"""Transferable, team-ID-independent goal models for PitchAPI V3."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from scipy.optimize import minimize
from scipy.stats import poisson, skellam

from football.forecasting.dixon_coles import GoalForecast, GoalMarkets, ScoreMatrix

PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3"
FEATURE_ID = "MATCHFORGE_TRANSFERABLE_ROLLING_LAST10_V1"
REFERENCE_ALGORITHM = "transferable-rolling-goals-poisson-v1"
CHALLENGER_ALGORITHM = "transferable-rolling-goals-npxg-poisson-v1"
HISTORY_WINDOW = 10
_RATE_FLOOR = 0.1


class TransferableModelError(ValueError):
    """Transferable model input or state violates the frozen V3 contract."""


@dataclass(frozen=True, slots=True)
class HistoryObservationV1:
    match_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_goals: int
    away_goals: int
    home_npxg: float
    away_npxg: float

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        if self.home_team_id == self.away_team_id:
            raise TransferableModelError("home and away teams must differ")
        for name, value in (("home_goals", self.home_goals), ("away_goals", self.away_goals)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TransferableModelError(f"{name} must be a non-negative integer")
        for name, npxg_value in (
            ("home_npxg", self.home_npxg),
            ("away_npxg", self.away_npxg),
        ):
            if not math.isfinite(npxg_value) or npxg_value < 0.0:
                raise TransferableModelError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class TransferableForecastContextV1:
    """Pre-match context. Target outcome fields are structurally absent."""

    match_id: UUID
    scope_key: str
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        if not self.scope_key:
            raise TransferableModelError("scope_key must not be empty")
        if self.home_team_id == self.away_team_id:
            raise TransferableModelError("home and away teams must differ")


@dataclass(frozen=True, slots=True)
class TeamHistoryFeaturesV1:
    appearances: int
    goals_for_mean: float
    goals_against_mean: float
    npxg_for_mean: float


@dataclass(frozen=True, slots=True)
class MatchHistoryFeaturesV1:
    home: TeamHistoryFeaturesV1
    away: TeamHistoryFeaturesV1


@dataclass(frozen=True, slots=True)
class _TeamAppearance:
    kickoff_at: datetime
    match_id: UUID
    goals_for: int
    goals_against: int
    npxg_for: float


class RollingHistoryV1:
    """Causal rolling state shared by reference and challenger."""

    def __init__(self, *, window: int = HISTORY_WINDOW) -> None:
        if isinstance(window, bool) or window != HISTORY_WINDOW:
            raise TransferableModelError("V3 history window must equal 10")
        self.window = window
        self._teams: dict[UUID, deque[_TeamAppearance]] = defaultdict(deque)
        self._matches: set[UUID] = set()

    def features(
        self, home_team_id: UUID, away_team_id: UUID, *, cutoff: datetime
    ) -> MatchHistoryFeaturesV1:
        _aware(cutoff, "cutoff")
        return MatchHistoryFeaturesV1(
            home=self._team_features(home_team_id, cutoff),
            away=self._team_features(away_team_id, cutoff),
        )

    def update_batch(
        self,
        observations: tuple[HistoryObservationV1, ...],
        *,
        next_cutoff: datetime | None = None,
    ) -> None:
        if not observations:
            raise TransferableModelError("history update batch must not be empty")
        kickoffs = {item.kickoff_at for item in observations}
        if len(kickoffs) != 1:
            raise TransferableModelError("history update batch must share one kickoff")
        kickoff = observations[0].kickoff_at
        if next_cutoff is not None and kickoff >= next_cutoff:
            raise TransferableModelError("history observations must strictly precede cutoff")
        identifiers = {item.match_id for item in observations}
        if len(identifiers) != len(observations) or identifiers & self._matches:
            raise TransferableModelError("duplicate history observation")
        for item in sorted(observations, key=lambda row: str(row.match_id)):
            self._append(
                item.home_team_id,
                _TeamAppearance(
                    item.kickoff_at,
                    item.match_id,
                    item.home_goals,
                    item.away_goals,
                    item.home_npxg,
                ),
            )
            self._append(
                item.away_team_id,
                _TeamAppearance(
                    item.kickoff_at,
                    item.match_id,
                    item.away_goals,
                    item.home_goals,
                    item.away_npxg,
                ),
            )
        self._matches.update(identifiers)

    def _append(self, team_id: UUID, value: _TeamAppearance) -> None:
        history = self._teams[team_id]
        if history and value.kickoff_at < history[-1].kickoff_at:
            raise TransferableModelError("history updates must be chronological")
        history.append(value)
        while len(history) > self.window:
            history.popleft()

    def _team_features(self, team_id: UUID, cutoff: datetime) -> TeamHistoryFeaturesV1:
        history = self._teams.get(team_id, ())
        if any(item.kickoff_at >= cutoff for item in history):
            raise TransferableModelError("history observations must strictly precede cutoff")
        if len(history) < self.window:
            raise TransferableModelError("team requires 10 prior appearances")
        selected = tuple(history)[-self.window :]
        return TeamHistoryFeaturesV1(
            appearances=len(selected),
            goals_for_mean=sum(item.goals_for for item in selected) / self.window,
            goals_against_mean=sum(item.goals_against for item in selected) / self.window,
            npxg_for_mean=sum(item.npxg_for for item in selected) / self.window,
        )


@dataclass(frozen=True, slots=True)
class TransferableParametersV1:
    home_intercept: float
    away_intercept: float
    attack_goals_weight: float
    defense_goals_weight: float
    beta_xg_for: float
    population_goal_mean: float
    population_npxg_mean: float

    def __post_init__(self) -> None:
        values = (
            self.home_intercept,
            self.away_intercept,
            self.attack_goals_weight,
            self.defense_goals_weight,
            self.beta_xg_for,
            self.population_goal_mean,
            self.population_npxg_mean,
        )
        if any(not math.isfinite(value) for value in values):
            raise TransferableModelError("transferable parameters must be finite")
        if not 0.0 <= self.beta_xg_for <= 1.0:
            raise TransferableModelError("beta_xg_for must be in [0,1]")
        if self.population_goal_mean <= 0.0 or self.population_npxg_mean <= 0.0:
            raise TransferableModelError("population means must be positive")

    def to_dict(self) -> dict[str, float]:
        return {
            "attack_goals_weight": self.attack_goals_weight,
            "away_intercept": self.away_intercept,
            "beta_xg_for": self.beta_xg_for,
            "defense_goals_weight": self.defense_goals_weight,
            "home_intercept": self.home_intercept,
            "population_goal_mean": self.population_goal_mean,
            "population_npxg_mean": self.population_npxg_mean,
        }


@dataclass(frozen=True, slots=True)
class TransferableTrainingRowV1:
    context: TransferableForecastContextV1
    features: MatchHistoryFeaturesV1
    home_goals: int
    away_goals: int


class TransferableGoalModelV1:
    def __init__(self, parameters: TransferableParametersV1) -> None:
        self.parameters = parameters

    def forecast(
        self, context: TransferableForecastContextV1, history: RollingHistoryV1
    ) -> GoalForecast:
        features = history.features(
            context.home_team_id,
            context.away_team_id,
            cutoff=context.kickoff_at,
        )
        return self.forecast_features(features)

    def forecast_features(self, features: MatchHistoryFeaturesV1) -> GoalForecast:
        home_mean, away_mean = expected_goals(self.parameters, features)
        return _poisson_forecast(home_mean, away_mean)


def expected_goals(
    parameters: TransferableParametersV1, features: MatchHistoryFeaturesV1
) -> tuple[float, float]:
    home_attack = _log_ratio(features.home.goals_for_mean, parameters.population_goal_mean)
    away_attack = _log_ratio(features.away.goals_for_mean, parameters.population_goal_mean)
    home_defense = _log_ratio(features.home.goals_against_mean, parameters.population_goal_mean)
    away_defense = _log_ratio(features.away.goals_against_mean, parameters.population_goal_mean)
    home_xg = _log_ratio(features.home.npxg_for_mean, parameters.population_npxg_mean)
    away_xg = _log_ratio(features.away.npxg_for_mean, parameters.population_npxg_mean)
    home = math.exp(
        parameters.home_intercept
        + parameters.attack_goals_weight * home_attack
        + parameters.defense_goals_weight * away_defense
        + parameters.beta_xg_for * home_xg
    )
    away = math.exp(
        parameters.away_intercept
        + parameters.attack_goals_weight * away_attack
        + parameters.defense_goals_weight * home_defense
        + parameters.beta_xg_for * away_xg
    )
    if not math.isfinite(home) or not math.isfinite(away) or home <= 0.0 or away <= 0.0:
        raise TransferableModelError("forecast goal means must be finite and positive")
    return home, away


def build_training_rows(
    observations: Iterable[HistoryObservationV1], *, scope_key: str
) -> tuple[TransferableTrainingRowV1, ...]:
    ordered = sorted(observations, key=lambda row: (row.kickoff_at, str(row.match_id)))
    history = RollingHistoryV1()
    rows: list[TransferableTrainingRowV1] = []
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end].kickoff_at == ordered[position].kickoff_at:
            end += 1
        batch = ordered[position:end]
        for item in batch:
            try:
                features = history.features(
                    item.home_team_id,
                    item.away_team_id,
                    cutoff=item.kickoff_at,
                )
            except TransferableModelError as error:
                if "10 prior appearances" not in str(error):
                    raise
                continue
            rows.append(
                TransferableTrainingRowV1(
                    context=TransferableForecastContextV1(
                        match_id=item.match_id,
                        scope_key=scope_key,
                        kickoff_at=item.kickoff_at,
                        home_team_id=item.home_team_id,
                        away_team_id=item.away_team_id,
                    ),
                    features=features,
                    home_goals=item.home_goals,
                    away_goals=item.away_goals,
                )
            )
        history.update_batch(tuple(batch))
        position = end
    return tuple(rows)


def fit_transferable_parameters(
    rows: Sequence[TransferableTrainingRowV1],
    observations: Sequence[HistoryObservationV1],
    *,
    include_xg: bool,
) -> TransferableParametersV1:
    if not rows or not observations:
        raise TransferableModelError("transferable fitting requires development rows")
    goal_mean = sum(item.home_goals + item.away_goals for item in observations) / (
        2 * len(observations)
    )
    npxg_mean = sum(item.home_npxg + item.away_npxg for item in observations) / (
        2 * len(observations)
    )
    initial = [math.log(goal_mean * 1.1), math.log(goal_mean * 0.9), 0.5, 0.5]
    bounds = [(-3.0, 3.0), (-3.0, 3.0), (-2.0, 2.0), (-2.0, 2.0)]
    if include_xg:
        initial.append(0.1)
        bounds.append((0.0, 1.0))

    def objective(values: Sequence[float]) -> float:
        parameters = TransferableParametersV1(
            home_intercept=float(values[0]),
            away_intercept=float(values[1]),
            attack_goals_weight=float(values[2]),
            defense_goals_weight=float(values[3]),
            beta_xg_for=float(values[4]) if include_xg else 0.0,
            population_goal_mean=goal_mean,
            population_npxg_mean=npxg_mean,
        )
        return sum(_poisson_loss(parameters, row) for row in rows)

    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        bounds=bounds,
        options={"ftol": 1e-12, "maxiter": 1_000},
    )
    if not result.success or not math.isfinite(float(result.fun)):
        raise TransferableModelError(f"transferable optimizer failed: {result.message}")
    return TransferableParametersV1(
        home_intercept=float(result.x[0]),
        away_intercept=float(result.x[1]),
        attack_goals_weight=float(result.x[2]),
        defense_goals_weight=float(result.x[3]),
        beta_xg_for=float(result.x[4]) if include_xg else 0.0,
        population_goal_mean=goal_mean,
        population_npxg_mean=npxg_mean,
    )


def parameter_payload(
    parameters: TransferableParametersV1, *, model_role: str
) -> Mapping[str, object]:
    algorithm = REFERENCE_ALGORITHM if model_role == "REFERENCE" else CHALLENGER_ALGORITHM
    return MappingProxyType(
        {
            "algorithm_version": algorithm,
            "feature_id": FEATURE_ID,
            "history_window": HISTORY_WINDOW,
            "model_role": model_role,
            "parameters": parameters.to_dict(),
            "protocol_id": PROTOCOL_ID,
            "team_id_parameters": False,
            "unseen_team_policy": "same rolling-last-10 feature construction for every team",
        }
    )


def _poisson_loss(parameters: TransferableParametersV1, row: TransferableTrainingRowV1) -> float:
    home, away = expected_goals(parameters, row.features)
    return (
        home
        - row.home_goals * math.log(home)
        + math.lgamma(row.home_goals + 1)
        + away
        - row.away_goals * math.log(away)
        + math.lgamma(row.away_goals + 1)
    )


def _poisson_forecast(home_mean: float, away_mean: float) -> GoalForecast:
    labels = ("0", "1", "2", "3", "4", "5+")
    home = [float(poisson.pmf(value, home_mean)) for value in range(5)]
    away = [float(poisson.pmf(value, away_mean)) for value in range(5)]
    home.append(1.0 - sum(home))
    away.append(1.0 - sum(away))
    matrix = tuple(tuple(h * a for a in away) for h in home)
    away_win = float(skellam.cdf(-1, home_mean, away_mean))
    draw = float(skellam.pmf(0, home_mean, away_mean))
    home_win = 1.0 - away_win - draw
    total_mean = home_mean + away_mean

    def over(threshold: int) -> float:
        return 1.0 - float(poisson.cdf(threshold, total_mean))

    return GoalForecast(
        lambda_home=home_mean,
        lambda_away=away_mean,
        low_score_correlation=0.0,
        score_matrix=ScoreMatrix(labels=labels, probabilities=matrix),
        markets=GoalMarkets(
            home_win=home_win,
            draw=draw,
            away_win=away_win,
            over_1_5=over(1),
            over_2_5=over(2),
            over_3_5=over(3),
            both_teams_to_score=(1.0 - math.exp(-home_mean)) * (1.0 - math.exp(-away_mean)),
            home_clean_sheet=math.exp(-away_mean),
            away_clean_sheet=math.exp(-home_mean),
        ),
    )


def _log_ratio(value: float, population: float) -> float:
    return math.log(max(value, _RATE_FLOOR) / population)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TransferableModelError(f"{field_name} must include a timezone")
