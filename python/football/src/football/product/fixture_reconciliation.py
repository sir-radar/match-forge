"""Resolve operational duplicate fixtures using explicit provider-ID crosswalks."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg import Connection

from football.product.domain import sha256_json
from football.product.identity_crosswalks import OPERATIONAL_TEAM_CROSSWALKS
from football.storage.locks import FIXTURE_CROSSWALK_LOCK, IDENTITY_ADMISSION_LOCK, acquire_locks


def reconcile_product_fixtures(
    connection: Connection[Any], *, fixture_ids: tuple[UUID, ...] | None = None
) -> int:
    """Keep source rows; select one display fixture for verified duplicate pairs."""
    if fixture_ids is not None and (not fixture_ids or len(fixture_ids) > 32):
        raise ValueError("scoped reconciliation requires 1 to 32 fixture IDs")
    crosswalks = [
        dict(
            source_provider=source[0],
            source_id=source[1],
            target_provider=target[0],
            target_id=target[1],
        )
        for source, target in OPERATIONAL_TEAM_CROSSWALKS.items()
    ]
    with connection.cursor() as cursor:
        # Mapping and history-decision triggers use this lock. Acquire it before
        # the fixture crosswalk lock, including when no mapping is being changed.
        acquire_locks(cursor, (IDENTITY_ADMISSION_LOCK, FIXTURE_CROSSWALK_LOCK))
        if fixture_ids is not None:
            fixture_ids = fixture_neighborhood(connection, fixture_ids)
        cursor.execute(
            """UPDATE football.fixture_identity_resolutions SET active = false
               WHERE active AND resolution_version = 'ProductFixtureCrosswalkV1'
                 AND (%s::uuid[] IS NULL OR member_fixture_id=ANY(%s::uuid[])
                      OR representative_fixture_id=ANY(%s::uuid[])
                      OR evidence_json->>'source_fixture_id'=ANY(%s::text[])
                      OR evidence_json->>'target_fixture_id'=ANY(%s::text[]))""",
            (
                list(fixture_ids) if fixture_ids is not None else None,
                list(fixture_ids or ()),
                list(fixture_ids or ()),
                [str(key) for key in fixture_ids or ()],
                [str(key) for key in fixture_ids or ()],
            ),
        )
        cursor.execute(
            """WITH links AS (
                SELECT DISTINCT source.team_id source_team, target.team_id target_team
                  FROM jsonb_to_recordset(%s::jsonb) AS x(
                      source_provider text, source_id text, target_provider text, target_id text)
                  JOIN football.providers sp ON sp.code = x.source_provider
                  JOIN football.providers tp ON tp.code = x.target_provider
                  JOIN football.product_effective_team_mappings source
                    ON source.provider_id = sp.id AND source.provider_team_id = x.source_id
                   AND source.valid_to IS NULL
                   AND source.mapping_confidence = 1
                   AND football.product_mapping_trusted('team', source.id, source.effective_team_id)
                  JOIN football.product_effective_team_mappings target
                    ON target.provider_id = tp.id AND target.provider_team_id = x.target_id
                   AND target.valid_to IS NULL
                   AND target.mapping_confidence = 1
                   AND football.product_mapping_trusted('team', target.id, target.effective_team_id)
            )
            SELECT DISTINCT source.fixture_id, target.fixture_id,
                   source.competition_id, source.kickoff_at,
                   source.status, source.updated_at, target.status, target.updated_at,
                   EXISTS (SELECT 1 FROM football.product_team_match_history history
                           WHERE history.fixture_id = target.fixture_id) AS target_has_history
              FROM football.product_fixtures source
              JOIN links home ON home.source_team = source.home_team_id
              JOIN links away ON away.source_team = source.away_team_id
              JOIN football.product_fixtures target
                ON target.home_team_id = home.target_team
               AND target.away_team_id = away.target_team
               AND target.competition_id = source.competition_id
               AND target.kickoff_at = source.kickoff_at
               AND target.fixture_id <> source.fixture_id
               AND (home.source_team <> home.target_team
                    OR away.source_team <> away.target_team
                    OR source.fixture_id::text < target.fixture_id::text)
              JOIN football.matches sm ON sm.id = source.fixture_id
              JOIN football.matches tm ON tm.id = target.fixture_id AND tm.season_id = sm.season_id
             WHERE (%s::uuid[] IS NULL OR source.fixture_id=ANY(%s::uuid[])
                    OR target.fixture_id=ANY(%s::uuid[]))
               AND NOT EXISTS (
                SELECT 1 FROM football.product_team_match_history history
                 WHERE history.fixture_id = source.fixture_id)
               AND (source.home_score IS NULL OR target.home_score IS NULL
                    OR (source.home_score = target.home_score
                        AND source.away_score = target.away_score))
               AND (source.status IN ('SCHEDULED', 'LIVE')
                    OR target.status IN ('SCHEDULED', 'LIVE') OR source.status = target.status)
               AND NOT EXISTS (
                SELECT 1 FROM football.fixture_identity_resolutions resolution
                 WHERE resolution.active
                   AND resolution.resolution_version <> 'ProductFixtureCrosswalkV1'
                   AND resolution.member_fixture_id IN (source.fixture_id, target.fixture_id)
                   AND (resolution.member_fixture_id = source.fixture_id
                        OR resolution.resolution_status NOT IN ('UNIQUE', 'DUPLICATE_RESOLVED')
                        OR resolution.representative_fixture_id <> target.fixture_id))
             ORDER BY source.fixture_id, target.fixture_id""",
            (
                json.dumps(crosswalks),
                list(fixture_ids) if fixture_ids is not None else None,
                list(fixture_ids or ()),
                list(fixture_ids or ()),
            ),
        )
        pairs = cursor.fetchall()
        membership = Counter(member for pair in pairs for member in pair[:2])
        pairs = [pair for pair in pairs if membership[pair[0]] == membership[pair[1]] == 1]
        for (
            source,
            target,
            competition,
            kickoff,
            source_status,
            source_at,
            target_status,
            target_at,
            target_has_history,
        ) in pairs:
            priority = {
                "SCHEDULED": 0,
                "LIVE": 1,
                "HALF_TIME": 1,
                "INTERRUPTED": 1,
                "SUSPENDED": 1,
                "FINISHED": 2,
                "POSTPONED": 2,
                "CANCELLED": 2,
                "ABANDONED": 2,
                "AWARDED": 2,
            }
            representative = (
                target
                if target_has_history
                else max(
                    (
                        (priority[source_status], source_at, str(source), source),
                        (priority[target_status], target_at, str(target), target),
                    ),
                )[3]
            )
            evidence = {
                "source_fixture_id": str(source),
                "target_fixture_id": str(target),
                "competition_id": str(competition),
                "kickoff_at": kickoff.isoformat(),
                "provider_team_crosswalks": crosswalks,
            }
            for member in (source,) if target_has_history else (source, target):
                cursor.execute(
                    """INSERT INTO football.fixture_identity_resolutions (
                        canonical_real_fixture_id, member_fixture_id, representative_fixture_id,
                        resolution_status, selected_competition_id, resolution_reason,
                        evidence_json, evidence_sha256, resolution_version, active, created_at)
                    VALUES (%s, %s, %s, 'DUPLICATE_RESOLVED', %s,
                        'Explicit provider team IDs, identical competition, season and kickoff',
                        %s::jsonb, %s, 'ProductFixtureCrosswalkV1', true, %s)
                    ON CONFLICT (canonical_real_fixture_id, member_fixture_id, resolution_version)
                    DO UPDATE SET representative_fixture_id = EXCLUDED.representative_fixture_id,
                                  active = true""",
                    (
                        target,
                        member,
                        representative,
                        competition,
                        json.dumps(evidence),
                        sha256_json(evidence),
                        datetime.now(UTC),
                    ),
                )
        if fixture_ids is not None:
            repaired = cursor.execute(
                "SELECT football.reconcile_unknown_season_fixtures(%s::uuid[])",
                (list(fixture_ids),),
            ).fetchone()
            assert repaired is not None
            return len(pairs) + int(repaired[0])
        cursor.execute("SELECT football.reconcile_unknown_season_fixtures()")
        repaired_unknown_season_result = cursor.fetchone()
        assert repaired_unknown_season_result is not None
        repaired_unknown_season_fixtures = int(repaired_unknown_season_result[0])
    return len(pairs) + repaired_unknown_season_fixtures


def fixture_neighborhood(
    connection: Connection[Any], fixture_ids: tuple[UUID, ...]
) -> tuple[UUID, ...]:
    rows = connection.execute(
        """SELECT f.fixture_id FROM football.product_fixtures f WHERE
           (f.competition_id,f.kickoff_at) IN (SELECT competition_id,kickoff_at
              FROM football.product_fixtures WHERE fixture_id=ANY(%s::uuid[]))
           ORDER BY f.fixture_id LIMIT 101""",
        (list(fixture_ids),),
    ).fetchall()
    if not rows or len(rows) > 100:
        raise ValueError("fixture neighborhood requires separate bounded review (maximum 100)")
    return tuple(row[0] for row in rows)
