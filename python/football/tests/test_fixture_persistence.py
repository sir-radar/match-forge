from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from football.ingestion.change_sets import CanonicalChangeSetV1
from football.ingestion.fixture_persistence import (
    F3FixtureSourceV1,
    FixturePersistenceError,
    FixtureProcessingAttemptV1,
    FixtureQuarantineOutcomeV1,
    PostgresF3FixtureSourceRegistryV1,
    PostgresFixtureChangeSetStoreV1,
    PostgresFixtureProcessingAttemptStoreV1,
    PostgresFixtureQuarantineOutcomeStoreV1,
)
from psycopg.types.json import Jsonb


def test_fixture_source_registry_is_idempotent_and_preserves_fixture_identity() -> None:
    cursor = _FixtureCursor()
    store = PostgresF3FixtureSourceRegistryV1()

    first = store.register(cast(Any, cursor), _source())
    retry = store.register(cast(Any, cursor), _source())

    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert cursor.snapshot is not None
    assert cursor.snapshot[-1] == _source().fixture_id
    assert cursor.resource is not None
    assert cursor.resource[2] == _source().raw_sha256


def test_fixture_source_registry_rejects_existing_real_source() -> None:
    with pytest.raises(FixturePersistenceError, match="source identity"):
        PostgresF3FixtureSourceRegistryV1().register(
            cast(Any, _FixtureCursor(conflicting_snapshot=True)), _source()
        )


def test_attempt_store_keeps_failed_and_reprocessed_attempts_append_only() -> None:
    cursor = _FixtureCursor()
    source = PostgresF3FixtureSourceRegistryV1().register(cast(Any, cursor), _source())
    store = PostgresFixtureProcessingAttemptStoreV1()
    failed = _attempt(source.source_resource_id, "quarantined", "IDENTITY_UNRESOLVED")
    completed = _attempt(source.source_resource_id, "succeeded", None)

    first = store.register(
        cast(Any, cursor), source_snapshot_id=source.source_snapshot_id, attempt=failed
    )
    retry = store.register(
        cast(Any, cursor), source_snapshot_id=source.source_snapshot_id, attempt=failed
    )
    second = store.register(
        cast(Any, cursor), source_snapshot_id=source.source_snapshot_id, attempt=completed
    )

    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert second.status == "inserted"
    assert len(cursor.attempts) == 2
    assert cursor.attempts[failed.sha256][6:8] == ("quarantined", "IDENTITY_UNRESOLVED")
    assert cursor.attempts[completed.sha256][6:9] == ("succeeded", None, "published")


def test_attempt_store_rejects_conflicting_retry() -> None:
    cursor = _FixtureCursor(conflicting_attempt=True)
    source = PostgresF3FixtureSourceRegistryV1().register(cast(Any, cursor), _source())
    with pytest.raises(FixturePersistenceError, match="conflicts"):
        PostgresFixtureProcessingAttemptStoreV1().register(
            cast(Any, cursor),
            source_snapshot_id=source.source_snapshot_id,
            attempt=_attempt(source.source_resource_id, "quarantined", "IDENTITY_UNRESOLVED"),
        )


def test_quarantine_outcome_store_is_append_only_and_idempotent() -> None:
    cursor = _FixtureCursor()
    outcome = FixtureQuarantineOutcomeV1(
        quarantine_record_id=_FixtureCursor.QUARANTINE_ID,
        reprocess_request_id=_FixtureCursor.REQUEST_ID,
        processing_attempt_id=_FixtureCursor.ATTEMPT_ID,
        resolution_decision_id=_FixtureCursor.DECISION_ID,
        outcome="resolved",
        recorded_at=_time() + timedelta(minutes=2),
    )
    store = PostgresFixtureQuarantineOutcomeStoreV1()

    first = store.register(cast(Any, cursor), outcome)
    retry = store.register(cast(Any, cursor), outcome)

    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert len(cursor.outcomes) == 1


