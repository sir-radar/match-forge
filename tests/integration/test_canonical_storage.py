from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from football.temporal.repository import PointInTimeRepository
from psycopg import Connection
from psycopg.errors import (
    CheckViolation,
    DeadlockDetected,
    ExclusionViolation,
    ForeignKeyViolation,
    UniqueViolation,
)

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with psycopg.connect(DATABASE_URL) as database_connection:
        yield database_connection


def _source_lineage(
    connection: Connection[Any], suffix: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with connection.cursor() as cursor:
        provider_id = cursor.execute(
            """
            INSERT INTO football.providers (code, name, source_type)
            VALUES (%s, %s, 'git_repository')
            RETURNING id
            """,
            (f"provider_{suffix}", f"Provider {suffix}"),
        ).fetchone()[0]
        snapshot_id = cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, repository, git_sha,
                 acquired_at, manifest_path, manifest_sha256, status)
            VALUES (%s, %s, %s, 'example/open-data', %s, %s, %s, %s, 'acquired')
            RETURNING id
            """,
            (
                provider_id,
                f"example/open-data/{suffix}",
                "b" * 40,
                "b" * 40,
                datetime(2026, 1, 1, tzinfo=UTC),
                f"manifests/{suffix}.json",
                "a" * 64,
            ),
        ).fetchone()[0]
        resource_id = cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, %s, %s, 2, 'application/json', 'parsed', 'valid', %s)
            RETURNING id
            """,
            (
                snapshot_id,
                f"data/{suffix}.json",
                "c" * 64,
                datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ).fetchone()[0]
    return provider_id, snapshot_id, resource_id


def _additional_snapshot(
    connection: Connection[Any],
    provider_id: uuid.UUID,
    suffix: str,
    acquired_at: datetime,
) -> tuple[uuid.UUID, uuid.UUID]:
    source_revision = f"{suffix}00000000"[:40]
    with connection.cursor() as cursor:
        source_identity = cursor.execute(
            "SELECT source_identity FROM football.source_snapshots WHERE provider_id = %s",
            (provider_id,),
        ).fetchone()[0]
        snapshot_id = cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, repository, git_sha,
                 acquired_at, manifest_path, manifest_sha256, status)
            VALUES (%s, %s, %s, 'example/open-data', %s, %s, %s, %s, 'acquired')
            RETURNING id
            """,
            (
                provider_id,
                source_identity,
                source_revision,
                source_revision,
                acquired_at,
                f"manifests/{suffix}-revision.json",
                "e" * 64,
            ),
        ).fetchone()[0]
        resource_id = cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, %s, %s, 3, 'application/json', 'parsed', 'valid', %s)
            RETURNING id
            """,
            (snapshot_id, f"data/{suffix}-revision.json", "f" * 64, acquired_at),
        ).fetchone()[0]
    return snapshot_id, resource_id


def test_provider_mapping_uses_uuidv7_and_rejects_ambiguous_overlap(
    connection: Connection[Any],
) -> None:
    provider_id, snapshot_id, _ = _source_lineage(connection, uuid.uuid4().hex)
    with connection.cursor() as cursor:
        first_team_id = cursor.execute(
            "INSERT INTO football.teams (entity_kind) VALUES ('national_team') RETURNING id"
        ).fetchone()[0]
        second_team_id = cursor.execute(
            "INSERT INTO football.teams (entity_kind) VALUES ('national_team') RETURNING id"
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.team_provider_mappings
                (team_id, provider_id, provider_team_id, mapping_method,
                 mapping_confidence, source_snapshot_id, first_seen_at, last_seen_at)
            VALUES (%s, %s, '779', 'explicit_crosswalk', 1, %s, %s, %s)
            """,
            (
                first_team_id,
                provider_id,
                snapshot_id,
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )

        version, provider_team_id = cursor.execute(
            """
            SELECT uuid_extract_version(team_id), provider_team_id
            FROM football.team_provider_mappings
            WHERE provider_id = %s
            """,
            (provider_id,),
        ).fetchone()
        assert version == 7
        assert provider_team_id == "779"

        with pytest.raises(ExclusionViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.team_provider_mappings
                    (team_id, provider_id, provider_team_id, mapping_method,
                     mapping_confidence, source_snapshot_id, first_seen_at, last_seen_at)
                VALUES (%s, %s, '779', 'manual', 1, %s, %s, %s)
                """,
                (
                    second_team_id,
                    provider_id,
                    snapshot_id,
                    datetime(2026, 1, 2, tzinfo=UTC),
                    datetime(2026, 1, 2, tzinfo=UTC),
                ),
            )


