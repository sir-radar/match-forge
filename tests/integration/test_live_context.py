from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from football.product.api_football import ApiResponse
from football.product.context_ingestion import ContextObservationStore
from psycopg.errors import RaiseException, UniqueViolation

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
COMPETITION = UUID(int=8100)
SEASON = UUID(int=8101)
HOME = UUID(int=8102)
AWAY = UUID(int=8103)
FIXTURE = UUID(int=8104)
PROVIDER = UUID(int=8105)
SNAPSHOT = UUID(int=8106)
KICKOFF = datetime(2030, 1, 1, 18, tzinfo=UTC)
OBSERVED = datetime(2029, 12, 31, 17, tzinfo=UTC)


@pytest.fixture
def connection() -> psycopg.Connection[object]:
    with psycopg.connect(DATABASE_URL) as database:
        _seed_fixture(database)
        yield database
        database.rollback()


def test_availability_observations_are_immutable(
    connection: psycopg.Connection[object],
) -> None:
    observation_id = UUID(int=8110)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.product_availability_observations (
                observation_id, fixture_id, team_id, provider_player_id,
                availability_type, availability_state, observed_at, known_at,
                provider, source_snapshot_id, source_checksum
            ) VALUES (%s, %s, %s, 'provider-player', 'INJURY',
                'UNAVAILABLE_INJURY', %s, %s, 'api_football', %s, %s)
            """,
            (observation_id, FIXTURE, HOME, OBSERVED, OBSERVED, SNAPSHOT, "a" * 64),
        )

    with pytest.raises(RaiseException, match="immutable"), connection.cursor() as cursor:
        cursor.execute(
            """
                UPDATE football.product_availability_observations
                SET reason = 'changed' WHERE observation_id = %s
                """,
            (observation_id,),
        )


def test_identical_predictive_input_cannot_create_duplicate_revision(
    connection: psycopg.Connection[object],
) -> None:
    _insert_forecast(connection, UUID(int=8120), "1" * 64, "d" * 64)

    with pytest.raises(UniqueViolation):
        _insert_forecast(connection, UUID(int=8121), "2" * 64, "d" * 64)


def test_forecast_revisions_are_immutable(connection: psycopg.Connection[object]) -> None:
    forecast_id = UUID(int=8122)
    _insert_forecast(connection, forecast_id, "3" * 64, "4" * 64)

    with pytest.raises(RaiseException, match="immutable"), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE football.product_forecasts SET expected_home_goals = 9 WHERE forecast_id = %s",
            (forecast_id,),
        )


def test_confirmed_lineup_supersedes_latest_prediction(
    connection: psycopg.Connection[object],
) -> None:
    predicted_id = UUID(int=8130)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.product_lineup_observations (
                lineup_observation_id, fixture_id, team_id, kickoff_at,
                lineup_mode, formation, prediction_confidence, coach_context,
                preference_sample_size, observed_at, known_at, provider,
                source_snapshot_id, source_checksum
            ) VALUES (%s, %s, %s, %s, 'PREDICTED_REPEAT_XI', '4-3-3',
                'LOW', 'UNKNOWN', 0, %s, %s, 'matchforge', %s, %s)
            """,
            (predicted_id, FIXTURE, HOME, KICKOFF, OBSERVED, OBSERVED, SNAPSHOT, "8" * 64),
        )

    response = ApiResponse(
        path="/fixtures/lineups",
        fetched_at=datetime(2029, 12, 31, 18, tzinfo=UTC),
        raw=b'{"response":[{"team":{"id":1}}]}',
        rows=(
            {
                "team": {"id": 1},
                "formation": "4-2-3-1",
                "coach": {"id": 44},
                "startXI": [{"player": {"id": 99, "pos": "G", "grid": "1:1"}}],
                "substitutes": [],
            },
        ),
        remaining_day=50,
    )

    inserted = ContextObservationStore(connection).persist_lineups(
        FIXTURE, KICKOFF, response, SNAPSHOT
    )

    assert inserted == 1
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT supersedes_predicted_lineup_id
            FROM football.product_lineup_observations
            WHERE fixture_id = %s AND team_id = %s AND lineup_mode = 'CONFIRMED'
            """,
            (FIXTURE, HOME),
        )
        assert cursor.fetchone() == (predicted_id,)


def _insert_forecast(
    connection: psycopg.Connection[object],
    forecast_id: UUID,
    semantic_sha: str,
    predictive_sha: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.product_forecasts (
                forecast_id, semantic_sha256, fixture_id, model_label,
                model_algorithm_version, model_artifact_sha256, created_at,
                football_cutoff, knowledge_cutoff, knowledge_mode,
                expected_home_goals, expected_away_goals, probabilities,
                score_matrix, payload_sha256, publication_mode, forecast_horizon,
                predictive_input_snapshot_sha256, context_snapshot_sha256,
                revision_reason_codes, new_information_ids
            ) VALUES (%s, %s, %s, 'MVP_FORECAST',
                'transferable-rolling-goals-poisson-v1', %s, %s, %s, %s,
                'bitemporal', 1.2, 1.1, '{}'::jsonb, '[]'::jsonb, %s,
                'MVP_OWNER_AUTHORIZED', '24H', %s, %s,
                '["INITIAL_FORECAST"]'::jsonb, '[]'::jsonb)
            """,
            (
                forecast_id,
                semantic_sha,
                FIXTURE,
                "b" * 64,
                OBSERVED,
                OBSERVED,
                OBSERVED,
                "c" * 64,
                predictive_sha,
                "e" * 64,
            ),
        )


