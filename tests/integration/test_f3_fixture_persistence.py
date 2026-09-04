from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from football.ingestion.change_sets import CanonicalChangeSetV1
from football.ingestion.fixture_persistence import (
    F3FixtureSourceV1,
    FixtureProcessingAttemptV1,
    FixtureQuarantineOutcomeV1,
    PostgresF3FixtureSourceRegistryV1,
    PostgresFixtureChangeSetStoreV1,
    PostgresFixtureProcessingAttemptStoreV1,
    PostgresFixtureQuarantineOutcomeStoreV1,
)
from psycopg import Connection
from psycopg.errors import CheckViolation, RaiseException

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


def test_fixture_persistence_is_isolated_append_only_and_not_model_eligible(
    connection: Connection[Any],
) -> None:
    with connection.cursor() as cursor:
        provider_id = cursor.execute(
            """
            INSERT INTO football.providers (code, name, source_type)
            VALUES ('football_data_uk', 'Football-Data', 'file_download')
            RETURNING id
            """
        ).fetchone()[0]
        real_snapshot_id = _real_source(cursor, provider_id)
        fixture = PostgresF3FixtureSourceRegistryV1().register(cursor, _fixture_source())
        retried_fixture = PostgresF3FixtureSourceRegistryV1().register(cursor, _fixture_source())
        assert fixture.status == "inserted"
        assert retried_fixture.status == "verified_existing"
        assert fixture.source_resource_id == retried_fixture.source_resource_id

        real_count, fixture_count = cursor.execute(
            """
            SELECT
                count(*) FILTER (WHERE source_kind = 'REAL_PROVIDER'),
                count(*) FILTER (WHERE source_kind = 'CONTRACT_FIXTURE')
            FROM football.source_snapshots
            WHERE provider_id = %s
            """,
            (provider_id,),
        ).fetchone()
        assert (real_count, fixture_count) == (1, 1)
        with (
            pytest.raises(RaiseException, match="matching contract fixture snapshot"),
            connection.transaction(),
        ):
            cursor.execute(
                """
                INSERT INTO football.fixture_sources (source_snapshot_id, fixture_id)
                VALUES (%s, 'misclassified-real-source')
                """,
                (real_snapshot_id,),
            )

        sync_run_id, quarantine_id, request_id, decision_id = _fixture_history(
            cursor, provider_id, fixture.source_snapshot_id, fixture.source_resource_id
        )
        attempt_store = PostgresFixtureProcessingAttemptStoreV1()
        failed = attempt_store.register(
            cursor,
            source_snapshot_id=fixture.source_snapshot_id,
            attempt=_attempt(fixture.source_resource_id, request_id, decision_id, "quarantined"),
        )
        succeeded = attempt_store.register(
            cursor,
            source_snapshot_id=fixture.source_snapshot_id,
            attempt=_attempt(fixture.source_resource_id, request_id, decision_id, "succeeded"),
        )
        assert failed.status == "inserted"
        assert succeeded.status == "inserted"
        assert failed.attempt_id != succeeded.attempt_id
        assert cursor.execute(
            """
            SELECT processing_status, failure_reason, raw_sha256
            FROM football.fixture_processing_attempts
            WHERE source_resource_id = %s
            ORDER BY completed_at
            """,
            (fixture.source_resource_id,),
        ).fetchall() == [
            ("quarantined", "IDENTITY_UNRESOLVED", "a" * 64),
            ("succeeded", None, "a" * 64),
        ]
        with pytest.raises(CheckViolation), connection.transaction():
            cursor.execute(
                """
                INSERT INTO football.fixture_processing_attempts
                    (attempt_key, source_snapshot_id, source_resource_id, raw_sha256,
                     reprocess_request_id, resolution_decision_id, processing_status,
                     failure_reason, publication_status, started_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'quarantined', 'IDENTITY_UNRESOLVED',
                        'published', %s, %s)
                """,
                (
                    "5" * 64,
                    fixture.source_snapshot_id,
                    fixture.source_resource_id,
                    "a" * 64,
                    request_id,
                    decision_id,
                    _time(),
                    _time(),
                ),
            )

        with (
            pytest.raises(RaiseException, match="SHA must match its registered source resource"),
            connection.transaction(),
        ):
            cursor.execute(
                """
                INSERT INTO football.fixture_processing_attempts
                    (attempt_key, source_snapshot_id, source_resource_id, raw_sha256,
                     reprocess_request_id, resolution_decision_id, processing_status,
                     failure_reason, publication_status, started_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'quarantined', 'IDENTITY_UNRESOLVED',
                        'not_published', %s, %s)
                """,
                (
                    "6" * 64,
                    fixture.source_snapshot_id,
                    fixture.source_resource_id,
                    "b" * 64,
                    request_id,
                    decision_id,
                    _time(),
                    _time(),
                ),
            )

        outcome = PostgresFixtureQuarantineOutcomeStoreV1().register(
            cursor,
            FixtureQuarantineOutcomeV1(
                quarantine_record_id=quarantine_id,
                reprocess_request_id=request_id,
                processing_attempt_id=succeeded.attempt_id,
                resolution_decision_id=decision_id,
                outcome="resolved",
                recorded_at=_time() + timedelta(minutes=3),
            ),
        )
        assert outcome.status == "inserted"
        assert cursor.execute(
            "SELECT status, reason_code FROM football.quarantine_records WHERE id = %s",
            (quarantine_id,),
        ).fetchone() == ("open", "IDENTITY_UNRESOLVED")
        with (
            pytest.raises(RaiseException, match="must retain one quarantine reprocess chain"),
            connection.transaction(),
        ):
            cursor.execute(
                """
                INSERT INTO football.quarantine_resolution_outcomes
                    (outcome_key, quarantine_record_id, reprocess_request_id,
                     processing_attempt_id, resolution_decision_id, outcome, recorded_at)
                VALUES (%s, %s, %s, %s, %s, 'resolved', %s)
                """,
                (
                    "7" * 64,
                    quarantine_id,
                    request_id,
                    succeeded.attempt_id,
                    uuid4(),
                    _time(),
                ),
            )

        change = PostgresFixtureChangeSetStoreV1().register(
            cursor,
            source_snapshot_id=fixture.source_snapshot_id,
            change_set=_change_set(sync_run_id),
        )
        assert change.status == "inserted"
        assert cursor.execute(
            "SELECT publication_scope FROM football.canonical_change_sets WHERE id = %s",
            (change.change_set_id,),
        ).fetchone() == ("CONTRACT_FIXTURE",)

        with (
            pytest.raises(RaiseException, match="cannot create analytical datasets"),
            connection.transaction(),
        ):
            cursor.execute(
                """
                INSERT INTO football.dataset_versions
                    (id, source_snapshot_id, dataset_name, layer, identity_hash,
                     schema_version, schema_sha256, normalizer_version, manifest_path,
                     manifest_sha256, status, published_at)
                VALUES (%s, %s, 'fixture_data', 'normalized', %s, 'v1', %s, 'v1',
                        'fixtures/f3/dataset.json', %s, 'published', %s)
                """,
                (
                    uuid4(),
                    fixture.source_snapshot_id,
                    "d" * 64,
                    "e" * 64,
                    "f" * 64,
                    _time(),
                ),
            )


