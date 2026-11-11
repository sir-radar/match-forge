"""Provider identifier resolution for the product sync."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from football.product.api_football import (
    continent_for_country,
    inferred_division,
)
from football.product.domain import (
    normalize_team_name,
    stable_id,
)
from football.product.sync_support import (
    FALLBACK_PROVIDER_CODE,
    PROVIDER_CODE,
    ProductSyncBase,
    _integer,
    _mapping,
)


class ProductIdentityMixin(ProductSyncBase):
    """Resolve provider competitions, teams and matches to canonical identifiers."""

    def _competition_id(self, provider_competition_id: str, snapshot_id: UUID) -> UUID:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT cpm.competition_id
                FROM football.competition_provider_mappings cpm
                JOIN football.providers p ON p.id = cpm.provider_id
                WHERE p.code = %s AND cpm.provider_competition_id = %s
                  AND cpm.valid_to IS NULL
                ORDER BY cpm.first_seen_at LIMIT 1
                """,
                (PROVIDER_CODE, provider_competition_id),
            )
            found = cursor.fetchone()
        if found is not None:
            return cast(UUID, found[0])
        competition_id = stable_id("competition", PROVIDER_CODE, provider_competition_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO football.competitions (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (competition_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.competition_provider_mappings (
                    competition_id, provider_id, provider_competition_id, first_seen_at,
                    last_seen_at, mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, id, %s, clock_timestamp(), clock_timestamp(),
                    'deterministic', 1.0, %s FROM football.providers WHERE code = %s
                """,
                (competition_id, provider_competition_id, snapshot_id, PROVIDER_CODE),
            )
        return competition_id

    def _team_id(
        self,
        row: Mapping[str, Any],
        country: str,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> UUID:
        provider_team_id = str(_integer(row, "id"))
        normalized_name = normalize_team_name(str(row["name"]))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = %s AND provider_team_id = %s
                """,
                (PROVIDER_CODE, provider_team_id),
            )
            found = cursor.fetchone()
        team_id = (
            cast(UUID, found[0])
            if found is not None
            else stable_id("team", PROVIDER_CODE, provider_team_id)
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.teams (id, entity_kind)
                VALUES (%s, 'club') ON CONFLICT DO NOTHING
                """,
                (team_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.product_teams (team_id, name, country, crest_url, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (team_id) DO UPDATE SET name = EXCLUDED.name,
                    crest_url = EXCLUDED.crest_url, updated_at = EXCLUDED.updated_at
                """,
                (team_id, row["name"], country or None, row.get("logo"), observed_at),
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_aliases (
                    provider_code, provider_team_id, normalized_name, country, team_id
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider_code, provider_team_id) DO UPDATE SET
                    normalized_name = EXCLUDED.normalized_name,
                    country = EXCLUDED.country,
                    team_id = EXCLUDED.team_id
                """,
                (PROVIDER_CODE, provider_team_id, normalized_name, country or None, team_id),
            )
        self._reconcile_team_provider_mapping(team_id, provider_team_id, snapshot_id, observed_at)
        return team_id

    def _reconcile_team_provider_mapping(
        self,
        team_id: UUID,
        provider_team_id: str,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE football.team_provider_mappings mapping
                SET valid_to = %s, last_seen_at = GREATEST(last_seen_at, %s)
                FROM football.providers provider
                WHERE mapping.provider_id = provider.id
                  AND provider.code = %s
                  AND mapping.provider_team_id = %s
                  AND mapping.valid_to IS NULL
                  AND mapping.team_id <> %s
                """,
                (observed_at, observed_at, PROVIDER_CODE, provider_team_id, team_id),
            )
            cursor.execute(
                """
                INSERT INTO football.team_provider_mappings (
                    team_id, provider_id, provider_team_id, valid_from,
                    first_seen_at, last_seen_at, mapping_method,
                    mapping_confidence, source_snapshot_id
                ) SELECT %s, provider.id, %s, %s, %s, %s,
                    'deterministic', 1.0, %s
                FROM football.providers provider
                WHERE provider.code = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM football.team_provider_mappings existing
                      WHERE existing.provider_id = provider.id
                        AND existing.provider_team_id = %s
                        AND existing.valid_to IS NULL
                  )
                """,
                (
                    team_id,
                    provider_team_id,
                    observed_at,
                    observed_at,
                    observed_at,
                    snapshot_id,
                    PROVIDER_CODE,
                    provider_team_id,
                ),
            )

    def _fallback_competition_mapping(
        self, code: str, competition_id: UUID, snapshot_id: UUID, observed_at: datetime
    ) -> None:
        self.connection.execute(
            """INSERT INTO football.competition_provider_mappings (
                   competition_id, provider_id, provider_competition_id,
                   valid_from, first_seen_at, last_seen_at,
                   mapping_method, mapping_confidence, source_snapshot_id)
               SELECT %s, p.id, %s, clock_timestamp(), %s, %s, 'explicit_crosswalk', 1, %s
               FROM football.providers p WHERE p.code = %s AND NOT EXISTS (
                   SELECT 1 FROM football.competition_provider_mappings m
                   WHERE m.provider_id = p.id AND m.provider_competition_id = %s
                     AND m.valid_to IS NULL)""",
            (
                competition_id,
                code,
                observed_at,
                observed_at,
                snapshot_id,
                FALLBACK_PROVIDER_CODE,
                code,
            ),
        )

    def _fallback_team_id(
        self,
        row: Mapping[str, Any],
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> UUID:
        provider_team_id = str(_integer(row, "id"))
        normalized_name = normalize_team_name(str(row["name"]))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = %s AND provider_team_id = %s
                """,
                (FALLBACK_PROVIDER_CODE, provider_team_id),
            )
            found = cursor.fetchone()
        team_id = (
            cast(UUID, found[0])
            if found is not None
            else stable_id("team", FALLBACK_PROVIDER_CODE, provider_team_id)
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.teams (id, entity_kind)
                VALUES (%s, 'club') ON CONFLICT DO NOTHING
                """,
                (team_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.product_teams (team_id, name, crest_url, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (team_id) DO UPDATE SET
                    crest_url = COALESCE(EXCLUDED.crest_url, football.product_teams.crest_url),
                    updated_at = EXCLUDED.updated_at
                """,
                (team_id, row["name"], row.get("crest"), observed_at),
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_aliases (
                    provider_code, provider_team_id, normalized_name, team_id
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider_code, provider_team_id) DO NOTHING
                """,
                (FALLBACK_PROVIDER_CODE, provider_team_id, normalized_name, team_id),
            )
            cursor.execute(
                """
                INSERT INTO football.team_provider_mappings (
                    team_id, provider_id, provider_team_id, first_seen_at, last_seen_at,
                    mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, id, %s, %s, %s, 'deterministic',
                    1.0, %s FROM football.providers p
                WHERE p.code = %s AND NOT EXISTS (
                    SELECT 1 FROM football.team_provider_mappings existing
                    WHERE existing.provider_id = p.id
                      AND existing.provider_team_id = %s
                )
                """,
                (
                    team_id,
                    provider_team_id,
                    observed_at,
                    observed_at,
                    snapshot_id,
                    FALLBACK_PROVIDER_CODE,
                    provider_team_id,
                ),
            )
        return team_id

    def _ensure_match_mapping(
        self,
        cursor: Any,
        match_id: UUID,
        provider_match_id: str,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO football.match_provider_mappings (
                match_id, provider_id, provider_match_id, first_seen_at, last_seen_at,
                mapping_method, mapping_confidence, source_snapshot_id
            ) SELECT %s, id, %s, %s, %s, 'deterministic', 1.0, %s
              FROM football.providers p
             WHERE p.code = %s
               AND NOT EXISTS (
                   SELECT 1 FROM football.match_provider_mappings existing
                   WHERE existing.provider_id = p.id AND existing.provider_match_id = %s
               )
            """,
            (
                match_id,
                provider_match_id,
                observed_at,
                observed_at,
                snapshot_id,
                PROVIDER_CODE,
                provider_match_id,
            ),
        )

    def _mapped_match_id(self, provider_code: str, provider_match_id: str) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.match_id
                FROM football.match_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = %s AND mapping.provider_match_id = %s
                  AND mapping.valid_to IS NULL
                  AND (mapping.valid_from IS NULL OR mapping.valid_from <= clock_timestamp())
                """,
                (provider_code, provider_match_id),
            )
            found = cursor.fetchone()
        return cast(UUID, found[0]) if found is not None else None

    def _ensure_provider_match_mapping(
        self,
        cursor: Any,
        match_id: UUID,
        provider_match_id: str,
        snapshot_id: UUID,
        observed_at: datetime,
        provider_code: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO football.match_provider_mappings (
                match_id, provider_id, provider_match_id, first_seen_at, last_seen_at,
                mapping_method, mapping_confidence, source_snapshot_id
            ) SELECT %s, id, %s, %s, %s, 'deterministic', 1.0, %s
              FROM football.providers p
             WHERE p.code = %s
               AND NOT EXISTS (
                   SELECT 1 FROM football.match_provider_mappings existing
                   WHERE existing.provider_id = p.id AND existing.provider_match_id = %s
               )
            """,
            (
                match_id,
                provider_match_id,
                observed_at,
                observed_at,
                snapshot_id,
                provider_code,
                provider_match_id,
            ),
        )

    def _competition_exists(self, competition_id: UUID) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM football.product_competitions WHERE competition_id = %s",
                (competition_id,),
            )
            return cursor.fetchone() is not None

    def _ensure_season(self, competition_id: UUID, season_id: UUID) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.seasons (id, competition_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (season_id, competition_id),
            )

    def _store_fixture_competition(
        self,
        row: Mapping[str, Any],
        competition_id: UUID,
        observed_at: datetime,
    ) -> None:
        league = _mapping(row, "league")
        name = str(league["name"])
        country = str(league.get("country") or "World")
        season = int(league["season"])
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.product_competitions (
                    competition_id, name, country, continent, division, competition_type,
                    season_label, fixtures_available, results_available, standings_available,
                    h2h_available, forecast_available, xg_available, team_stats_available,
                    availability_status, source_roles, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 'LEAGUE', %s, true, true, %s,
                    false, false, false, false, 'NOT_ENOUGH_HISTORY', %s::jsonb, %s)
                ON CONFLICT (competition_id) DO NOTHING
                """,
                (
                    competition_id,
                    name,
                    country,
                    continent_for_country(country),
                    inferred_division(name, "League"),
                    str(season),
                    bool(league.get("standings")),
                    json.dumps({"fixtures": [PROVIDER_CODE], "results": [PROVIDER_CODE]}),
                    observed_at,
                ),
            )
