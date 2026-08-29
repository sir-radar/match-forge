from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import Connection, Cursor
from psycopg.types.json import Jsonb

from football.forecasting.elo import EloRun, EloTeamRating


class EloStorageError(RuntimeError):
    """An Elo model version or immutable history row conflicts with stored state."""


@dataclass(frozen=True)
class EloPublicationResult:
    model_version: str
    ratings_seen: int
    ratings_inserted: int
    status: str


class PostgresEloHistory:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def publish(self, run: EloRun) -> EloPublicationResult:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"elo-model:{run.config.model_version}",),
            )
            model_inserted = self._register_model(cursor, run)
            ratings_inserted = sum(self._rating(cursor, run, rating) for rating in run.history)
        return EloPublicationResult(
            model_version=run.config.model_version,
            ratings_seen=len(run.history),
            ratings_inserted=ratings_inserted,
            status="published" if model_inserted or ratings_inserted else "verified_existing",
        )

    def rating_at(
        self, model_version: str, team_id: UUID, cutoff: datetime
    ) -> EloTeamRating | None:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("Elo rating cutoff must include a timezone")
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT match_id, competition_id, team_id, opponent_team_id,
                       rating_timestamp, is_home, pre_match_rating, rating,
                       expected_score, actual_score
                FROM football.team_elo_history
                WHERE model_version = %s AND team_id = %s AND rating_timestamp <= %s
                ORDER BY rating_timestamp DESC, match_id DESC
                LIMIT 1
                """,
                (model_version, team_id, cutoff),
            ).fetchone()
        if row is None:
            return None
        return _stored_rating(row)

    @staticmethod
    def _register_model(cursor: Cursor[Any], run: EloRun) -> int:
        inserted = cursor.execute(
            """
            INSERT INTO football.elo_model_versions
                (model_version, config_sha256, config)
            VALUES (%s, %s, %s)
            ON CONFLICT (model_version) DO NOTHING
            """,
            (run.config.model_version, run.config.sha256, Jsonb(run.config.to_dict())),
        ).rowcount
        row = cursor.execute(
            """
            SELECT config_sha256, config
            FROM football.elo_model_versions WHERE model_version = %s
            """,
            (run.config.model_version,),
        ).fetchone()
        if row != (run.config.sha256, run.config.to_dict()):
            raise EloStorageError(
                f"Elo model version conflicts with stored configuration: {run.config.model_version}"
            )
        return inserted

    @staticmethod
    def _rating(cursor: Cursor[Any], run: EloRun, rating: EloTeamRating) -> int:
        inserted = cursor.execute(
            """
            INSERT INTO football.team_elo_history
                (model_version, team_id, opponent_team_id, match_id, competition_id,
                 rating_timestamp, is_home, pre_match_rating, rating,
                 expected_score, actual_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_version, team_id, match_id) DO NOTHING
            """,
            (
                run.config.model_version,
                rating.team_id,
                rating.opponent_team_id,
                rating.match_id,
                rating.competition_id,
                rating.rating_timestamp,
                rating.is_home,
                rating.pre_match_rating,
                rating.rating,
                rating.expected_score,
                rating.actual_score,
            ),
        ).rowcount
        row = cursor.execute(
            """
            SELECT match_id, competition_id, team_id, opponent_team_id,
                   rating_timestamp, is_home, pre_match_rating, rating,
                   expected_score, actual_score
            FROM football.team_elo_history
            WHERE model_version = %s AND team_id = %s AND match_id = %s
            """,
            (run.config.model_version, rating.team_id, rating.match_id),
        ).fetchone()
        if row is None or _stored_rating(row) != rating:
            raise EloStorageError(
                f"Elo history conflicts with stored rating: {run.config.model_version} "
                f"{rating.team_id} {rating.match_id}"
            )
        return inserted


def _stored_rating(row: tuple[Any, ...]) -> EloTeamRating:
    return EloTeamRating(
        match_id=UUID(str(row[0])),
        competition_id=UUID(str(row[1])),
        team_id=UUID(str(row[2])),
        opponent_team_id=UUID(str(row[3])),
        rating_timestamp=row[4],
        is_home=bool(row[5]),
        pre_match_rating=float(row[6]),
        rating=float(row[7]),
        expected_score=float(row[8]),
        actual_score=float(row[9]),
    )