def test_fixture_change_set_is_scoped_and_rejects_real_source() -> None:
    cursor = _FixtureCursor()
    source = PostgresF3FixtureSourceRegistryV1().register(cast(Any, cursor), _source())
    store = PostgresFixtureChangeSetStoreV1()

    first = store.register(
        cast(Any, cursor), source_snapshot_id=source.source_snapshot_id, change_set=_change_set()
    )
    retry = store.register(
        cast(Any, cursor), source_snapshot_id=source.source_snapshot_id, change_set=_change_set()
    )

    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert cursor.change_set is not None
    assert cursor.change_set[4] == "CONTRACT_FIXTURE"
    with pytest.raises(FixturePersistenceError, match="registered fixture"):
        store.register(
            cast(Any, _FixtureCursor(unregistered_fixture=True)),
            source_snapshot_id=source.source_snapshot_id,
            change_set=_change_set(),
        )


def test_fixture_contract_rejects_invalid_model_eligible_or_mutable_inputs() -> None:
    with pytest.raises(FixturePersistenceError, match="fixture identity"):
        F3FixtureSourceV1(
            fixture_id="",
            fixture_locator="https://example.test/f3.csv",
            raw_sha256="a" * 64,
            raw_byte_size=1,
            resource_path="f3.csv",
            media_type="text/csv",
            acquired_at=_time(),
            manifest_path="fixtures/f3.json",
            manifest_sha256="b" * 64,
        )
    with pytest.raises(FixturePersistenceError, match="publication status"):
        _attempt(_FixtureCursor.RESOURCE_ID, "succeeded", None, publication_status="not_published")
    with pytest.raises(FixturePersistenceError, match="publication status"):
        _attempt(
            _FixtureCursor.RESOURCE_ID,
            "quarantined",
            "IDENTITY_UNRESOLVED",
            publication_status="published",
        )


def _source() -> F3FixtureSourceV1:
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
    resource_id: UUID,
    status: str,
    reason: str | None,
    *,
    publication_status: str | None = None,
) -> FixtureProcessingAttemptV1:
    return FixtureProcessingAttemptV1(
        source_resource_id=str(resource_id),
        raw_sha256="a" * 64,
        reprocess_request_id=str(_FixtureCursor.REQUEST_ID),
        resolution_decision_id=str(_FixtureCursor.DECISION_ID),
        processing_status=cast(Any, status),
        failure_reason=reason,
        publication_status=cast(
            Any, publication_status or ("published" if status == "succeeded" else "not_published")
        ),
        started_at=_time(),
        completed_at=_time() + timedelta(minutes=1 if status == "quarantined" else 2),
    )


