from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from statistics import fmean, pvariance
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from scipy.optimize import minimize

from football.contracts.source import canonical_json_bytes

CornerDistribution = Literal["poisson", "negative_binomial"]

_MODEL_VERSION = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_EFFECT_BOUND = 3.0
_LOG_DISPERSION_BOUNDS = (-8.0, 4.0)
_FEATURE_NAMES = ("possession_tendency", "shot_rate", "cross_rate", "recent_corners")


class CornerContractError(ValueError):
    """A corner model configuration, training match, or fixture is invalid."""


class CornerFitError(RuntimeError):
    """A corner count model did not produce a usable fitted solution."""


@dataclass(frozen=True)
class CornerFeatures:
    possession_tendency: float
    shot_rate: float
    cross_rate: float
    recent_corners: float

    def __post_init__(self) -> None:
        for field_name, value in self.values.items():
            _finite(value, field_name)
            if value < 0.0:
                raise CornerContractError(f"{field_name} must be non-negative")
        if self.possession_tendency > 1.0:
            raise CornerContractError("possession_tendency must be between 0 and 1")

    @property
    def values(self) -> dict[str, float]:
        return {
            "possession_tendency": self.possession_tendency,
            "shot_rate": self.shot_rate,
            "cross_rate": self.cross_rate,
            "recent_corners": self.recent_corners,
        }


@dataclass(frozen=True)
class CornerFixture:
    competition_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    home_features: CornerFeatures
    away_features: CornerFeatures

    def __post_init__(self) -> None:
        if self.home_team_id == self.away_team_id:
            raise CornerContractError("home and away teams must differ")


@dataclass(frozen=True)
class CornerMatch:
    match_id: UUID
    competition_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_corners: int
    away_corners: int
    home_features: CornerFeatures
    away_features: CornerFeatures

    def __post_init__(self) -> None:
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise CornerContractError("kickoff_at must include a timezone")
        if self.home_team_id == self.away_team_id:
            raise CornerContractError("home and away teams must differ")
        for value in (self.home_corners, self.away_corners):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CornerContractError("corner counts must be non-negative integers")


@dataclass(frozen=True)
class CornerModelConfig:
    model_version: str
    time_decay_half_life_days: float | None = 180.0
    max_iterations: int = 1_000
    tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if not isinstance(self.model_version, str) or not _MODEL_VERSION.fullmatch(
            self.model_version
        ):
            raise CornerContractError(
                "model_version must use lowercase letters, digits, ., _, or -"
            )
        if self.time_decay_half_life_days is not None:
            _positive(self.time_decay_half_life_days, "time-decay half-life")
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, int)
            or self.max_iterations <= 0
        ):
            raise CornerContractError("max_iterations must be a positive integer")
        _positive(self.tolerance, "tolerance")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "time_decay_half_life_days": self.time_decay_half_life_days,
            "max_iterations": self.max_iterations,
            "tolerance": self.tolerance,
        }

    def match_weight(self, age_days: float) -> float:
        _finite(age_days, "match age")
        if age_days < 0.0:
            raise CornerContractError("match age must be non-negative")
        if self.time_decay_half_life_days is None:
            return 1.0
        return math.pow(0.5, age_days / self.time_decay_half_life_days)