def _seed_fixture(connection: psycopg.Connection[object]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO football.providers (id, code, name, source_type) "
            "VALUES (%s, 'live_context_test', 'Live context test', 'http_api')",
            (PROVIDER,),
        )
        cursor.execute(
            """
            INSERT INTO football.source_snapshots (
                id, provider_id, source_identity, source_revision, acquired_at,
                manifest_path, manifest_sha256, status
            ) VALUES (%s, %s, 'live-context-test', 'v1', %s,
                'tests/live-context.json', %s, 'validated')
            """,
            (SNAPSHOT, PROVIDER, OBSERVED, "f" * 64),
        )
        cursor.execute("INSERT INTO football.competitions (id) VALUES (%s)", (COMPETITION,))
        cursor.execute(
            "INSERT INTO football.seasons (id, competition_id) VALUES (%s, %s)",
            (SEASON, COMPETITION),
        )
        cursor.execute("INSERT INTO football.teams (id) VALUES (%s), (%s)", (HOME, AWAY))
        cursor.execute(
            "INSERT INTO football.matches (id, competition_id, season_id) VALUES (%s, %s, %s)",
            (FIXTURE, COMPETITION, SEASON),
        )
        cursor.execute(
            """
            INSERT INTO football.product_competitions (
                competition_id, name, country, continent, competition_type,
                season_label, availability_status, source_roles, updated_at
            ) VALUES (%s, 'Test League', 'Test', 'Other', 'LEAGUE', '2030',
                'NOT_ENOUGH_HISTORY', '{}'::jsonb, %s)
            """,
            (COMPETITION, OBSERVED),
        )
        cursor.execute(
            """
            INSERT INTO football.product_teams (team_id, name, updated_at)
            VALUES (%s, 'Home', %s), (%s, 'Away', %s)
            """,
            (HOME, OBSERVED, AWAY, OBSERVED),
        )
        cursor.execute(
            """
            INSERT INTO football.product_team_aliases (
                provider_code, provider_team_id, normalized_name, team_id
            ) VALUES ('api_football', '1', 'home', %s),
                     ('api_football', '2', 'away', %s)
            """,
            (HOME, AWAY),
        )
        cursor.execute(
            """
            INSERT INTO football.product_fixtures (
                fixture_id, competition_id, home_team_id, away_team_id,
                kickoff_at, status, forecast_availability, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'SCHEDULED',
                'NOT_ENOUGH_HISTORY', %s)
            """,
            (FIXTURE, COMPETITION, HOME, AWAY, KICKOFF, OBSERVED),
        )
