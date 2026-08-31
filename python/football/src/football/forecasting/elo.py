from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from football.contracts.source import canonical_json_bytes

_MODEL_VERSION = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_RATING_SCALE = 400.0


class EloContractError(ValueError):
    """An Elo configuration or chronological match input is invalid."""


@dataclass(frozen=True)
class EloConfig:
    model_version: str
    initial_rating: float = 1500.0
    k_factor: float = 20.0
    home_advantage: float = 100.0
    time_decay_half_life_days: float | None = 365.0
    competition_weights: Mapping[UUID, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _MODEL_VERSION.fullmatch(self.model_version):
            raise EloContractError("model_version must use lowercase letters, digits, ., _, or -")
        _finite(self.initial_rating, "initial_rating")
        _positive(self.k_factor, "k_factor")
        _finite(self.home_advantage, "home_advantage")
        if self.time_decay_half_life_days is not None:
            _positive(self.time_decay_half_life_days, "time_decay_half_life_days")
        weights: dict[UUID, float] = {}
        for competition_id, weight in self.competition_weights.items():
            if not isinstance(competition_id, UUID):
                raise EloContractError("competition weight keys must be UUIDs")
            _positive(weight, "competition weight")
            weights[competition_id] = float(weight)
        object.__setattr__(self, "competition_weights", MappingProxyType(weights))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "initial_rating": self.initial_rating,
            "k_factor": self.k_factor,
            "home_advantage": self.home_advantage,
            "time_decay_half_life_days": self.time_decay_half_life_days,
            "competition_weights": {
                str(competition_id): weight
                for competition_id, weight in sorted(
                    self.competition_weights.items(), key=lambda item: str(item[0])
                )
            },
        }


@dataclass(frozen=True)
class EloMatch:
    match_id: UUID
    competition_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_score: int
    away_score: int

    def __post_init__(self) -> None:
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise EloContractError("kickoff_at must include a timezone")
        if self.home_team_id == self.away_team_id:
            raise EloContractError("home and away teams must differ")
        for field_name, value in (("home_score", self.home_score), ("away_score", self.away_score)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EloContractError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True)
class EloTeamRating:
    match_id: UUID
    competition_id: UUID
    team_id: UUID
    opponent_team_id: UUID
    rating_timestamp: datetime
    is_home: bool
    pre_match_rating: float
    rating: float
    expected_score: float
    actual_score: float


@dataclass(frozen=True)
class RatedEloMatch:
    match_id: UUID
    competition_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_score: int
    away_score: int
    home_pre_match_rating: float
    away_pre_match_rating: float
    expected_home_score: float
    actual_home_score: float
    home_post_match_rating: float
    away_post_match_rating: float

    @property
    def history(self) -> tuple[EloTeamRating, EloTeamRating]:
        return (
            EloTeamRating(
                match_id=self.match_id,
                competition_id=self.competition_id,
                team_id=self.home_team_id,
                opponent_team_id=self.away_team_id,
                rating_timestamp=self.kickoff_at,
                is_home=True,
                pre_match_rating=self.home_pre_match_rating,
                rating=self.home_post_match_rating,
                expected_score=self.expected_home_score,
                actual_score=self.actual_home_score,
            ),
            EloTeamRating(
                match_id=self.match_id,
                competition_id=self.competition_id,
                team_id=self.away_team_id,
                opponent_team_id=self.home_team_id,
                rating_timestamp=self.kickoff_at,
                is_home=False,
                pre_match_rating=self.away_pre_match_rating,
                rating=self.away_post_match_rating,
                expected_score=1.0 - self.expected_home_score,
                actual_score=1.0 - self.actual_home_score,
            ),
        )


@dataclass(frozen=True)
class EloRun:
    config: EloConfig
    matches: tuple[RatedEloMatch, ...]

    @property
    def history(self) -> tuple[EloTeamRating, ...]:
        return tuple(rating for match in self.matches for rating in match.history)


@dataclass(frozen=True)
class _TeamState:
    rating: float
    last_played_at: datetime


