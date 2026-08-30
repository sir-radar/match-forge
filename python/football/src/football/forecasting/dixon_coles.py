from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from scipy.optimize import minimize
from scipy.stats import poisson, skellam

from football.contracts.source import canonical_json_bytes

_MODEL_VERSION = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PARAMETER_BOUND = 3.0
_HOME_ADVANTAGE_BOUND = 1.5
_CORRELATION_BOUND = 0.25


class DixonColesContractError(ValueError):
    """A Dixon-Coles configuration, match, or prediction input is invalid."""


class DixonColesFitError(RuntimeError):
    """Dixon-Coles parameter fitting did not produce a usable solution."""


@dataclass(frozen=True)
class DixonColesConfig:
    model_version: str
    time_decay_half_life_days: float | None = 365.0
    score_matrix_tail_start: int = 5
    max_iterations: int = 1_000
    tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if not isinstance(self.model_version, str) or not _MODEL_VERSION.fullmatch(
            self.model_version
        ):
            raise DixonColesContractError(
                "model_version must use lowercase letters, digits, ., _, or -"
            )
        if self.time_decay_half_life_days is not None:
            _positive(self.time_decay_half_life_days, "time-decay half-life")
        if (
            isinstance(self.score_matrix_tail_start, bool)
            or not isinstance(self.score_matrix_tail_start, int)
            or self.score_matrix_tail_start < 2
        ):
            raise DixonColesContractError(
                "score-matrix tail start must be an integer of at least 2"
            )
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, int)
            or self.max_iterations <= 0
        ):
            raise DixonColesContractError("max_iterations must be a positive integer")
        _positive(self.tolerance, "tolerance")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "time_decay_half_life_days": self.time_decay_half_life_days,
            "score_matrix_tail_start": self.score_matrix_tail_start,
            "max_iterations": self.max_iterations,
            "tolerance": self.tolerance,
        }

    def match_weight(self, age_days: float) -> float:
        _finite(age_days, "match age")
        if age_days < 0.0:
            raise DixonColesContractError("match age must be finite and non-negative")
        if self.time_decay_half_life_days is None:
            return 1.0
        return math.pow(0.5, age_days / self.time_decay_half_life_days)


@dataclass(frozen=True)
class GoalMatch:
    match_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_goals: int
    away_goals: int

    def __post_init__(self) -> None:
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise DixonColesContractError("kickoff_at must include a timezone")
        if self.home_team_id == self.away_team_id:
            raise DixonColesContractError("home and away teams must differ")
        for field_name, value in (
            ("home_goals", self.home_goals),
            ("away_goals", self.away_goals),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DixonColesContractError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True)
class DixonColesParameters:
    attack_strengths: Mapping[UUID, float] = field(default_factory=dict)
    defense_strengths: Mapping[UUID, float] = field(default_factory=dict)
    home_advantage: float = 0.0
    low_score_correlation: float = 0.0

    def __post_init__(self) -> None:
        attacks = _strengths(self.attack_strengths, "attack")
        defenses = _strengths(self.defense_strengths, "defense")
        if not attacks or attacks.keys() != defenses.keys():
            raise DixonColesContractError(
                "attack and defense strengths must contain the same fitted teams"
            )
        _finite(self.home_advantage, "home_advantage")
        if abs(self.home_advantage) > _HOME_ADVANTAGE_BOUND:
            raise DixonColesContractError(
                f"home_advantage must be between -{_HOME_ADVANTAGE_BOUND} "
                f"and {_HOME_ADVANTAGE_BOUND}"
            )
        _finite(self.low_score_correlation, "low_score_correlation")
        if abs(self.low_score_correlation) > _CORRELATION_BOUND:
            raise DixonColesContractError(
                f"low_score_correlation must be between -{_CORRELATION_BOUND} "
                f"and {_CORRELATION_BOUND}"
            )
        object.__setattr__(self, "attack_strengths", MappingProxyType(attacks))
        object.__setattr__(self, "defense_strengths", MappingProxyType(defenses))


@dataclass(frozen=True)
class DixonColesFit:
    model_version: str
    config: DixonColesConfig
    config_sha256: str
    training_sha256: str
    training_match_count: int
    training_cutoff: datetime
    parameters: DixonColesParameters
    negative_log_likelihood: float
    converged: bool