def _real_source(cursor: Any, provider_id: UUID) -> UUID:
    return cursor.execute(
        """
        INSERT INTO football.source_snapshots
            (provider_id, source_identity, source_revision, acquired_at, manifest_path,
             manifest_sha256, status)
        VALUES (%s, 'https://www.football-data.co.uk/mmz4281/1516/E0.csv', %s, %s,
                'manifests/p1.json', %s, 'acquired')
        RETURNING id
        """,
        (provider_id, "b" * 64, _time(), "c" * 64),
    ).fetchone()[0]


def _fixture_history(
    cursor: Any, provider_id: UUID, snapshot_id: UUID, resource_id: UUID
) -> tuple[UUID, UUID, UUID, UUID]:
    sync_run_id = cursor.execute(
        """
        INSERT INTO football.provider_sync_runs
            (provider_id, policy_version, status, run_key, started_at, completed_at)
        VALUES (%s, 'F3FixturePersistenceV1', 'succeeded', %s, %s, %s)
        RETURNING id
        """,
        (provider_id, "1" * 64, _time(), _time()),
    ).fetchone()[0]
    job_id = cursor.execute(
        """
        INSERT INTO football.acquisition_jobs
            (sync_run_id, provider_id, resource_key, scope_key, resource_identity,
             resource_revision, status)
        VALUES (%s, %s, 'f3', 'phase1b', 'fixture-f3', %s, 'quarantined')
        RETURNING id
        """,
        (sync_run_id, provider_id, "a" * 64),
    ).fetchone()[0]
    cursor.execute(
        """
        INSERT INTO football.acquired_resources
            (acquisition_job_id, source_snapshot_id, source_resource_id, raw_path,
             raw_sha256, size_bytes, status, acquired_at)
        VALUES (%s, %s, %s, 'fixtures/f3.csv', %s, 41, 'quarantined', %s)
        """,
        (job_id, snapshot_id, resource_id, "a" * 64, _time()),
    )
    quarantine_id = cursor.execute(
        """
        INSERT INTO football.quarantine_records
            (acquisition_job_id, source_resource_id, finding_key, reason_code, details, status)
        VALUES (%s, %s, %s, 'IDENTITY_UNRESOLVED', '{}'::jsonb, 'open')
        RETURNING id
        """,
        (job_id, resource_id, "2" * 64),
    ).fetchone()[0]
    request_id = cursor.execute(
        """
        INSERT INTO football.quarantine_reprocess_requests
            (request_key, source_quarantine_record_id, trigger, trigger_ref,
             policy_version, scheduled_at)
        VALUES (%s, %s, 'MAPPING_REVIEWED', 'f3-review', 'F3FixturePersistenceV1', %s)
        RETURNING id
        """,
        ("3" * 64, quarantine_id, _time()),
    ).fetchone()[0]
    decision_id = cursor.execute(
        """
        INSERT INTO football.resolution_decisions
            (decision_key, subject_type, provider_id, provider_entity_id, evidence_refs,
             candidate_canonical_ids, rule_version, confidence, status, selected_canonical_id,
             actor, reason, created_at)
        VALUES (%s, 'team', %s, 'fixture-f3-team', '[]'::jsonb, '[]'::jsonb,
                'F3FixturePersistenceV1', 1, 'MANUALLY_APPROVED', %s,
                'test', 'reviewed fixture mapping', %s)
        RETURNING id
        """,
        ("4" * 64, provider_id, uuid4(), _time()),
    ).fetchone()[0]
    return sync_run_id, quarantine_id, request_id, decision_id


