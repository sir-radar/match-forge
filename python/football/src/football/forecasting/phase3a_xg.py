from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from scipy.optimize import minimize

import football.forecasting.dixon_coles as dc
from football.contracts.source import canonical_json_bytes
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesContractError,
    DixonColesFitError,
    DixonColesParameters,
    GoalForecast,
    GoalMatch,
)

FEATURE_ID = "MATCHFORGE_NPXG_FOR_LAST10_V1"
ALGORITHM_VERSION = "phase3a-npxg-for-last10-v1"


@dataclass(frozen=True, slots=True)
class XgFeatureMatchV1:
    match: GoalMatch
    home_signal: float
    away_signal: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.home_signal) or not math.isfinite(self.away_signal):
            raise DixonColesContractError("xG-for signals must be finite")


@dataclass(frozen=True, slots=True)
class Phase3AXgParametersV1:
    reference: DixonColesParameters
    beta_xg_for: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.beta_xg_for) or not 0.0 <= self.beta_xg_for <= 1.0:
            raise DixonColesContractError("beta_xg_for must be finite and in [0,1]")


@dataclass(frozen=True, slots=True)
class Phase3AXgFitV1:
    config: DixonColesConfig
    config_sha256: str
    training_sha256: str
    training_match_count: int
    parameters: Phase3AXgParametersV1
    negative_log_likelihood: float
    converged: bool


class Phase3AXgForModelV1:
    def __init__(self, config: DixonColesConfig) -> None:
        self.config = config

    def fit(self, rows: tuple[XgFeatureMatchV1, ...]) -> Phase3AXgFitV1:
        if not rows:
            raise DixonColesContractError("xG challenger fitting requires matches")
        ordered = tuple(
            sorted(rows, key=lambda row: (row.match.kickoff_at, str(row.match.match_id)))
        )
        matches = tuple(row.match for row in ordered)
        if len({match.match_id for match in matches}) != len(matches):
            raise DixonColesContractError("duplicate match in xG challenger input")
        team_ids = tuple(
            sorted(
                {team for match in matches for team in (match.home_team_id, match.away_team_id)},
                key=str,
            )
        )
        indexes = {team: index for index, team in enumerate(team_ids)}
        weights = tuple(
            self.config.match_weight(
                (matches[-1].kickoff_at - match.kickoff_at).total_seconds() / 86_400.0
            )
            for match in matches
        )
        initial = [*dc._initial_parameters(matches, len(team_ids)), 0.25]
        bounds = (
            [(-3.0, 3.0)] * (len(team_ids) - 1)
            + [(-3.0, 3.0)] * len(team_ids)
            + [(-1.5, 1.5), (-0.25, 0.25), (0.0, 1.0)]
        )

        def objective(values: Sequence[float]) -> tuple[float, tuple[float, ...]]:
            return _objective(values, ordered, weights, indexes, len(team_ids))

        result = minimize(
            objective,
            initial,
            method="SLSQP",
            jac=True,
            bounds=bounds,
            options={"maxiter": self.config.max_iterations, "ftol": self.config.tolerance},
        )
        if (
            not bool(result.success)
            or not math.isfinite(float(result.fun))
            or float(result.fun) >= 1e100
        ):
            raise DixonColesFitError(f"xG challenger optimizer did not converge: {result.message}")
        stationarity = dc._projected_gradient_max(result.x, result.jac, bounds)
        if not math.isfinite(stationarity) or stationarity > self.config.gradient_tolerance:
            raise DixonColesFitError(
                f"xG challenger optimizer reported a non-stationary solution: {stationarity}"
            )
        attacks, defenses, home_advantage, correlation = dc._unpack(result.x[:-1], len(team_ids))
        parameters = Phase3AXgParametersV1(
            reference=DixonColesParameters(
                attack_strengths=dict(zip(team_ids, attacks, strict=True)),
                defense_strengths=dict(zip(team_ids, defenses, strict=True)),
                home_advantage=home_advantage,
                low_score_correlation=correlation,
            ),
            beta_xg_for=float(result.x[-1]),
        )
        return Phase3AXgFitV1(
            config=self.config,
            config_sha256=self.config.sha256,
            training_sha256=_training_sha256(self.config.sha256, ordered),
            training_match_count=len(ordered),
            parameters=parameters,
            negative_log_likelihood=float(result.fun),
            converged=True,
        )

    def forecast(
        self,
        parameters: Phase3AXgParametersV1,
        home_team_id: UUID,
        away_team_id: UUID,
        home_signal: float,
        away_signal: float,
    ) -> GoalForecast:
        if not math.isfinite(home_signal) or not math.isfinite(away_signal):
            raise DixonColesContractError("xG-for signals must be finite")
        baseline = parameters.reference
        try:
            lambda_home = math.exp(
                baseline.attack_strengths[home_team_id]
                + baseline.defense_strengths[away_team_id]
                + baseline.home_advantage
                + parameters.beta_xg_for * home_signal
            )
            lambda_away = math.exp(
                baseline.attack_strengths[away_team_id]
                + baseline.defense_strengths[home_team_id]
                + parameters.beta_xg_for * away_signal
            )
        except KeyError as error:
            raise DixonColesContractError(f"team is not fitted: {error.args[0]}") from error
        for home, away in ((0, 0), (0, 1), (1, 0), (1, 1)):
            if dc._tau(home, away, lambda_home, lambda_away, baseline.low_score_correlation) <= 0.0:
                raise DixonColesContractError("low-score correction is non-positive")
        return GoalForecast(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            low_score_correlation=baseline.low_score_correlation,
            score_matrix=dc._score_matrix(
                lambda_home,
                lambda_away,
                baseline.low_score_correlation,
                self.config.score_matrix_tail_start,
            ),
            markets=dc._markets(lambda_home, lambda_away, baseline.low_score_correlation),
        )


