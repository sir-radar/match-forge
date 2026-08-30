from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import class_row

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.contracts import PointInTimeScopeV1


class ForecastingDatasetError(RuntimeError):
    """A point-in-time forecasting dataset cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class CompletedMatchV1:
    match_id: UUID
    competition_id: UUID
    season_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_score: int
    away_score: int


@dataclass(frozen=True, slots=True)
class ForecastMatchContextV1:
    match_id: UUID
    competition_id: UUID
    season_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID

    def __post_init__(self) -> None:
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise ForecastingDatasetError("forecast kickoff_at must include a timezone")
        if self.home_team_id == self.away_team_id:
            raise ForecastingDatasetError("forecast home and away teams must differ")

    @property
    def sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "ForecastMatchContextV1",
            "match_id": str(self.match_id),
            "competition_id": str(self.competition_id),
            "season_id": str(self.season_id),
            "kickoff_at": self.kickoff_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "home_team_id": str(self.home_team_id),
            "away_team_id": str(self.away_team_id),
        }


@dataclass(frozen=True, slots=True)
class ForecastBatchV1:
    scope: PointInTimeScopeV1
    matches: tuple[ForecastMatchContextV1, ...]

    def __post_init__(self) -> None:
        if not self.matches:
            raise ForecastingDatasetError("forecast batch must contain at least one match")
        identifiers = [match.match_id for match in self.matches]
        if len(identifiers) != len(set(identifiers)):
            raise ForecastingDatasetError("forecast batch contains duplicate matches")
        if any(match.kickoff_at != self.scope.football_cutoff for match in self.matches):
            raise ForecastingDatasetError("forecast batch kickoff must equal football cutoff")


class PointInTimeMatchDatasetProvider:
    """Resolve immutable history and label-free targets at explicit dual cutoffs."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def completed_history(
        self,
        scope: PointInTimeScopeV1,
        competition_id: UUID,
        season_id: UUID,
    ) -> tuple[CompletedMatchV1, ...]:
        self._verify_scope(scope)
        with self._connection.cursor(row_factory=class_row(CompletedMatchV1)) as cursor:
            rows = cursor.execute(
                """
                SELECT match.id AS match_id, match.competition_id, match.season_id,
                       observation.kickoff_at, observation.home_team_id,
                       observation.away_team_id, observation.home_score,
                       observation.away_score
                FROM football.matches AS match
                JOIN football.match_observations AS observation
                  ON observation.match_id = match.id
                WHERE match.competition_id = %s
                  AND match.season_id = %s
                  AND observation.source_snapshot_id = %s
                  AND football.known_at(
                      observation.known_from, observation.known_to, %s
                  )
                  AND observation.lifecycle = 'completed'
                  AND observation.kickoff_at < %s
                  AND observation.home_team_id IS NOT NULL
                  AND observation.away_team_id IS NOT NULL
                  AND observation.home_score IS NOT NULL
                  AND observation.away_score IS NOT NULL
                ORDER BY observation.kickoff_at, match.id
                """,
                (
                    competition_id,
                    season_id,
                    scope.source_snapshot_id,
                    scope.knowledge_cutoff,
                    scope.football_cutoff,
                ),
            ).fetchall()
        return tuple(rows)

    def forecast_batch(
        self,
        scope: PointInTimeScopeV1,
        competition_id: UUID,
        season_id: UUID,
    ) -> ForecastBatchV1:
        self._verify_scope(scope)
        with self._connection.cursor(row_factory=class_row(ForecastMatchContextV1)) as cursor:
            rows = cursor.execute(
                """
                SELECT match.id AS match_id, match.competition_id, match.season_id,
                       observation.kickoff_at, observation.home_team_id,
                       observation.away_team_id
                FROM football.matches AS match
                JOIN football.match_observations AS observation
                  ON observation.match_id = match.id
                WHERE match.competition_id = %s
                  AND match.season_id = %s
                  AND observation.source_snapshot_id = %s
                  AND football.known_at(
                      observation.known_from, observation.known_to, %s
                  )
                  AND observation.kickoff_at = %s
                  AND observation.home_team_id IS NOT NULL
                  AND observation.away_team_id IS NOT NULL
                  AND observation.lifecycle NOT IN ('abandoned', 'postponed', 'cancelled')
                ORDER BY match.id
                """,
                (
                    competition_id,
                    season_id,
                    scope.source_snapshot_id,
                    scope.knowledge_cutoff,
                    scope.football_cutoff,
                ),
            ).fetchall()
        if not rows:
            raise ForecastingDatasetError("point-in-time scope contains no forecast targets")
        return ForecastBatchV1(scope=scope, matches=tuple(rows))

    def _verify_scope(self, scope: PointInTimeScopeV1) -> None:
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT status
                FROM football.dataset_versions
                WHERE id = %s AND source_snapshot_id = %s
                """,
                (scope.dataset_version_id, scope.source_snapshot_id),
            ).fetchone()
        if row != ("published",):
            raise ForecastingDatasetError(
                "point-in-time scope does not reference one published dataset/source pair"
            )
