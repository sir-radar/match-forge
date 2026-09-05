from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.forecasting.artifacts import ModelArtifactPublisher, PortableModelArtifactStore
from football.forecasting.contracts import (
    BaselineForecastV1,
    MatchResultProbabilitiesV1,
    ModelFamily,
    ModelFitSpecV1,
    PointInTimeScopeV1,
    forecast_payload_sha256,
)
from football.forecasting.corner import CornerModelConfig
from football.forecasting.dataset import (
    CompletedMatchV1,
    EvaluationMatchOutcomeV1,
    ForecastMatchContextV1,
)
from football.forecasting.dixon_coles import DixonColesConfig
from football.forecasting.elo import EloConfig
from football.forecasting.evaluation import EvaluatedMatchResultV1, evaluate_match_results
from football.forecasting.execution import Sprint2BatchModeler, Sprint2ExecutionPolicyV1
from football.forecasting.execution_publication import (
    Sprint2BatchPublisher,
    Sprint2ExecutionProvenanceV1,
)
from football.forecasting.governance import (
    EvaluationReportPublisher,
    GovernancePublicationError,
    ModelPromotionEventV1,
    PostgresModelPromotionRegistry,
    Sprint2EvaluationReportV1,
)
from football.forecasting.publication import BaselineForecastPublisher
from football.retirement import PostgresArtifactRetirementStore
from football.temporal.repository import PointInTimeRepository
from psycopg import Connection
from psycopg.errors import (
    CheckViolation,
    DeadlockDetected,
    ExclusionViolation,
    ForeignKeyViolation,
    RaiseException,
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
                VALUES (%s, 'Invalid', 1, %s, 1, NULL, 2)
                """,
                (player_observation, timedelta(minutes=70)),
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


def test_dataset_lineage_rejects_resource_from_another_snapshot(
    connection: Connection[Any],
) -> None:
    _first_provider, first_snapshot, _first_resource = _source_lineage(connection, uuid.uuid4().hex)
    _second_provider, _second_snapshot, second_resource = _source_lineage(
        connection, uuid.uuid4().hex
    )
    dataset_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'events', 'normalized', %s, 'v1', %s,
                    'statsbomb-normalizer-v1', 'manifests/dataset.json', %s,
                    'published', %s)
            """,
            (
                dataset_id,
                first_snapshot,
                "d" * 64,
                "e" * 64,
                "f" * 64,
                datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )

        with pytest.raises(ForeignKeyViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.dataset_inputs
                    (dataset_version_id, source_snapshot_id, source_resource_id, input_role)
                VALUES (%s, %s, %s, 'source')
                """,
                (dataset_id, first_snapshot, second_resource),
            )


def test_model_artifact_publication_reconciles_identical_retry(
    connection: Connection[Any], tmp_path: Path
) -> None:
    _provider_id, snapshot_id, _resource_id = _source_lineage(connection, uuid.uuid4().hex)
    now = datetime(2026, 8, 29, 16, 0, tzinfo=UTC)
    with connection.cursor() as cursor:
        dataset_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
        artifact_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'events', 'normalized', %s, 'v1', %s,
                    'statsbomb-normalizer-v1', %s, %s, 'published', %s)
            """,
            (
                dataset_id,
                snapshot_id,
                dataset_id.hex * 2,
                "2" * 64,
                f"manifests/{dataset_id}.json",
                "3" * 64,
                now,
            ),
        )
    fit_spec = ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="dixon-coles-v1",
        config_sha256="4" * 64,
        scope=PointInTimeScopeV1(
            dataset_version_id=dataset_id,
            source_snapshot_id=snapshot_id,
            feature_set_version="sprint2-features-v1",
            football_cutoff=now,
            knowledge_cutoff=now,
            knowledge_mode="bitemporal",
            quality_policy_sha256="5" * 64,
            target_set_sha256="6" * 64,
        ),
        code_commit_sha="7" * 40,
        dependency_lock_sha256="8" * 64,
    )
    publisher = ModelArtifactPublisher(connection, tmp_path)

    with connection.transaction(force_rollback=True):
        orphaned = publisher.publish(
            model_artifact_id=artifact_id,
            fit_spec=fit_spec,
            state={"contract": "DixonColesModelStateV1", "home_advantage": 0.2},
            created_at=now,
        )
        assert orphaned.status == "published"
    with connection.cursor() as cursor:
        assert cursor.execute(
            "SELECT count(*) FROM football.model_artifacts WHERE fit_spec_sha256 = %s",
            (fit_spec.sha256,),
        ).fetchone() == (0,)

    first = publisher.publish(
        model_artifact_id=artifact_id,
        fit_spec=fit_spec,
        state={"contract": "DixonColesModelStateV1", "home_advantage": 0.2},
        created_at=now + timedelta(hours=1),
    )
    with connection.cursor() as cursor:
        retry_artifact_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
    retry = publisher.publish(
        model_artifact_id=retry_artifact_id,
        fit_spec=fit_spec,
        state={"contract": "DixonColesModelStateV1", "home_advantage": 0.2},
        created_at=now,
    )

    assert first.status == "published"
    assert first.manifest.created_at == now
    assert retry.status == "verified_existing"
    assert retry.manifest.model_artifact_id == artifact_id
    with connection.cursor() as cursor:
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.model_artifacts WHERE fit_spec_sha256 = %s",
                (fit_spec.sha256,),
            ).fetchone()[0]
            == 1
        )
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.model_artifact_files WHERE model_artifact_id = %s",
                (artifact_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.model_artifact_inputs WHERE model_artifact_id = %s",
                (artifact_id,),
            ).fetchone()[0]
            == 1
        )
        assert cursor.execute(
            """
                SELECT count(*) FROM football.dependency_edges
                WHERE upstream_kind = 'DATASET' AND upstream_id = %s
                  AND relationship = 'FITTED_FROM'
                  AND downstream_kind = 'MODEL_ARTIFACT' AND downstream_id = %s
                """,
            (dataset_id, artifact_id),
        ).fetchone() == (1,)