def serialize_phase3a_fit(fit: Phase3AXgFitV1) -> dict[str, object]:
    parameters = fit.parameters.reference
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "config": fit.config.to_dict(),
        "config_sha256": fit.config_sha256,
        "converged": fit.converged,
        "feature_id": FEATURE_ID,
        "negative_log_likelihood": fit.negative_log_likelihood,
        "parameters": {
            "attack_strengths": {
                str(key): value
                for key, value in sorted(
                    parameters.attack_strengths.items(), key=lambda item: str(item[0])
                )
            },
            "beta_xg_for": fit.parameters.beta_xg_for,
            "defense_strengths": {
                str(key): value
                for key, value in sorted(
                    parameters.defense_strengths.items(), key=lambda item: str(item[0])
                )
            },
            "home_advantage": parameters.home_advantage,
            "low_score_correlation": parameters.low_score_correlation,
        },
        "training_match_count": fit.training_match_count,
        "training_sha256": fit.training_sha256,
    }


def deserialize_phase3a_fit(value: Mapping[str, object]) -> Phase3AXgFitV1:
    config_value = value["config"]
    parameters_value = value["parameters"]
    if not isinstance(config_value, dict) or not isinstance(parameters_value, dict):
        raise DixonColesContractError("invalid xG challenger artifact")
    config = DixonColesConfig(**config_value)
    attacks = parameters_value["attack_strengths"]
    defenses = parameters_value["defense_strengths"]
    if not isinstance(attacks, dict) or not isinstance(defenses, dict):
        raise DixonColesContractError("invalid xG challenger strengths")
    return Phase3AXgFitV1(
        config=config,
        config_sha256=str(value["config_sha256"]),
        training_sha256=str(value["training_sha256"]),
        training_match_count=_integer(value["training_match_count"], "training_match_count"),
        parameters=Phase3AXgParametersV1(
            reference=DixonColesParameters(
                attack_strengths=MappingProxyType(
                    {UUID(key): float(item) for key, item in attacks.items()}
                ),
                defense_strengths=MappingProxyType(
                    {UUID(key): float(item) for key, item in defenses.items()}
                ),
                home_advantage=float(parameters_value["home_advantage"]),
                low_score_correlation=float(parameters_value["low_score_correlation"]),
            ),
            beta_xg_for=float(parameters_value["beta_xg_for"]),
        ),
        negative_log_likelihood=_number(
            value["negative_log_likelihood"], "negative_log_likelihood"
        ),
        converged=bool(value["converged"]),
    )


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DixonColesContractError(f"{field} must be an integer")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DixonColesContractError(f"{field} must be numeric")
    return float(value)


def _objective(
    values: Sequence[float],
    rows: tuple[XgFeatureMatchV1, ...],
    weights: tuple[float, ...],
    indexes: Mapping[UUID, int],
    team_count: int,
) -> tuple[float, tuple[float, ...]]:
    attacks, defenses, home_advantage, correlation = dc._unpack(values[:-1], team_count)
    beta = float(values[-1])
    attack_gradient = [0.0] * team_count
    defense_gradient = [0.0] * team_count
    home_advantage_gradient = 0.0
    correlation_gradient = 0.0
    beta_gradient = 0.0
    likelihood = 0.0
    for row, weight in zip(rows, weights, strict=True):
        match = row.match
        home = indexes[match.home_team_id]
        away = indexes[match.away_team_id]
        lambda_home = math.exp(
            attacks[home] + defenses[away] + home_advantage + beta * row.home_signal
        )
        lambda_away = math.exp(attacks[away] + defenses[home] + beta * row.away_signal)
        correction, home_correction, away_correction, correlation_correction = (
            dc._tau_with_derivatives(
                match.home_goals, match.away_goals, lambda_home, lambda_away, correlation
            )
        )
        if correction <= 0.0 or not math.isfinite(correction):
            return 1e100, tuple(0.0 for _ in values)
        likelihood -= weight * (
            dc._poisson_log_probability(match.home_goals, lambda_home)
            + dc._poisson_log_probability(match.away_goals, lambda_away)
            + math.log(correction)
        )
        home_gradient = weight * (lambda_home - match.home_goals - home_correction / correction)
        away_gradient = weight * (lambda_away - match.away_goals - away_correction / correction)
        attack_gradient[home] += home_gradient
        attack_gradient[away] += away_gradient
        defense_gradient[away] += home_gradient
        defense_gradient[home] += away_gradient
        home_advantage_gradient += home_gradient
        correlation_gradient -= weight * correlation_correction / correction
        beta_gradient += home_gradient * row.home_signal + away_gradient * row.away_signal
    free = tuple(attack_gradient[i] - attack_gradient[-1] for i in range(team_count - 1))
    return likelihood, (
        *free,
        *defense_gradient,
        home_advantage_gradient,
        correlation_gradient,
        beta_gradient,
    )


def _training_sha256(config_sha256: str, rows: tuple[XgFeatureMatchV1, ...]) -> str:
    payload = {
        "config_sha256": config_sha256,
        "feature_id": FEATURE_ID,
        "matches": [
            {
                "away_goals": row.match.away_goals,
                "away_signal": row.away_signal,
                "away_team_id": str(row.match.away_team_id),
                "home_goals": row.match.home_goals,
                "home_signal": row.home_signal,
                "home_team_id": str(row.match.home_team_id),
                "kickoff_at": row.match.kickoff_at.isoformat(),
                "match_id": str(row.match.match_id),
            }
            for row in rows
        ],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