@dataclass(frozen=True)
class ScoreMatrix:
    labels: tuple[str, ...]
    probabilities: tuple[tuple[float, ...], ...]

    def probability(self, home_goals: str, away_goals: str) -> float:
        try:
            home_index = self.labels.index(home_goals)
            away_index = self.labels.index(away_goals)
        except ValueError as error:
            raise DixonColesContractError("score bucket is not present in the matrix") from error
        return self.probabilities[home_index][away_index]


@dataclass(frozen=True)
class GoalMarkets:
    home_win: float
    draw: float
    away_win: float
    over_1_5: float
    over_2_5: float
    over_3_5: float
    both_teams_to_score: float
    home_clean_sheet: float
    away_clean_sheet: float


@dataclass(frozen=True)
class GoalForecast:
    lambda_home: float
    lambda_away: float
    low_score_correlation: float
    score_matrix: ScoreMatrix
    markets: GoalMarkets

    def exact_score_probability(self, home_goals: int, away_goals: int) -> float:
        for field_name, value in (("home_goals", home_goals), ("away_goals", away_goals)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DixonColesContractError(f"{field_name} must be a non-negative integer")
        independent = _poisson_probability(home_goals, self.lambda_home) * _poisson_probability(
            away_goals, self.lambda_away
        )
        return independent * _tau(
            home_goals,
            away_goals,
            self.lambda_home,
            self.lambda_away,
            self.low_score_correlation,
        )


class DixonColesModel:
    def __init__(self, config: DixonColesConfig) -> None:
        self.config = config

    def fit(self, matches: tuple[GoalMatch, ...]) -> DixonColesFit:
        if not matches:
            raise DixonColesContractError("Dixon-Coles fitting requires at least two teams")
        identifiers = [match.match_id for match in matches]
        if len(identifiers) != len(set(identifiers)):
            raise DixonColesContractError("duplicate match in Dixon-Coles input")
        ordered = tuple(sorted(matches, key=lambda match: (match.kickoff_at, str(match.match_id))))
        team_ids = tuple(
            sorted(
                {
                    team_id
                    for match in ordered
                    for team_id in (match.home_team_id, match.away_team_id)
                },
                key=str,
            )
        )
        if len(team_ids) < 2:
            raise DixonColesContractError("Dixon-Coles fitting requires at least two teams")
        team_indexes = {team_id: index for index, team_id in enumerate(team_ids)}
        cutoff = ordered[-1].kickoff_at
        weights = tuple(
            self.config.match_weight((cutoff - match.kickoff_at).total_seconds() / 86_400.0)
            for match in ordered
        )
        initial = _initial_parameters(ordered, len(team_ids))
        bounds = (
            [(-_PARAMETER_BOUND, _PARAMETER_BOUND)] * (len(team_ids) - 1)
            + [(-_PARAMETER_BOUND, _PARAMETER_BOUND)] * len(team_ids)
            + [(-_HOME_ADVANTAGE_BOUND, _HOME_ADVANTAGE_BOUND)]
            + [(-_CORRELATION_BOUND, _CORRELATION_BOUND)]
        )

        def objective(values: Sequence[float]) -> float:
            attacks, defenses, home_advantage, correlation = _unpack(values, len(team_ids))
            negative_log_likelihood = 0.0
            for match, weight in zip(ordered, weights, strict=True):
                home_index = team_indexes[match.home_team_id]
                away_index = team_indexes[match.away_team_id]
                lambda_home = math.exp(attacks[home_index] + defenses[away_index] + home_advantage)
                lambda_away = math.exp(attacks[away_index] + defenses[home_index])
                correction = _tau(
                    match.home_goals,
                    match.away_goals,
                    lambda_home,
                    lambda_away,
                    correlation,
                )
                if correction <= 0.0 or not math.isfinite(correction):
                    return 1e100
                log_probability = (
                    _poisson_log_probability(match.home_goals, lambda_home)
                    + _poisson_log_probability(match.away_goals, lambda_away)
                    + math.log(correction)
                )
                negative_log_likelihood -= weight * log_probability
            return negative_log_likelihood

        result = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": self.config.max_iterations, "ftol": self.config.tolerance},
        )
        if not bool(result.success) or not math.isfinite(float(result.fun)):
            raise DixonColesFitError(f"Dixon-Coles optimizer did not converge: {result.message}")
        attacks, defenses, home_advantage, correlation = _unpack(result.x, len(team_ids))
        parameters = DixonColesParameters(
            attack_strengths=dict(zip(team_ids, attacks, strict=True)),
            defense_strengths=dict(zip(team_ids, defenses, strict=True)),
            home_advantage=home_advantage,
            low_score_correlation=correlation,
        )
        return DixonColesFit(
            model_version=self.config.model_version,
            config=self.config,
            config_sha256=self.config.sha256,
            training_sha256=_training_sha256(self.config.sha256, ordered),
            training_match_count=len(ordered),
            training_cutoff=cutoff,
            parameters=parameters,
            negative_log_likelihood=float(result.fun),
            converged=True,
        )

    def forecast(
        self,
        parameters: DixonColesParameters,
        home_team_id: UUID,
        away_team_id: UUID,
    ) -> GoalForecast:
        if home_team_id == away_team_id:
            raise DixonColesContractError("home and away teams must differ")
        if home_team_id not in parameters.attack_strengths:
            raise DixonColesContractError(f"team is not fitted: {home_team_id}")
        if away_team_id not in parameters.attack_strengths:
            raise DixonColesContractError(f"team is not fitted: {away_team_id}")
        lambda_home = math.exp(
            parameters.attack_strengths[home_team_id]
            + parameters.defense_strengths[away_team_id]
            + parameters.home_advantage
        )
        lambda_away = math.exp(
            parameters.attack_strengths[away_team_id] + parameters.defense_strengths[home_team_id]
        )
        for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1)):
            if (
                _tau(
                    home_goals,
                    away_goals,
                    lambda_home,
                    lambda_away,
                    parameters.low_score_correlation,
                )
                <= 0.0
            ):
                raise DixonColesContractError(
                    "low-score correlation produces a non-positive score probability"
                )
        matrix = _score_matrix(
            lambda_home,
            lambda_away,
            parameters.low_score_correlation,
            self.config.score_matrix_tail_start,
        )
        markets = _markets(lambda_home, lambda_away, parameters.low_score_correlation)
        return GoalForecast(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            low_score_correlation=parameters.low_score_correlation,
            score_matrix=matrix,
            markets=markets,
        )


