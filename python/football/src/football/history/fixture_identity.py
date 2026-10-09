"""Resolve canonical fixture rows into physically possible real-match history.

Raw canonical rows and provider mappings remain immutable. This module supplies the
single resolution path used by audits, qualification, snapshots, Elo, and references.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import Connection
from psycopg.rows import dict_row

RESOLUTION_VERSION = "RealFixtureIdentityV1"
ADMITTED_STATUSES = frozenset(("UNIQUE", "DUPLICATE_RESOLVED"))


class ResolutionStatus(StrEnum):
    UNIQUE = "UNIQUE"
    DUPLICATE_RESOLVED = "DUPLICATE_RESOLVED"
    AMBIGUOUS_QUARANTINED = "AMBIGUOUS_QUARANTINED"
    IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED = "IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED"


@dataclass(frozen=True, slots=True)
class ProviderFixtureEvidence:
    provider_code: str
    provider_match_id: str
    source_snapshot_id: UUID
    source_identity: str | None
    source_revision: str | None
    provider_path: str | None
    resource_sha256: str | None
    provider_competition_id: str | None


@dataclass(frozen=True, slots=True)
class CanonicalHistoryRow:
    fixture_id: UUID
    kickoff_at: datetime
    competition_id: UUID
    competition_name: str
    country: str
    division: int | None
    season_label: str
    home_team_id: UUID
    away_team_id: UUID
    home_team_name: str
    away_team_name: str
    home_goals: int
    away_goals: int
    home_xg: float | None
    away_xg: float | None
    source_provider_code: str
    source_snapshot_id: UUID
    source_kickoff_precision: str
    provider_evidence: tuple[ProviderFixtureEvidence, ...]

    def __post_init__(self) -> None:
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise ValueError("kickoff_at must include a timezone")
        if self.home_team_id == self.away_team_id:
            raise ValueError("canonical history teams must differ")


@dataclass(frozen=True, slots=True)
class RealFixtureIdentityV1:
    canonical_real_fixture_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    canonical_competition_id: UUID | None
    member_fixture_ids: tuple[UUID, ...]
    representative_fixture_id: UUID
    provider_evidence: tuple[ProviderFixtureEvidence, ...]
    resolution_status: ResolutionStatus
    resolution_reason: str
    version: str = RESOLUTION_VERSION

    @property
    def admitted(self) -> bool:
        return self.resolution_status.value in ADMITTED_STATUSES

    @property
    def evidence_sha256(self) -> str:
        return semantic_sha256(
            {
                "provider_evidence": [evidence_payload(item) for item in self.provider_evidence],
                "resolution_reason": self.resolution_reason,
                "selected_competition_id": str(self.canonical_competition_id)
                if self.canonical_competition_id
                else None,
            }
        )


@dataclass(frozen=True, slots=True)
class ResolvedHistoricalMatchV1:
    real_fixture_id: UUID
    representative_fixture_id: UUID
    kickoff_at: datetime
    competition_id: UUID
    competition_name: str
    country: str
    division: int | None
    season_label: str
    home_team_id: UUID
    away_team_id: UUID
    home_team_name: str
    away_team_name: str
    home_goals: int
    away_goals: int
    home_xg: float | None
    away_xg: float | None
    source_provider_codes: tuple[str, ...]
    source_snapshot_ids: tuple[UUID, ...]
    member_fixture_ids: tuple[UUID, ...]
    identity_status: ResolutionStatus
    source_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class CanonicalHistoryAudit:
    raw_rows: tuple[CanonicalHistoryRow, ...]
    identities: tuple[RealFixtureIdentityV1, ...]
    resolved_history: tuple[ResolvedHistoricalMatchV1, ...]
    counts: Mapping[str, int]
    by_provider: Mapping[str, Mapping[str, int]]
    by_competition: Mapping[str, Mapping[str, int]]
    by_season: Mapping[str, Mapping[str, int]]

    @property
    def unresolved_failures(self) -> int:
        return physical_timeline_conflicts(self.resolved_history)

    @property
    def manifest(self) -> list[dict[str, object]]:
        return [
            {
                "real_fixture_id": str(item.canonical_real_fixture_id),
                "member_fixture_ids": [str(value) for value in item.member_fixture_ids],
                "representative_fixture_id": str(item.representative_fixture_id),
                "competition_id": str(item.canonical_competition_id)
                if item.canonical_competition_id
                else None,
                "kickoff_at": item.kickoff_at.astimezone(UTC).isoformat(),
                "home_team_id": str(item.home_team_id),
                "away_team_id": str(item.away_team_id),
                "resolution_status": item.resolution_status.value,
                "resolution_reason": item.resolution_reason,
                "source_evidence_sha256": item.evidence_sha256,
                "version": item.version,
            }
            for item in self.identities
        ]


def load_persisted_resolved_history(
    connection: Connection[Any],
    *,
    exclude_real_fixture_ids: Sequence[UUID] = (),
    team_ids: Sequence[UUID] = (),
    competition_ids: Sequence[UUID] = (),
    maximum_kickoff: datetime | None = None,
) -> tuple[ResolvedHistoricalMatchV1, ...]:
    """Load admitted outcomes, excluding protected real fixtures in SQL."""
    rows = connection.execute(
        """
        SELECT resolution.canonical_real_fixture_id,
               resolution.representative_fixture_id,
               history.kickoff_at, resolution.selected_competition_id AS competition_id,
               competition.name AS competition_name, competition.country,
               competition.division, competition.season_label,
               history.home_team_id, history.away_team_id,
               home.name AS home_team_name, away.name AS away_team_name,
               history.home_goals, history.away_goals, history.home_xg, history.away_xg,
               ARRAY(
                   SELECT member.member_fixture_id
                     FROM football.fixture_identity_resolutions member
                    WHERE member.canonical_real_fixture_id =
                          resolution.canonical_real_fixture_id
                      AND member.resolution_version = resolution.resolution_version
                      AND member.active
                    ORDER BY member.member_fixture_id
               ) AS members,
               ARRAY(
                   SELECT DISTINCT member_history.source_provider_code
                     FROM football.fixture_identity_resolutions member
                     JOIN football.product_team_match_history member_history
                       ON member_history.fixture_id = member.member_fixture_id
                    WHERE member.canonical_real_fixture_id =
                          resolution.canonical_real_fixture_id
                      AND member.resolution_version = resolution.resolution_version
                      AND member.active
                    ORDER BY member_history.source_provider_code
               ) AS providers,
               ARRAY(
                   SELECT DISTINCT member_history.source_snapshot_id
                     FROM football.fixture_identity_resolutions member
                     JOIN football.product_team_match_history member_history
                       ON member_history.fixture_id = member.member_fixture_id
                    WHERE member.canonical_real_fixture_id =
                          resolution.canonical_real_fixture_id
                      AND member.resolution_version = resolution.resolution_version
                      AND member.active
                    ORDER BY member_history.source_snapshot_id
               ) AS snapshots,
               resolution.resolution_status, resolution.evidence_sha256
          FROM football.fixture_identity_resolutions resolution
          JOIN football.product_team_match_history history
            ON history.fixture_id = resolution.representative_fixture_id
          JOIN football.product_competitions competition
            ON competition.competition_id = resolution.selected_competition_id
          JOIN football.product_teams home ON home.team_id = history.home_team_id
          JOIN football.product_teams away ON away.team_id = history.away_team_id
         WHERE resolution.active
           AND resolution.member_fixture_id = resolution.representative_fixture_id
           AND resolution.resolution_status IN ('UNIQUE', 'DUPLICATE_RESOLVED')
           AND NOT (resolution.canonical_real_fixture_id = ANY(%s::uuid[]))
           AND (%s::timestamptz IS NULL OR history.kickoff_at <= %s)
           AND (
                (cardinality(%s::uuid[]) = 0 AND cardinality(%s::uuid[]) = 0)
                OR history.competition_id = ANY(%s::uuid[])
                OR history.home_team_id = ANY(%s::uuid[])
                OR history.away_team_id = ANY(%s::uuid[])
           )
         ORDER BY history.kickoff_at, resolution.canonical_real_fixture_id
        """,
        (
            list(exclude_real_fixture_ids),
            maximum_kickoff,
            maximum_kickoff,
            list(competition_ids),
            list(team_ids),
            list(competition_ids),
            list(team_ids),
            list(team_ids),
        ),
    ).fetchall()
    return tuple(
        ResolvedHistoricalMatchV1(
            cast(UUID, row[0]),
            cast(UUID, row[1]),
            cast(datetime, row[2]),
            cast(UUID, row[3]),
            str(row[4]),
            str(row[5]),
            cast(int | None, row[6]),
            str(row[7]),
            cast(UUID, row[8]),
            cast(UUID, row[9]),
            str(row[10]),
            str(row[11]),
            int(row[12]),
            int(row[13]),
            cast(float | None, row[14]),
            cast(float | None, row[15]),
            tuple(str(value) for value in row[17]),
            tuple(cast(Sequence[UUID], row[18])),
            tuple(cast(Sequence[UUID], row[16])),
            ResolutionStatus(str(row[19])),
            str(row[20]),
        )
        for row in rows
    )


def load_persisted_resolved_metadata(connection: Connection[Any]) -> tuple[dict[str, object], ...]:
    """Load admitted real-fixture metadata without selecting any outcome column."""
    previous_factory = connection.row_factory
    connection.row_factory = dict_row
    try:
        rows = connection.execute(
            """
            SELECT resolution.canonical_real_fixture_id::text AS real_fixture_id,
                   resolution.representative_fixture_id::text,
                   history.kickoff_at,
                   resolution.selected_competition_id::text AS competition_id,
                   competition.name AS competition_name, competition.country,
                   competition.division, competition.season_label,
                   history.home_team_id::text, history.away_team_id::text,
                   home.name AS home_team_name, away.name AS away_team_name,
                   history.source_provider_code,
                   history.source_snapshot_id::text,
                   resolution.resolution_status, resolution.evidence_sha256,
                   resolution.member_fixture_id::text AS member_fixture_id
              FROM football.fixture_identity_resolutions resolution
              JOIN football.product_team_match_history history
                ON history.fixture_id = resolution.representative_fixture_id
              JOIN football.product_competitions competition
                ON competition.competition_id = resolution.selected_competition_id
              JOIN football.product_teams home ON home.team_id = history.home_team_id
              JOIN football.product_teams away ON away.team_id = history.away_team_id
             WHERE resolution.active
               AND resolution.resolution_status IN ('UNIQUE', 'DUPLICATE_RESOLVED')
             ORDER BY resolution.canonical_real_fixture_id,
                      resolution.member_fixture_id
            """
        ).fetchall()
    finally:
        connection.row_factory = previous_factory
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        value = dict(row)
        real_id = str(value["real_fixture_id"])
        if real_id not in grouped:
            grouped[real_id] = {
                **value,
                "member_fixture_ids": [str(value["member_fixture_id"])],
            }
        else:
            cast(list[str], grouped[real_id]["member_fixture_ids"]).append(
                str(value["member_fixture_id"])
            )
    for value in grouped.values():
        value.pop("member_fixture_id", None)
    return tuple(
        sorted(
            grouped.values(),
            key=lambda row: (cast(datetime, row["kickoff_at"]), str(row["real_fixture_id"])),
        )
    )


def load_canonical_history(connection: Connection[Any]) -> tuple[CanonicalHistoryRow, ...]:
    """Load retained history and compact provider lineage without N+1 queries."""
    previous_factory = connection.row_factory
    connection.row_factory = dict_row
    try:
        rows = connection.execute(
            """
            SELECT h.fixture_id, h.kickoff_at, h.competition_id,
                   competition.name AS competition_name, competition.country,
                   competition.division, competition.season_label,
                   h.home_team_id, h.away_team_id,
                   home.name AS home_team_name, away.name AS away_team_name,
                   h.home_goals, h.away_goals, h.home_xg, h.away_xg,
                   h.source_provider_code, h.source_snapshot_id,
                   h.source_kickoff_precision,
                   COALESCE(
                       jsonb_agg(DISTINCT jsonb_build_object(
                           'provider_code', provider.code,
                           'provider_match_id', mapping.provider_match_id,
                           'source_snapshot_id', mapping.source_snapshot_id,
                           'source_identity', snapshot.source_identity,
                           'source_revision', snapshot.source_revision,
                           'provider_path', resource.provider_path,
                           'resource_sha256', resource.sha256,
                           'provider_competition_id', competition_mapping.provider_competition_id
                       )) FILTER (WHERE mapping.id IS NOT NULL),
                       '[]'::jsonb
                   ) AS provider_evidence
              FROM football.product_team_match_history h
              JOIN football.product_competitions competition
                ON competition.competition_id = h.competition_id
              JOIN football.product_teams home ON home.team_id = h.home_team_id
              JOIN football.product_teams away ON away.team_id = h.away_team_id
              LEFT JOIN football.match_provider_mappings mapping
                ON mapping.match_id = h.fixture_id AND mapping.valid_to IS NULL
              LEFT JOIN football.providers provider ON provider.id = mapping.provider_id
              LEFT JOIN football.source_snapshots snapshot
                ON snapshot.id = mapping.source_snapshot_id
              LEFT JOIN football.source_resources resource
                ON resource.source_snapshot_id = mapping.source_snapshot_id
               AND resource.provider_path = split_part(mapping.provider_match_id, '#', 1)
              LEFT JOIN football.competition_provider_mappings competition_mapping
                ON competition_mapping.competition_id = h.competition_id
               AND competition_mapping.provider_id = mapping.provider_id
               AND competition_mapping.valid_to IS NULL
             GROUP BY h.fixture_id, h.kickoff_at, h.competition_id,
                      competition.name, competition.country, competition.division,
                      competition.season_label, h.home_team_id, h.away_team_id,
                      home.name, away.name, h.home_goals, h.away_goals,
                      h.home_xg, h.away_xg, h.source_provider_code,
                      h.source_snapshot_id, h.source_kickoff_precision
             ORDER BY h.kickoff_at, h.fixture_id
            """
        ).fetchall()
    finally:
        connection.row_factory = previous_factory
    return tuple(_row(value) for value in rows)


def audit_canonical_history(rows: Sequence[CanonicalHistoryRow]) -> CanonicalHistoryAudit:
    """Resolve exact candidates, then quarantine every impossible team schedule."""
    grouped: dict[tuple[UUID, UUID, datetime], list[CanonicalHistoryRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.home_team_id, row.away_team_id, row.kickoff_at)].append(row)

    identities = [_resolve_exact_cluster(tuple(cluster)) for cluster in grouped.values()]
    by_real_id = {item.canonical_real_fixture_id: item for item in identities}
    provider_members: dict[tuple[str, str], set[UUID]] = defaultdict(set)
    for item in identities:
        for evidence in item.provider_evidence:
            provider_members[(evidence.provider_code, evidence.provider_match_id)].add(
                item.canonical_real_fixture_id
            )
    conflicting_provider_ids = {
        real_id for members in provider_members.values() if len(members) > 1 for real_id in members
    }
    for real_id in conflicting_provider_ids:
        by_real_id[real_id] = replace(
            by_real_id[real_id],
            canonical_competition_id=None,
            resolution_status=ResolutionStatus.AMBIGUOUS_QUARANTINED,
            resolution_reason="PROVIDER_MATCH_ID_HAS_CONTRADICTORY_FIXTURE_FACTS",
        )
    slots: dict[tuple[UUID, datetime], set[UUID]] = defaultdict(set)
    for item in identities:
        slots[(item.home_team_id, item.kickoff_at)].add(item.canonical_real_fixture_id)
        slots[(item.away_team_id, item.kickoff_at)].add(item.canonical_real_fixture_id)
    impossible_ids = {
        real_id for members in slots.values() if len(members) > 1 for real_id in members
    }
    for real_id in impossible_ids:
        current = by_real_id[real_id]
        if not current.admitted:
            continue
        by_real_id[real_id] = replace(
            current,
            canonical_competition_id=None,
            resolution_status=ResolutionStatus.IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED,
            resolution_reason="TEAM_TIMESTAMP_CONFLICT_AFTER_EXACT_CLUSTER_RESOLUTION",
        )
    final_identities = tuple(
        sorted(
            by_real_id.values(),
            key=lambda item: (item.kickoff_at, str(item.canonical_real_fixture_id)),
        )
    )
    raw_by_id = {row.fixture_id: row for row in rows}
    resolved = tuple(
        _resolved_match(item, raw_by_id)
        for item in final_identities
        if item.admitted and item.canonical_competition_id is not None
    )
    if physical_timeline_conflicts(resolved):
        raise RuntimeError("CANONICAL_HISTORY_REPAIR_REQUIRED")
    counts = _counts(rows, final_identities, resolved)
    return CanonicalHistoryAudit(
        tuple(rows),
        final_identities,
        resolved,
        counts,
        _breakdown(rows, final_identities, "provider"),
        _breakdown(rows, final_identities, "competition"),
        _breakdown(rows, final_identities, "season"),
    )


def persist_resolutions(
    connection: Connection[Any], identities: Sequence[RealFixtureIdentityV1], created_at: datetime
) -> None:
    """Replace active V1 rows atomically; repeated identical audits converge."""
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must include a timezone")
    members = [member for item in identities for member in item.member_fixture_ids]
    if len(members) != len(set(members)):
        raise ValueError("member fixture belongs to multiple real fixtures")
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE football.fixture_identity_resolutions SET active = false WHERE active"
        )
        for item in identities:
            evidence = {
                "provider_evidence": [evidence_payload(value) for value in item.provider_evidence],
                "member_fixture_ids": [str(value) for value in item.member_fixture_ids],
            }
            for member in item.member_fixture_ids:
                cursor.execute(
                    """
                    INSERT INTO football.fixture_identity_resolutions (
                        canonical_real_fixture_id, member_fixture_id,
                        representative_fixture_id, resolution_status,
                        selected_competition_id, resolution_reason, evidence_json,
                        evidence_sha256, resolution_version, active, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, true, %s)
                    ON CONFLICT (
                        canonical_real_fixture_id, member_fixture_id, resolution_version
                    ) DO UPDATE SET
                        representative_fixture_id = EXCLUDED.representative_fixture_id,
                        resolution_status = EXCLUDED.resolution_status,
                        selected_competition_id = EXCLUDED.selected_competition_id,
                        resolution_reason = EXCLUDED.resolution_reason,
                        evidence_json = EXCLUDED.evidence_json,
                        evidence_sha256 = EXCLUDED.evidence_sha256,
                        active = true,
                        created_at = EXCLUDED.created_at
                    """,
                    (
                        item.canonical_real_fixture_id,
                        member,
                        item.representative_fixture_id,
                        item.resolution_status.value,
                        item.canonical_competition_id,
                        item.resolution_reason,
                        json.dumps(evidence, sort_keys=True, separators=(",", ":")),
                        item.evidence_sha256,
                        item.version,
                        created_at,
                    ),
                )


def physical_timeline_conflicts(history: Sequence[ResolvedHistoricalMatchV1]) -> int:
    slots: Counter[tuple[UUID, datetime]] = Counter()
    for row in history:
        slots[(row.home_team_id, row.kickoff_at)] += 1
        slots[(row.away_team_id, row.kickoff_at)] += 1
    return sum(value > 1 for value in slots.values())


def semantic_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def evidence_payload(value: ProviderFixtureEvidence) -> dict[str, object]:
    payload = asdict(value)
    payload["source_snapshot_id"] = str(value.source_snapshot_id)
    return cast(dict[str, object], payload)


def _resolve_exact_cluster(cluster: tuple[CanonicalHistoryRow, ...]) -> RealFixtureIdentityV1:
    ordered = tuple(sorted(cluster, key=lambda row: str(row.fixture_id)))
    first = ordered[0]
    members = tuple(row.fixture_id for row in ordered)
    evidence = tuple(
        sorted(
            {item for row in ordered for item in row.provider_evidence},
            key=lambda item: (
                item.provider_code,
                item.provider_match_id,
                str(item.source_snapshot_id),
            ),
        )
    )
    real_id = uuid5(
        NAMESPACE_URL,
        "matchforge:real-fixture:v1:"
        f"{first.kickoff_at.astimezone(UTC).isoformat()}:{first.home_team_id}:{first.away_team_id}",
    )
    competitions = {row.competition_id for row in ordered}
    scores = {(row.home_goals, row.away_goals) for row in ordered}
    if len(ordered) == 1:
        return _identity(
            real_id,
            first,
            members,
            evidence,
            first.competition_id,
            ResolutionStatus.UNIQUE,
            "ONE_CANONICAL_FIXTURE_ROW",
        )
    if len(scores) != 1:
        return _identity(
            real_id,
            first,
            members,
            evidence,
            None,
            ResolutionStatus.AMBIGUOUS_QUARANTINED,
            "CONFLICTING_SCORE_FACTS",
        )
    if len(competitions) != 1:
        return _identity(
            real_id,
            first,
            members,
            evidence,
            None,
            ResolutionStatus.AMBIGUOUS_QUARANTINED,
            "COMPETITION_IDENTITY_CONFLICT_NO_UNIQUE_PROVIDER_SUPPORT",
        )
    provider_codes = {item.provider_code for item in evidence}
    provider_match_keys = {(item.provider_code, item.provider_match_id) for item in evidence}
    same_resource = (
        len(
            {
                (item.provider_code, item.source_snapshot_id, item.provider_path)
                for item in evidence
                if item.provider_path is not None
            }
        )
        == 1
    )
    if len(provider_codes) > 1 or len(provider_match_keys) == 1 or same_resource:
        return _identity(
            real_id,
            first,
            members,
            evidence,
            next(iter(competitions)),
            ResolutionStatus.DUPLICATE_RESOLVED,
            "INDEPENDENT_PROVIDER_OR_IMMUTABLE_PROVIDER_EVIDENCE_MATCH",
        )
    return _identity(
        real_id,
        first,
        members,
        evidence,
        None,
        ResolutionStatus.AMBIGUOUS_QUARANTINED,
        "DUPLICATE_CANDIDATE_WITHOUT_STRONG_PROVIDER_EVIDENCE",
    )


def _identity(
    real_id: UUID,
    row: CanonicalHistoryRow,
    members: tuple[UUID, ...],
    evidence: tuple[ProviderFixtureEvidence, ...],
    competition_id: UUID | None,
    status: ResolutionStatus,
    reason: str,
) -> RealFixtureIdentityV1:
    representative = min(
        (value.fixture_id for value in (row,) if competition_id in (None, value.competition_id)),
        default=row.fixture_id,
        key=str,
    )
    return RealFixtureIdentityV1(
        real_id,
        row.kickoff_at,
        row.home_team_id,
        row.away_team_id,
        competition_id,
        members,
        representative,
        evidence,
        status,
        reason,
    )


def _resolved_match(
    identity: RealFixtureIdentityV1, raw_by_id: Mapping[UUID, CanonicalHistoryRow]
) -> ResolvedHistoricalMatchV1:
    candidates = [
        raw_by_id[value]
        for value in identity.member_fixture_ids
        if raw_by_id[value].competition_id == identity.canonical_competition_id
    ]
    representative = min(candidates, key=lambda row: str(row.fixture_id))
    return ResolvedHistoricalMatchV1(
        identity.canonical_real_fixture_id,
        representative.fixture_id,
        representative.kickoff_at,
        cast(UUID, identity.canonical_competition_id),
        representative.competition_name,
        representative.country,
        representative.division,
        representative.season_label,
        representative.home_team_id,
        representative.away_team_id,
        representative.home_team_name,
        representative.away_team_name,
        representative.home_goals,
        representative.away_goals,
        representative.home_xg,
        representative.away_xg,
        tuple(sorted({row.source_provider_code for row in candidates})),
        tuple(sorted({row.source_snapshot_id for row in candidates}, key=str)),
        identity.member_fixture_ids,
        identity.resolution_status,
        identity.evidence_sha256,
    )


def _counts(
    rows: Sequence[CanonicalHistoryRow],
    identities: Sequence[RealFixtureIdentityV1],
    resolved: Sequence[ResolvedHistoricalMatchV1],
) -> dict[str, int]:
    exact = [item for item in identities if len(item.member_fixture_ids) > 1]
    ambiguous = [
        item
        for item in identities
        if item.resolution_status is ResolutionStatus.AMBIGUOUS_QUARANTINED
    ]
    impossible = [
        item
        for item in identities
        if item.resolution_status is ResolutionStatus.IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED
    ]
    by_id = {row.fixture_id: row for row in rows}
    return {
        "raw_fixture_rows": len(rows),
        "unique_real_fixtures": len(resolved),
        "exact_duplicate_clusters": len(exact),
        "auto_resolved_duplicate_clusters": sum(
            item.resolution_status is ResolutionStatus.DUPLICATE_RESOLVED for item in exact
        ),
        "ambiguous_quarantined_clusters": len(ambiguous),
        "team_double_booking_clusters": len(impossible),
        "competition_identity_conflicts": sum(
            len({by_id[value].competition_id for value in item.member_fixture_ids}) > 1
            for item in identities
        ),
        "score_conflicts": sum(
            len(
                {
                    (by_id[value].home_goals, by_id[value].away_goals)
                    for value in item.member_fixture_ids
                }
            )
            > 1
            for item in identities
        ),
        "provider_match_identity_conflicts": sum(
            item.resolution_reason == "PROVIDER_MATCH_ID_HAS_CONTRADICTORY_FIXTURE_FACTS"
            for item in identities
        ),
        "rows_excluded_from_model_history": len(rows) - len(resolved),
        "resolved_history_rows": len(resolved),
        "unresolved_admitted_timeline_conflicts": physical_timeline_conflicts(resolved),
    }


def _breakdown(
    rows: Sequence[CanonicalHistoryRow],
    identities: Sequence[RealFixtureIdentityV1],
    dimension: str,
) -> dict[str, dict[str, int]]:
    status_by_member = {
        member: item.resolution_status for item in identities for member in item.member_fixture_ids
    }
    output: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        if dimension == "provider":
            key = row.source_provider_code
        elif dimension == "competition":
            key = f"{row.competition_id}:{row.competition_name}"
        else:
            key = row.season_label
        output[key]["raw_rows"] += 1
        status = status_by_member[row.fixture_id]
        output[key]["admitted_rows"] += int(status.value in ADMITTED_STATUSES)
        output[key]["quarantined_rows"] += int(status.value not in ADMITTED_STATUSES)
    return {key: dict(sorted(value.items())) for key, value in sorted(output.items())}


def _row(value: Mapping[str, object]) -> CanonicalHistoryRow:
    evidence = tuple(
        ProviderFixtureEvidence(
            str(item["provider_code"]),
            str(item["provider_match_id"]),
            UUID(str(item["source_snapshot_id"])),
            str(item["source_identity"]) if item.get("source_identity") is not None else None,
            str(item["source_revision"]) if item.get("source_revision") is not None else None,
            str(item["provider_path"]) if item.get("provider_path") is not None else None,
            str(item["resource_sha256"]) if item.get("resource_sha256") is not None else None,
            str(item["provider_competition_id"])
            if item.get("provider_competition_id") is not None
            else None,
        )
        for item in cast(list[dict[str, object]], value["provider_evidence"])
    )
    return CanonicalHistoryRow(
        cast(UUID, value["fixture_id"]),
        cast(datetime, value["kickoff_at"]),
        cast(UUID, value["competition_id"]),
        str(value["competition_name"]),
        str(value["country"]),
        cast(int | None, value["division"]),
        str(value["season_label"]),
        cast(UUID, value["home_team_id"]),
        cast(UUID, value["away_team_id"]),
        str(value["home_team_name"]),
        str(value["away_team_name"]),
        int(cast(int, value["home_goals"])),
        int(cast(int, value["away_goals"])),
        cast(float | None, value["home_xg"]),
        cast(float | None, value["away_xg"]),
        str(value["source_provider_code"]),
        cast(UUID, value["source_snapshot_id"]),
        str(value["source_kickoff_precision"]),
        evidence,
    )