class TeamEloModel:
    def __init__(self, config: EloConfig) -> None:
        self.config = config

    def rate(self, matches: tuple[EloMatch, ...]) -> EloRun:
        identifiers = [match.match_id for match in matches]
        if len(identifiers) != len(set(identifiers)):
            raise EloContractError("duplicate match in Elo input")
        ordered = tuple(sorted(matches, key=lambda match: (match.kickoff_at, str(match.match_id))))
        state: dict[UUID, _TeamState] = {}
        rated: list[RatedEloMatch] = []
        for match in ordered:
            home_pre = self._pre_match_rating(state, match.home_team_id, match.kickoff_at)
            away_pre = self._pre_match_rating(state, match.away_team_id, match.kickoff_at)
            expected_home = _expected_home(home_pre, away_pre, self.config.home_advantage)
            actual_home = _actual_home(match.home_score, match.away_score)
            goal_difference = abs(match.home_score - match.away_score)
            margin = 1.0 if goal_difference <= 1 else 1.0 + math.log(goal_difference)
            competition_weight = self.config.competition_weights.get(match.competition_id, 1.0)
            change = (
                self.config.k_factor * competition_weight * margin * (actual_home - expected_home)
            )
            home_post = home_pre + change
            away_post = away_pre - change
            rated.append(
                RatedEloMatch(
                    match_id=match.match_id,
                    competition_id=match.competition_id,
                    kickoff_at=match.kickoff_at,
                    home_team_id=match.home_team_id,
                    away_team_id=match.away_team_id,
                    home_score=match.home_score,
                    away_score=match.away_score,
                    home_pre_match_rating=home_pre,
                    away_pre_match_rating=away_pre,
                    expected_home_score=expected_home,
                    actual_home_score=actual_home,
                    home_post_match_rating=home_post,
                    away_post_match_rating=away_post,
                )
            )
            state[match.home_team_id] = _TeamState(home_post, match.kickoff_at)
            state[match.away_team_id] = _TeamState(away_post, match.kickoff_at)
        return EloRun(self.config, tuple(rated))

    def rating_before(self, run: EloRun, team_id: UUID, cutoff: datetime) -> float:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise EloContractError("rating cutoff must include a timezone")
        if run.config != self.config:
            raise EloContractError("Elo run does not match model configuration")
        latest = next(
            (rating for rating in reversed(run.history) if rating.team_id == team_id),
            None,
        )
        if latest is None:
            return self.config.initial_rating
        if cutoff <= latest.rating_timestamp:
            raise EloContractError("rating cutoff precedes latest completed match")
        return self._decayed_rating(latest.rating, latest.rating_timestamp, cutoff)

    def _pre_match_rating(
        self, state: dict[UUID, _TeamState], team_id: UUID, kickoff_at: datetime
    ) -> float:
        previous = state.get(team_id)
        if previous is None:
            return self.config.initial_rating
        elapsed_days = (kickoff_at - previous.last_played_at).total_seconds() / 86_400.0
        if elapsed_days == 0:
            raise EloContractError("one team cannot play two matches at the same timestamp")
        if elapsed_days < 0:
            raise EloContractError("Elo matches must be processed chronologically")
        return self._decayed_rating(previous.rating, previous.last_played_at, kickoff_at)

    def _decayed_rating(self, rating: float, rating_timestamp: datetime, cutoff: datetime) -> float:
        elapsed_days = (cutoff - rating_timestamp).total_seconds() / 86_400.0
        half_life = self.config.time_decay_half_life_days
        if half_life is None:
            return rating
        retained = math.pow(0.5, elapsed_days / half_life)
        return self.config.initial_rating + (rating - self.config.initial_rating) * retained


def _expected_home(home_rating: float, away_rating: float, home_advantage: float) -> float:
    exponent = math.log(10.0) * (away_rating - home_rating - home_advantage) / _RATING_SCALE
    if exponent >= 700.0:
        return 0.0
    if exponent <= -700.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(exponent))


def _actual_home(home_score: int, away_score: int) -> float:
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EloContractError(f"{field_name} must be finite")


def _positive(value: float, field_name: str) -> None:
    _finite(value, field_name)
    if value <= 0:
        raise EloContractError(f"{field_name} must be positive")