def _initial_parameters(matches: tuple[GoalMatch, ...], team_count: int) -> list[float]:
    home_mean = sum(match.home_goals for match in matches) / len(matches)
    away_mean = sum(match.away_goals for match in matches) / len(matches)
    smoothed_home = max(home_mean, 0.1)
    smoothed_away = max(away_mean, 0.1)
    baseline_defense = math.log(smoothed_away)
    home_advantage = math.log(smoothed_home / smoothed_away)
    return (
        [0.0] * (team_count - 1)
        + [min(max(baseline_defense, -_PARAMETER_BOUND), _PARAMETER_BOUND)] * team_count
        + [min(max(home_advantage, -_HOME_ADVANTAGE_BOUND), _HOME_ADVANTAGE_BOUND), 0.0]
    )


def _unpack(
    values: Sequence[float], team_count: int
) -> tuple[tuple[float, ...], tuple[float, ...], float, float]:
    free_attacks = tuple(float(value) for value in values[: team_count - 1])
    attacks = (*free_attacks, -sum(free_attacks))
    defenses = tuple(float(value) for value in values[team_count - 1 : 2 * team_count - 1])
    return attacks, defenses, float(values[-2]), float(values[-1])


def _score_matrix(
    lambda_home: float,
    lambda_away: float,
    correlation: float,
    tail_start: int,
) -> ScoreMatrix:
    labels = tuple(str(goals) for goals in range(tail_start)) + (f"{tail_start}+",)
    home_probabilities = [_poisson_probability(goals, lambda_home) for goals in range(tail_start)]
    away_probabilities = [_poisson_probability(goals, lambda_away) for goals in range(tail_start)]
    home_probabilities.append(max(0.0, 1.0 - sum(home_probabilities)))
    away_probabilities.append(max(0.0, 1.0 - sum(away_probabilities)))
    rows: list[tuple[float, ...]] = []
    for home_index, home_probability in enumerate(home_probabilities):
        row: list[float] = []
        for away_index, away_probability in enumerate(away_probabilities):
            probability = home_probability * away_probability
            if home_index < 2 and away_index < 2:
                probability *= _tau(
                    home_index,
                    away_index,
                    lambda_home,
                    lambda_away,
                    correlation,
                )
            row.append(probability)
        rows.append(tuple(row))
    return ScoreMatrix(labels=labels, probabilities=tuple(rows))