def test_forecast_publication_supports_multiple_primary_artifacts_and_retry(
    connection: Connection[Any], tmp_path: Path
) -> None:
    _provider_id, snapshot_id, _resource_id = _source_lineage(connection, uuid.uuid4().hex)
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    with connection.cursor() as cursor:
        dataset_id, first_artifact_id, second_artifact_id, forecast_id = cursor.execute(
            "SELECT uuidv7(), uuidv7(), uuidv7(), uuidv7()"
        ).fetchone()
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
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'events', 'normalized', %s, 'v1', %s,
                    'statsbomb-normalizer-v1', %s, %s, 'published', %s)
            """,
            (
                dataset_id,
                snapshot_id,
                dataset_id.hex * 2,
                "9" * 64,
                f"manifests/{dataset_id}.json",
                "a" * 64,
                now,
            ),
        )
    scope = PointInTimeScopeV1(
        dataset_version_id=dataset_id,
        source_snapshot_id=snapshot_id,
        feature_set_version="sprint2-features-v1",
        football_cutoff=now,
        knowledge_cutoff=now,
        knowledge_mode="bitemporal",
        quality_policy_sha256="b" * 64,
        target_set_sha256="c" * 64,
    )
    model_publisher = ModelArtifactPublisher(connection, tmp_path)
    model_specs: tuple[tuple[uuid.UUID, ModelFamily, str], ...] = (
        (first_artifact_id, "DIXON_COLES_GOALS", "d" * 64),
        (second_artifact_id, "TEAM_ELO", "e" * 64),
    )
    for artifact_id, model_family, config_sha256 in model_specs:
        model_publisher.publish(
            model_artifact_id=artifact_id,
            fit_spec=ModelFitSpecV1(
                model_family=model_family,
                algorithm_version="baseline-v1",
                config_sha256=config_sha256,
                scope=scope,
                code_commit_sha="f" * 40,
                dependency_lock_sha256="1" * 64,
            ),
            state={"contract": "TestModelStateV1", "coefficient": 0.2},
            created_at=now,
        )
    probabilities = MatchResultProbabilitiesV1(home=0.45, draw=0.3, away=0.25)
    forecast = BaselineForecastV1(
        forecast_id=forecast_id,
        match_id=match_id,
        prediction_cutoff=now,
        scope=scope,
        probability_variant="MODEL_RAW",
        model_artifact_ids=(first_artifact_id, second_artifact_id),
        forecast_context_sha256="d" * 64,
        payload_sha256=forecast_payload_sha256(probabilities),
        match_result=probabilities,
    )
    publisher = BaselineForecastPublisher(connection, tmp_path)

    first = publisher.publish(forecast, now)
    with connection.cursor() as cursor:
        retry_forecast_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
    retry = publisher.publish(replace(forecast, forecast_id=retry_forecast_id), now)

    assert first.status == "published"
    assert retry.status == "verified_existing"
    assert retry.forecast.forecast_id == forecast_id
    with connection.cursor() as cursor:
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.baseline_forecasts WHERE id = %s",
                (forecast_id,),
            ).fetchone()[0]
            == 1
        )
        roles = cursor.execute(
            """
            SELECT artifact_role FROM football.forecast_artifacts
            WHERE forecast_id = %s ORDER BY model_artifact_id
            """,
            (forecast_id,),
        ).fetchall()
        dependency_count = cursor.execute(
            """
            SELECT count(*) FROM football.dependency_edges
            WHERE upstream_kind = 'MODEL_ARTIFACT'
              AND downstream_kind = 'FORECAST'
              AND downstream_id = %s
              AND relationship = 'FORECAST_WITH'
            """,
            (forecast_id,),
        ).fetchone()
    assert roles == [("PRIMARY",), ("PRIMARY",)]
    assert dependency_count == (2,)

    retirements = PostgresArtifactRetirementStore(connection)
    retired = retirements.retire_forecast(
        forecast_id,
        evidence_reference="tests/integration/test_canonical_storage.py",
        recorded_at=now,
        code_commit_sha="a" * 40,
    )
    retry_retired = retirements.retire_forecast(
        forecast_id,
        evidence_reference="tests/integration/test_canonical_storage.py",
        recorded_at=now,
        code_commit_sha="a" * 40,
    )

    assert retired.status == "inserted"
    assert retry_retired.status == "verified_existing"
    with connection.cursor() as cursor:
        assert cursor.execute(
            "SELECT payload_sha256 FROM football.baseline_forecasts WHERE id = %s",
            (forecast_id,),
        ).fetchone() == (forecast.payload_sha256,)
        assert cursor.execute(
            "SELECT count(*) FROM football.forecast_artifacts WHERE forecast_id = %s",
            (forecast_id,),
        ).fetchone() == (2,)
        assert cursor.execute(
            """
            SELECT count(*) FROM football.dependency_edges
            WHERE downstream_kind = 'FORECAST' AND downstream_id = %s
            """,
            (forecast_id,),
        ).fetchone() == (2,)
        with pytest.raises(RaiseException, match="append-only"), connection.transaction():
            cursor.execute(
                "UPDATE football.artifact_retirement_events SET reason = 'changed' WHERE id = %s",
                (retired.event.retirement_event_id,),
            )


def test_sprint2_batch_publication_registers_complete_retry_safe_batch(
    connection: Connection[Any], tmp_path: Path
) -> None:
    _provider_id, snapshot_id, _resource_id = _source_lineage(
        connection, f"sprint2_{uuid.uuid4().hex}"
    )
    published_at = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    with connection.cursor() as cursor:
        dataset_id = cursor.execute("SELECT uuidv7()").fetchone()[0]
        competition_id = cursor.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        season_id = cursor.execute(
            "INSERT INTO football.seasons (competition_id) VALUES (%s) RETURNING id",
            (competition_id,),
        ).fetchone()[0]
        target_match_id = cursor.execute(
            """
            INSERT INTO football.matches (competition_id, season_id)
            VALUES (%s, %s) RETURNING id
            """,
            (competition_id, season_id),
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'events', 'normalized', %s, 'v1', %s,
                    'statsbomb-normalizer-v1', %s, %s, 'published', %s)
            """,
            (
                dataset_id,
                snapshot_id,
                dataset_id.hex * 2,
                "1" * 64,
                f"manifests/{dataset_id}.json",
                "2" * 64,
                published_at,
            ),
        )
    teams = tuple(uuid.UUID(int=index) for index in range(1, 5))
    start = datetime(2015, 8, 1, 14, 0, tzinfo=UTC)
    schedule = (
        (0, 1, 2, 0),
        (2, 3, 1, 0),
        (1, 2, 1, 1),
        (3, 0, 0, 1),
        (0, 2, 3, 1),
        (1, 3, 2, 1),
        (2, 0, 1, 1),
        (3, 1, 0, 2),
        (0, 3, 2, 1),
        (2, 1, 0, 0),
        (1, 0, 1, 2),
        (3, 2, 1, 1),
    )
    history = tuple(
        CompletedMatchV1(
            match_id=uuid.UUID(int=index + 1),
            competition_id=competition_id,
            season_id=season_id,
            kickoff_at=start + timedelta(days=index * 7),
            home_team_id=teams[home],
            away_team_id=teams[away],
            home_score=home_score,
            away_score=away_score,
        )
        for index, (home, away, home_score, away_score) in enumerate(schedule)
    )
    outcomes = tuple(
        EvaluationMatchOutcomeV1(
            match_id=match.match_id,
            kickoff_at=match.kickoff_at,
            home_score=match.home_score,
            away_score=match.away_score,
            home_corners=4 + index % 4,
            away_corners=3 + (index + 1) % 3,
            outcome_known_at=match.kickoff_at + timedelta(hours=2),
        )
        for index, match in enumerate(history)
    )
    cutoff = history[-1].kickoff_at + timedelta(days=7)
    policy = Sprint2ExecutionPolicyV1(
        elo_config=EloConfig(model_version="sprint2-elo-v1", time_decay_half_life_days=None),
        dixon_coles_config=DixonColesConfig(
            model_version="sprint2-dixon-coles-v1",
            time_decay_half_life_days=None,
            max_iterations=400,
        ),
        corner_config=CornerModelConfig(
            model_version="sprint2-corners-v1",
            time_decay_half_life_days=None,
            max_iterations=400,
        ),
    )
    modeler = Sprint2BatchModeler(policy)
    fitted = modeler.fit(history, outcomes, cutoff)
    forecasts = modeler.forecast_batch(
        fitted,
        (
            ForecastMatchContextV1(
                target_match_id,
                competition_id,
                season_id,
                cutoff,
                teams[0],
                teams[1],
            ),
        ),
    )
    scope = PointInTimeScopeV1(
        dataset_version_id=dataset_id,
        source_snapshot_id=snapshot_id,
        feature_set_version=policy.feature_set_version,
        football_cutoff=cutoff,
        knowledge_cutoff=published_at,
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256="3" * 64,
        target_set_sha256="4" * 64,
    )
    publisher = Sprint2BatchPublisher(
        artifact_publisher=ModelArtifactPublisher(connection, tmp_path),
        artifact_loader=PortableModelArtifactStore(tmp_path),
        forecast_publisher=BaselineForecastPublisher(connection, tmp_path),
        policy=policy,
        provenance=Sprint2ExecutionProvenanceV1(
            code_commit_sha="5" * 40,
            dependency_lock_sha256="6" * 64,
            published_at=published_at,
        ),
    )

    first = publisher.publish_batch(scope, fitted, forecasts)
    retry = publisher.publish_batch(scope, fitted, forecasts)

    assert retry == first
    with connection.cursor() as cursor:
        assert cursor.execute(
            "SELECT count(*) FROM football.model_artifacts WHERE id = ANY(%s)",
            (list(first.model_artifact_ids),),
        ).fetchone() == (4,)
        assert cursor.execute(
            "SELECT count(*) FROM football.baseline_forecasts WHERE match_id = %s",
            (target_match_id,),
        ).fetchone() == (4,)
        assert cursor.execute(
            """
            SELECT count(*) FROM football.forecast_artifacts AS relation
            JOIN football.baseline_forecasts AS forecast ON forecast.id = relation.forecast_id
            WHERE forecast.match_id = %s
            """,
            (target_match_id,),
        ).fetchone() == (4,)