def test_source_lineage_rejects_cross_snapshot_resource_and_path_traversal(
    connection: Connection[Any],
) -> None:
    provider_id, snapshot_id, _ = _source_lineage(connection, uuid.uuid4().hex)
    second_snapshot_id, second_resource_id = _additional_snapshot(
        connection,
        provider_id,
        uuid.uuid4().hex,
        datetime(2026, 2, 1, tzinfo=UTC),
    )
    observed_at = datetime(2026, 2, 1, tzinfo=UTC)
    with connection.cursor() as cursor:
        player_id = cursor.execute(
            "INSERT INTO football.players DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        with pytest.raises(ForeignKeyViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.player_observations
                    (player_id, provider_id, provider_player_id, full_name,
                     known_from, source_snapshot_id, source_resource_id, acquired_at)
                VALUES (%s, %s, 'cross-snapshot', 'Cross Snapshot', %s, %s, %s, %s)
                """,
                (
                    player_id,
                    provider_id,
                    observed_at,
                    snapshot_id,
                    second_resource_id,
                    observed_at,
                ),
            )

        with pytest.raises(CheckViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.source_resources
                    (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                     parse_status, validation_status, acquired_at)
                VALUES (%s, '../outside.json', %s, 1, 'application/json',
                        'parsed', 'valid', %s)
                """,
                (second_snapshot_id, "a" * 64, observed_at),
            )


def test_point_in_time_repository_uses_half_open_knowledge_intervals(
    connection: Connection[Any],
) -> None:
    provider_id, snapshot_id, resource_id = _source_lineage(connection, uuid.uuid4().hex)
    second_snapshot_id, second_resource_id = _additional_snapshot(
        connection,
        provider_id,
        uuid.uuid4().hex,
        datetime(2026, 2, 1, tzinfo=UTC),
    )
    overlapping_snapshot_id, overlapping_resource_id = _additional_snapshot(
        connection,
        provider_id,
        uuid.uuid4().hex,
        datetime(2026, 1, 15, tzinfo=UTC),
    )
    with connection.cursor() as cursor:
        player_id = cursor.execute(
            "INSERT INTO football.players DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.player_observations
                (player_id, provider_id, provider_player_id, full_name,
                 known_from, known_to, source_snapshot_id, source_resource_id, acquired_at)
            VALUES
                (%s, %s, '5503', 'Lionel Andrés Messi', %s, %s, %s, %s, %s),
                (%s, %s, '5503', 'Lionel Messi', %s, NULL, %s, %s, %s)
            """,
            (
                player_id,
                provider_id,
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 2, 1, tzinfo=UTC),
                snapshot_id,
                resource_id,
                datetime(2026, 1, 1, tzinfo=UTC),
                player_id,
                provider_id,
                datetime(2026, 2, 1, tzinfo=UTC),
                second_snapshot_id,
                second_resource_id,
                datetime(2026, 2, 1, tzinfo=UTC),
            ),
        )

    repository = PointInTimeRepository(connection)
    january = repository.player_observation_at(
        player_id, provider_id, datetime(2026, 1, 15, tzinfo=UTC)
    )
    boundary = repository.player_observation_at(
        player_id, provider_id, datetime(2026, 2, 1, tzinfo=UTC)
    )

    assert january is not None and january.full_name == "Lionel Andrés Messi"
    assert boundary is not None and boundary.full_name == "Lionel Messi"
    assert repository.current_player_observation(player_id, provider_id) == boundary

    with (
        pytest.raises(ExclusionViolation),
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            INSERT INTO football.player_observations
                (player_id, provider_id, provider_player_id, full_name,
                 known_from, known_to, source_snapshot_id, source_resource_id, acquired_at)
            VALUES (%s, %s, '5503', 'Overlapping', %s, NULL, %s, %s, %s)
            """,
            (
                player_id,
                provider_id,
                datetime(2026, 1, 15, tzinfo=UTC),
                overlapping_snapshot_id,
                overlapping_resource_id,
                datetime(2026, 1, 15, tzinfo=UTC),
            ),
        )


def test_match_season_must_belong_to_same_competition(connection: Connection[Any]) -> None:
    with connection.cursor() as cursor:
        first_competition = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        second_competition = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        season_id = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (first_competition,),
        ).fetchone()[0]

        with pytest.raises(ForeignKeyViolation), connection.transaction():
            cursor.execute(
                "INSERT INTO football.matches (competition_id, season_id) VALUES (%s, %s)",
                (second_competition, season_id),
            )