@dataclass(frozen=True)
class CornerParameters:
    intercept: float
    team_corner_strengths: Mapping[UUID, float] = field(default_factory=dict)
    opponent_concession_strengths: Mapping[UUID, float] = field(default_factory=dict)
    competition_effects: Mapping[UUID, float] = field(default_factory=dict)
    home_advantage: float = 0.0
    possession_coefficient: float = 0.0
    shot_coefficient: float = 0.0
    cross_coefficient: float = 0.0
    recent_coefficient: float = 0.0
    feature_means: CornerFeatures = field(
        default_factory=lambda: CornerFeatures(0.0, 0.0, 0.0, 0.0)
    )
    feature_scales: CornerFeatures = field(
        default_factory=lambda: CornerFeatures(1.0, 1.0, 1.0, 1.0)
    )
    dispersion: float | None = None

    def __post_init__(self) -> None:
        _bounded(self.intercept, "intercept")
        teams = _effects(self.team_corner_strengths, "team corner strength")
        opponents = _effects(self.opponent_concession_strengths, "opponent concession strength")
        competitions = _effects(self.competition_effects, "competition effect")
        if not teams or teams.keys() != opponents.keys():
            raise CornerContractError(
                "corner and concession strengths must contain the same fitted teams"
            )
        if not competitions:
            raise CornerContractError("competition effects must contain fitted competitions")
        for field_name, value in (
            ("home_advantage", self.home_advantage),
            ("possession_coefficient", self.possession_coefficient),
            ("shot_coefficient", self.shot_coefficient),
            ("cross_coefficient", self.cross_coefficient),
            ("recent_coefficient", self.recent_coefficient),
        ):
            _bounded(value, field_name)
        for value in self.feature_scales.values.values():
            if value <= 0.0:
                raise CornerContractError("feature scales must be positive")
        if self.dispersion is not None:
            _positive(self.dispersion, "dispersion")
        object.__setattr__(self, "team_corner_strengths", MappingProxyType(teams))
        object.__setattr__(self, "opponent_concession_strengths", MappingProxyType(opponents))
        object.__setattr__(self, "competition_effects", MappingProxyType(competitions))

    @property
    def coefficients(self) -> tuple[float, float, float, float]:
        return (
            self.possession_coefficient,
            self.shot_coefficient,
            self.cross_coefficient,
            self.recent_coefficient,
        )


@dataclass(frozen=True)
class CornerFit:
    model_version: str
    config: CornerModelConfig
    config_sha256: str
    training_sha256: str
    training_match_count: int
    training_cutoff: datetime
    distribution: CornerDistribution
    parameters: CornerParameters
    negative_log_likelihood: float
    aic: float
    converged: bool


@dataclass(frozen=True)
class CornerModelComparison:
    poisson: CornerFit
    negative_binomial: CornerFit
    observed_mean: float
    observed_variance: float
    overdispersed: bool
    preferred_distribution: CornerDistribution


@dataclass(frozen=True)
class CornerForecast:
    distribution: CornerDistribution
    lambda_home: float
    lambda_away: float
    home_variance: float
    away_variance: float
    dispersion: float | None

    def home_probability(self, corners: int) -> float:
        return _count_probability(corners, self.lambda_home, self.dispersion)

    def away_probability(self, corners: int) -> float:
        return _count_probability(corners, self.lambda_away, self.dispersion)


@dataclass(frozen=True)
class _CornerRow:
    corners: int
    team_index: int
    opponent_index: int
    competition_index: int
    is_home: bool
    features: CornerFeatures
    weight: float


@dataclass(frozen=True)
class _FitContext:
    matches: tuple[CornerMatch, ...]
    team_ids: tuple[UUID, ...]
    competition_ids: tuple[UUID, ...]
    rows: tuple[_CornerRow, ...]
    feature_means: CornerFeatures
    feature_scales: CornerFeatures
    cutoff: datetime
    training_sha256: str


