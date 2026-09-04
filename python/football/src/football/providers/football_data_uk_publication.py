from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from football.ingestion.change_sets import CanonicalChangeSetV1
from football.ingestion.registration import RegisteredSource

_MATCH_RESOLUTION_POLICY = "FootballDataUkPhase1BMatchResolutionV1"
_P1_SOURCE_PATH = "mmz4281/1516/E0.csv"
TrustedPublicationStatusV1 = Literal["inserted", "verified_existing"]


class FootballDataUkTrustedPublicationError(ValueError):
    """Trusted P1 publication conflicts with reviewed source evidence."""


@dataclass(frozen=True, slots=True)
class FootballDataUkTrustedP1MatchV1:
    canonical_match_id: UUID
    provider_match_ref: str
    provider_match_date: date
    provider_local_kickoff_time: time | None
    canonical_home_team_id: UUID
    canonical_away_team_id: UUID
    full_time_home_goals: int
    full_time_away_goals: int
    resolution_decision_key: str

    def __post_init__(self) -> None:
        if not self.provider_match_ref or len(self.resolution_decision_key) != 64:
            raise FootballDataUkTrustedPublicationError(
                "provider match reference and resolution decision key are required"
            )
        if self.canonical_home_team_id == self.canonical_away_team_id:
            raise FootballDataUkTrustedPublicationError("trusted match teams must be distinct")
        if self.full_time_home_goals < 0 or self.full_time_away_goals < 0:
            raise FootballDataUkTrustedPublicationError("trusted match scores must be non-negative")


@dataclass(frozen=True, slots=True)
class RegisteredFootballDataUkTrustedPublicationV1:
    observation_ids: tuple[UUID, ...]
    change_set_id: UUID
    status: TrustedPublicationStatusV1