def test_evaluation_and_model_promotion_are_governed_and_retry_safe(
    connection: Connection[Any], tmp_path: Path
) -> None:
    _provider_id, snapshot_id, _resource_id = _source_lineage(connection, uuid.uuid4().hex)
    now = datetime(2026, 8, 30, 13, 0, tzinfo=UTC)
    with connection.cursor() as cursor:
        dataset_id, artifact_id, evaluation_id, promotion_id = cursor.execute(
            "SELECT uuidv7(), uuidv7(), uuidv7(), uuidv7()"
        ).fetchone()
        cursor.execute(
            """
            INSERT INTO football.dataset_versions
                (id, source_snapshot_id, dataset_name, layer, identity_hash,
                 schema_version, schema_sha256, normalizer_version, manifest_path,
                 manifest_sha256, status, published_at)
            VALUES (%s, %s, 'events', 'normalized', %s, 'v1', %s,
                    'statsbomb-normalizer-v1', %s, %s, 'published', %s)
            """,
            (
                dataset_id,
                snapshot_id,
                dataset_id.hex * 2,
                "2" * 64,
                f"manifests/{dataset_id}.json",
                "3" * 64,
                now,
            ),
        )
    scope = PointInTimeScopeV1(
        dataset_version_id=dataset_id,
        source_snapshot_id=snapshot_id,
        feature_set_version="sprint2-features-v1",
        football_cutoff=now,
        knowledge_cutoff=now,
        knowledge_mode="bitemporal",
        quality_policy_sha256="4" * 64,
        target_set_sha256="5" * 64,
    )
    ModelArtifactPublisher(connection, tmp_path).publish(
        model_artifact_id=artifact_id,
        fit_spec=ModelFitSpecV1(
            model_family="DIXON_COLES_GOALS",
            algorithm_version="dixon-coles-v1",
            config_sha256="6" * 64,
            scope=scope,
            code_commit_sha="7" * 40,
            dependency_lock_sha256="8" * 64,
        ),
        state={"contract": "DixonColesModelStateV1", "home_advantage": 0.2},
        created_at=now,
    )
    probabilities = (
        MatchResultProbabilitiesV1(0.7, 0.2, 0.1),
        MatchResultProbabilitiesV1(0.2, 0.6, 0.2),
        MatchResultProbabilitiesV1(0.1, 0.2, 0.7),
    )
    outcomes = ("HOME", "DRAW", "AWAY")
    metrics = evaluate_match_results(
        tuple(
            EvaluatedMatchResultV1(
                kickoff_at=now + timedelta(days=index, hours=1),
                prediction_cutoff=now + timedelta(days=index),
                outcome_known_at=now + timedelta(days=index, hours=3),
                probabilities=probability,
                outcome=outcome,
            )
            for index, (probability, outcome) in enumerate(
                zip(probabilities, outcomes, strict=True)
            )
        )
    )
    report = Sprint2EvaluationReportV1(
        evaluation_run_id=evaluation_id,
        policy_version="sprint2-gate-v1",
        scope=scope,
        status="PASS",
        completed_at=now,
        raw_match_result_metrics=metrics,
    )
    report_publisher = EvaluationReportPublisher(connection, tmp_path)

    first_report = report_publisher.publish(report)
    retry_report = report_publisher.publish(report)
    event = ModelPromotionEventV1(
        promotion_event_id=promotion_id,
        model_artifact_id=artifact_id,
        evaluation_run_id=evaluation_id,
        role="match_result/baseline",
        designation="BASELINE_APPROVED",
        recorded_at=now,
    )
    promotion_registry = PostgresModelPromotionRegistry(connection)
    first_event = promotion_registry.record(event)
    retry_event = promotion_registry.record(event)

    assert first_report.status == "published"
    assert retry_report.status == "verified_existing"
    assert first_event.status == "published"
    assert retry_event.status == "verified_existing"
    retirement_store = PostgresArtifactRetirementStore(connection)
    first_retirement = retirement_store.retire_evaluation(
        evaluation_id,
        evidence_reference="tests/integration/test_canonical_storage.py",
        recorded_at=now,
        code_commit_sha="a" * 40,
    )
    retry_retirement = retirement_store.retire_evaluation(
        evaluation_id,
        evidence_reference="tests/integration/test_canonical_storage.py",
        recorded_at=now,
        code_commit_sha="a" * 40,
    )
    assert first_retirement.status == "inserted"
    assert retry_retirement.status == "verified_existing"
    with connection.cursor() as cursor:
        assert (
            cursor.execute(
                "SELECT count(*) FROM football.model_promotion_events WHERE id = %s",
                (promotion_id,),
            ).fetchone()[0]
            == 1
        )
        assert cursor.execute(
            "SELECT report_sha256 FROM football.sprint2_evaluation_runs WHERE id = %s",
            (evaluation_id,),
        ).fetchone() == (first_report.report_sha256,)
        assert cursor.execute(
            """
                SELECT count(*) FROM football.dependency_edges
                WHERE upstream_kind = 'DATASET' AND upstream_id = %s
                  AND relationship = 'EVALUATED_WITH'
                  AND downstream_kind = 'EVALUATION' AND downstream_id = %s
                """,
            (dataset_id, evaluation_id),
        ).fetchone() == (1,)
    with pytest.raises(GovernancePublicationError, match="calibration artifact"):
        promotion_registry.record(
            ModelPromotionEventV1(
                promotion_event_id=uuid.uuid4(),
                model_artifact_id=artifact_id,
                evaluation_run_id=evaluation_id,
                role="match_result/calibrator",
                designation="CALIBRATION_APPROVED",
                recorded_at=now + timedelta(seconds=1),
            )
        )


