from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from scipy.optimize import minimize_scalar
from scipy.special import gammaln, logsumexp
from scipy.stats import binom, poisson

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

_ALGORITHM_VERSION = "dcv3-shared-match-pace-mixture-v1"
_KAPPA_XATOL = 1e-10
_KAPPA_MAXITER = 500
_PROFILE_SIZE = 1_001
_PROFILE_STEP = 0.001
_STATIONARITY_STEP = 1e-5
_TAIL_TOLERANCE = 1e-12
_HARD_SUPPORT_LIMIT = 1_000_000
_INVALID_OBJECTIVE = 1e100
_CENTERED_SERIES_MAX_HALF_WIDTH = 0.05
_CENTERED_SERIES_TERMS = 4


@dataclass(frozen=True)
class DixonColesSharedMatchPaceFit:
    base_fit: DixonColesFit
    kappa: float
    config_sha256: str
    training_sha256: str
    weighted_joint_nll: float
    converged: bool


@dataclass(frozen=True)
class DixonColesSharedMatchPaceGoalForecast:
    lambda_home: float
    lambda_away: float
    low_score_correlation: float
    kappa: float
    score_matrix: ScoreMatrix
    markets: GoalMarkets
    _total_probabilities: tuple[float, ...]

    def exact_score_probability(self, home_goals: int, away_goals: int) -> float:
        _count(home_goals, "home_goals")
        _count(away_goals, "away_goals")
        return _joint_probability(
            home_goals,
            away_goals,
            self.lambda_home,
            self.lambda_away,
            self.kappa,
            self.low_score_correlation,
        )

    def home_marginal(self, goals: int) -> float:
        _count(goals, "goals")
        return _poisson_mixture_probability(goals, self.lambda_home, self.kappa)

    def away_marginal(self, goals: int) -> float:
        _count(goals, "goals")
        return _poisson_mixture_probability(goals, self.lambda_away, self.kappa)

    def home_mean(self) -> float:
        return self.lambda_home

    def away_mean(self) -> float:
        return self.lambda_away


class DixonColesSharedMatchPaceModel:
    """Frozen DCv3 model with one mean-preserving shared uniform pace width."""

    def __init__(self, base_config: DixonColesConfig) -> None:
        if base_config.model_version != "dixon-coles-v3":
            raise DixonColesContractError(
                "shared match pace requires the frozen dixon-coles-v3 base model"
            )
        if base_config.effect_regularization != 16.0:
            raise DixonColesContractError("shared match pace requires effect regularization 16.0")
        self.base_config = base_config

    @property
    def config_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.config_dict())).hexdigest()

    def config_dict(self) -> dict[str, object]:
        return {
            "algorithm_version": _ALGORITHM_VERSION,
            "base_dcv3_config_sha256": self.base_config.sha256,
            "pace_distribution": "uniform-shared-mean-preserving-v1",
            "kappa_domain": [0.0, 1.0],
            "accepted_kappa_domain": "open-interval-0-1",
            "shared_home_away_pace": True,
            "rho_correction": "post-mixture-dc-four-cell-mass-transfer-v1",
            "kappa_fit_policy": "conditional-weighted-exact-joint-nll-v1",
            "optimizer": "scipy-minimize-scalar-bounded-v1",
            "optimizer_xatol": _KAPPA_XATOL,
            "optimizer_maxiter": _KAPPA_MAXITER,
            "profile_points": _PROFILE_SIZE,
            "stationarity_step": _STATIONARITY_STEP,
            "tail_probability_tolerance": _TAIL_TOLERANCE,
            "hard_support_limit": _HARD_SUPPORT_LIMIT,
        }

    def fit(self, matches: tuple[GoalMatch, ...]) -> DixonColesSharedMatchPaceFit:
        try:
            base_fit = DixonColesModel(self.base_config).fit(matches)
        except DixonColesFitError as error:
            raise DixonColesFitError("BASE_DCV3_FIT_FAILURE") from error
        ordered = tuple(sorted(matches, key=lambda match: (match.kickoff_at, str(match.match_id))))
        cutoff = ordered[-1].kickoff_at
        weights = tuple(
            self.base_config.match_weight((cutoff - match.kickoff_at).total_seconds() / 86_400.0)
            for match in ordered
        )
        means = tuple(
            _means(base_fit.parameters, match.home_team_id, match.away_team_id) for match in ordered
        )
        objective = _objective(
            ordered,
            weights,
            means,
            base_fit.parameters.low_score_correlation,
            self.base_config.score_matrix_tail_start,
        )
        kappa, nll = _fit_kappa(objective)
        return DixonColesSharedMatchPaceFit(
            base_fit=base_fit,
            kappa=kappa,
            config_sha256=self.config_sha256,
            training_sha256=_training_sha256(self.config_sha256, ordered),
            weighted_joint_nll=nll,
            converged=True,
        )

    def forecast(
        self,
        parameters: DixonColesParameters,
        kappa: float,
        home_team_id: UUID,
        away_team_id: UUID,
    ) -> DixonColesSharedMatchPaceGoalForecast | GoalForecast:
        _kappa(kappa)
        if kappa == 0.0:
            return DixonColesModel(self.base_config).forecast(
                parameters, home_team_id, away_team_id
            )
        home_mean, away_mean = _means(parameters, home_team_id, away_team_id)
        correlation = parameters.low_score_correlation
        _validate_low_score_cells(home_mean, away_mean, kappa, correlation)
        totals = _total_support(home_mean + away_mean, kappa)
        matrix = _score_matrix(
            home_mean,
            away_mean,
            kappa,
            correlation,
            self.base_config.score_matrix_tail_start,
        )
        markets = _markets(home_mean, away_mean, kappa, correlation, totals)
        return DixonColesSharedMatchPaceGoalForecast(
            lambda_home=home_mean,
            lambda_away=away_mean,
            low_score_correlation=correlation,
            kappa=kappa,
            score_matrix=matrix,
            markets=markets,
            _total_probabilities=totals,
        )