def test_provider_season_identity_is_scoped_by_competition(
    connection: Connection[Any],
) -> None:
    provider_id, snapshot_id, _ = _source_lineage(connection, uuid.uuid4().hex)
    seen_at = datetime(2026, 1, 1, tzinfo=UTC)
    with connection.cursor() as cursor:
        first_competition = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        second_competition = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        first_season = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (first_competition,),
        ).fetchone()[0]
        second_season = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (second_competition,),
        ).fetchone()[0]
        third_season = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (first_competition,),
        ).fetchone()[0]
        cursor.executemany(
            """
            INSERT INTO football.season_provider_mappings
                (season_id, provider_id, provider_competition_id, provider_season_id,
                 first_seen_at, last_seen_at, mapping_method, mapping_confidence,
                 source_snapshot_id)
            VALUES (%s, %s, %s, '27', %s, %s, 'explicit_crosswalk', 1, %s)
            """,
            [
                (first_season, provider_id, "2", seen_at, seen_at, snapshot_id),
                (second_season, provider_id, "3", seen_at, seen_at, snapshot_id),
            ],
        )

        assert (
            cursor.execute(
                "SELECT count(*) FROM football.season_provider_mappings WHERE provider_id = %s",
                (provider_id,),
            ).fetchone()[0]
            == 2
        )

        with pytest.raises(ExclusionViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.season_provider_mappings
                    (season_id, provider_id, provider_competition_id, provider_season_id,
                     first_seen_at, last_seen_at, mapping_method, mapping_confidence,
                     source_snapshot_id)
                VALUES (%s, %s, '2', '27', %s, %s, 'manual', 1, %s)
                """,
                (third_season, provider_id, seen_at, seen_at, snapshot_id),
            )


def test_lineup_history_rejects_two_current_home_sides(connection: Connection[Any]) -> None:
    provider_id, snapshot_id, resource_id = _source_lineage(connection, uuid.uuid4().hex)
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
        first_team = cursor.execute(
            "INSERT INTO football.teams (entity_kind) VALUES ('national_team') RETURNING id"
        ).fetchone()[0]
        second_team = cursor.execute(
            "INSERT INTO football.teams (entity_kind) VALUES ('national_team') RETURNING id"
        ).fetchone()[0]
        first_participation = cursor.execute(
            """
            INSERT INTO football.match_team_participations (match_id, team_id)
            VALUES (%s, %s) RETURNING id
            """,
            (match_id, first_team),
        ).fetchone()[0]
        second_participation = cursor.execute(
            """
            INSERT INTO football.match_team_participations (match_id, team_id)
            VALUES (%s, %s) RETURNING id
            """,
            (match_id, second_team),
        ).fetchone()[0]
        known_from = datetime(2026, 1, 1, tzinfo=UTC)
        cursor.execute(
            """
            INSERT INTO football.match_team_participation_observations
                (match_team_participation_id, match_id, provider_id, side, known_from,
                 source_snapshot_id, source_resource_id, acquired_at)
            VALUES (%s, %s, %s, 'home', %s, %s, %s, %s)
            """,
            (
                first_participation,
                match_id,
                provider_id,
                known_from,
                snapshot_id,
                resource_id,
                known_from,
            ),
        )

        with pytest.raises(ExclusionViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.match_team_participation_observations
                    (match_team_participation_id, match_id, provider_id, side, known_from,
                     source_snapshot_id, source_resource_id, acquired_at)
                VALUES (%s, %s, %s, 'home', %s, %s, %s, %s)
                """,
                (
                    second_participation,
                    match_id,
                    provider_id,
                    known_from,
                    snapshot_id,
                    resource_id,
                    known_from,
                ),
            )

        player_id = cursor.execute(
            "INSERT INTO football.players DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        player_participation = cursor.execute(
            """
            INSERT INTO football.match_player_participations
                (match_team_participation_id, player_id)
            VALUES (%s, %s) RETURNING id
            """,
            (first_participation, player_id),
        ).fetchone()[0]
        player_observation = cursor.execute(
            """
            INSERT INTO football.match_player_participation_observations
                (match_player_participation_id, provider_id, jersey_number,
                 was_in_lineup, was_starter, known_from, source_snapshot_id,
                 source_resource_id, acquired_at)
            VALUES (%s, %s, 10, true, true, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                player_participation,
                provider_id,
                known_from,
                snapshot_id,
                resource_id,
                known_from,
            ),
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.player_position_stints
                (match_player_observation_id, provider_position_id, position_name,
                 period_from, clock_from, period_to, clock_to, sequence)
            VALUES (%s, '23', 'Center Forward', 1, %s, 1, %s, 1)
            """,
            (player_observation, timedelta(minutes=0), timedelta(minutes=64, seconds=9)),
        )

        with pytest.raises(CheckViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.player_position_stints
                    (match_player_observation_id, position_name, period_from,
                     clock_from, period_to, clock_to, sequence)
                VALUES (%s, 'Invalid', 1, %s, 1, %s, 2)
                """,
                (player_observation, timedelta(minutes=70), timedelta(minutes=60)),
            )


def test_event_catalog_rejects_duplicate_source_order(connection: Connection[Any]) -> None:
    provider_id, snapshot_id, resource_id = _source_lineage(connection, uuid.uuid4().hex)
    observed_at = datetime(2026, 1, 1, tzinfo=UTC)
    with connection.cursor() as cursor:
        competition_id = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        season_id = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (competition_id,),
        ).fetchone()[0]
        match_id = cursor.execute(
            "INSERT INTO football.matches (competition_id, season_id) VALUES (%s, %s) RETURNING id",
            (competition_id, season_id),
        ).fetchone()[0]
        first_event = cursor.execute(
            "INSERT INTO football.event_catalog (match_id) VALUES (%s) RETURNING id",
            (match_id,),
        ).fetchone()[0]
        second_event = cursor.execute(
            "INSERT INTO football.event_catalog (match_id) VALUES (%s) RETURNING id",
            (match_id,),
        ).fetchone()[0]
        cursor.executemany(
            """
            INSERT INTO football.event_provider_mappings
                (event_id, provider_id, provider_match_id, provider_event_id,
                 source_snapshot_id, first_seen_at, last_seen_at)
            VALUES (%s, %s, '3869685', %s, %s, %s, %s)
            """,
            [
                (first_event, provider_id, "event-a", snapshot_id, observed_at, observed_at),
                (second_event, provider_id, "event-b", snapshot_id, observed_at, observed_at),
            ],
        )
        cursor.execute(
            """
            INSERT INTO football.event_observations
                (event_id, match_id, provider_id, provider_match_id, provider_event_id,
                 event_index, provider_event_type, period, event_clock, known_from,
                 source_snapshot_id, source_resource_id, acquired_at)
            VALUES (%s, %s, %s, '3869685', 'event-a', 1, 'Starting XI', 1, %s,
                    %s, %s, %s, %s)
            """,
            (
                first_event,
                match_id,
                provider_id,
                timedelta(0),
                observed_at,
                snapshot_id,
                resource_id,
                observed_at,
            ),
        )

        with pytest.raises(UniqueViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.event_observations
                    (event_id, match_id, provider_id, provider_match_id, provider_event_id,
                     event_index, provider_event_type, period, event_clock, known_from,
                     source_snapshot_id, source_resource_id, acquired_at)
                VALUES (%s, %s, %s, '3869685', 'event-b', 1, 'Half Start', 1, %s,
                        %s, %s, %s, %s)
                """,
                (
                    second_event,
                    match_id,
                    provider_id,
                    timedelta(0),
                    observed_at,
                    snapshot_id,
                    resource_id,
                    observed_at,
                ),
            )


