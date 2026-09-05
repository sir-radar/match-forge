from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.contracts import DependencyNodeV1
from football.ingestion.dependencies import (
    PostgresDependencyStoreV1,
    SourceCorrectionPropagatorV1,
)
from psycopg import Connection
from psycopg.errors import RaiseException
from psycopg.types.json import Jsonb

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


def test_trusted_source_correction_propagates_append_only_and_isolated(
    connection: Connection[Any],
) -> None:
    with connection.cursor() as cursor:
        source = _source(cursor)
        change_set_id = _change_set(cursor, source)
        store = PostgresDependencyStoreV1()
        dataset = _node("DATASET")
        model = _node("MODEL_ARTIFACT")
        forecast = _node("FORECAST")
        evaluation = _node("EVALUATION")
        unrelated_source = _node("SOURCE_RESOURCE")
        unrelated_dataset = _node("DATASET")
        store.register_dependency(
            cursor, upstream=source.node, relationship="INPUT_TO", downstream=dataset
        )
        store.register_dependency(
            cursor, upstream=dataset, relationship="FITTED_FROM", downstream=model
        )
        store.register_dependency(
            cursor, upstream=model, relationship="FORECAST_WITH", downstream=forecast
        )
        store.register_dependency(
            cursor, upstream=dataset, relationship="EVALUATED_WITH", downstream=evaluation
        )
        store.register_dependency(
            cursor,
            upstream=unrelated_source,
            relationship="INPUT_TO",
            downstream=unrelated_dataset,
        )

        first = SourceCorrectionPropagatorV1(store).propagate(cursor, change_set_id)
        retry = SourceCorrectionPropagatorV1(store).propagate(cursor, change_set_id)

        assert first.status == "propagated"
        assert {event.event.node for event in first.state_events} == {
            dataset,
            model,
            forecast,
            evaluation,
        }
        assert all(event.status == "inserted" for event in first.state_events)
        assert all(event.status == "verified_existing" for event in retry.state_events)
        assert store.effective_state(cursor, dataset) == "REBUILD_REQUIRED"
        assert store.effective_state(cursor, model) == "AFFECTED_BY_SOURCE_CORRECTION"
        assert store.effective_state(cursor, unrelated_dataset) == "VALID"
        event_count = cursor.execute(
            "SELECT count(*) FROM football.derived_state_events"
        ).fetchone()
        assert event_count == (4,)

        later_change_set_id = _change_set(cursor, source, marker="later")
        later = SourceCorrectionPropagatorV1(store).propagate(cursor, later_change_set_id)

        assert all(event.status == "inserted" for event in later.state_events)
        event_count = cursor.execute(
            "SELECT count(*) FROM football.derived_state_events"
        ).fetchone()
        assert event_count == (8,)


def test_fixture_scoped_change_set_cannot_create_derived_state_events(
    connection: Connection[Any],
) -> None:
    with connection.cursor() as cursor:
        source = _source(cursor)
        fixture_change_set_id = _change_set(cursor, source, publication_scope="CONTRACT_FIXTURE")

        with pytest.raises(RaiseException, match="trusted real-provider"), connection.transaction():
            PostgresDependencyStoreV1().record_derived_state(
                cursor,
                node=_node("DATASET"),
                state="REBUILD_REQUIRED",
                reason="fixture state must be rejected",
                cause_change_set_id=fixture_change_set_id,
                recorded_at=source.published_at,
            )

        result = SourceCorrectionPropagatorV1().propagate(cursor, fixture_change_set_id)

        assert result.status == "not_real_provider"
        assert result.state_events == ()
        event_count = cursor.execute(
            "SELECT count(*) FROM football.derived_state_events"
        ).fetchone()
        assert event_count == (0,)


def test_state_events_are_append_only_and_supersession_needs_replacement(
    connection: Connection[Any],
) -> None:
    with connection.cursor() as cursor:
        source = _source(cursor)
        change_set_id = _change_set(cursor, source)
        store = PostgresDependencyStoreV1()
        old_dataset = _node("DATASET")
        new_dataset = _node("DATASET")

        with pytest.raises(RaiseException, match="replacement edge"), connection.transaction():
            store.record_derived_state(
                cursor,
                node=old_dataset,
                state="SUPERSEDED",
                reason="replacement is absent",
                cause_change_set_id=change_set_id,
                recorded_at=source.published_at,
            )
        store.register_dependency(
            cursor,
            upstream=old_dataset,
            relationship="DERIVED_FROM",
            downstream=new_dataset,
        )
        event = store.record_derived_state(
            cursor,
            node=old_dataset,
            state="SUPERSEDED",
            reason="replacement is registered",
            cause_change_set_id=change_set_id,
            recorded_at=source.published_at,
        )

        assert event.status == "inserted"
        with pytest.raises(RaiseException, match="append-only"):
            cursor.execute("UPDATE football.derived_state_events SET reason = 'changed'")