def _objective(
    matches: Sequence[GoalMatch],
    weights: Sequence[float],
    means: Sequence[tuple[float, float]],
    correlation: float,
    score_matrix_tail_start: int | None = None,
) -> Callable[[float], float]:
    total_weight = sum(weights)
    if not math.isfinite(total_weight) or total_weight <= 0.0:
        raise DixonColesFitError("INVALID_TRAINING_LIKELIHOOD")
    unique_means = tuple(dict.fromkeys(means))

    def evaluate(kappa: float) -> float:
        _kappa(kappa)
        if score_matrix_tail_start is not None:
            for home_mean, away_mean in unique_means:
                _validate_low_score_cells(home_mean, away_mean, kappa, correlation)
                _score_matrix(
                    home_mean,
                    away_mean,
                    kappa,
                    correlation,
                    score_matrix_tail_start,
                )
                _total_support(home_mean + away_mean, kappa)
        value = 0.0
        for match, weight, (home_mean, away_mean) in zip(matches, weights, means, strict=True):
            probability = _joint_probability(
                match.home_goals,
                match.away_goals,
                home_mean,
                away_mean,
                kappa,
                correlation,
            )
            if probability <= 0.0 or not math.isfinite(probability):
                raise DixonColesFitError("INVALID_TRAINING_LIKELIHOOD")
            value -= weight * math.log(probability)
        result = value / total_weight
        if not math.isfinite(result):
            raise DixonColesFitError("INVALID_TRAINING_LIKELIHOOD")
        return result

    return evaluate


def _fit_kappa(objective: Callable[[float], float]) -> tuple[float, float]:
    lower = objective(0.0)
    upper = objective(1.0)
    try:
        result = minimize_scalar(
            objective,
            method="bounded",
            bounds=(0.0, 1.0),
            options={"xatol": _KAPPA_XATOL, "maxiter": _KAPPA_MAXITER},
        )
    except DixonColesFitError:
        raise
    except Exception as error:
        raise DixonColesFitError("OPTIMIZER_FAILURE") from error
    candidate = float(result.x)
    if (
        not bool(result.success)
        or not math.isfinite(float(result.fun))
        or not math.isfinite(candidate)
        or candidate < 0.0
        or candidate > 1.0
        or int(getattr(result, "nit", 0)) > _KAPPA_MAXITER
    ):
        raise DixonColesFitError("OPTIMIZER_FAILURE")
    candidate_value = objective(candidate)
    best = min(lower, upper, candidate_value)
    tolerance = _objective_tolerance(best)
    if lower <= best + tolerance:
        raise DixonColesFitError("LOWER_BOUNDARY_DCV3_LIMIT")
    if upper <= best + tolerance:
        raise DixonColesFitError("UPPER_BOUNDARY_OPTIMUM")
    if not _STATIONARITY_STEP < candidate < 1.0 - _STATIONARITY_STEP:
        raise DixonColesFitError("NON_IDENTIFIABLE_PACE_PARAMETER")
    if candidate_value >= lower - tolerance or candidate_value >= upper - tolerance:
        raise DixonColesFitError("NON_IDENTIFIABLE_PACE_PARAMETER")
    _verify_stationarity(objective, candidate, candidate_value, tolerance)
    _verify_profile(objective, candidate, candidate_value, tolerance)
    return candidate, candidate_value


