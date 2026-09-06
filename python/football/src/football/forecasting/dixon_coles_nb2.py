from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from scipy.optimize import minimize_scalar

from football.contracts.source import canonical_json_bytes
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesContractError,
    DixonColesFit,
    DixonColesFitError,
    DixonColesModel,
    DixonColesParameters,
    GoalForecast,
    GoalMarkets,
    GoalMatch,
    ScoreMatrix,
)

_ALGORITHM_VERSION = "dcv3-nb2-residual-dispersion-v1"
_ALPHA_CEILING = 100.0
_ALPHA_XATOL = 1e-10
_ALPHA_MAXITER = 500
_TAIL_TOLERANCE = 1e-12
_HARD_SUPPORT_LIMIT = 1_000_000
_INVALID_OBJECTIVE = 1e100


@dataclass(frozen=True)
class DixonColesNB2Fit:
    base_fit: DixonColesFit
    alpha: float
    config_sha256: str
    training_sha256: str
    conditional_joint_nll: float
    converged: bool


@dataclass(frozen=True)
class DixonColesNB2GoalForecast:
    lambda_home: float
    lambda_away: float
    low_score_correlation: float
    alpha: float
    score_matrix: ScoreMatrix
    markets: GoalMarkets
    _home_probabilities: tuple[float, ...]
    _away_probabilities: tuple[float, ...]
    low_score_mass_transfer: float

    def exact_score_probability(self, home_goals: int, away_goals: int) -> float:
        _count(home_goals, "home_goals")
        _count(away_goals, "away_goals")
        return _joint_probability(
            home_goals,
            away_goals,
            self.lambda_home,
            self.lambda_away,
            self.alpha,
            self.low_score_correlation,
        )

    def home_marginal(self, goals: int) -> float:
        _count(goals, "goals")
        return _nb2_probability(goals, self.lambda_home, self.alpha)

    def away_marginal(self, goals: int) -> float:
        _count(goals, "goals")
        return _nb2_probability(goals, self.lambda_away, self.alpha)


class DixonColesNB2ResidualDispersionModel:
    """Frozen DCv3 conditional-mean model with one fitted NB2 dispersion."""

    def __init__(self, base_config: DixonColesConfig) -> None:
        if base_config.model_version != "dixon-coles-v3":
            raise DixonColesContractError("DCv3-NB2 requires the frozen dixon-coles-v3 base model")
        if base_config.effect_regularization != 16.0:
            raise DixonColesContractError("DCv3-NB2 requires effect regularization 16.0")
        self.base_config = base_config

    @property
    def config_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.config_dict())).hexdigest()

    def config_dict(self) -> dict[str, object]:
        return {
            "algorithm_version": _ALGORITHM_VERSION,
            "base_dcv3_config_sha256": self.base_config.sha256,
            "nb2_parameterization": "nb2-mean-alpha-v1",
            "shared_dispersion": True,
            "rho_correction": "dc-four-cell-mass-transfer-v1",
            "alpha_fit_policy": "conditional-weighted-joint-nll-v1",
            "alpha_numerical_ceiling": _ALPHA_CEILING,
            "optimizer": "scipy-bounded-scalar-v1",
            "optimizer_xatol": _ALPHA_XATOL,
            "optimizer_maxiter": _ALPHA_MAXITER,
            "tail_probability_tolerance": _TAIL_TOLERANCE,
            "hard_support_limit": _HARD_SUPPORT_LIMIT,
        }

    def fit(self, matches: tuple[GoalMatch, ...]) -> DixonColesNB2Fit:
        base_fit = DixonColesModel(self.base_config).fit(matches)
        ordered = tuple(sorted(matches, key=lambda match: (match.kickoff_at, str(match.match_id))))
        cutoff = ordered[-1].kickoff_at
        weights = tuple(
            self.base_config.match_weight((cutoff - match.kickoff_at).total_seconds() / 86_400.0)
            for match in ordered
        )
        means = tuple(
            _means(base_fit.parameters, match.home_team_id, match.away_team_id) for match in ordered
        )

        def objective(alpha: float) -> float:
            if not math.isfinite(alpha) or alpha < 0.0 or alpha > _ALPHA_CEILING:
                return _INVALID_OBJECTIVE
            value = 0.0
            for match, weight, (home_mean, away_mean) in zip(ordered, weights, means, strict=True):
                probability = _joint_probability(
                    match.home_goals,
                    match.away_goals,
                    home_mean,
                    away_mean,
                    alpha,
                    base_fit.parameters.low_score_correlation,
                )
                if probability <= 0.0 or not math.isfinite(probability):
                    return _INVALID_OBJECTIVE
                value -= weight * math.log(probability)
            return value if math.isfinite(value) else _INVALID_OBJECTIVE

        boundary_objective = objective(0.0)
        result = minimize_scalar(
            objective,
            method="bounded",
            bounds=(0.0, _ALPHA_CEILING),
            options={"xatol": _ALPHA_XATOL, "maxiter": _ALPHA_MAXITER},
        )
        if not bool(result.success) or not math.isfinite(float(result.fun)):
            raise DixonColesFitError(f"NB2 alpha optimizer did not converge: {result.message}")
        candidate = float(result.x)
        candidate_objective = objective(candidate)
        if candidate >= _ALPHA_CEILING - _ALPHA_XATOL:
            raise DixonColesFitError("ALPHA_NOT_IDENTIFIED_WITHIN_NUMERICAL_DOMAIN")
        if candidate_objective >= _INVALID_OBJECTIVE or boundary_objective >= _INVALID_OBJECTIVE:
            raise DixonColesFitError("NB2 alpha objective is not finite")
        alpha = 0.0 if candidate_objective >= boundary_objective - _ALPHA_XATOL else candidate
        final_objective = boundary_objective if alpha == 0.0 else candidate_objective
        if alpha > 0.0:
            _verify_local_minimum(objective, alpha, final_objective)
        _validate_training_probabilities(
            ordered, means, alpha, base_fit.parameters.low_score_correlation
        )
        return DixonColesNB2Fit(
            base_fit=base_fit,
            alpha=alpha,
            config_sha256=self.config_sha256,
            training_sha256=_training_sha256(self.config_sha256, ordered),
            conditional_joint_nll=final_objective,
            converged=True,
        )

    def forecast(
        self,
        parameters: DixonColesParameters,
        alpha: float,
        home_team_id: UUID,
        away_team_id: UUID,
    ) -> DixonColesNB2GoalForecast | GoalForecast:
        _alpha(alpha)
        if alpha == 0.0:
            return DixonColesModel(self.base_config).forecast(
                parameters, home_team_id, away_team_id
            )
        home_mean, away_mean = _means(parameters, home_team_id, away_team_id)
        correlation = parameters.low_score_correlation
        for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1)):
            _probability(
                _joint_probability(home_goals, away_goals, home_mean, away_mean, alpha, correlation)
            )
        home_probabilities = _support(home_mean, alpha)
        away_probabilities = _support(away_mean, alpha)
        matrix = _score_matrix(
            home_mean,
            away_mean,
            alpha,
            correlation,
            self.base_config.score_matrix_tail_start,
        )
        markets = _markets(
            home_probabilities,
            away_probabilities,
            home_mean,
            away_mean,
            alpha,
            correlation,
        )
        return DixonColesNB2GoalForecast(
            lambda_home=home_mean,
            lambda_away=away_mean,
            low_score_correlation=correlation,
            alpha=alpha,
            score_matrix=matrix,
            markets=markets,
            _home_probabilities=home_probabilities,
            _away_probabilities=away_probabilities,
            low_score_mass_transfer=correlation
            * _nb2_probability(1, home_mean, alpha)
            * _nb2_probability(1, away_mean, alpha),
        )