class FootballDataUkPostgresTrustedPublicationV1:
    """Publish reviewed Football-Data P1 score observations and one change set."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        sync_run_id: UUID,
        source: RegisteredSource,
        source_path: str,
        matches: tuple[FootballDataUkTrustedP1MatchV1, ...],
        change_set_id: str,
        published_at: datetime,
        quality_policy_version: str,
    ) -> RegisteredFootballDataUkTrustedPublicationV1:
        if not matches:
            raise FootballDataUkTrustedPublicationError("trusted publication requires matches")
        if published_at.tzinfo is None or not change_set_id or not quality_policy_version:
            raise FootballDataUkTrustedPublicationError(
                "publication time, change-set identity, and quality policy are required"
            )
        if source_path != _P1_SOURCE_PATH or source_path not in source.resource_ids:
            raise FootballDataUkTrustedPublicationError(
                "trusted publication is limited to the frozen P1 overlap resource"
            )
        _require_unique(matches)
        source_resource_id = source.resource_ids[source_path]
        raw_sha256, acquired_at = _verify_source(cursor, source, source_resource_id)
        observation_ids: list[UUID] = []
        inserted = False
        for match in matches:
            _verify_resolution(cursor, source.provider_id, match)
            observation_id, observation_inserted = _observation(
                cursor,
                source,
                source_resource_id,
                acquired_at,
                match,
            )
            observation_ids.append(observation_id)
            inserted = inserted or observation_inserted
        change_set = CanonicalChangeSetV1(
            change_set_id=change_set_id,
            created_at=published_at,
            sync_run_ids=(str(sync_run_id),),
            source_resources=((f"football_data_uk/{source_path}", raw_sha256),),
            affected_canonical_ids=tuple(str(match.canonical_match_id) for match in matches),
            added_observation_refs=tuple(f"match_observation:{value}" for value in observation_ids),
            superseding_observation_refs=(),
            affected_partitions=(),
            football_time_start=None,
            football_time_end=None,
            knowledge_time_start=acquired_at,
            knowledge_time_end=acquired_at,
            resolution_policy_version=_MATCH_RESOLUTION_POLICY,
            quality_policy_version=quality_policy_version,
        )
        persisted_change_set_id, change_set_inserted = _change_set(cursor, sync_run_id, change_set)
        status: TrustedPublicationStatusV1 = (
            "inserted" if inserted or change_set_inserted else "verified_existing"
        )
        return RegisteredFootballDataUkTrustedPublicationV1(
            observation_ids=tuple(observation_ids),
            change_set_id=persisted_change_set_id,
            status=status,
        )


def _require_unique(matches: tuple[FootballDataUkTrustedP1MatchV1, ...]) -> None:
    match_ids = tuple(match.canonical_match_id for match in matches)
    provider_refs = tuple(match.provider_match_ref for match in matches)
    if len(match_ids) != len(set(match_ids)) or len(provider_refs) != len(set(provider_refs)):
        raise FootballDataUkTrustedPublicationError("trusted matches must be unique")


def _verify_source(
    cursor: Cursor[Any], source: RegisteredSource, source_resource_id: UUID
) -> tuple[str, datetime]:
    row = cursor.execute(
        """
        SELECT provider.code, resource.sha256, resource.acquired_at, snapshot.source_kind
        FROM football.source_resources AS resource
        JOIN football.source_snapshots AS snapshot ON snapshot.id = resource.source_snapshot_id
        JOIN football.providers AS provider ON provider.id = snapshot.provider_id
        WHERE resource.id = %s AND resource.source_snapshot_id = %s
          AND snapshot.provider_id = %s
        """,
        (source_resource_id, source.snapshot_id, source.provider_id),
    ).fetchone()
    if row is None or row[0] != "football_data_uk" or row[3] != "REAL_PROVIDER":
        raise FootballDataUkTrustedPublicationError("trusted source is not Football-Data evidence")
    return str(row[1]), row[2]


def _verify_resolution(
    cursor: Cursor[Any], provider_id: UUID, match: FootballDataUkTrustedP1MatchV1
) -> None:
    row = cursor.execute(
        """
        SELECT status, selected_canonical_id, rule_version, provider_entity_id
        FROM football.resolution_decisions
        WHERE decision_key = %s AND provider_id = %s AND subject_type = 'match'
        """,
        (match.resolution_decision_key, provider_id),
    ).fetchone()
    expected = (
        "AUTO_ACCEPTED",
        match.canonical_match_id,
        _MATCH_RESOLUTION_POLICY,
        match.provider_match_ref,
    )
    if row != expected:
        raise FootballDataUkTrustedPublicationError(
            "trusted match lacks its reviewed Football-Data resolution decision"
        )


def _observation(
    cursor: Cursor[Any],
    source: RegisteredSource,
    source_resource_id: UUID,
    acquired_at: datetime,
    match: FootballDataUkTrustedP1MatchV1,
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
        source.snapshot_id,
        source_resource_id,
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
        (source.snapshot_id, match.provider_match_ref),
    ).fetchone()
    if row is None or row[1:] != values:
        raise FootballDataUkTrustedPublicationError(
            "trusted match observation conflicts with immutable publication evidence"
        )
    return UUID(str(row[0])), inserted


def _change_set(
    cursor: Cursor[Any], sync_run_id: UUID, change_set: CanonicalChangeSetV1
) -> tuple[UUID, bool]:
    values = (
        sync_run_id,
        change_set.sha256,
        "published",
        Jsonb(change_set.to_dict()),
        "REAL_PROVIDER",
        change_set.created_at,
    )
    inserted = (
        cursor.execute(
            """
        INSERT INTO football.canonical_change_sets
            (sync_run_id, change_key, status, changes, publication_scope, published_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (change_key) DO NOTHING
        """,
            values,
        ).rowcount
        == 1
    )
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
        raise FootballDataUkTrustedPublicationError(
            "trusted change set conflicts with immutable publication evidence"
        )
    return UUID(str(row[0])), inserted
