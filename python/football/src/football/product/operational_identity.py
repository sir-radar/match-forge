"""Fixture identity resolution for the operational provider sync."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from football.product.domain import (
    fixture_identity,
    normalize_team_name,
    sha256_json,
    stable_id,
)
from football.product.operational_seasons import OperationalSeasonMixin
from football.product.operational_support import (
    FixtureObservation,
    _normalize_competition_name,
)
from football.storage.locks import FIXTURE_CROSSWALK_LOCK, IDENTITY_ADMISSION_LOCK, acquire_locks


class OperationalIdentityMixin(OperationalSeasonMixin):
    """Resolve provider fixtures to canonical fixtures and teams."""

    def _provider_scoped_identity(self, table: str, provider_value: str) -> UUID:
        if table == "competition_provider_mappings":
            return stable_id("provider-scoped-competition", self.provider_code, provider_value)
        if table == "team_provider_mappings":
            return stable_id("provider-scoped-team", self.provider_code, provider_value)
        if table == "match_provider_mappings":
            return stable_id("provider-scoped-match", self.provider_code, provider_value)
        raise ValueError(f"unsupported provider mapping table: {table}")

    def _mapped_or_scoped_team(self, provider_team_id: str) -> UUID:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.effective_team_id
                     FROM football.product_effective_team_mappings mapping
                     JOIN football.providers provider ON provider.id = mapping.provider_id
                    WHERE provider.code = %s AND mapping.provider_team_id = %s
                      AND mapping.valid_to IS NULL AND mapping.mapping_confidence = 1""",
                (self.provider_code, provider_team_id),
            )
            mapped = cursor.fetchone()
        if mapped is not None:
            return cast(UUID, mapped[0])
        return stable_id("provider-scoped-team", self.provider_code, provider_team_id)

    def _verified_provider_entities(self, row: FixtureObservation) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.competition_id, competition.metadata_status
                   FROM football.competition_provider_mappings mapping
                   JOIN football.providers provider ON provider.id = mapping.provider_id
                   JOIN football.product_competitions competition
                     ON competition.competition_id = mapping.competition_id
                   WHERE provider.code = %s AND mapping.provider_competition_id = %s
                     AND mapping.valid_to IS NULL AND mapping.mapping_confidence = 1
                     AND football.product_mapping_trusted(
                         'competition', mapping.id, mapping.competition_id)
                     AND (SELECT count(DISTINCT tm.provider_team_id)
                          FROM football.product_effective_team_mappings tm
                          WHERE tm.provider_id = provider.id AND tm.valid_to IS NULL
                            AND tm.provider_team_id IN (%s, %s)
                            AND football.product_mapping_trusted(
                                'team', tm.id, tm.effective_team_id)) = 2""",
                (
                    self.provider_code,
                    row.provider_competition_id,
                    row.provider_home_team_id,
                    row.provider_away_team_id,
                ),
            )
            competition = cursor.fetchone()
        return (
            competition is not None
            and competition[1] == "VERIFIED"
            and competition[0]
            != self._provider_scoped_identity(
                "competition_provider_mappings", row.provider_competition_id
            )
            and all(
                self._mapped_or_scoped_team(team)
                != self._provider_scoped_identity("team_provider_mappings", team)
                for team in (row.provider_home_team_id, row.provider_away_team_id)
            )
        )

    def _candidate_mapping_conflict(
        self, row: FixtureObservation, candidate: Sequence[Any]
    ) -> str | None:
        provider_values = (
            (
                "competition_provider_mappings",
                "provider_competition_id",
                "competition_id",
                row.provider_competition_id,
                candidate[1],
            ),
            (
                "team_provider_mappings",
                "provider_team_id",
                "team_id",
                row.provider_home_team_id,
                candidate[2],
            ),
            (
                "team_provider_mappings",
                "provider_team_id",
                "team_id",
                row.provider_away_team_id,
                candidate[3],
            ),
        )
        with self.connection.cursor() as cursor:
            for (
                table,
                provider_column,
                canonical_column,
                provider_value,
                candidate_value,
            ) in provider_values:
                read_table = (
                    "product_effective_team_mappings"
                    if table == "team_provider_mappings"
                    else table
                )
                read_column = (
                    "effective_team_id" if table == "team_provider_mappings" else canonical_column
                )
                cursor.execute(
                    f"""SELECT mapping.{read_column}
                          FROM football.{read_table} mapping
                          JOIN football.providers provider ON provider.id = mapping.provider_id
                         WHERE provider.code = %s
                           AND mapping.{provider_column} = %s
                           AND mapping.valid_to IS NULL""",
                    (self.provider_code, provider_value),
                )
                existing = cursor.fetchone()
                if (
                    existing is not None
                    and existing[0] != candidate_value
                    and existing[0] != self._provider_scoped_identity(table, provider_value)
                ):
                    return f"verified {table} contradicts exact-name candidate"
        return None

    def _trusted_direct_fixture(self, fixture_id: UUID, row: FixtureObservation) -> bool:
        if not self._verified_provider_entities(row):
            return False
        candidate = self.connection.execute(
            """SELECT fixture_id, competition_id, home_team_id, away_team_id
               FROM football.product_fixtures WHERE fixture_id = %s
                 AND kickoff_at BETWEEN %s AND %s""",
            (
                fixture_id,
                row.kickoff_at - self.kickoff_tolerance,
                row.kickoff_at + self.kickoff_tolerance,
            ),
        ).fetchone()
        return candidate is not None and self._candidate_mapping_conflict(row, candidate) is None

    def _trusted_duplicate_representative(
        self, member_fixture_id: UUID, row: FixtureObservation
    ) -> UUID | None:
        candidate = self.connection.execute(
            """SELECT fixture.fixture_id,fixture.competition_id,
                      fixture.home_team_id,fixture.away_team_id
                 FROM football.fixture_identity_resolutions resolution
                 JOIN football.product_effective_fixtures fixture
                   ON fixture.fixture_id=resolution.representative_fixture_id
                WHERE resolution.member_fixture_id=%s AND resolution.active
                  AND resolution.resolution_status='DUPLICATE_RESOLVED'
                  AND fixture.identity_status='VERIFIED'
                  AND fixture.kickoff_at BETWEEN %s AND %s""",
            (
                member_fixture_id,
                row.kickoff_at - self.kickoff_tolerance,
                row.kickoff_at + self.kickoff_tolerance,
            ),
        ).fetchone()
        if (
            candidate is None
            or not self._verified_provider_entities(row)
            or self._candidate_mapping_conflict(row, candidate) is not None
        ):
            return None
        return cast(UUID, candidate[0])

    def _reconcile_direct_mapping_candidate(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        member_fixture_id: UUID,
        representative_fixture_id: UUID,
    ) -> bool:
        if member_fixture_id == representative_fixture_id:
            return False
        self._reconcile_retained_members(row, representative_fixture_id, snapshot_id)
        return (
            self._trusted_duplicate_representative(member_fixture_id, row)
            == representative_fixture_id
        )

    def _resolve_conflicting_candidate(
        self,
        row: FixtureObservation,
        snapshot_id: UUID | None,
        direct: tuple[UUID, str],
        fixture_id: UUID,
    ) -> UUID | None:
        """Only an evidence-backed reconciliation may replace a conflicting native binding."""
        if snapshot_id is None:
            return None
        if self._reconcile_direct_mapping_candidate(row, snapshot_id, direct[0], fixture_id):
            return fixture_id
        self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "CONTRADICTORY",
            "existing match mapping conflicts with exact fixture candidate",
            {
                "rule": "verified_provider_ids_unique_exact_kickoff",
                "existing_fixture_id": str(direct[0]),
                "existing_mapping_method": direct[1],
                "candidate_fixture_id": str(fixture_id),
            },
        )
        return None

    def _reconcile_exact_fixture(self, row: FixtureObservation, snapshot_id: UUID) -> UUID | None:
        competition_name = row.provider_competition_name
        if competition_name is None:
            self._record_mapping_decision(
                row, snapshot_id, None, "REVIEW_REQUIRED", "provider competition name missing", {}
            )
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture.fixture_id, fixture.competition_id,
                       fixture.home_team_id, fixture.away_team_id,
                       competition.name, home.name, away.name,
                       fixture.status, fixture.home_score, fixture.away_score
                FROM (
                    SELECT fixture_id, competition_id, home_team_id, away_team_id,
                           kickoff_at, status, home_score, away_score
                    FROM football.product_effective_fixtures WHERE identity_status = 'VERIFIED'
                    UNION ALL
                    SELECT history.fixture_id, history.competition_id, history.home_team_id,
                           history.away_team_id, history.kickoff_at, 'FINISHED',
                           history.home_goals, history.away_goals
                    FROM football.product_eligible_fixture_history_at(
                        statement_timestamp(), ARRAY(
                            SELECT h.fixture_id FROM football.product_team_match_history h
                            WHERE h.kickoff_at BETWEEN %s AND %s
                        )) history
                    WHERE NOT EXISTS (SELECT 1 FROM football.product_fixtures existing
                                      WHERE existing.fixture_id = history.fixture_id)
                      AND history.source_kickoff_precision = 'EXACT'
                ) fixture
                JOIN football.product_competitions competition
                  ON competition.competition_id = fixture.competition_id
                JOIN football.product_teams home ON home.team_id = fixture.home_team_id
                JOIN football.product_teams away ON away.team_id = fixture.away_team_id
                WHERE fixture.kickoff_at BETWEEN %s AND %s
                ORDER BY fixture.fixture_id
                """,
                (
                    row.kickoff_at - self.kickoff_tolerance,
                    row.kickoff_at + self.kickoff_tolerance,
                    row.kickoff_at - self.kickoff_tolerance,
                    row.kickoff_at + self.kickoff_tolerance,
                ),
            )
            nearby = cursor.fetchall()
        exact = [
            candidate
            for candidate in nearby
            if _normalize_competition_name(candidate[4])
            == _normalize_competition_name(competition_name)
            and normalize_team_name(candidate[5]) == normalize_team_name(row.home_team_name)
            and normalize_team_name(candidate[6]) == normalize_team_name(row.away_team_name)
        ]
        evidence = {
            "rule": "unique_exact_competition_home_away_utc_kickoff_v1",
            "kickoff_tolerance_seconds": int(self.kickoff_tolerance.total_seconds()),
            "provider_competition": competition_name,
            "provider_home_team": row.home_team_name,
            "provider_away_team": row.away_team_name,
            "nearby_candidates": len(nearby),
            "exact_candidates": [str(item[0]) for item in exact],
        }
        if len(exact) != 1:
            reason = "no exact canonical candidate" if not exact else "ambiguous exact candidates"
            self._record_mapping_decision(
                row, snapshot_id, None, "REVIEW_REQUIRED", reason, evidence
            )
            return None
        candidate = exact[0]
        fixture_id = cast(UUID, candidate[0])
        self._materialize_history_fixture(fixture_id, row.observed_at)
        mapping_conflict = self._candidate_mapping_conflict(row, candidate)
        if mapping_conflict is not None:
            self._record_mapping_decision(
                row,
                snapshot_id,
                fixture_id,
                "CONTRADICTORY",
                mapping_conflict,
                evidence,
            )
            return None
        if (
            row.status == "FINISHED"
            and candidate[7] == "FINISHED"
            and candidate[8] is not None
            and (candidate[8], candidate[9]) != (row.home_score, row.away_score)
        ):
            self._record_mapping_decision(
                row,
                snapshot_id,
                fixture_id,
                "CONTRADICTORY",
                "finished score contradicts canonical result",
                evidence
                | {
                    "canonical_score": [candidate[8], candidate[9]],
                    "provider_score": [row.home_score, row.away_score],
                },
            )
            return None
        self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "REVIEW_REQUIRED",
            "explicit cross-provider evidence required",
            evidence,
        )
        return None

    def _materialize_history_fixture(self, fixture_id: UUID, observed_at: datetime) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO football.product_fixtures (
                       fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                       status, home_score, away_score, forecast_availability, updated_at,
                       result_score_basis
                   ) SELECT fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                            'FINISHED', home_goals, away_goals, 'NOT_ENOUGH_HISTORY', %s,
                            'REGULATION_90'
                       FROM football.product_eligible_match_history WHERE fixture_id = %s
                   ON CONFLICT (fixture_id) DO NOTHING""",
                (observed_at, fixture_id),
            )

    def _resolve_fixture(
        self, row: FixtureObservation, snapshot_id: UUID | None = None
    ) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.match_id, mapping.mapping_method
                FROM football.match_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = %s AND mapping.provider_match_id = %s
                  AND mapping.valid_to IS NULL
                  AND mapping.mapping_method IN ('explicit_crosswalk', 'manual', 'deterministic')
                  AND mapping.mapping_confidence = 1
                """,
                (self.provider_code, row.provider_match_id),
            )
            direct = cursor.fetchall()
            if len(direct) == 1:
                representative = self._trusted_duplicate_representative(direct[0][0], row)
                if representative is not None:
                    return representative
            if (
                len(direct) == 1
                and self._trusted_direct_fixture(direct[0][0], row)
                and direct[0][0]
                != stable_id("provider-scoped-match", self.provider_code, row.provider_match_id)
            ):
                return cast(UUID, direct[0][0])
            cursor.execute(
                """
                SELECT fixture.fixture_id, fixture.competition_id,
                       fixture.home_team_id, fixture.away_team_id
                FROM (
                    SELECT fixture_id, competition_id, home_team_id, away_team_id,
                           kickoff_at, 'EXACT' AS source_kickoff_precision,
                           home_score, away_score
                    FROM football.product_effective_fixtures WHERE identity_status = 'VERIFIED'
                    UNION ALL
                    SELECT history.fixture_id, history.competition_id, history.home_team_id,
                           history.away_team_id, history.kickoff_at,
                           history.source_kickoff_precision, history.home_goals, history.away_goals
                    FROM football.product_eligible_fixture_history_at(
                        statement_timestamp(), ARRAY(
                            SELECT h.fixture_id FROM football.product_team_match_history h
                            WHERE h.kickoff_at BETWEEN %s AND %s
                        )) history
                    WHERE NOT EXISTS (SELECT 1 FROM football.product_fixtures existing
                                      WHERE existing.fixture_id = history.fixture_id)
                ) fixture
                JOIN football.product_effective_team_aliases home
                  ON home.team_id = fixture.home_team_id
                 AND home.provider_code = %s AND home.provider_team_id = %s
                JOIN football.product_effective_team_aliases away
                  ON away.team_id = fixture.away_team_id
                 AND away.provider_code = %s AND away.provider_team_id = %s
                JOIN football.competition_provider_mappings competition_mapping
                  ON competition_mapping.competition_id = fixture.competition_id
                JOIN football.providers provider
                  ON provider.id = competition_mapping.provider_id AND provider.code = %s
                WHERE competition_mapping.provider_competition_id = %s
                  AND competition_mapping.valid_to IS NULL
                  AND competition_mapping.mapping_method IN (
                      'explicit_crosswalk', 'manual', 'deterministic'
                  )
                  AND competition_mapping.mapping_confidence = 1
                  AND football.product_mapping_trusted(
                      'competition', competition_mapping.id, competition_mapping.competition_id)
                  AND EXISTS (SELECT 1 FROM football.product_effective_team_mappings hm
                      WHERE hm.provider_id = provider.id AND hm.provider_team_id = %s
                        AND hm.effective_team_id = fixture.home_team_id AND hm.valid_to IS NULL
                        AND football.product_mapping_trusted('team', hm.id, hm.effective_team_id))
                  AND EXISTS (SELECT 1 FROM football.product_effective_team_mappings am
                      WHERE am.provider_id = provider.id AND am.provider_team_id = %s
                        AND am.effective_team_id = fixture.away_team_id AND am.valid_to IS NULL
                        AND football.product_mapping_trusted('team', am.id, am.effective_team_id))
                  AND ((fixture.source_kickoff_precision = 'EXACT'
                        AND fixture.kickoff_at BETWEEN %s AND %s)
                       OR (fixture.source_kickoff_precision = 'DATE_ONLY'
                           AND fixture.kickoff_at::date = %s::date
                           AND fixture.home_score = %s AND fixture.away_score = %s))
                ORDER BY fixture.fixture_id
                """,
                (
                    row.kickoff_at - timedelta(days=1),
                    row.kickoff_at + timedelta(days=1),
                    self.provider_code,
                    row.provider_home_team_id,
                    self.provider_code,
                    row.provider_away_team_id,
                    self.provider_code,
                    row.provider_competition_id,
                    row.provider_home_team_id,
                    row.provider_away_team_id,
                    row.kickoff_at - self.kickoff_tolerance,
                    row.kickoff_at + self.kickoff_tolerance,
                    row.kickoff_at,
                    row.home_score,
                    row.away_score,
                ),
            )
            candidates = cursor.fetchall()
        if len(candidates) == 1:
            fixture_id = cast(UUID, candidates[0][0])
            if len(direct) == 1 and direct[0][0] != fixture_id:
                return self._resolve_conflicting_candidate(row, snapshot_id, direct[0], fixture_id)
            self._materialize_history_fixture(candidates[0][0], row.observed_at)
            if snapshot_id is not None:
                self._persist_deterministic_mapping(
                    row, snapshot_id, candidates[0], mapping_method="explicit_crosswalk"
                )
                self._record_mapping_decision(
                    row,
                    snapshot_id,
                    candidates[0][0],
                    "AUTO_ACCEPTED",
                    "verified provider IDs and kickoff matched",
                    {"rule": "verified_competition_team_ids_unique_kickoff_or_date_score"},
                )
            return fixture_id
        if snapshot_id is None:
            return None
        reconciled = self._reconcile_exact_fixture(row, snapshot_id)
        if reconciled is None and len(direct) == 1 and self._verified_provider_entities(row):
            return None
        provisional_id = stable_id(
            "provider-scoped-match", self.provider_code, row.provider_match_id
        )
        return reconciled or (
            provisional_id if any(item[0] == provisional_id for item in direct) else None
        )

    def _persist_deterministic_mapping(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        candidate: Sequence[Any],
        *,
        mapping_method: str = "deterministic",
        competition_only: bool = False,
    ) -> None:
        fixture_id, competition_id, home_team_id, away_team_id = candidate[:4]
        mapping_at = (
            datetime.now(UTC)
            if mapping_method in {"manual", "explicit_crosswalk"}
            else row.observed_at
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM football.providers WHERE code = %s", (self.provider_code,)
            )
            provider = cursor.fetchone()
            if provider is None:
                raise ValueError("provider registration missing")
            provider_id = provider[0]
            preserve_observations = False
            entities = (
                (
                    "competition_provider_mappings",
                    "provider_competition_id",
                    "competition_id",
                    row.provider_competition_id,
                    competition_id,
                ),
                (
                    "team_provider_mappings",
                    "provider_team_id",
                    "team_id",
                    row.provider_home_team_id,
                    home_team_id,
                ),
                (
                    "team_provider_mappings",
                    "provider_team_id",
                    "team_id",
                    row.provider_away_team_id,
                    away_team_id,
                ),
                (
                    "match_provider_mappings",
                    "provider_match_id",
                    "match_id",
                    row.provider_match_id,
                    fixture_id,
                ),
            )
            for table, identity_column, canonical_column, provider_value, canonical_value in (
                entities[:1] if competition_only else entities
            ):
                read_table = (
                    "product_effective_team_mappings"
                    if table == "team_provider_mappings"
                    else table
                )
                read_column = (
                    "effective_team_id" if table == "team_provider_mappings" else canonical_column
                )
                trust = (
                    f"football.product_mapping_trusted('team',id,{read_column})"
                    if table == "team_provider_mappings"
                    else f"football.product_mapping_trusted('competition',id,{read_column})"
                    if table == "competition_provider_mappings"
                    else "false"
                )
                cursor.execute(
                    f"""SELECT {read_column}, mapping_method, {canonical_column}, {trust}
                         FROM football.{read_table}
                         WHERE provider_id = %s AND {identity_column} = %s AND valid_to IS NULL""",
                    (provider_id, provider_value),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    corrected = existing[0] != existing[2]
                    preserve_observations |= corrected
                    admitted = existing[3]
                    if corrected and existing[0] != canonical_value:
                        raise ValueError(
                            "linked correction conflicts with requested fixture mapping"
                        )
                    if existing[0] != canonical_value or (
                        mapping_method == "manual"
                        and existing[1] != "manual"
                        and not corrected
                        and not admitted
                    ):
                        provisional_id = self._provider_scoped_identity(table, provider_value)
                        if mapping_method != "manual" and (
                            mapping_method != "explicit_crosswalk" or existing[0] != provisional_id
                        ):
                            raise ValueError(f"contradictory existing {table} mapping")
                        cursor.execute(
                            f"""UPDATE football.{table}
                                   SET valid_to = %s, last_seen_at = GREATEST(last_seen_at, %s)
                                 WHERE provider_id = %s AND {identity_column} = %s
                                   AND valid_to IS NULL""",
                            (mapping_at, mapping_at, provider_id, provider_value),
                        )
                    else:
                        cursor.execute(
                            f"""UPDATE football.{table}
                                   SET last_seen_at = GREATEST(last_seen_at, %s)
                                 WHERE provider_id = %s AND {identity_column} = %s
                                   AND valid_to IS NULL""",
                            (row.observed_at, provider_id, provider_value),
                        )
                        continue
                cursor.execute(
                    f"""INSERT INTO football.{table} (
                            {canonical_column}, provider_id, {identity_column},
                            valid_from, first_seen_at, last_seen_at,
                            mapping_method, mapping_confidence, source_snapshot_id
                         ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)""",
                    (
                        canonical_value,
                        provider_id,
                        provider_value,
                        mapping_at if mapping_method in {"manual", "explicit_crosswalk"} else None,
                        mapping_at,
                        max(mapping_at, row.observed_at),
                        mapping_method,
                        snapshot_id,
                    ),
                )
            team_aliases = (
                (row.provider_home_team_id, row.home_team_name, home_team_id),
                (row.provider_away_team_id, row.away_team_name, away_team_id),
            )
            for provider_team_id, team_name, team_id in () if competition_only else team_aliases:
                normalized_name = normalize_team_name(team_name)
                if not normalized_name:
                    logging.getLogger(__name__).warning(
                        "search alias unavailable for provider=%s team=%s snapshot=%s; "
                        "original name retained",
                        self.provider_code,
                        provider_team_id,
                        snapshot_id,
                    )
                    continue
                cursor.execute(
                    """INSERT INTO football.product_team_aliases (
                           provider_code, provider_team_id, normalized_name, team_id
                       ) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (provider_code, provider_team_id) DO UPDATE SET
                           normalized_name = EXCLUDED.normalized_name,
                           team_id = CASE WHEN %s IN ('manual', 'explicit_crosswalk')
                               THEN EXCLUDED.team_id
                               ELSE football.product_team_aliases.team_id END""",
                    (
                        self.provider_code,
                        provider_team_id,
                        normalized_name,
                        team_id,
                        mapping_method,
                    ),
                )
            if not preserve_observations and not competition_only:
                cursor.execute(
                    """UPDATE football.product_provider_resource_observations
                      SET canonical_fixture_id = %s,
                          known_at = CASE WHEN point_in_time_eligibility = 'UNKNOWN'
                              THEN GREATEST(COALESCE(known_at, observed_at), %s)
                              ELSE known_at END,
                          point_in_time_eligibility = CASE
                              WHEN point_in_time_eligibility = 'UNKNOWN' THEN 'ELIGIBLE'
                              ELSE point_in_time_eligibility END
                    WHERE provider_code = %s AND provider_match_id = %s""",
                    (fixture_id, mapping_at, self.provider_code, row.provider_match_id),
                )
        self._store_observation(row, snapshot_id, fixture_id)

    def _create_provider_scoped_fixture(
        self, row: FixtureObservation, snapshot_id: UUID, *, season_label: str | None = None
    ) -> UUID | None:
        """Create a provisional fixture only when its competition season is known."""
        season_label = self._usable_provider_season_label(row, snapshot_id, season_label)
        if season_label is None:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.competition_id
                     FROM football.competition_provider_mappings mapping
                     JOIN football.providers provider ON provider.id = mapping.provider_id
                    WHERE provider.code = %s
                      AND mapping.provider_competition_id = %s
                      AND mapping.valid_to IS NULL
                      AND mapping.mapping_confidence = 1""",
                (self.provider_code, row.provider_competition_id),
            )
            mapped_competition = cursor.fetchone()
        competition_id = (
            cast(UUID, mapped_competition[0])
            if mapped_competition is not None
            else stable_id(
                "provider-scoped-competition", self.provider_code, row.provider_competition_id
            )
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT season_label, metadata_status, geographic_scope
                   FROM football.product_competitions
                   WHERE competition_id = %s""",
                (competition_id,),
            )
            metadata = cursor.fetchone()
        season_label = self._usable_provider_season_label(row, snapshot_id, season_label, metadata)
        if season_label is None:
            return None
        existing_mapping = self.connection.execute(
            """SELECT mapping.match_id
                 FROM football.match_provider_mappings mapping
                 JOIN football.providers provider ON provider.id=mapping.provider_id
                WHERE provider.code=%s AND mapping.provider_match_id=%s
                  AND mapping.valid_to IS NULL""",
            (self.provider_code, row.provider_match_id),
        ).fetchone()
        provisional_id = self._provider_scoped_identity(
            "match_provider_mappings", row.provider_match_id
        )
        if existing_mapping is not None and existing_mapping[0] != provisional_id:
            return None
        self._load_geographic_scopes()
        assert self._geographic_scopes is not None
        geographic_scope = self._geographic_scopes.get(row.provider_competition_id)
        if metadata is not None and metadata[2] is not None:
            if geographic_scope is not None and geographic_scope != metadata[2]:
                raise ValueError("CONFLICTING_COMPETITION_GEOGRAPHY")
            geographic_scope = metadata[2]
        if geographic_scope is None:
            self._record_mapping_decision(
                row,
                snapshot_id,
                None,
                "REVIEW_REQUIRED",
                "CANONICAL_FIXTURE_GEOGRAPHY_REQUIRED",
                {},
            )
            return None
        source_season_label = season_label
        season_label = self._canonical_crosswalk_season_label(row, metadata, season_label)
        season_id = stable_id("season", competition_id, season_label)
        home_id = self._mapped_or_scoped_team(row.provider_home_team_id)
        away_id = self._mapped_or_scoped_team(row.provider_away_team_id)
        verified = self._fixture_identity_is_verified(
            row, competition_id, metadata, season_label, home_id, away_id
        )
        fixture_id = (
            fixture_identity(competition_id, season_label, row.kickoff_at, home_id, away_id)
            if verified
            else stable_id("provider-scoped-match", self.provider_code, row.provider_match_id)
        )
        if home_id == away_id:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO football.competitions (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (competition_id,),
            )
            cursor.execute(
                """INSERT INTO football.product_competitions (
                       competition_id, name, country, continent, division,
                       competition_type, season_label, fixtures_available,
                       results_available, availability_status, source_roles, updated_at,
                       metadata_status, geographic_scope
                   ) VALUES (%s, %s, 'Unknown', 'Unknown', NULL, 'UNKNOWN', %s, true, %s,
                       'SOURCE_DATA_INCOMPLETE', %s::jsonb, %s, 'PROVISIONAL', %s)
                   ON CONFLICT (competition_id) DO UPDATE SET
                       geographic_scope = COALESCE(
                           football.product_competitions.geographic_scope,
                           EXCLUDED.geographic_scope),
                       updated_at = GREATEST(
                           football.product_competitions.updated_at, EXCLUDED.updated_at
                       )""",
                (
                    competition_id,
                    row.provider_competition_name,
                    season_label,
                    row.status == "FINISHED" and row.home_score is not None,
                    json.dumps(
                        {
                            "fixtures": [self.provider_code],
                            "results": [self.provider_code],
                            "standings": [],
                            "h2h": [],
                            "team_stats": [],
                        },
                        sort_keys=True,
                    ),
                    row.observed_at,
                    geographic_scope,
                ),
            )
            cursor.execute(
                """INSERT INTO football.seasons (id, competition_id)
                   VALUES (%s, %s) ON CONFLICT DO NOTHING""",
                (season_id, competition_id),
            )
            for team_id, name in ((home_id, row.home_team_name), (away_id, row.away_team_name)):
                cursor.execute(
                    """INSERT INTO football.teams (id, entity_kind)
                       VALUES (%s, 'club') ON CONFLICT DO NOTHING""",
                    (team_id,),
                )
                cursor.execute(
                    """INSERT INTO football.product_teams (team_id, name, updated_at)
                       VALUES (%s, %s, %s) ON CONFLICT (team_id) DO UPDATE SET
                           updated_at = GREATEST(
                               football.product_teams.updated_at, EXCLUDED.updated_at
                           )""",
                    (team_id, name, row.observed_at),
                )
            cursor.execute(
                """INSERT INTO football.matches (id, competition_id, season_id)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                (fixture_id, competition_id, season_id),
            )
            cursor.execute(
                """INSERT INTO football.product_fixtures (
                       fixture_id, competition_id, home_team_id, away_team_id,
                       kickoff_at, status, home_score, away_score,
                       forecast_availability, updated_at, result_score_basis, identity_status
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s)
                   ON CONFLICT (fixture_id) DO NOTHING""",
                (
                    fixture_id,
                    competition_id,
                    home_id,
                    away_id,
                    row.kickoff_at,
                    row.status,
                    row.home_score,
                    row.away_score,
                    "NOT_ENOUGH_HISTORY" if verified else "SOURCE_DATA_INCOMPLETE",
                    row.source_updated_at or row.observed_at,
                    row.result_score_basis,
                    "VERIFIED" if verified else "PROVISIONAL",
                ),
            )
            created = cursor.rowcount == 1
        candidate = (
            fixture_id,
            competition_id,
            home_id,
            away_id,
            row.provider_competition_name,
            row.home_team_name,
            row.away_team_name,
            row.status,
            row.home_score,
            row.away_score,
        )
        self._persist_deterministic_mapping(
            row,
            snapshot_id,
            candidate,
            mapping_method="explicit_crosswalk" if verified else "deterministic",
        )
        self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "AUTO_ACCEPTED",
            "provider-scoped canonical fixture created",
            {
                "identity_scope": "verified_provider_ids" if verified else "provider",
                "forecast_eligible": verified,
                "season_label": season_label,
                "source_season_label": source_season_label,
            },
        )
        return fixture_id if created else fixture_id

    def _insert_qualified_history(
        self, row: FixtureObservation, fixture_id: UUID, snapshot_id: UUID
    ) -> int:
        if row.status != "FINISHED" or row.home_score is None or row.away_score is None:
            return 0
        with self.connection.cursor() as cursor:
            if row.result_score_basis != "REGULATION_90":
                if self.provider_code != "pitchapi":
                    return 0
                cursor.execute(
                    """SELECT competition.competition_type,
                              fixture.forecast_availability
                         FROM football.product_effective_fixtures fixture
                         JOIN football.product_competitions competition
                           ON competition.competition_id = fixture.competition_id
                        WHERE fixture.fixture_id = %s""",
                    (fixture_id,),
                )
                qualification = cursor.fetchone()
                if (
                    qualification is None
                    or qualification[0] != "LEAGUE"
                    or qualification[1] == "SOURCE_DATA_INCOMPLETE"
                ):
                    return 0
            cursor.execute(
                """INSERT INTO football.product_team_match_history (
                       fixture_id, competition_id, home_team_id, away_team_id,
                       kickoff_at, home_goals, away_goals, source_provider_code,
                       source_snapshot_id, source_kickoff_precision
                   ) SELECT fixture_id, competition_id, home_team_id, away_team_id,
                            kickoff_at, %s, %s, %s, %s, 'EXACT'
                       FROM football.product_effective_fixtures WHERE fixture_id = %s
                   ON CONFLICT (fixture_id) DO UPDATE SET
                       competition_id=EXCLUDED.competition_id,
                       home_team_id=EXCLUDED.home_team_id,away_team_id=EXCLUDED.away_team_id,
                       kickoff_at=EXCLUDED.kickoff_at,
                       source_provider_code=EXCLUDED.source_provider_code,
                       source_snapshot_id=EXCLUDED.source_snapshot_id,
                       source_kickoff_precision=EXCLUDED.source_kickoff_precision
                   WHERE %s AND
                     (football.product_team_match_history.home_goals,
                      football.product_team_match_history.away_goals)=
                     (EXCLUDED.home_goals,EXCLUDED.away_goals)
                     AND NOT EXISTS (SELECT 1 FROM football.product_eligible_fixture_history_at(
                         statement_timestamp(),ARRAY[EXCLUDED.fixture_id]))
                     AND (football.product_team_match_history.source_provider_code,
                          football.product_team_match_history.source_snapshot_id)
                         IS DISTINCT FROM
                         (EXCLUDED.source_provider_code,EXCLUDED.source_snapshot_id)""",
                (
                    row.home_score,
                    row.away_score,
                    self.provider_code,
                    snapshot_id,
                    fixture_id,
                    self._verified_provider_entities(row),
                ),
            )
            return cursor.rowcount

    def _retained_fixture_members(self, row: FixtureObservation) -> list[UUID]:
        members = self.connection.execute(
            """SELECT DISTINCT canonical_fixture_id
               FROM football.product_provider_fixture_observations
               WHERE provider_code=%s AND provider_match_id=%s
                 AND provider_competition_id=%s AND provider_home_team_id=%s
                 AND provider_away_team_id=%s AND kickoff_at=%s
                 AND canonical_fixture_id IS NOT NULL""",
            (
                self.provider_code,
                row.provider_match_id,
                row.provider_competition_id,
                row.provider_home_team_id,
                row.provider_away_team_id,
                row.kickoff_at,
            ),
        ).fetchall()
        return [member[0] for member in members]

    def _resolve_reviewed_member(
        self,
        original: UUID | None,
        target: tuple[Any, ...],
        row: FixtureObservation,
        snapshot: UUID,
        review: UUID,
    ) -> None:
        if original is None or original == target[0]:
            return
        evidence = {
            "provider_mapping_decision_id": str(review),
            "provider": self.provider_code,
            "provider_match_id": row.provider_match_id,
            "source_snapshot_id": str(snapshot),
            "original_fixture_id": str(original),
            "reviewed_fixture_id": str(target[0]),
        }
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK, FIXTURE_CROSSWALK_LOCK))
        provisional = self.connection.execute(
            "SELECT identity_status,kickoff_at,status,home_score,away_score "
            "FROM football.product_fixtures "
            "WHERE fixture_id = %s FOR UPDATE",
            (original,),
        ).fetchone()
        if provisional is None or provisional[0] not in {"PROVISIONAL", "VERIFIED"}:
            return
        if provisional[1] != row.kickoff_at or (
            provisional[2] == row.status == "FINISHED"
            and (provisional[3], provisional[4]) != (row.home_score, row.away_score)
        ):
            raise ValueError("retained fixture member contradicts reviewed context")
        if self.connection.execute(
            """SELECT 1 FROM football.fixture_identity_resolutions
               WHERE member_fixture_id=%s AND representative_fixture_id=%s
                 AND resolution_status='DUPLICATE_RESOLVED' AND active""",
            (original, target[0]),
        ).fetchone():
            return
        self.connection.execute(
            """UPDATE football.fixture_identity_resolutions SET active = false
               WHERE member_fixture_id = %s AND active""",
            (original,),
        )
        self.connection.execute(
            """INSERT INTO football.fixture_identity_resolutions (
                   canonical_real_fixture_id, member_fixture_id, representative_fixture_id,
                   resolution_status, selected_competition_id, resolution_reason, evidence_json,
                   evidence_sha256, resolution_version, active, created_at)
               VALUES (%s, %s, %s, 'DUPLICATE_RESOLVED', %s,
                       'Reviewed retained provider IDs and fixture context',
                       %s::jsonb, %s, %s, true, clock_timestamp())""",
            (
                target[0],
                original,
                target[0],
                target[1],
                json.dumps(evidence),
                sha256_json(evidence),
                f"operator-review:{review}",
            ),
        )

    def _reconcile_retained_members(
        self, row: FixtureObservation, fixture_id: UUID, snapshot: UUID
    ) -> None:
        """Reconcile earlier copies only after native competition and team IDs qualify."""
        if not self._verified_provider_entities(row):
            return
        target = self.connection.execute(
            """SELECT fixture_id,competition_id,home_team_id,away_team_id
               FROM football.product_effective_fixtures WHERE fixture_id=%s
                 AND identity_status='VERIFIED' AND kickoff_at=%s""",
            (fixture_id, row.kickoff_at),
        ).fetchone()
        if target is None or self._candidate_mapping_conflict(row, target) is not None:
            return
        members = [member for member in self._retained_fixture_members(row) if member != fixture_id]
        quarantine = self.connection.execute(
            """SELECT canonical_real_fixture_id,evidence_sha256
               FROM football.fixture_identity_resolutions WHERE member_fixture_id=%s AND active
                 AND resolution_status='AMBIGUOUS_QUARANTINED'
                 AND resolution_reason='PROVISIONAL_PROVIDER_IDENTITY'
                 AND evidence_json->'member_fixture_ids'=jsonb_build_array(%s::text)""",
            (fixture_id, fixture_id),
        ).fetchone()
        if not members and quarantine is None:
            return
        decision = self._record_mapping_decision(
            row,
            snapshot,
            fixture_id,
            "AUTO_ACCEPTED",
            "admitted native IDs identify retained fixture members",
            {"rule": "admitted_competition_home_away_exact_kickoff_native_fixture_id"},
        )
        for member in members:
            try:
                self._resolve_reviewed_member(member, target, row, snapshot, decision)
            except ValueError as error:
                reason = str(error).splitlines()[0]
                if reason != "retained fixture member contradicts reviewed context":
                    raise
                self._record_mapping_decision(
                    row,
                    snapshot,
                    fixture_id,
                    "CONTRADICTORY",
                    reason,
                    {
                        "member_fixture_id": str(member),
                        "rule": "retained_provider_observation_context_review",
                    },
                )
        if quarantine is not None:
            evidence = {
                "provider_mapping_decision_id": str(decision),
                "source_snapshot_id": str(snapshot),
                "previous_evidence_sha256": quarantine[1],
            }
            self.connection.execute(
                """UPDATE football.fixture_identity_resolutions SET active=false
                   WHERE member_fixture_id=%s AND active""",
                (fixture_id,),
            )
            self.connection.execute(
                """INSERT INTO football.fixture_identity_resolutions (
                     canonical_real_fixture_id,member_fixture_id,representative_fixture_id,
                     resolution_status,selected_competition_id,resolution_reason,evidence_json,
                     evidence_sha256,resolution_version,active,created_at)
                   VALUES (%s,%s,%s,'UNIQUE',%s,'Admitted native provider identities',
                           %s::jsonb,%s,%s,true,clock_timestamp())""",
                (
                    quarantine[0],
                    fixture_id,
                    fixture_id,
                    target[1],
                    json.dumps(evidence),
                    sha256_json(evidence),
                    f"admitted-native-ids:{decision}",
                ),
            )