class _Source:
    def __init__(
        self,
        *,
        node: DependencyNodeV1,
        sync_run_id: UUID,
        resource_ref: str,
        checksum: str,
        published_at: datetime,
    ) -> None:
        self.node = node
        self.sync_run_id = sync_run_id
        self.resource_ref = resource_ref
        self.checksum = checksum
        self.published_at = published_at


def _source(cursor: Any) -> _Source:
    marker = uuid4().hex
    published_at = datetime(2026, 9, 5, 12, tzinfo=UTC)
    provider_id = cursor.execute(
        """
        INSERT INTO football.providers (code, name, source_type)
        VALUES (%s, %s, 'file_download')
        RETURNING id
        """,
        (f"dependency_{marker}", f"Dependency {marker}"),
    ).fetchone()[0]
    snapshot_id = cursor.execute(
        """
        INSERT INTO football.source_snapshots
            (provider_id, source_identity, source_revision, acquired_at, manifest_path,
             manifest_sha256, status)
        VALUES (%s, %s, 'v1', %s, %s, %s, 'acquired')
        RETURNING id
        """,
        (
            provider_id,
            f"dependency/{marker}",
            published_at,
            f"manifests/{marker}.json",
            "a" * 64,
        ),
    ).fetchone()[0]
    path = f"data/{marker}.json"
    checksum = "b" * 64
    resource_id = cursor.execute(
        """
        INSERT INTO football.source_resources
            (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
             parse_status, validation_status, acquired_at)
        VALUES (%s, %s, %s, 2, 'application/json', 'parsed', 'valid', %s)
        RETURNING id
        """,
        (snapshot_id, path, checksum, published_at),
    ).fetchone()[0]
    sync_run_id = cursor.execute(
        """
        INSERT INTO football.provider_sync_runs
            (provider_id, policy_version, status, run_key, started_at, completed_at)
        VALUES (%s, 'dependency-v1', 'succeeded', %s, %s, %s)
        RETURNING id
        """,
        (provider_id, "c" * 32 + marker[:32], published_at, published_at),
    ).fetchone()[0]
    job_id = cursor.execute(
        """
        INSERT INTO football.acquisition_jobs
            (sync_run_id, provider_id, resource_key, scope_key, resource_identity,
             resource_revision, status)
        VALUES (%s, %s, %s, 'global', %s, 'v1', 'validated')
        RETURNING id
        """,
        (sync_run_id, provider_id, path, f"dependency/{marker}"),
    ).fetchone()[0]
    cursor.execute(
        """
        INSERT INTO football.acquired_resources
            (acquisition_job_id, source_snapshot_id, source_resource_id, raw_path, raw_sha256,
             size_bytes, status, acquired_at)
        VALUES (%s, %s, %s, %s, %s, 2, 'validated', %s)
        """,
        (job_id, snapshot_id, resource_id, f"raw/{marker}.json", checksum, published_at),
    )
    return _Source(
        node=DependencyNodeV1("SOURCE_RESOURCE", UUID(str(resource_id))),
        sync_run_id=UUID(str(sync_run_id)),
        resource_ref=f"dependency_{marker}/{path}",
        checksum=checksum,
        published_at=published_at,
    )


def _change_set(
    cursor: Any,
    source: _Source,
    *,
    marker: str = "first",
    publication_scope: str = "REAL_PROVIDER",
) -> UUID:
    change_key = (marker.encode().hex() + "d" * 64)[:64]
    return UUID(
        str(
            cursor.execute(
                """
                INSERT INTO football.canonical_change_sets
                    (sync_run_id, change_key, status, changes, publication_scope, published_at)
                VALUES (%s, %s, 'published', %s, %s, %s)
                RETURNING id
                """,
                (
                    source.sync_run_id,
                    change_key,
                    Jsonb(
                        {
                            "source_resources": [
                                {
                                    "resource_ref": source.resource_ref,
                                    "sha256": source.checksum,
                                }
                            ],
                            "added_observation_refs": [],
                            "superseding_observation_refs": [],
                        }
                    ),
                    publication_scope,
                    source.published_at,
                ),
            ).fetchone()[0]
        )
    )


def _node(kind: str) -> DependencyNodeV1:
    return DependencyNodeV1(kind=kind, object_id=uuid4())  # type: ignore[arg-type]