class CornerModels:
    def __init__(self, config: CornerModelConfig) -> None:
        self.config = config

    def fit(self, matches: tuple[CornerMatch, ...]) -> CornerModelComparison:
        context = self._context(matches)
        poisson_fit = self._fit_distribution(context, "poisson")
        negative_binomial_fit = self._fit_distribution(context, "negative_binomial")
        observed_mean, observed_variance = _weighted_moments(context.rows)
        preferred: CornerDistribution = (
            "negative_binomial" if negative_binomial_fit.aic < poisson_fit.aic else "poisson"
        )
        return CornerModelComparison(
            poisson=poisson_fit,
            negative_binomial=negative_binomial_fit,
            observed_mean=observed_mean,
            observed_variance=observed_variance,
            overdispersed=observed_variance > observed_mean,
            preferred_distribution=preferred,
        )

    def forecast(self, fit: CornerFit, fixture: CornerFixture) -> CornerForecast:
        if (
            fit.model_version != self.config.model_version
            or fit.config_sha256 != self.config.sha256
        ):
            raise CornerContractError("corner fit does not match model configuration")
        parameters = fit.parameters
        if (fit.distribution == "poisson") != (parameters.dispersion is None):
            raise CornerContractError("corner fit distribution and dispersion disagree")
        for team_id in (fixture.home_team_id, fixture.away_team_id):
            if team_id not in parameters.team_corner_strengths:
                raise CornerContractError(f"team is not fitted: {team_id}")
        if fixture.competition_id not in parameters.competition_effects:
            raise CornerContractError(f"competition is not fitted: {fixture.competition_id}")
        lambda_home = self._expected(
            parameters,
            fixture.home_team_id,
            fixture.away_team_id,
            fixture.competition_id,
            True,
            fixture.home_features,
        )
        lambda_away = self._expected(
            parameters,
            fixture.away_team_id,
            fixture.home_team_id,
            fixture.competition_id,
            False,
            fixture.away_features,
        )
        dispersion = parameters.dispersion
        home_variance = lambda_home
        away_variance = lambda_away
        if dispersion is not None:
            home_variance += dispersion * lambda_home * lambda_home
            away_variance += dispersion * lambda_away * lambda_away
        return CornerForecast(
            distribution=fit.distribution,
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            home_variance=home_variance,
            away_variance=away_variance,
            dispersion=dispersion,
        )

    def _context(self, matches: tuple[CornerMatch, ...]) -> _FitContext:
        if not matches:
            raise CornerContractError("corner fitting requires at least one match")
        match_ids = [match.match_id for match in matches]
        if len(match_ids) != len(set(match_ids)):
            raise CornerContractError("duplicate match in corner input")
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
        competition_ids = tuple(sorted({match.competition_id for match in ordered}, key=str))
        team_indexes = {team_id: index for index, team_id in enumerate(team_ids)}
        competition_indexes = {
            competition_id: index for index, competition_id in enumerate(competition_ids)
        }
        cutoff = ordered[-1].kickoff_at
        features = [
            item for match in ordered for item in (match.home_features, match.away_features)
        ]
        feature_means, feature_scales = _feature_scaling(features)
        rows: list[_CornerRow] = []
        for match in ordered:
            weight = self.config.match_weight(
                (cutoff - match.kickoff_at).total_seconds() / 86_400.0
            )
            competition_index = competition_indexes[match.competition_id]
            rows.extend(
                (
                    _CornerRow(
                        match.home_corners,
                        team_indexes[match.home_team_id],
                        team_indexes[match.away_team_id],
                        competition_index,
                        True,
                        match.home_features,
                        weight,
                    ),
                    _CornerRow(
                        match.away_corners,
                        team_indexes[match.away_team_id],
                        team_indexes[match.home_team_id],
                        competition_index,
                        False,
                        match.away_features,
                        weight,
                    ),
                )
            )
        return _FitContext(
            matches=ordered,
            team_ids=team_ids,
            competition_ids=competition_ids,
            rows=tuple(rows),
            feature_means=feature_means,
            feature_scales=feature_scales,
            cutoff=cutoff,
            training_sha256=_training_sha256(self.config.sha256, ordered),
        )

    def _fit_distribution(
        self, context: _FitContext, distribution: CornerDistribution
    ) -> CornerFit:
        team_count = len(context.team_ids)
        competition_count = len(context.competition_ids)
        base_parameter_count = 2 * (team_count - 1) + (competition_count - 1) + 6
        observed_mean, variance = _weighted_moments(context.rows)
        observed_mean = max(observed_mean, 0.1)
        initial = [0.0] * base_parameter_count
        intercept_index = 2 * (team_count - 1) + (competition_count - 1)
        initial[intercept_index] = min(max(math.log(observed_mean), -_EFFECT_BOUND), _EFFECT_BOUND)
        bounds = [(-_EFFECT_BOUND, _EFFECT_BOUND)] * base_parameter_count
        if distribution == "negative_binomial":
            initial_dispersion = max((variance - observed_mean) / (observed_mean**2), 0.01)
            initial.append(
                min(
                    max(math.log(initial_dispersion), _LOG_DISPERSION_BOUNDS[0]),
                    _LOG_DISPERSION_BOUNDS[1],
                )
            )
            bounds.append(_LOG_DISPERSION_BOUNDS)

        def objective(values: Sequence[float]) -> float:
            unpacked = _unpack(values, team_count, competition_count, distribution)
            negative_log_likelihood = 0.0
            for row in context.rows:
                expected = _row_expected(
                    row,
                    unpacked,
                    context.feature_means,
                    context.feature_scales,
                )
                if distribution == "poisson":
                    log_probability = _poisson_log_probability(row.corners, expected)
                else:
                    if unpacked.dispersion is None:
                        raise AssertionError("negative-binomial dispersion is missing")
                    log_probability = _negative_binomial_log_probability(
                        row.corners, expected, unpacked.dispersion
                    )
                negative_log_likelihood -= row.weight * log_probability
            return negative_log_likelihood

        result = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": self.config.max_iterations, "ftol": self.config.tolerance},
        )
        if not bool(result.success) or not math.isfinite(float(result.fun)):
            raise CornerFitError(
                f"{distribution} corner optimizer did not converge: {result.message}"
            )
        unpacked = _unpack(result.x, team_count, competition_count, distribution)
        parameters = CornerParameters(
            intercept=unpacked.intercept,
            team_corner_strengths=dict(zip(context.team_ids, unpacked.team_effects, strict=True)),
            opponent_concession_strengths=dict(
                zip(context.team_ids, unpacked.opponent_effects, strict=True)
            ),
            competition_effects=dict(
                zip(context.competition_ids, unpacked.competition_effects, strict=True)
            ),
            home_advantage=unpacked.home_advantage,
            possession_coefficient=unpacked.feature_coefficients[0],
            shot_coefficient=unpacked.feature_coefficients[1],
            cross_coefficient=unpacked.feature_coefficients[2],
            recent_coefficient=unpacked.feature_coefficients[3],
            feature_means=context.feature_means,
            feature_scales=context.feature_scales,
            dispersion=unpacked.dispersion,
        )
        parameter_count = len(initial)
        return CornerFit(
            model_version=self.config.model_version,
            config=self.config,
            config_sha256=self.config.sha256,
            training_sha256=context.training_sha256,
            training_match_count=len(context.matches),
            training_cutoff=context.cutoff,
            distribution=distribution,
            parameters=parameters,
            negative_log_likelihood=float(result.fun),
            aic=2.0 * parameter_count + 2.0 * float(result.fun),
            converged=True,
        )

    @staticmethod
    def _expected(
        parameters: CornerParameters,
        team_id: UUID,
        opponent_id: UUID,
        competition_id: UUID,
        is_home: bool,
        features: CornerFeatures,
    ) -> float:
        standardized = _standardize(features, parameters.feature_means, parameters.feature_scales)
        linear = (
            parameters.intercept
            + parameters.team_corner_strengths[team_id]
            + parameters.opponent_concession_strengths[opponent_id]
            + parameters.competition_effects[competition_id]
            + (parameters.home_advantage if is_home else 0.0)
            + sum(
                coefficient * feature
                for coefficient, feature in zip(parameters.coefficients, standardized, strict=True)
            )
        )
        return math.exp(min(max(linear, -20.0), 20.0))