def _verify_stationarity(
    objective: Callable[[float], float], candidate: float, value: float, tolerance: float
) -> None:
    lower = objective(candidate - _STATIONARITY_STEP)
    upper = objective(candidate + _STATIONARITY_STEP)
    gradient = (upper - lower) / (2.0 * _STATIONARITY_STEP)
    gradient_tolerance = 10.0 * tolerance / _STATIONARITY_STEP
    if (
        abs(gradient) > gradient_tolerance
        or lower <= value + tolerance
        or upper <= value + tolerance
    ):
        raise DixonColesFitError("STATIONARITY_CHECK_FAILED")


def _verify_profile(
    objective: Callable[[float], float], candidate: float, value: float, tolerance: float
) -> None:
    values = tuple(objective(index * _PROFILE_STEP) for index in range(_PROFILE_SIZE))
    if any(
        not math.isfinite(profile_value) or profile_value >= _INVALID_OBJECTIVE
        for profile_value in values
    ):
        raise DixonColesFitError("INVALID_PROBABILITY")
    minima = tuple(
        index
        for index in range(1, _PROFILE_SIZE - 1)
        if values[index] <= values[index - 1] and values[index] <= values[index + 1]
    )
    if not minima:
        raise DixonColesFitError("NON_IDENTIFIABLE_PACE_PARAMETER")
    candidate_basins = tuple(
        index
        for index in minima
        if (index - 1) * _PROFILE_STEP <= candidate <= (index + 1) * _PROFILE_STEP
    )
    candidate_basin = candidate_basins[0] if len(candidate_basins) == 1 else None
    refined = tuple((index, *_refine_basin(objective, index)) for index in minima)
    for index, other_kappa, other_value in refined:
        if index == candidate_basin:
            continue
        if abs(other_kappa - candidate) > 1e-8 and abs(other_value - value) <= tolerance:
            raise DixonColesFitError("AMBIGUOUS_OPTIMUM")


def _refine_basin(objective: Callable[[float], float], index: int) -> tuple[float, float]:
    result = minimize_scalar(
        objective,
        method="bounded",
        bounds=((index - 1) * _PROFILE_STEP, (index + 1) * _PROFILE_STEP),
        options={"xatol": _KAPPA_XATOL, "maxiter": _KAPPA_MAXITER},
    )
    kappa = float(result.x)
    if not bool(result.success) or not math.isfinite(kappa) or not math.isfinite(float(result.fun)):
        raise DixonColesFitError("OPTIMIZER_FAILURE")
    return kappa, objective(kappa)


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
    kappa: float,
    correlation: float,
) -> float:
    _count(home_goals, "home_goals")
    _count(away_goals, "away_goals")
    base = _base_joint_probability(home_goals, away_goals, home_mean, away_mean, kappa)
    delta = correlation * _base_joint_probability(1, 1, home_mean, away_mean, kappa)
    if (home_goals, away_goals) in ((0, 0), (1, 1)):
        return _probability(base - delta)
    if (home_goals, away_goals) in ((0, 1), (1, 0)):
        return _probability(base + delta)
    return _probability(base)


def _base_joint_probability(
    home_goals: int, away_goals: int, home_mean: float, away_mean: float, kappa: float
) -> float:
    total_mean = _positive_mean(home_mean) + _positive_mean(away_mean)
    total_goals = home_goals + away_goals
    total_probability = _poisson_mixture_probability(total_goals, total_mean, kappa)
    home_share = home_mean / total_mean
    allocation = math.exp(
        gammaln(total_goals + 1.0)
        - gammaln(home_goals + 1.0)
        - gammaln(away_goals + 1.0)
        + home_goals * math.log(home_share)
        + away_goals * math.log1p(-home_share)
    )
    return _probability(total_probability * allocation)


