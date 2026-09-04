from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.ingestion.change_sets import CanonicalChangeSetV1

FixtureAttemptStatusV1 = Literal["quarantined", "succeeded"]
FixturePublicationStatusV1 = Literal["not_published", "published"]
FixtureOutcomeV1 = Literal["resolved", "still_quarantined"]


class FixturePersistenceError(ValueError):
    pass


FixtureRegistrationStatusV1 = Literal["inserted", "verified_existing"]


@dataclass(frozen=True, slots=True)
class RegisteredFixtureSourceV1:
    provider_id: UUID
    source_snapshot_id: UUID
    source_resource_id: UUID
    status: FixtureRegistrationStatusV1


@dataclass(frozen=True, slots=True)
class RegisteredFixtureProcessingAttemptV1:
    attempt_id: UUID
    attempt_key: str
    status: FixtureRegistrationStatusV1


@dataclass(frozen=True, slots=True)
class RegisteredFixtureQuarantineOutcomeV1:
    outcome_id: UUID
    outcome_key: str
    status: FixtureRegistrationStatusV1


@dataclass(frozen=True, slots=True)
class RegisteredFixtureChangeSetV1:
    change_set_id: UUID
    change_key: str
    status: FixtureRegistrationStatusV1


@dataclass(frozen=True, slots=True)
class F3FixtureTrustedMatchV1:
    canonical_match_id: UUID
    provider_match_ref: str
    provider_match_date: date
    provider_local_kickoff_time: time | None
    canonical_home_team_id: UUID
    canonical_away_team_id: UUID
    full_time_home_goals: int
    full_time_away_goals: int
    resolution_decision_id: UUID

    def __post_init__(self) -> None:
        if (
            not self.provider_match_ref
            or self.canonical_home_team_id == self.canonical_away_team_id
        ):
            raise FixturePersistenceError("fixture match identity and distinct teams are required")
        if self.full_time_home_goals < 0 or self.full_time_away_goals < 0:
            raise FixturePersistenceError("fixture match scores must be non-negative")


@dataclass(frozen=True, slots=True)
class RegisteredFixturePublicationV1:
    observation_id: UUID
    change_set_id: UUID
    status: FixtureRegistrationStatusV1


@dataclass(frozen=True, slots=True)
class FixtureProcessingRunV1:
    run_id: str
    source_snapshot_id: UUID
    raw_sha256: str
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        if not self.run_id or len(self.raw_sha256) != 64:
            raise FixturePersistenceError("fixture run identity and SHA-256 are required")
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise FixturePersistenceError("fixture run timestamps must be timezone-aware")
        if self.completed_at < self.started_at:
            raise FixturePersistenceError("fixture run completion precedes start")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "source_snapshot_id": str(self.source_snapshot_id),
            "raw_sha256": self.raw_sha256,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
        }


class PostgresFixtureProcessingRunStoreV1:
    """Register a distinct fixture processing run before each attempt."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        provider_id: UUID,
        run: FixtureProcessingRunV1,
    ) -> UUID:
        values = (
            provider_id,
            "FootballDataUkPhase1BF3FixtureProcessingV1",
            "succeeded",
            run.sha256,
            run.started_at,
            run.completed_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.provider_sync_runs
                (provider_id, policy_version, status, run_key, started_at, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, provider_id, policy_version, status, run_key, started_at, completed_at
            FROM football.provider_sync_runs
            WHERE run_key = %s
            """,
            (run.sha256,),
        ).fetchone()
        if row is None or row[1:] != values:
            raise FixturePersistenceError("fixture processing run conflicts with stored evidence")
        if inserted not in {0, 1}:
            raise FixturePersistenceError("fixture processing run has an invalid insert result")
        return UUID(str(row[0]))