def test_concurrent_first_seen_mapping_leaves_one_canonical_team(
    connection: Connection[Any],
) -> None:
    provider_id, snapshot_id, _ = _source_lineage(connection, uuid.uuid4().hex)
    with connection.cursor() as cursor:
        candidate_ids = list(cursor.execute("SELECT uuidv7(), uuidv7()").fetchone())
    connection.commit()
    barrier = threading.Barrier(2, timeout=10)

    def create_mapping(team_id: uuid.UUID) -> bool:
        try:
            with (
                psycopg.connect(DATABASE_URL) as worker_connection,
                worker_connection.cursor() as cursor,
            ):
                cursor.execute(
                    "INSERT INTO football.teams (id, entity_kind) VALUES (%s, 'national_team')",
                    (team_id,),
                )
                barrier.wait()
                cursor.execute(
                    """
                    INSERT INTO football.team_provider_mappings
                        (team_id, provider_id, provider_team_id, mapping_method,
                         mapping_confidence, source_snapshot_id, first_seen_at, last_seen_at)
                    VALUES (%s, %s, 'race-779', 'explicit_crosswalk', 1, %s, %s, %s)
                    """,
                    (
                        team_id,
                        provider_id,
                        snapshot_id,
                        datetime(2026, 1, 1, tzinfo=UTC),
                        datetime(2026, 1, 1, tzinfo=UTC),
                    ),
                )
            return True
        except (DeadlockDetected, ExclusionViolation):
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create_mapping, candidate_ids))

    assert sorted(results) == [False, True]
    with connection.cursor() as cursor:
        mapped_count = cursor.execute(
            """
            SELECT count(*)
            FROM football.team_provider_mappings
            WHERE provider_team_id = 'race-779'
            """
        ).fetchone()[0]
        team_count = cursor.execute(
            "SELECT count(*) FROM football.teams WHERE id = ANY(%s)", (candidate_ids,)
        ).fetchone()[0]
    assert mapped_count == 1
    assert team_count == 1