def _poisson_mixture_probability(goals: int, mean: float, kappa: float) -> float:
    _count(goals, "goals")
    mean = _positive_mean(mean)
    _kappa(kappa)
    if kappa == 0.0:
        return _probability(math.exp(goals * math.log(mean) - mean - gammaln(goals + 1.0)))
    half_width = mean * kappa
    if half_width <= _CENTERED_SERIES_MAX_HALF_WIDTH:
        return _centered_mixture_probability(goals, mean, kappa)
    lower = mean * (1.0 - kappa)
    upper = mean * (1.0 + kappa)
    log_difference = _log_regularized_gamma_difference(goals + 1, lower, upper)
    return _probability(math.exp(log_difference - math.log(2.0 * kappa * mean)))


def _centered_mixture_probability(goals: int, mean: float, kappa: float) -> float:
    """Evaluate the frozen uniform mixture without endpoint subtraction.

    With ``h = mean * kappa`` and ``t`` uniform on ``[-1, 1]``, the exact
    mixture is the Poisson mass at ``mean`` times
    ``sum(C(goals, j) * kappa**j * M_j(h))``, where
    ``M_j(h) = integral(t**j * exp(-h * t), -1, 1) / 2``.  The finite
    calculation integrates the Taylor series for ``exp(-h * t)`` through
    degree seven.  For ``h <= 0.05``, its absolute mixture remainder is at
    most ``exp(2h) * h**8 / 8! < 1.1e-15`` before binary64 rounding.
    """
    base_probability = math.exp(goals * math.log(mean) - mean - gammaln(goals + 1.0))
    if base_probability == 0.0:
        return 0.0
    binomial_weight = 1.0
    terms: list[float] = []
    for power in range(goals + 1):
        terms.append(binomial_weight * _centered_exponential_moment(power, mean * kappa))
        if power < goals:
            binomial_weight *= (goals - power) * kappa / (power + 1)
    return _probability(base_probability * math.fsum(terms))


def _centered_exponential_moment(power: int, half_width: float) -> float:
    if power % 2 == 0:
        return math.fsum(
            half_width ** (2 * term) / ((power + 2 * term + 1) * math.factorial(2 * term))
            for term in range(_CENTERED_SERIES_TERMS)
        )
    return -math.fsum(
        half_width ** (2 * term + 1) / ((power + 2 * term + 2) * math.factorial(2 * term + 1))
        for term in range(_CENTERED_SERIES_TERMS)
    )


def _log_regularized_gamma_difference(shape: int, lower: float, upper: float) -> float:
    midpoint = (lower + upper) / 2.0
    if poisson.sf(shape - 1, midpoint) <= 0.5:
        log_lower = _log_poisson_upper_tail(shape, lower)
        log_upper = _log_poisson_upper_tail(shape, upper)
        return _log_positive_difference(log_upper, log_lower)
    log_lower = float(poisson.logcdf(shape - 1, lower))
    log_upper = float(poisson.logcdf(shape - 1, upper))
    return _log_positive_difference(log_lower, log_upper)


def _log_positive_difference(larger: float, smaller: float) -> float:
    if not math.isfinite(larger):
        raise DixonColesFitError("INVALID_PROBABILITY")
    if smaller == -math.inf:
        return larger
    if not math.isfinite(smaller) or larger <= smaller:
        raise DixonColesFitError("INVALID_PROBABILITY")
    return larger + math.log1p(-math.exp(smaller - larger))


def _log_poisson_upper_tail(start: int, mean: float) -> float:
    if mean == 0.0:
        return -math.inf
    log_probability = start * math.log(mean) - mean - gammaln(start + 1.0)
    terms = [log_probability]
    for goals in range(start + 1, start + 10_001):
        log_probability += math.log(mean) - math.log(goals)
        terms.append(log_probability)
        if goals > mean and log_probability < max(terms) - 50.0:
            return float(logsumexp(terms))
    raise DixonColesFitError("SUPPORT_TAIL_FAILURE")


def _validate_low_score_cells(
    home_mean: float, away_mean: float, kappa: float, correlation: float
) -> None:
    for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1)):
        _joint_probability(home_goals, away_goals, home_mean, away_mean, kappa, correlation)


