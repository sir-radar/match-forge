"""Roster-independent rolling npxG-for/against Dixon-Coles research model."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson, skellam

HISTORY_WINDOW = 10
FEATURE_OFFSET = 0.05
TAIL_START = 10
RATE_MINIMUM = 0.05
RATE_MAXIMUM = 6.0
TAU_MINIMUM = 1e-9
ModelRole = Literal["reference", "v5", "candidate", "poisson_candidate"]


class ResearchModelError(ValueError):
    """Input or fitted state violates the frozen V2 research contract."""


@dataclass(frozen=True, slots=True)
class ResearchObservationV2:
    match_id: UUID
    scope_key: str
    competition: str
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_goals: int
    away_goals: int
    home_npxg: float
    away_npxg: float

    def __post_init__(self) -> None:
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise ResearchModelError("kickoff_at must include a timezone")
        if not self.scope_key or not self.competition:
            raise ResearchModelError("scope and competition must not be empty")
        if self.home_team_id == self.away_team_id:
            raise ResearchModelError("home and away teams must differ")
        for name, goal_value in (
            ("home_goals", self.home_goals),
            ("away_goals", self.away_goals),
        ):
            if isinstance(goal_value, bool) or not isinstance(goal_value, int) or goal_value < 0:
                raise ResearchModelError(f"{name} must be a non-negative integer")
        for name, npxg_value in (
            ("home_npxg", self.home_npxg),
            ("away_npxg", self.away_npxg),
        ):
            if not math.isfinite(npxg_value) or npxg_value < 0.0:
                raise ResearchModelError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class RollingFeaturesV2:
    home_goals_for: float
    home_goals_against: float
    home_npxg_for: float
    home_npxg_against: float
    away_goals_for: float
    away_goals_against: float
    away_npxg_for: float
    away_npxg_against: float

    def __post_init__(self) -> None:
        if any(not math.isfinite(value) for value in self.values()):
            raise ResearchModelError("rolling features must be finite")

    def values(self) -> tuple[float, ...]:
        return (
            self.home_goals_for,
            self.home_goals_against,
            self.home_npxg_for,
            self.home_npxg_against,
            self.away_goals_for,
            self.away_goals_against,
            self.away_npxg_for,
            self.away_npxg_against,
        )


@dataclass(frozen=True, slots=True)
class ResearchRowV2:
    match_id: UUID
    scope_key: str
    competition: str
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    features: RollingFeaturesV2
    home_goals: int
    away_goals: int


@dataclass(frozen=True, slots=True)
class ModelParametersV2:
    global_intercept: float
    global_home_advantage: float
    goals_for_weight: float
    goals_against_weight: float
    npxg_for_weight: float
    npxg_against_weight: float
    rho: float
    competition_baseline_deviations: Mapping[str, float]
    competition_home_advantage_deviations: Mapping[str, float]
    regularization: tuple[float, float, float]

    def __post_init__(self) -> None:
        scalar = (
            self.global_intercept,
            self.global_home_advantage,
            self.goals_for_weight,
            self.goals_against_weight,
            self.npxg_for_weight,
            self.npxg_against_weight,
            self.rho,
            *self.competition_baseline_deviations.values(),
            *self.competition_home_advantage_deviations.values(),
            *self.regularization,
        )
        if any(not math.isfinite(value) for value in scalar):
            raise ResearchModelError("model parameters must be finite")
        if any(
            value < 0.0
            for value in (
                self.goals_for_weight,
                self.goals_against_weight,
                self.npxg_for_weight,
                self.npxg_against_weight,
            )
        ):
            raise ResearchModelError("feature weights must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "competition_baseline_deviations": dict(
                sorted(self.competition_baseline_deviations.items())
            ),
            "competition_home_advantage_deviations": dict(
                sorted(self.competition_home_advantage_deviations.items())
            ),
            "global_home_advantage": self.global_home_advantage,
            "global_intercept": self.global_intercept,
            "goals_against_weight": self.goals_against_weight,
            "goals_for_weight": self.goals_for_weight,
            "npxg_against_weight": self.npxg_against_weight,
            "npxg_for_weight": self.npxg_for_weight,
            "regularization": list(self.regularization),
            "rho": self.rho,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ModelParametersV2:
        return cls(
            global_intercept=float(cast(float, value["global_intercept"])),
            global_home_advantage=float(cast(float, value["global_home_advantage"])),
            goals_for_weight=float(cast(float, value["goals_for_weight"])),
            goals_against_weight=float(cast(float, value["goals_against_weight"])),
            npxg_for_weight=float(cast(float, value["npxg_for_weight"])),
            npxg_against_weight=float(cast(float, value["npxg_against_weight"])),
            rho=float(cast(float, value["rho"])),
            competition_baseline_deviations={
                str(key): float(cast(float, item))
                for key, item in cast(
                    Mapping[str, object], value["competition_baseline_deviations"]
                ).items()
            },
            competition_home_advantage_deviations={
                str(key): float(cast(float, item))
                for key, item in cast(
                    Mapping[str, object], value["competition_home_advantage_deviations"]
                ).items()
            },
            regularization=cast(
                tuple[float, float, float],
                tuple(
                    float(cast(float, item))
                    for item in cast(Sequence[object], value["regularization"])
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class PredictionV2:
    lambda_home: float
    lambda_away: float
    rho: float
    score_matrix: tuple[tuple[float, ...], ...]
    one_x_two: tuple[float, float, float]

    def exact_score_probability(self, home_goals: int, away_goals: int) -> float:
        return (
            float(poisson.pmf(home_goals, self.lambda_home))
            * float(poisson.pmf(away_goals, self.lambda_away))
            * dixon_coles_tau(home_goals, away_goals, self.lambda_home, self.lambda_away, self.rho)
        )


@dataclass(frozen=True, slots=True)
class _Appearance:
    kickoff_at: datetime
    goals_for: int
    goals_against: int
    npxg_for: float
    npxg_against: float


def research_rows(observations: Iterable[ResearchObservationV2]) -> tuple[ResearchRowV2, ...]:
    grouped: dict[str, list[ResearchObservationV2]] = defaultdict(list)
    for observation in observations:
        grouped[observation.scope_key].append(observation)
    rows: list[ResearchRowV2] = []
    for scope_key in sorted(grouped):
        rows.extend(_scope_rows(grouped[scope_key]))
    return tuple(sorted(rows, key=lambda row: (row.kickoff_at, str(row.match_id))))


def _scope_rows(observations: Sequence[ResearchObservationV2]) -> list[ResearchRowV2]:
    ordered = sorted(observations, key=lambda row: (row.kickoff_at, str(row.match_id)))
    histories: dict[UUID, deque[_Appearance]] = defaultdict(deque)
    prior_goals = 0.0
    prior_npxg = 0.0
    prior_team_appearances = 0
    output: list[ResearchRowV2] = []
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end].kickoff_at == ordered[position].kickoff_at:
            end += 1
        batch = ordered[position:end]
        goal_center = prior_goals / prior_team_appearances if prior_team_appearances else None
        npxg_center = prior_npxg / prior_team_appearances if prior_team_appearances else None
        if goal_center is not None and npxg_center is not None:
            for item in batch:
                home = histories[item.home_team_id]
                away = histories[item.away_team_id]
                if len(home) >= HISTORY_WINDOW and len(away) >= HISTORY_WINDOW:
                    output.append(_row(item, home, away, goal_center, npxg_center))
        for item in sorted(batch, key=lambda row: str(row.match_id)):
            _append(histories[item.home_team_id], item, home=True)
            _append(histories[item.away_team_id], item, home=False)
            prior_goals += item.home_goals + item.away_goals
            prior_npxg += item.home_npxg + item.away_npxg
            prior_team_appearances += 2
        position = end
    return output


def _append(history: deque[_Appearance], item: ResearchObservationV2, *, home: bool) -> None:
    history.append(
        _Appearance(
            kickoff_at=item.kickoff_at,
            goals_for=item.home_goals if home else item.away_goals,
            goals_against=item.away_goals if home else item.home_goals,
            npxg_for=item.home_npxg if home else item.away_npxg,
            npxg_against=item.away_npxg if home else item.home_npxg,
        )
    )
    while len(history) > HISTORY_WINDOW:
        history.popleft()


def _row(
    item: ResearchObservationV2,
    home: Sequence[_Appearance],
    away: Sequence[_Appearance],
    goal_center: float,
    npxg_center: float,
) -> ResearchRowV2:
    if any(value.kickoff_at >= item.kickoff_at for value in (*home, *away)):
        raise ResearchModelError("rolling history must strictly precede target kickoff")
    features = RollingFeaturesV2(
        *_team_features(home, goal_center, npxg_center),
        *_team_features(away, goal_center, npxg_center),
    )
    return ResearchRowV2(
        item.match_id,
        item.scope_key,
        item.competition,
        item.kickoff_at,
        item.home_team_id,
        item.away_team_id,
        features,
        item.home_goals,
        item.away_goals,
    )


def _team_features(
    history: Sequence[_Appearance], goal_center: float, npxg_center: float
) -> tuple[float, float, float, float]:
    selected = tuple(history)[-HISTORY_WINDOW:]
    return (
        _log_center(sum(item.goals_for for item in selected) / HISTORY_WINDOW, goal_center),
        _log_center(sum(item.goals_against for item in selected) / HISTORY_WINDOW, goal_center),
        _log_center(sum(item.npxg_for for item in selected) / HISTORY_WINDOW, npxg_center),
        _log_center(sum(item.npxg_against for item in selected) / HISTORY_WINDOW, npxg_center),
    )


def _log_center(value: float, center: float) -> float:
    return math.log((value + FEATURE_OFFSET) / (center + FEATURE_OFFSET))


def dixon_coles_tau(
    home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float
) -> float:
    if (home_goals, away_goals) == (0, 0):
        return 1.0 - lambda_home * lambda_away * rho
    if (home_goals, away_goals) == (0, 1):
        return 1.0 + lambda_home * rho
    if (home_goals, away_goals) == (1, 0):
        return 1.0 + lambda_away * rho
    if (home_goals, away_goals) == (1, 1):
        return 1.0 - rho
    return 1.0


def expected_goals(parameters: ModelParametersV2, row: ResearchRowV2) -> tuple[float, float]:
    baseline = parameters.global_intercept + parameters.competition_baseline_deviations.get(
        row.competition, 0.0
    )
    home_advantage = (
        parameters.global_home_advantage
        + parameters.competition_home_advantage_deviations.get(row.competition, 0.0)
    )
    features = row.features
    home_log = (
        baseline
        + home_advantage
        + parameters.goals_for_weight * features.home_goals_for
        + parameters.goals_against_weight * features.away_goals_against
        + parameters.npxg_for_weight * features.home_npxg_for
        + parameters.npxg_against_weight * features.away_npxg_against
    )
    away_log = (
        baseline
        + parameters.goals_for_weight * features.away_goals_for
        + parameters.goals_against_weight * features.home_goals_against
        + parameters.npxg_for_weight * features.away_npxg_for
        + parameters.npxg_against_weight * features.home_npxg_against
    )
    return math.exp(home_log), math.exp(away_log)


def forecast(parameters: ModelParametersV2, features: RollingFeaturesV2) -> PredictionV2:
    synthetic = ResearchRowV2(
        UUID(int=0),
        "forecast",
        "unseen",
        datetime.fromisoformat("2000-01-01T00:00:00+00:00"),
        UUID(int=1),
        UUID(int=2),
        features,
        0,
        0,
    )
    home, away = expected_goals(parameters, synthetic)
    if not RATE_MINIMUM <= home <= RATE_MAXIMUM or not RATE_MINIMUM <= away <= RATE_MAXIMUM:
        raise ResearchModelError("forecast goal rate outside frozen bounds")
    if (
        min(
            dixon_coles_tau(x, y, home, away, parameters.rho)
            for x, y in ((0, 0), (0, 1), (1, 0), (1, 1))
        )
        < TAU_MINIMUM
    ):
        raise ResearchModelError("Dixon-Coles tau violates positivity bound")
    matrix = _score_matrix(home, away, parameters.rho)
    one_x_two = _one_x_two(home, away, parameters.rho)
    return PredictionV2(home, away, parameters.rho, matrix, one_x_two)


def predict_row(parameters: ModelParametersV2, row: ResearchRowV2) -> PredictionV2:
    home, away = expected_goals(parameters, row)
    synthetic_parameters = ModelParametersV2(
        math.log(away),
        math.log(home / away),
        0.0,
        0.0,
        0.0,
        0.0,
        parameters.rho,
        {},
        {},
        parameters.regularization,
    )
    return forecast(synthetic_parameters, row.features)


def _score_matrix(home: float, away: float, rho: float) -> tuple[tuple[float, ...], ...]:
    home_probabilities = [float(poisson.pmf(value, home)) for value in range(TAIL_START)]
    away_probabilities = [float(poisson.pmf(value, away)) for value in range(TAIL_START)]
    home_probabilities.append(1.0 - sum(home_probabilities))
    away_probabilities.append(1.0 - sum(away_probabilities))
    matrix = [
        [home_probability * away_probability for away_probability in away_probabilities]
        for home_probability in home_probabilities
    ]
    for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
        matrix[x][y] *= dixon_coles_tau(x, y, home, away, rho)
    total = sum(sum(row) for row in matrix)
    if abs(total - 1.0) > 1e-12:
        raise ResearchModelError("Dixon-Coles score matrix is not normalized")
    return tuple(tuple(value for value in row) for row in matrix)


def _one_x_two(home: float, away: float, rho: float) -> tuple[float, float, float]:
    away_win = float(skellam.cdf(-1, home, away))
    draw = float(skellam.pmf(0, home, away))
    home_win = 1.0 - away_win - draw
    p00 = math.exp(-home - away)
    p01 = p00 * away
    p10 = p00 * home
    p11 = p00 * home * away
    away_win += p01 * (dixon_coles_tau(0, 1, home, away, rho) - 1.0)
    home_win += p10 * (dixon_coles_tau(1, 0, home, away, rho) - 1.0)
    draw += p00 * (dixon_coles_tau(0, 0, home, away, rho) - 1.0)
    draw += p11 * (dixon_coles_tau(1, 1, home, away, rho) - 1.0)
    values = (home_win, draw, away_win)
    if any(value <= 0.0 or value >= 1.0 for value in values):
        raise ResearchModelError("1X2 probabilities must be inside (0,1)")
    if abs(sum(values) - 1.0) > 1e-12:
        raise ResearchModelError("1X2 probabilities are not normalized")
    return values


def fit_model(
    rows: Sequence[ResearchRowV2],
    *,
    model_role: ModelRole,
    regularization: tuple[float, float, float],
) -> ModelParametersV2:
    if not rows:
        raise ResearchModelError("model fitting requires at least one row")
    competitions = tuple(sorted({row.competition for row in rows}))
    layout = _Layout(competitions, model_role)
    initial = layout.initial(rows)
    bounds = layout.bounds()

    def objective(values: np.ndarray) -> tuple[float, np.ndarray]:
        return _objective_and_gradient(values, rows, layout, regularization)

    constraints = {
        "type": "ineq",
        "fun": lambda values: _constraints(values, rows, layout),
        "jac": lambda values: _constraint_jacobian(values, rows, layout),
    }
    result = minimize(
        objective,
        initial,
        method="SLSQP",
        jac=True,
        bounds=bounds,
        constraints=(constraints,),
        options={"ftol": 1e-10, "maxiter": 1000, "disp": False},
    )
    if not result.success or not math.isfinite(float(result.fun)):
        raise ResearchModelError(f"optimizer failed: {result.message}")
    if float(np.min(_constraints(result.x, rows, layout))) < -1e-8:
        raise ResearchModelError("optimizer returned an infeasible solution")
    return layout.parameters(result.x, regularization)


class _Layout:
    def __init__(self, competitions: tuple[str, ...], role: ModelRole) -> None:
        self.competitions = competitions
        self.role = role
        self.index = {
            "intercept": 0,
            "home": 1,
            "gf": 2,
            "ga": 3,
            "xf": 4,
            "xa": 5,
            "rho": 6,
        }
        self.comp_start = 7
        self.comp_free = (
            max(0, len(competitions) - 1) if role in ("candidate", "poisson_candidate") else 0
        )
        self.home_comp_start = self.comp_start + self.comp_free
        self.size = 7 + 2 * self.comp_free

    def initial(self, rows: Sequence[ResearchRowV2]) -> np.ndarray:
        home = max(sum(row.home_goals for row in rows) / len(rows), RATE_MINIMUM)
        away = max(sum(row.away_goals for row in rows) / len(rows), RATE_MINIMUM)
        values = np.zeros(self.size, dtype=float)
        values[:7] = (math.log(away), math.log(home / away), 0.25, 0.25, 0.25, 0.25, 0.0)
        if self.role == "reference":
            values[4:7] = 0.0
        elif self.role == "v5":
            values[5:7] = 0.0
        return values

    def bounds(self) -> tuple[tuple[float, float], ...]:
        bounds: list[tuple[float, float]] = [
            (-1.5, 1.5),
            (-0.75, 0.75),
            (0.0, 2.0),
            (0.0, 2.0),
            (0.0, 2.0),
            (0.0, 2.0),
            (-0.15, 0.15),
        ]
        if self.role == "reference":
            bounds[4] = bounds[5] = bounds[6] = (0.0, 0.0)
        elif self.role == "v5":
            bounds[5] = bounds[6] = (0.0, 0.0)
        elif self.role == "poisson_candidate":
            bounds[6] = (0.0, 0.0)
        bounds.extend([(-0.75, 0.75)] * (2 * self.comp_free))
        return tuple(bounds)

    def competition_vectors(self, competition: str) -> tuple[np.ndarray, np.ndarray]:
        baseline = np.zeros(self.size)
        home = np.zeros(self.size)
        if self.comp_free:
            position = self.competitions.index(competition)
            if position < self.comp_free:
                baseline[self.comp_start + position] = 1.0
                home[self.home_comp_start + position] = 1.0
            else:
                baseline[self.comp_start : self.comp_start + self.comp_free] = -1.0
                home[self.home_comp_start : self.home_comp_start + self.comp_free] = -1.0
        return baseline, home

    def parameters(
        self, values: Sequence[float], regularization: tuple[float, float, float]
    ) -> ModelParametersV2:
        baseline, home = self._deviations(values)
        return ModelParametersV2(
            global_intercept=float(values[0]),
            global_home_advantage=float(values[1]),
            goals_for_weight=float(values[2]),
            goals_against_weight=float(values[3]),
            npxg_for_weight=float(values[4]),
            npxg_against_weight=float(values[5]),
            rho=float(values[6]),
            competition_baseline_deviations=baseline,
            competition_home_advantage_deviations=home,
            regularization=regularization,
        )

    def _deviations(self, values: Sequence[float]) -> tuple[dict[str, float], dict[str, float]]:
        if not self.comp_free:
            return {}, {}
        baseline_values = [float(value) for value in values[self.comp_start : self.home_comp_start]]
        home_values = [float(value) for value in values[self.home_comp_start :]]
        baseline_values.append(-sum(baseline_values))
        home_values.append(-sum(home_values))
        return (
            dict(zip(self.competitions, baseline_values, strict=True)),
            dict(zip(self.competitions, home_values, strict=True)),
        )


def _design(row: ResearchRowV2, layout: _Layout) -> tuple[np.ndarray, np.ndarray]:
    baseline, home_comp = layout.competition_vectors(row.competition)
    home = baseline + home_comp
    away = baseline.copy()
    home[:7] += (
        1.0,
        1.0,
        row.features.home_goals_for,
        row.features.away_goals_against,
        row.features.home_npxg_for,
        row.features.away_npxg_against,
        0.0,
    )
    away[:7] += (
        1.0,
        0.0,
        row.features.away_goals_for,
        row.features.home_goals_against,
        row.features.away_npxg_for,
        row.features.home_npxg_against,
        0.0,
    )
    return home, away


def _objective_and_gradient(
    values: np.ndarray,
    rows: Sequence[ResearchRowV2],
    layout: _Layout,
    regularization: tuple[float, float, float],
) -> tuple[float, np.ndarray]:
    total = 0.0
    gradient = np.zeros(layout.size)
    rho = float(values[6])
    for row in rows:
        home_design, away_design = _design(row, layout)
        home = math.exp(float(np.dot(values, home_design)))
        away = math.exp(float(np.dot(values, away_design)))
        tau, tau_home, tau_away, tau_rho = _tau_derivatives(
            row.home_goals, row.away_goals, home, away, rho
        )
        if tau <= 0.0:
            return 1e100, np.zeros(layout.size)
        total += (
            home
            - row.home_goals * math.log(home)
            + math.lgamma(row.home_goals + 1)
            + away
            - row.away_goals * math.log(away)
            + math.lgamma(row.away_goals + 1)
            - math.log(tau)
        )
        gradient += (home - row.home_goals - tau_home * home / tau) * home_design
        gradient += (away - row.away_goals - tau_away * away / tau) * away_design
        gradient[6] -= tau_rho / tau
    total /= len(rows)
    gradient /= len(rows)
    if layout.comp_free:
        baseline = np.asarray(values[layout.comp_start : layout.home_comp_start])
        home_values = np.asarray(values[layout.home_comp_start :])
        full_baseline = np.append(baseline, -float(np.sum(baseline)))
        full_home = np.append(home_values, -float(np.sum(home_values)))
        total += regularization[0] * float(np.mean(full_baseline**2))
        total += regularization[1] * float(np.mean(full_home**2))
        gradient[layout.comp_start : layout.home_comp_start] += (
            2.0 * regularization[0] * (baseline + float(np.sum(baseline))) / len(full_baseline)
        )
        gradient[layout.home_comp_start :] += (
            2.0 * regularization[1] * (home_values + float(np.sum(home_values))) / len(full_home)
        )
    total += regularization[2] * rho * rho
    gradient[6] += 2.0 * regularization[2] * rho
    return total, gradient


def _tau_derivatives(
    home_goals: int, away_goals: int, home: float, away: float, rho: float
) -> tuple[float, float, float, float]:
    if (home_goals, away_goals) == (0, 0):
        return 1.0 - home * away * rho, -away * rho, -home * rho, -home * away
    if (home_goals, away_goals) == (0, 1):
        return 1.0 + home * rho, rho, 0.0, home
    if (home_goals, away_goals) == (1, 0):
        return 1.0 + away * rho, 0.0, rho, away
    if (home_goals, away_goals) == (1, 1):
        return 1.0 - rho, 0.0, 0.0, -1.0
    return 1.0, 0.0, 0.0, 0.0


def _constraints(values: np.ndarray, rows: Sequence[ResearchRowV2], layout: _Layout) -> np.ndarray:
    output: list[float] = []
    rho = float(values[6])
    for row in rows:
        home_design, away_design = _design(row, layout)
        home = math.exp(float(np.dot(values, home_design)))
        away = math.exp(float(np.dot(values, away_design)))
        output.extend(
            (
                home - RATE_MINIMUM,
                RATE_MAXIMUM - home,
                away - RATE_MINIMUM,
                RATE_MAXIMUM - away,
                *(dixon_coles_tau(x, y, home, away, rho) - TAU_MINIMUM for x, y in _LOW_CELLS),
            )
        )
    return np.asarray(output)


def _constraint_jacobian(
    values: np.ndarray, rows: Sequence[ResearchRowV2], layout: _Layout
) -> np.ndarray:
    constraints_per_row = 4 + len(_LOW_CELLS)
    output = np.zeros((len(rows) * constraints_per_row, layout.size))
    rho = float(values[6])
    for index, row in enumerate(rows):
        home_design, away_design = _design(row, layout)
        home = math.exp(float(np.dot(values, home_design)))
        away = math.exp(float(np.dot(values, away_design)))
        home_gradient = home * home_design
        away_gradient = away * away_design
        start = index * constraints_per_row
        output[start] = home_gradient
        output[start + 1] = -home_gradient
        output[start + 2] = away_gradient
        output[start + 3] = -away_gradient
        for offset, (x, y) in enumerate(_LOW_CELLS, start=4):
            _, tau_home, tau_away, tau_rho = _tau_derivatives(x, y, home, away, rho)
            output[start + offset] = tau_home * home_gradient + tau_away * away_gradient
            output[start + offset, 6] += tau_rho
    return output


_LOW_CELLS = ((0, 0), (0, 1), (1, 0), (1, 1))