def _means(
    parameters: DixonColesParameters, home_team_id: UUID, away_team_id: UUID
) -> tuple[float, float]:
    if home_team_id == away_team_id:
        raise DixonColesContractError("home and away teams must differ")
    if (
        home_team_id not in parameters.attack_strengths
        or away_team_id not in parameters.attack_strengths
    ):
        raise DixonColesContractError("team is not fitted")
    return (
        math.exp(
            parameters.attack_strengths[home_team_id]
            + parameters.defense_strengths[away_team_id]
            + parameters.home_advantage
        ),
        math.exp(
            parameters.attack_strengths[away_team_id] + parameters.defense_strengths[home_team_id]
        ),
    )


def _joint_probability(
    home_goals: int,
    away_goals: int,
    home_mean: float,
    away_mean: float,
    alpha: float,
    correlation: float,
) -> float:
    base = _nb2_probability(home_goals, home_mean, alpha) * _nb2_probability(
        away_goals, away_mean, alpha
    )
    delta = (
        correlation * _nb2_probability(1, home_mean, alpha) * _nb2_probability(1, away_mean, alpha)
    )
    if (home_goals, away_goals) in ((0, 0), (1, 1)):
        return _probability(base - delta)
    if (home_goals, away_goals) in ((0, 1), (1, 0)):
        return _probability(base + delta)
    return _probability(base)


def _nb2_probability(goals: int, mean: float, alpha: float) -> float:
    _count(goals, "goals")
    if not math.isfinite(mean) or mean <= 0.0:
        raise DixonColesContractError("expected goals must be positive and finite")
    _alpha(alpha)
    if alpha == 0.0:
        return math.exp(goals * math.log(mean) - mean - math.lgamma(goals + 1.0))
    shape = 1.0 / alpha
    log_probability = (
        math.lgamma(goals + shape)
        - math.lgamma(shape)
        - math.lgamma(goals + 1.0)
        - shape * math.log1p(alpha * mean)
        + goals * (math.log(alpha * mean) - math.log1p(alpha * mean))
    )
    return _probability(math.exp(log_probability))