def test_validation_findings_reject_cross_dataset_and_snapshot_lineage(
    connection: Connection[Any],
) -> None:
    _first_provider, first_snapshot, first_resource = _source_lineage(connection, uuid.uuid4().hex)
    _second_provider, second_snapshot, second_resource = _source_lineage(
        connection, uuid.uuid4().hex
    )
    first_dataset = uuid.uuid4()
    second_dataset = uuid.uuid4()
    validation_run = uuid.uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with connection.cursor() as cursor:
        for dataset_id, snapshot_id, identity in (
            (first_dataset, first_snapshot, first_dataset.hex * 2),
            (second_dataset, second_snapshot, second_dataset.hex * 2),
        ):
            cursor.execute(
                """
                INSERT INTO football.dataset_versions
                    (id, source_snapshot_id, dataset_name, layer, identity_hash,
                     schema_version, schema_sha256, normalizer_version, manifest_path,
                     manifest_sha256, status, published_at)
                VALUES (%s, %s, 'events', 'normalized', %s, 'v1', %s,
                        'statsbomb-normalizer-v1', %s, %s, 'published', %s)
                """,
                (
                    dataset_id,
                    snapshot_id,
                    identity,
                    "3" * 64,
                    f"manifests/{dataset_id}.json",
                    "4" * 64,
                    now,
                ),
            )
        second_file = cursor.execute(
            """
            INSERT INTO football.dataset_files
                (dataset_version_id, relative_path, physical_sha256,
                 logical_sha256, row_count, size_bytes, schema_sha256)
            VALUES (%s, 'normalized/second.parquet', %s, %s, 1, 1, %s)
            RETURNING id
            """,
            (second_dataset, "5" * 64, "6" * 64, "3" * 64),
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO football.validation_runs
                (id, dataset_version_id, source_snapshot_id, identity_hash,
                 policy_version, policy_sha256, validator_version, status,
                 started_at, completed_at)
            VALUES (%s, %s, %s, %s, 'statsbomb-quality-policy-v1', %s,
                    'statsbomb-dataset-validator-v1', 'passed', %s, %s)
            """,
            (
                validation_run,
                first_dataset,
                first_snapshot,
                validation_run.hex * 2,
                "8" * 64,
                now,
                now,
            ),
        )

        with pytest.raises(ForeignKeyViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.validation_findings
                    (id, validation_run_id, dataset_version_id, source_snapshot_id,
                     dataset_file_id, source_resource_id, finding_key, rule_code,
                     severity, action, scope_type, message, evidence, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                        'SB_LINEUP_INCONSISTENCY', 'QUARANTINE', 'QUARANTINE_MATCH',
                        'match', 'cross-lineage test', '{}'::jsonb, %s)
                """,
                (
                    uuid.uuid4(),
                    validation_run,
                    first_dataset,
                    first_snapshot,
                    second_file,
                    first_resource,
                    uuid.uuid4().hex * 2,
                    now,
                ),
            )

        with pytest.raises(ForeignKeyViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.validation_findings
                    (id, validation_run_id, dataset_version_id, source_snapshot_id,
                     source_resource_id, finding_key, rule_code, severity, action,
                     scope_type, message, evidence, created_at)
                VALUES (%s, %s, %s, %s, %s, %s,
                        'SB_LINEUP_INCONSISTENCY', 'QUARANTINE', 'QUARANTINE_MATCH',
                        'match', 'cross-snapshot test', '{}'::jsonb, %s)
                """,
                (
                    uuid.uuid4(),
                    validation_run,
                    first_dataset,
                    first_snapshot,
                    second_resource,
                    uuid.uuid4().hex * 2,
                    now,
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