def _score_matrix(
    home_mean: float,
    away_mean: float,
    kappa: float,
    correlation: float,
    tail_start: int,
) -> ScoreMatrix:
    labels = tuple(str(goals) for goals in range(tail_start)) + (f"{tail_start}+",)
    home = [_poisson_mixture_probability(goals, home_mean, kappa) for goals in range(tail_start)]
    away = [_poisson_mixture_probability(goals, away_mean, kappa) for goals in range(tail_start)]
    cells = [[0.0 for _ in range(tail_start + 1)] for _ in range(tail_start + 1)]
    for home_goals in range(tail_start):
        for away_goals in range(tail_start):
            cells[home_goals][away_goals] = _base_joint_probability(
                home_goals, away_goals, home_mean, away_mean, kappa
            )
        cells[home_goals][-1] = home[home_goals] - sum(cells[home_goals][:-1])
    for away_goals in range(tail_start):
        cells[-1][away_goals] = away[away_goals] - sum(
            cells[home_goals][away_goals] for home_goals in range(tail_start)
        )
    cells[-1][-1] = 1.0 - sum(sum(row) for row in cells)
    delta = correlation * _base_joint_probability(1, 1, home_mean, away_mean, kappa)
    cells[0][0] -= delta
    cells[0][1] += delta
    cells[1][0] += delta
    cells[1][1] -= delta
    rows = tuple(tuple(_probability(value) for value in row) for row in cells)
    if not math.isclose(sum(sum(row) for row in rows), 1.0, abs_tol=_TAIL_TOLERANCE):
        raise DixonColesFitError("INVALID_PROBABILITY")
    return ScoreMatrix(labels=labels, probabilities=rows)


def _total_support(total_mean: float, kappa: float) -> tuple[float, ...]:
    probabilities: list[float] = []
    mass = 0.0
    for goals in range(_HARD_SUPPORT_LIMIT):
        if float(poisson.sf(goals - 1, total_mean * (1.0 + kappa))) <= _TAIL_TOLERANCE * 0.01:
            return tuple(probabilities)
        probability = _poisson_mixture_probability(goals, total_mean, kappa)
        probabilities.append(probability)
        mass += probability
        if not math.isfinite(mass) or mass > 1.0 + _TAIL_TOLERANCE:
            raise DixonColesFitError("INVALID_PROBABILITY")
    raise DixonColesFitError("SUPPORT_TAIL_FAILURE")


def _markets(
    home_mean: float,
    away_mean: float,
    kappa: float,
    correlation: float,
    totals: Sequence[float],
) -> GoalMarkets:
    total_mean = home_mean + away_mean
    home_share = home_mean / total_mean
    home_win = draw = away_win = 0.0
    for goals, probability in enumerate(totals):
        home_win += probability * float(binom.sf(goals // 2, goals, home_share))
        away_win += probability * float(binom.cdf((goals - 1) // 2, goals, home_share))
        if goals % 2 == 0:
            draw += probability * float(binom.pmf(goals // 2, goals, home_share))
    base_11 = _base_joint_probability(1, 1, home_mean, away_mean, kappa)
    delta = correlation * base_11
    home_zero = _poisson_mixture_probability(0, home_mean, kappa)
    away_zero = _poisson_mixture_probability(0, away_mean, kappa)
    return GoalMarkets(
        home_win=_probability(home_win + delta),
        draw=_probability(draw - 2.0 * delta),
        away_win=_probability(away_win + delta),
        over_1_5=_probability(sum(totals[2:]) - delta),
        over_2_5=_probability(sum(totals[3:])),
        over_3_5=_probability(sum(totals[4:])),
        both_teams_to_score=_probability(
            1.0
            - home_zero
            - away_zero
            + _base_joint_probability(0, 0, home_mean, away_mean, kappa)
            - delta
        ),
        home_clean_sheet=away_zero,
        away_clean_sheet=home_zero,
    )


def _objective_tolerance(value: float) -> float:
    return 1e-12 * max(1.0, abs(value))


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


def _kappa(value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise DixonColesContractError("kappa must be finite")
    if value < 0.0 or value > 1.0:
        raise DixonColesContractError("kappa must be between 0 and 1")


def _positive_mean(value: float) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise DixonColesContractError("expected goals must be positive and finite")
    return value


def _count(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DixonColesContractError(f"{name} must be a non-negative integer")


def _probability(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise DixonColesFitError("INVALID_PROBABILITY")
    return value