def _fixture_source() -> F3FixtureSourceV1:
    return F3FixtureSourceV1(
        fixture_id="football_data_uk_phase1b_f3_ambiguous_identity_v1",
        fixture_locator="fixture://football_data_uk/phase1b/f3/ambiguous_identity_v1.csv",
        raw_sha256="a" * 64,
        raw_byte_size=41,
        resource_path="fixtures/football_data_uk/phase1b/f3/ambiguous_identity_v1.csv",
        media_type="text/csv",
        acquired_at=_time(),
        manifest_path="fixtures/football_data_uk/phase1b/f3/manifest-v1.json",
        manifest_sha256="b" * 64,
    )


def _attempt(
    resource_id: UUID, request_id: UUID, decision_id: UUID, status: str
) -> FixtureProcessingAttemptV1:
    attempt_status = cast(Literal["quarantined", "succeeded"], status)
    publication_status = cast(
        Literal["not_published", "published"],
        "not_published" if status == "quarantined" else "published",
    )
    return FixtureProcessingAttemptV1(
        source_resource_id=str(resource_id),
        raw_sha256="a" * 64,
        reprocess_request_id=str(request_id),
        resolution_decision_id=str(decision_id),
        processing_status=attempt_status,
        failure_reason="IDENTITY_UNRESOLVED" if status == "quarantined" else None,
        publication_status=publication_status,
        started_at=_time(),
        completed_at=_time() + timedelta(minutes=1 if status == "quarantined" else 2),
    )


def _change_set(sync_run_id: UUID) -> CanonicalChangeSetV1:
    return CanonicalChangeSetV1(
        change_set_id="football-data-uk-f3-acceptance-v1",
        created_at=_time() + timedelta(minutes=3),
        sync_run_ids=(str(sync_run_id),),
        source_resources=(("fixture://football-data-uk/f3.csv", "a" * 64),),
        affected_canonical_ids=(str(uuid4()),),
        added_observation_refs=("match_observation:fixture-f3",),
        superseding_observation_refs=(),
        affected_partitions=(),
        football_time_start=None,
        football_time_end=None,
        knowledge_time_start=_time(),
        knowledge_time_end=_time(),
        resolution_policy_version="FootballDataUkPhase1BMatchResolutionV1",
        quality_policy_version="F3AcceptanceQualityV1",
    )


def _time() -> datetime:
    return datetime(2026, 9, 5, 12, tzinfo=UTC)