def _markets(lambda_home: float, lambda_away: float, correlation: float) -> GoalMarkets:
    corrections = {
        (home_goals, away_goals): _poisson_probability(home_goals, lambda_home)
        * _poisson_probability(away_goals, lambda_away)
        * (_tau(home_goals, away_goals, lambda_home, lambda_away, correlation) - 1.0)
        for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1))
    }
    home_win = float(skellam.sf(0, lambda_home, lambda_away)) + corrections[(1, 0)]
    draw = (
        float(skellam.pmf(0, lambda_home, lambda_away)) + corrections[(0, 0)] + corrections[(1, 1)]
    )
    away_win = float(skellam.cdf(-1, lambda_home, lambda_away)) + corrections[(0, 1)]
    return GoalMarkets(
        home_win=_probability(home_win),
        draw=_probability(draw),
        away_win=_probability(away_win),
        over_1_5=_probability(
            float(poisson.sf(1, lambda_home + lambda_away)) + corrections[(1, 1)]
        ),
        over_2_5=_probability(float(poisson.sf(2, lambda_home + lambda_away))),
        over_3_5=_probability(float(poisson.sf(3, lambda_home + lambda_away))),
        both_teams_to_score=_probability(
            (1.0 - math.exp(-lambda_home)) * (1.0 - math.exp(-lambda_away)) + corrections[(1, 1)]
        ),
        home_clean_sheet=_probability(math.exp(-lambda_away)),
        away_clean_sheet=_probability(math.exp(-lambda_home)),
    )


def _tau(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    correlation: float,
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * correlation
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * correlation
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * correlation
    if home_goals == 1 and away_goals == 1:
        return 1.0 - correlation
    return 1.0


def _poisson_probability(goals: int, expected_goals: float) -> float:
    return math.exp(_poisson_log_probability(goals, expected_goals))


def _poisson_log_probability(goals: int, expected_goals: float) -> float:
    return goals * math.log(expected_goals) - expected_goals - math.lgamma(goals + 1.0)


def _training_sha256(config_sha256: str, matches: tuple[GoalMatch, ...]) -> str:
    payload = {
        "config_sha256": config_sha256,
        "matches": [
            {
                "match_id": str(match.match_id),
                "kickoff_at": match.kickoff_at.isoformat(),
                "home_team_id": str(match.home_team_id),
                "away_team_id": str(match.away_team_id),
                "home_goals": match.home_goals,
                "away_goals": match.away_goals,
            }
            for match in matches
        ],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _strengths(values: Mapping[UUID, float], name: str) -> dict[UUID, float]:
    strengths: dict[UUID, float] = {}
    for team_id, value in values.items():
        if not isinstance(team_id, UUID):
            raise DixonColesContractError(f"{name} strength keys must be UUIDs")
        _finite(value, f"{name} strength")
        if abs(value) > _PARAMETER_BOUND:
            raise DixonColesContractError(
                f"{name} strength must be between -{_PARAMETER_BOUND} and {_PARAMETER_BOUND}"
            )
        strengths[team_id] = float(value)
    return strengths


def _probability(value: float) -> float:
    if not math.isfinite(value) or value < -1e-12 or value > 1.0 + 1e-12:
        raise DixonColesContractError("Dixon-Coles calculation produced an invalid probability")
    return min(max(value, 0.0), 1.0)


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DixonColesContractError(f"{field_name} must be finite")


def _positive(value: float, field_name: str) -> None:
    _finite(value, field_name)
    if value <= 0.0:
        raise DixonColesContractError(f"{field_name} must be positive")
