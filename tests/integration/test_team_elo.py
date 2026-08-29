from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest
from football.forecasting import (
    EloConfig,
    EloMatch,
    EloStorageError,
    PostgresEloHistory,
    TeamEloModel,
)
from psycopg import Connection
from psycopg.errors import ForeignKeyViolation

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
KICKOFF = datetime(2026, 8, 29, 15, 0, tzinfo=UTC)


@pytest.fixture
def connection() -> Connection[Any]:
    with psycopg.connect(DATABASE_URL) as database_connection:
        yield database_connection


def test_publishes_idempotent_immutable_history_and_reads_as_of_cutoff(
    connection: Connection[Any],
) -> None:
    competition_id, match_id, home_team_id, away_team_id = _canonical_match(connection)
    config = EloConfig(
        model_version="elo-integration-v1",
        home_advantage=0.0,
        time_decay_half_life_days=None,
    )
    match = _match(competition_id, match_id, home_team_id, away_team_id, 1, 0)
    history = PostgresEloHistory(connection)

    first = history.publish(TeamEloModel(config).rate((match,)))
    repeated = history.publish(TeamEloModel(config).rate((match,)))

    assert first.status == "published"
    assert first.ratings_seen == 2
    assert first.ratings_inserted == 2
    assert repeated.status == "verified_existing"
    assert repeated.ratings_inserted == 0
    assert (
        history.rating_at(config.model_version, home_team_id, KICKOFF - timedelta(seconds=1))
        is None
    )
    home_rating = history.rating_at(config.model_version, home_team_id, KICKOFF)
    assert home_rating is not None
    assert home_rating.rating == pytest.approx(1510.0)

    with connection.cursor() as cursor:
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.elo_model_versions WHERE model_version = %s",
                (config.model_version,),
            ).fetchone()[0]
            == 1
        )
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.team_elo_history WHERE model_version = %s",
                (config.model_version,),
            ).fetchone()[0]
            == 2
        )

    changed_result = _match(competition_id, match_id, home_team_id, away_team_id, 0, 1)
    with pytest.raises(EloStorageError, match="history conflicts"):
        history.publish(TeamEloModel(config).rate((changed_result,)))
    with pytest.raises(EloStorageError, match="configuration"):
        history.publish(
            TeamEloModel(
                EloConfig(
                    model_version=config.model_version,
                    home_advantage=50.0,
                    time_decay_half_life_days=None,
                )
            ).rate((match,))
        )

    unchanged = history.rating_at(config.model_version, home_team_id, KICKOFF)
    assert unchanged is not None
    assert unchanged.rating == pytest.approx(1510.0)


def test_history_requires_both_teams_to_participate_in_the_canonical_match(
    connection: Connection[Any],
) -> None:
    competition_id, match_id, home_team_id, _ = _canonical_match(connection)
    with connection.cursor() as cursor:
        non_participant = cursor.execute(
            "INSERT INTO football.teams (entity_kind) VALUES ('club') RETURNING id"
        ).fetchone()[0]
    run = TeamEloModel(EloConfig(model_version="elo-canonical-teams-v1", home_advantage=0.0)).rate(
        (_match(competition_id, match_id, home_team_id, non_participant, 1, 0),)
    )

    with pytest.raises(ForeignKeyViolation):
        PostgresEloHistory(connection).publish(run)

    with connection.cursor() as cursor:
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.elo_model_versions WHERE model_version = %s",
                (run.config.model_version,),
            ).fetchone()[0]
            == 0
        )


def test_rating_cutoff_requires_timezone(connection: Connection[Any]) -> None:
    history = PostgresEloHistory(connection)

    with pytest.raises(ValueError, match="timezone"):
        history.rating_at("elo-integration-v1", UUID(int=1), datetime(2026, 1, 1))


def _canonical_match(connection: Connection[Any]) -> tuple[UUID, UUID, UUID, UUID]:
    with connection.cursor() as cursor:
        competition_id = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        season_id = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (competition_id,),
        ).fetchone()[0]
        match_id = cursor.execute(
            """
            INSERT INTO football.matches (competition_id, season_id)
            VALUES (%s, %s) RETURNING id
            """,
            (competition_id, season_id),
        ).fetchone()[0]
        home_team_id = cursor.execute(
            "INSERT INTO football.teams (entity_kind) VALUES ('club') RETURNING id"
        ).fetchone()[0]
        away_team_id = cursor.execute(
            "INSERT INTO football.teams (entity_kind) VALUES ('club') RETURNING id"
        ).fetchone()[0]
        cursor.executemany(
            """
            INSERT INTO football.match_team_participations (match_id, team_id)
            VALUES (%s, %s)
            """,
            [(match_id, home_team_id), (match_id, away_team_id)],
        )
    return competition_id, match_id, home_team_id, away_team_id


def _match(
    competition_id: UUID,
    match_id: UUID,
    home_team_id: UUID,
    away_team_id: UUID,
    home_score: int,
    away_score: int,
) -> EloMatch:
    return EloMatch(
        match_id=match_id,
        competition_id=competition_id,
        kickoff_at=KICKOFF,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_score=home_score,
        away_score=away_score,
    )