@dataclass(frozen=True)
class _UnpackedParameters:
    team_effects: tuple[float, ...]
    opponent_effects: tuple[float, ...]
    competition_effects: tuple[float, ...]
    intercept: float
    home_advantage: float
    feature_coefficients: tuple[float, float, float, float]
    dispersion: float | None


def _unpack(
    values: Sequence[float],
    team_count: int,
    competition_count: int,
    distribution: CornerDistribution,
) -> _UnpackedParameters:
    index = 0
    free_team = tuple(float(value) for value in values[index : index + team_count - 1])
    index += team_count - 1
    free_opponent = tuple(float(value) for value in values[index : index + team_count - 1])
    index += team_count - 1
    free_competitions = tuple(
        float(value) for value in values[index : index + competition_count - 1]
    )
    index += competition_count - 1
    intercept = float(values[index])
    home_advantage = float(values[index + 1])
    feature_coefficients = tuple(float(value) for value in values[index + 2 : index + 6])
    dispersion = math.exp(float(values[-1])) if distribution == "negative_binomial" else None
    return _UnpackedParameters(
        team_effects=(*free_team, -sum(free_team)),
        opponent_effects=(*free_opponent, -sum(free_opponent)),
        competition_effects=(0.0, *free_competitions),
        intercept=intercept,
        home_advantage=home_advantage,
        feature_coefficients=(
            feature_coefficients[0],
            feature_coefficients[1],
            feature_coefficients[2],
            feature_coefficients[3],
        ),
        dispersion=dispersion,
    )