class PostgresF3FixtureSourceRegistryV1:
    """Register immutable F3 fixture source rows without changing provider identity."""

    def register(self, cursor: Cursor[Any], source: F3FixtureSourceV1) -> RegisteredFixtureSourceV1:
        provider_id = _provider_id(cursor)
        snapshot_values = (
            provider_id,
            source.fixture_locator,
            source.raw_sha256,
            source.acquired_at,
            source.manifest_path,
            source.manifest_sha256,
            source.fixture_id,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, acquired_at, manifest_path,
                 manifest_sha256, status, source_kind, fixture_id)
            VALUES (%s, %s, %s, %s, %s, %s, 'acquired', 'CONTRACT_FIXTURE', %s)
            ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
            """,
            snapshot_values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, acquired_at, manifest_path, manifest_sha256, source_kind, fixture_id
            FROM football.source_snapshots
            WHERE provider_id = %s AND source_identity = %s AND source_revision = %s
            """,
            snapshot_values[:3],
        ).fetchone()
        expected_snapshot = snapshot_values[3:6] + ("CONTRACT_FIXTURE", source.fixture_id)
        if row is None or row[1:] != expected_snapshot:
            raise FixturePersistenceError("fixture source conflicts with stored source identity")
        snapshot_id = UUID(str(row[0]))
        cursor.execute(
            """
            INSERT INTO football.fixture_sources (source_snapshot_id, fixture_id)
            VALUES (%s, %s)
            ON CONFLICT (source_snapshot_id) DO NOTHING
            """,
            (snapshot_id, source.fixture_id),
        )
        registry_row = cursor.execute(
            """
            SELECT fixture_id FROM football.fixture_sources WHERE source_snapshot_id = %s
            """,
            (snapshot_id,),
        ).fetchone()
        if registry_row != (source.fixture_id,):
            raise FixturePersistenceError("fixture source registry conflicts with source identity")
        resource_values = (
            snapshot_id,
            source.resource_path,
            source.raw_sha256,
            source.raw_byte_size,
            source.media_type,
            source.acquired_at,
        )
        resource_inserted = cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, %s, %s, %s, %s, 'pending', 'pending', %s)
            ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
            """,
            resource_values,
        ).rowcount
        resource_row = cursor.execute(
            """
            SELECT id, sha256, size_bytes, media_type, acquired_at
            FROM football.source_resources
            WHERE source_snapshot_id = %s AND provider_path = %s
            """,
            resource_values[:2],
        ).fetchone()
        if resource_row is None or resource_row[1:] != resource_values[2:]:
            raise FixturePersistenceError("fixture resource conflicts with immutable bytes")
        return RegisteredFixtureSourceV1(
            provider_id=provider_id,
            source_snapshot_id=snapshot_id,
            source_resource_id=UUID(str(resource_row[0])),
            status="inserted" if inserted == 1 or resource_inserted == 1 else "verified_existing",
        )


class PostgresFixtureProcessingAttemptStoreV1:
    """Append fixture attempts; never overwrite a prior quarantine."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        source_snapshot_id: UUID,
        attempt: FixtureProcessingAttemptV1,
    ) -> RegisteredFixtureProcessingAttemptV1:
        values = (
            attempt.sha256,
            UUID(attempt.sync_run_id),
            source_snapshot_id,
            UUID(attempt.source_resource_id),
            attempt.raw_sha256,
            UUID(attempt.reprocess_request_id) if attempt.reprocess_request_id else None,
            UUID(attempt.resolution_decision_id) if attempt.resolution_decision_id else None,
            attempt.processing_status,
            attempt.failure_reason,
            attempt.publication_status,
            attempt.started_at,
            attempt.completed_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.fixture_processing_attempts
            (attempt_key, sync_run_id, source_snapshot_id, source_resource_id, raw_sha256,
             reprocess_request_id, resolution_decision_id, processing_status,
             failure_reason, publication_status, started_at, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (attempt_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """SELECT id, sync_run_id, source_snapshot_id, source_resource_id, raw_sha256,
                      reprocess_request_id, resolution_decision_id, processing_status,
                      failure_reason, publication_status, started_at, completed_at
               FROM football.fixture_processing_attempts WHERE attempt_key = %s""",
            (attempt.sha256,),
        ).fetchone()
        if row is None or row[1:] != values[1:]:
            raise FixturePersistenceError(
                "fixture processing attempt conflicts with stored evidence"
            )
        return RegisteredFixtureProcessingAttemptV1(
            attempt_id=UUID(str(row[0])),
            attempt_key=attempt.sha256,
            status="inserted" if inserted == 1 else "verified_existing",
        )


@dataclass(frozen=True, slots=True)
class F3FixtureSourceV1:
    fixture_id: str
    fixture_locator: str
    raw_sha256: str
    raw_byte_size: int
    resource_path: str
    media_type: str
    acquired_at: datetime
    manifest_path: str
    manifest_sha256: str
    fixture_contract_version: str = "football-data-uk-phase1b-f3-v1"

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.fixture_locator.startswith("fixture://"):
            raise FixturePersistenceError("fixture identity and fixture locator are required")
        if len(self.raw_sha256) != 64 or self.raw_byte_size <= 0:
            raise FixturePersistenceError("fixture bytes require a SHA-256 and positive size")
        if not self.resource_path or self.resource_path.startswith("/"):
            raise FixturePersistenceError("fixture resource path must be relative")
        if not self.media_type or not self.manifest_path or len(self.manifest_sha256) != 64:
            raise FixturePersistenceError("fixture manifest and media type are required")
        if self.acquired_at.tzinfo is None:
            raise FixturePersistenceError("fixture acquisition time must be timezone-aware")
        if not self.fixture_contract_version:
            raise FixturePersistenceError("fixture contract version is required")

    @classmethod
    def from_payload(
        cls,
        *,
        payload: bytes,
        acquired_at: datetime,
        manifest_path: str,
        manifest_payload: bytes,
    ) -> F3FixtureSourceV1:
        return cls(
            fixture_id="football_data_uk_phase1b_f3_ambiguous_identity_v1",
            fixture_locator="fixture://football_data_uk/phase1b/f3/ambiguous_identity_v1.csv",
            raw_sha256=sha256_bytes(payload),
            raw_byte_size=len(payload),
            resource_path="fixtures/football_data_uk/phase1b/f3/ambiguous_identity_v1.csv",
            media_type="text/csv",
            acquired_at=acquired_at,
            manifest_path=manifest_path,
            manifest_sha256=sha256_bytes(manifest_payload),
        )

    @property
    def provider_id(self) -> str:
        return "football_data_uk"

    @property
    def source_kind(self) -> str:
        return "CONTRACT_FIXTURE"

    @property
    def resource_identity(self) -> str:
        return f"{self.fixture_locator}/sha256/{self.raw_sha256}"

    @property
    def resource_type(self) -> Literal["historical_league_csv"]:
        return "historical_league_csv"

    @property
    def provider_competition_code(self) -> str:
        return "E0"

    @property
    def provider_season_code(self) -> str:
        return "1516"


@dataclass(frozen=True, slots=True)
class FixtureProcessingAttemptV1:
    sync_run_id: str
    source_resource_id: str
    raw_sha256: str
    reprocess_request_id: str | None
    resolution_decision_id: str | None
    processing_status: FixtureAttemptStatusV1
    failure_reason: str | None
    publication_status: FixturePublicationStatusV1
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        if len(self.raw_sha256) != 64 or not self.source_resource_id or not self.sync_run_id:
            raise FixturePersistenceError("attempt run, source, and SHA-256 are required")
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise FixturePersistenceError("attempt timestamps must be timezone-aware")
        if self.completed_at < self.started_at:
            raise FixturePersistenceError("attempt completion precedes start")
        if (self.processing_status == "quarantined") != (self.failure_reason is not None):
            raise FixturePersistenceError("quarantined attempts require exactly one failure reason")
        if (self.processing_status == "quarantined") != (
            self.publication_status == "not_published"
        ):
            raise FixturePersistenceError(
                "fixture attempt publication status conflicts with processing status"
            )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "sync_run_id": self.sync_run_id,
            "source_resource_id": self.source_resource_id,
            "raw_sha256": self.raw_sha256,
            "reprocess_request_id": self.reprocess_request_id,
            "resolution_decision_id": self.resolution_decision_id,
            "processing_status": self.processing_status,
            "failure_reason": self.failure_reason,
            "publication_status": self.publication_status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class FixtureQuarantineOutcomeV1:
    quarantine_record_id: UUID
    reprocess_request_id: UUID
    processing_attempt_id: UUID
    resolution_decision_id: UUID
    outcome: FixtureOutcomeV1
    recorded_at: datetime

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None:
            raise FixturePersistenceError("quarantine outcome time must be timezone-aware")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "quarantine_record_id": str(self.quarantine_record_id),
            "reprocess_request_id": str(self.reprocess_request_id),
            "processing_attempt_id": str(self.processing_attempt_id),
            "resolution_decision_id": str(self.resolution_decision_id),
            "outcome": self.outcome,
            "recorded_at": self.recorded_at.isoformat(),
        }


class PostgresFixtureQuarantineOutcomeStoreV1:
    """Append reviewed fixture outcomes; the source quarantine remains unchanged."""

    def register(
        self, cursor: Cursor[Any], outcome: FixtureQuarantineOutcomeV1
    ) -> RegisteredFixtureQuarantineOutcomeV1:
        values = (
            outcome.sha256,
            outcome.quarantine_record_id,
            outcome.reprocess_request_id,
            outcome.processing_attempt_id,
            outcome.resolution_decision_id,
            outcome.outcome,
            outcome.recorded_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.quarantine_resolution_outcomes
                (outcome_key, quarantine_record_id, reprocess_request_id,
                 processing_attempt_id, resolution_decision_id, outcome, recorded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (outcome_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, quarantine_record_id, reprocess_request_id, processing_attempt_id,
                   resolution_decision_id, outcome, recorded_at
            FROM football.quarantine_resolution_outcomes
            WHERE outcome_key = %s
            """,
            (outcome.sha256,),
        ).fetchone()
        if row is None or row[1:] != values[1:]:
            raise FixturePersistenceError("quarantine outcome conflicts with stored history")
        return RegisteredFixtureQuarantineOutcomeV1(
            outcome_id=UUID(str(row[0])),
            outcome_key=outcome.sha256,
            status="inserted" if inserted == 1 else "verified_existing",
        )


class PostgresFixtureChangeSetStoreV1:
    """Persist acceptance-only changes that cannot enter real provider publication."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        source_snapshot_id: UUID,
        change_set: CanonicalChangeSetV1,
    ) -> RegisteredFixtureChangeSetV1:
        if len(change_set.sync_run_ids) != 1:
            raise FixturePersistenceError("fixture change set requires exactly one sync run")
        snapshot = cursor.execute(
            """
            SELECT fixture_id FROM football.fixture_sources
            WHERE source_snapshot_id = %s
            """,
            (source_snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise FixturePersistenceError("fixture change set requires a registered fixture source")
        try:
            sync_run_id = UUID(change_set.sync_run_ids[0])
        except ValueError as error:
            raise FixturePersistenceError(
                "fixture change set sync run ID must be a UUID"
            ) from error
        values = (
            sync_run_id,
            change_set.sha256,
            "published",
            Jsonb(change_set.to_dict()),
            "CONTRACT_FIXTURE",
            change_set.created_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.canonical_change_sets
                (sync_run_id, change_key, status, changes, publication_scope, published_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (change_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, sync_run_id, change_key, status, changes, publication_scope, published_at
            FROM football.canonical_change_sets
            WHERE change_key = %s
            """,
            (change_set.sha256,),
        ).fetchone()
        expected = values[:3] + (change_set.to_dict(),) + values[4:]
        if row is None or row[1:] != expected:
            raise FixturePersistenceError("fixture change set conflicts with isolated publication")
        return RegisteredFixtureChangeSetV1(
            change_set_id=UUID(str(row[0])),
            change_key=change_set.sha256,
            status="inserted" if inserted == 1 else "verified_existing",
        )


class PostgresF3FixturePublisherV1:
    """Publish one reviewed F3 score only into the fixture change-set scope."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        source: RegisteredFixtureSourceV1,
        sync_run_id: UUID,
        match: F3FixtureTrustedMatchV1,
        change_set_id: str,
        published_at: datetime,
    ) -> RegisteredFixturePublicationV1:
        if not change_set_id or published_at.tzinfo is None:
            raise FixturePersistenceError("fixture publication identity and time are required")
        acquired_at = _fixture_source_time(cursor, source)
        _fixture_match_resolution(cursor, source.provider_id, match)
        observation_id, observation_inserted = _fixture_observation(
            cursor, source, acquired_at, match
        )
        change_set = CanonicalChangeSetV1(
            change_set_id=change_set_id,
            created_at=published_at,
            sync_run_ids=(str(sync_run_id),),
            source_resources=(
                (f"fixture:{source.source_resource_id}", _fixture_sha(cursor, source)),
            ),
            affected_canonical_ids=(str(match.canonical_match_id),),
            added_observation_refs=(f"match_observation:{observation_id}",),
            superseding_observation_refs=(),
            affected_partitions=(),
            football_time_start=None,
            football_time_end=None,
            knowledge_time_start=acquired_at,
            knowledge_time_end=acquired_at,
            resolution_policy_version="FootballDataUkPhase1BMatchResolutionV1",
            quality_policy_version="FootballDataUkPhase1BF3FixtureQualityV1",
        )
        change = PostgresFixtureChangeSetStoreV1().register(
            cursor, source_snapshot_id=source.source_snapshot_id, change_set=change_set
        )
        return RegisteredFixturePublicationV1(
            observation_id=observation_id,
            change_set_id=change.change_set_id,
            status="inserted"
            if observation_inserted or change.status == "inserted"
            else "verified_existing",
        )


def _fixture_source_time(cursor: Cursor[Any], source: RegisteredFixtureSourceV1) -> datetime:
    row = cursor.execute(
        """
        SELECT resource.acquired_at
        FROM football.source_resources AS resource
        JOIN football.fixture_sources AS fixture
            ON fixture.source_snapshot_id = resource.source_snapshot_id
        WHERE resource.id = %s AND resource.source_snapshot_id = %s
        """,
        (source.source_resource_id, source.source_snapshot_id),
    ).fetchone()
    if row is None or not isinstance(row[0], datetime):
        raise FixturePersistenceError("fixture publication source is not registered")
    return row[0]


def _fixture_sha(cursor: Cursor[Any], source: RegisteredFixtureSourceV1) -> str:
    row = cursor.execute(
        "SELECT sha256 FROM football.source_resources WHERE id = %s",
        (source.source_resource_id,),
    ).fetchone()
    if row is None:
        raise FixturePersistenceError("fixture publication resource is missing")
    return str(row[0])


def _fixture_match_resolution(
    cursor: Cursor[Any], provider_id: UUID, match: F3FixtureTrustedMatchV1
) -> None:
    row = cursor.execute(
        """
        SELECT status, selected_canonical_id, rule_version
        FROM football.resolution_decisions
        WHERE id = %s AND provider_id = %s AND subject_type = 'match'
        """,
        (match.resolution_decision_id, provider_id),
    ).fetchone()
    if row != (
        "AUTO_ACCEPTED",
        match.canonical_match_id,
        "FootballDataUkPhase1BMatchResolutionV1",
    ):
        raise FixturePersistenceError("fixture match lacks its reviewed resolution")


def _fixture_observation(
    cursor: Cursor[Any],
    source: RegisteredFixtureSourceV1,
    acquired_at: datetime,
    match: F3FixtureTrustedMatchV1,
) -> tuple[UUID, bool]:
    values = (
        match.canonical_match_id,
        source.provider_id,
        match.provider_match_ref,
        match.provider_match_date,
        match.provider_local_kickoff_time,
        match.canonical_home_team_id,
        match.canonical_away_team_id,
        match.full_time_home_goals,
        match.full_time_away_goals,
        "completed",
        "completed",
        acquired_at,
        source.source_snapshot_id,
        source.source_resource_id,
        acquired_at,
    )
    inserted = (
        cursor.execute(
            """
        INSERT INTO football.match_observations
            (match_id, provider_id, provider_match_id, match_date, kick_off_local,
             home_team_id, away_team_id, home_score, away_score, lifecycle,
             provider_status, known_from, source_snapshot_id, source_resource_id, acquired_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_snapshot_id, provider_match_id) DO NOTHING
        """,
            values,
        ).rowcount
        == 1
    )
    row = cursor.execute(
        """
        SELECT id, match_id, provider_id, provider_match_id, match_date, kick_off_local,
               home_team_id, away_team_id, home_score, away_score, lifecycle,
               provider_status, known_from, source_snapshot_id, source_resource_id, acquired_at
        FROM football.match_observations
        WHERE source_snapshot_id = %s AND provider_match_id = %s
        """,
        (source.source_snapshot_id, match.provider_match_ref),
    ).fetchone()
    if row is None or row[1:] != values:
        raise FixturePersistenceError("fixture observation conflicts with immutable publication")
    return UUID(str(row[0])), inserted


def _provider_id(cursor: Cursor[Any]) -> UUID:
    row = cursor.execute(
        "SELECT id FROM football.providers WHERE code = 'football_data_uk'"
    ).fetchone()
    if row is None:
        raise FixturePersistenceError("Football-Data provider must be registered first")
    return UUID(str(row[0]))