def _change_set() -> CanonicalChangeSetV1:
    return CanonicalChangeSetV1(
        change_set_id="football-data-uk-f3-acceptance-v1",
        created_at=_time() + timedelta(minutes=3),
        sync_run_ids=(str(_FixtureCursor.SYNC_RUN_ID),),
        source_resources=(("fixture://football-data-uk/f3.csv", "a" * 64),),
        affected_canonical_ids=(str(UUID("00000000-0000-0000-0000-000000000010")),),
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


class _FixtureCursor:
    PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000001")
    SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000002")
    RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000003")
    ATTEMPT_ID = UUID("00000000-0000-0000-0000-000000000004")
    QUARANTINE_ID = UUID("00000000-0000-0000-0000-000000000005")
    REQUEST_ID = UUID("00000000-0000-0000-0000-000000000006")
    DECISION_ID = UUID("00000000-0000-0000-0000-000000000007")
    SYNC_RUN_ID = UUID("00000000-0000-0000-0000-000000000008")
    CHANGE_SET_ID = UUID("00000000-0000-0000-0000-000000000009")
    OUTCOME_ID = UUID("00000000-0000-0000-0000-000000000011")

    def __init__(
        self,
        *,
        conflicting_snapshot: bool = False,
        conflicting_attempt: bool = False,
        unregistered_fixture: bool = False,
    ) -> None:
        self.conflicting_snapshot = conflicting_snapshot
        self.conflicting_attempt = conflicting_attempt
        self.unregistered_fixture = unregistered_fixture
        self.snapshot: tuple[object, ...] | None = None
        self.resource: tuple[object, ...] | None = None
        self.attempts: dict[str, tuple[object, ...]] = {}
        self.outcomes: dict[str, tuple[object, ...]] = {}
        self.change_set: tuple[object, ...] | None = None
        self.rowcount = 0
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...] = ()) -> _FixtureCursor:
        for marker, handler in self._handlers():
            if marker in query:
                handler(params)
                return self
        raise AssertionError(f"unexpected query: {query}")

    def _handlers(self) -> tuple[tuple[str, Any], ...]:
        return (
            ("SELECT id FROM football.providers", self._provider),
            ("INSERT INTO football.source_snapshots", self._insert_snapshot),
            ("SELECT id, acquired_at, manifest_path", self._snapshot_row),
            ("INSERT INTO football.fixture_sources", self._insert_fixture),
            ("SELECT fixture_id FROM football.fixture_sources", self._fixture_row),
            ("INSERT INTO football.source_resources", self._insert_resource),
            ("SELECT id, sha256, size_bytes", self._resource_row),
            ("INSERT INTO football.fixture_processing_attempts", self._insert_attempt),
            ("SELECT id, source_snapshot_id, source_resource_id", self._attempt_row),
            ("INSERT INTO football.quarantine_resolution_outcomes", self._insert_outcome),
            ("SELECT id, quarantine_record_id", self._outcome_row),
            ("INSERT INTO football.canonical_change_sets", self._insert_change_set),
            ("SELECT id, sync_run_id, change_key", self._change_set_row),
        )

    def _provider(self, _: tuple[object, ...]) -> None:
        self._row = (self.PROVIDER_ID,)

    def _insert_snapshot(self, params: tuple[object, ...]) -> None:
        self.snapshot, self.rowcount = (params, 1) if self.snapshot is None else (self.snapshot, 0)

    def _snapshot_row(self, _: tuple[object, ...]) -> None:
        assert self.snapshot is not None
        suffix: tuple[object, ...] = self.snapshot[3:6] + ("CONTRACT_FIXTURE", self.snapshot[6])
        if self.conflicting_snapshot:
            suffix = (*suffix[:-2], "REAL_PROVIDER", None)
        self._row = (self.SNAPSHOT_ID, *suffix)

    def _insert_fixture(self, _: tuple[object, ...]) -> None:
        self.rowcount = 1

    def _fixture_row(self, _: tuple[object, ...]) -> None:
        self._row = None if self.unregistered_fixture else (_source().fixture_id,)

    def _insert_resource(self, params: tuple[object, ...]) -> None:
        self.resource, self.rowcount = (params, 1) if self.resource is None else (self.resource, 0)

    def _resource_row(self, _: tuple[object, ...]) -> None:
        assert self.resource is not None
        self._row = (self.RESOURCE_ID, *self.resource[2:])

    def _insert_attempt(self, params: tuple[object, ...]) -> None:
        key = cast(str, params[0])
        self.rowcount = 0 if key in self.attempts else 1
        self.attempts.setdefault(key, params)

    def _attempt_row(self, params: tuple[object, ...]) -> None:
        values = self.attempts[cast(str, params[0])]
        if self.conflicting_attempt:
            values = (*values[:6], "succeeded", *values[7:])
        self._row = (self.ATTEMPT_ID, *values[1:])

    def _insert_outcome(self, params: tuple[object, ...]) -> None:
        key = cast(str, params[0])
        self.rowcount = 0 if key in self.outcomes else 1
        self.outcomes.setdefault(key, params)

    def _outcome_row(self, params: tuple[object, ...]) -> None:
        self._row = (self.OUTCOME_ID, *self.outcomes[cast(str, params[0])][1:])

    def _insert_change_set(self, params: tuple[object, ...]) -> None:
        self.change_set, self.rowcount = (
            (params, 1) if self.change_set is None else (self.change_set, 0)
        )

    def _change_set_row(self, _: tuple[object, ...]) -> None:
        assert self.change_set is not None
        values = self.change_set
        self._row = (
            self.CHANGE_SET_ID,
            values[0],
            values[1],
            values[2],
            cast(Jsonb, values[3]).obj,
            values[4],
            values[5],
        )

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row