def _row_expected(
    row: _CornerRow,
    parameters: _UnpackedParameters,
    means: CornerFeatures,
    scales: CornerFeatures,
) -> float:
    standardized = _standardize(row.features, means, scales)
    linear = (
        parameters.intercept
        + parameters.team_effects[row.team_index]
        + parameters.opponent_effects[row.opponent_index]
        + parameters.competition_effects[row.competition_index]
        + (parameters.home_advantage if row.is_home else 0.0)
        + sum(
            coefficient * feature
            for coefficient, feature in zip(
                parameters.feature_coefficients, standardized, strict=True
            )
        )
    )
    return math.exp(min(max(linear, -20.0), 20.0))


def _feature_scaling(
    features: list[CornerFeatures],
) -> tuple[CornerFeatures, CornerFeatures]:
    columns = {name: [feature.values[name] for feature in features] for name in _FEATURE_NAMES}
    means = {name: fmean(values) for name, values in columns.items()}
    scales = {
        name: deviation if (deviation := math.sqrt(pvariance(values))) > 1e-12 else 1.0
        for name, values in columns.items()
    }
    return (
        CornerFeatures(**means),
        CornerFeatures(**scales),
    )


def _weighted_moments(rows: tuple[_CornerRow, ...]) -> tuple[float, float]:
    total_weight = sum(row.weight for row in rows)
    mean = sum(row.weight * row.corners for row in rows) / total_weight
    variance = sum(row.weight * (row.corners - mean) ** 2 for row in rows) / total_weight
    return mean, variance


def _standardize(
    features: CornerFeatures, means: CornerFeatures, scales: CornerFeatures
) -> tuple[float, float, float, float]:
    feature_values = features.values
    mean_values = means.values
    scale_values = scales.values
    standardized = tuple(
        (feature_values[name] - mean_values[name]) / scale_values[name] for name in _FEATURE_NAMES
    )
    return standardized[0], standardized[1], standardized[2], standardized[3]


def _count_probability(corners: int, expected: float, dispersion: float | None) -> float:
    if isinstance(corners, bool) or not isinstance(corners, int) or corners < 0:
        raise CornerContractError("corner count must be a non-negative integer")
    if dispersion is None:
        return math.exp(_poisson_log_probability(corners, expected))
    return math.exp(_negative_binomial_log_probability(corners, expected, dispersion))


def _poisson_log_probability(count: int, expected: float) -> float:
    return count * math.log(expected) - expected - math.lgamma(count + 1.0)


def _negative_binomial_log_probability(count: int, expected: float, dispersion: float) -> float:
    shape = 1.0 / dispersion
    return (
        math.lgamma(count + shape)
        - math.lgamma(shape)
        - math.lgamma(count + 1.0)
        + shape * math.log(shape / (shape + expected))
        + count * math.log(expected / (shape + expected))
    )


def _training_sha256(config_sha256: str, matches: tuple[CornerMatch, ...]) -> str:
    payload = {
        "config_sha256": config_sha256,
        "matches": [
            {
                "match_id": str(match.match_id),
                "competition_id": str(match.competition_id),
                "kickoff_at": match.kickoff_at.isoformat(),
                "home_team_id": str(match.home_team_id),
                "away_team_id": str(match.away_team_id),
                "home_corners": match.home_corners,
                "away_corners": match.away_corners,
                "home_features": match.home_features.values,
                "away_features": match.away_features.values,
            }
            for match in matches
        ],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _effects(values: Mapping[UUID, float], field_name: str) -> dict[UUID, float]:
    effects: dict[UUID, float] = {}
    for identifier, value in values.items():
        if not isinstance(identifier, UUID):
            raise CornerContractError(f"{field_name} keys must be UUIDs")
        _bounded(value, field_name)
        effects[identifier] = float(value)
    return effects


def _bounded(value: float, field_name: str) -> None:
    _finite(value, field_name)
    if abs(value) > _EFFECT_BOUND:
        raise CornerContractError(
            f"{field_name} must be between -{_EFFECT_BOUND} and {_EFFECT_BOUND}"
        )


def _positive(value: float, field_name: str) -> None:
    _finite(value, field_name)
    if value <= 0.0:
        raise CornerContractError(f"{field_name} must be positive")


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CornerContractError(f"{field_name} must be finite")