def _support(mean: float, alpha: float) -> tuple[float, ...]:
    probabilities: list[float] = []
    total = 0.0
    for goals in range(_HARD_SUPPORT_LIMIT):
        probability = _nb2_probability(goals, mean, alpha)
        probabilities.append(probability)
        total += probability
        if 1.0 - total <= _TAIL_TOLERANCE * 0.01:
            _probability(total)
            return tuple(probabilities)
    raise DixonColesFitError("NB2 tail support exhausted")


def _score_matrix(
    home_mean: float, away_mean: float, alpha: float, correlation: float, tail_start: int
) -> ScoreMatrix:
    labels = tuple(str(goals) for goals in range(tail_start)) + (f"{tail_start}+",)
    home = [_nb2_probability(goals, home_mean, alpha) for goals in range(tail_start)]
    away = [_nb2_probability(goals, away_mean, alpha) for goals in range(tail_start)]
    home.append(1.0 - sum(home))
    away.append(1.0 - sum(away))
    if home[-1] < 0.0 or away[-1] < 0.0:
        raise DixonColesFitError("NB2 score-matrix tail is negative")
    rows = tuple(
        tuple(
            _joint_bucket_probability(home_index, away_index, home, away, correlation)
            for away_index in range(len(away))
        )
        for home_index in range(len(home))
    )
    total = sum(sum(row) for row in rows)
    if not math.isclose(total, 1.0, abs_tol=_TAIL_TOLERANCE):
        raise DixonColesFitError("NB2 score matrix is not normalized")
    return ScoreMatrix(labels=labels, probabilities=rows)


def _joint_bucket_probability(
    home_goals: int,
    away_goals: int,
    home: Sequence[float],
    away: Sequence[float],
    correlation: float,
) -> float:
    base = home[home_goals] * away[away_goals]
    delta = correlation * home[1] * away[1]
    if (home_goals, away_goals) in ((0, 0), (1, 1)):
        return _probability(base - delta)
    if (home_goals, away_goals) in ((0, 1), (1, 0)):
        return _probability(base + delta)
    return _probability(base)


def _markets(
    home: Sequence[float],
    away: Sequence[float],
    home_mean: float,
    away_mean: float,
    alpha: float,
    correlation: float,
) -> GoalMarkets:
    home_win = draw = away_win = 0.0
    totals = [0.0] * (len(home) + len(away) - 1)
    for home_goals, _home_probability in enumerate(home):
        for away_goals, _away_probability in enumerate(away):
            probability = _joint_probability(
                home_goals, away_goals, home_mean, away_mean, alpha, correlation
            )
            totals[home_goals + away_goals] += probability
            if home_goals > away_goals:
                home_win += probability
            elif home_goals < away_goals:
                away_win += probability
            else:
                draw += probability
    if not math.isclose(sum(totals), 1.0, abs_tol=_TAIL_TOLERANCE):
        raise DixonColesFitError("NB2 total-goal distribution is not normalized")
    delta = (
        correlation * _nb2_probability(1, home_mean, alpha) * _nb2_probability(1, away_mean, alpha)
    )
    return GoalMarkets(
        home_win=_probability(home_win),
        draw=_probability(draw),
        away_win=_probability(away_win),
        over_1_5=_probability(sum(totals[2:])),
        over_2_5=_probability(sum(totals[3:])),
        over_3_5=_probability(sum(totals[4:])),
        both_teams_to_score=_probability((1.0 - home[0]) * (1.0 - away[0]) - delta),
        home_clean_sheet=_probability(away[0]),
        away_clean_sheet=_probability(home[0]),
    )


def _verify_local_minimum(objective: object, alpha: float, value: float) -> None:
    if not callable(objective):
        raise DixonColesFitError("NB2 alpha objective is invalid")
    step = max(1e-8, 1e-6 * (1.0 + alpha))
    for candidate in (max(0.0, alpha - step), min(_ALPHA_CEILING, alpha + step)):
        if candidate != alpha and float(objective(candidate)) < value - _ALPHA_XATOL:
            raise DixonColesFitError("ALPHA_OPTIMIZER_STATIONARITY_FAILURE")


def _validate_training_probabilities(
    matches: Sequence[GoalMatch],
    means: Sequence[tuple[float, float]],
    alpha: float,
    correlation: float,
) -> None:
    for match, (home_mean, away_mean) in zip(matches, means, strict=True):
        _probability(
            _joint_probability(
                match.home_goals,
                match.away_goals,
                home_mean,
                away_mean,
                alpha,
                correlation,
            )
        )


def _training_sha256(config_sha256: str, matches: Sequence[GoalMatch]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
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
        )
    ).hexdigest()


def _alpha(value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise DixonColesContractError("alpha must be finite")
    if value < 0.0 or value >= _ALPHA_CEILING:
        raise DixonColesContractError("alpha must be between 0 and 100")


def _count(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DixonColesContractError(f"{name} must be a non-negative integer")


def _probability(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise DixonColesFitError("NB2 calculation produced an invalid probability")
    return value
