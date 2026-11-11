"""Persistence layer for the operational provider sync."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from football.product.competition_geography import (
    verified_geographic_scopes,
)
from football.product.domain import (
    canonical_json,
    sha256_json,
    stable_id,
)
from football.product.live_resources import (
    LiveUpdate,
    live_update_order,
)
from football.product.operational_support import (
    DetailCounts,
    FixtureObservation,
    OperationalProviderSyncBase,
    _fixture_observation_sha256,
    _valid_transition,
)
from football.providers.fotmob import (
    FotmobResponse,
)
from football.providers.pitchapi import (
    PitchApiResponse,
)
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks
from football.storage.raw import ImmutableFileStore


class OperationalStoreMixin(OperationalProviderSyncBase):
    """Persist provider responses, observations, mapping decisions and live updates."""

    def _record_response(self, resource_name: str, response: Any) -> UUID:
        digest = response.sha256
        provider_id = stable_id("provider", self.provider_code)
        snapshot_id = stable_id("source-snapshot", self.provider_code, resource_name, digest)
        resource_id = stable_id("source-resource", snapshot_id, resource_name)
        relative = (
            Path("operational")
            / self.provider_code
            / response.fetched_at.strftime("%Y/%m/%d")
            / f"{digest}.json"
        )
        ImmutableFileStore(self.data_root).publish(str(relative), response.raw)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.providers (id, code, name, source_type)
                VALUES (%s, %s, %s, 'http_api') ON CONFLICT (code) DO NOTHING
                """,
                (provider_id, self.provider_code, self.provider_code),
            )
            cursor.execute(
                """
                INSERT INTO football.source_snapshots (
                    id, provider_id, source_identity, source_revision, acquired_at,
                    manifest_path, manifest_sha256, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'validated')
                ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
                """,
                (
                    snapshot_id,
                    provider_id,
                    resource_name,
                    digest,
                    response.fetched_at,
                    str(relative),
                    digest,
                ),
            )
            cursor.execute(
                """
                INSERT INTO football.source_resources (
                    id, source_snapshot_id, provider_path, sha256, size_bytes,
                    media_type, parse_status, validation_status, acquired_at
                ) VALUES (%s, %s, %s, %s, %s, 'application/json', 'parsed', 'valid', %s)
                ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
                """,
                (
                    resource_id,
                    snapshot_id,
                    resource_name,
                    digest,
                    len(response.raw),
                    response.fetched_at,
                ),
            )
            if cursor.rowcount:
                self._geographic_scopes = None
        return snapshot_id

    def _record_mapping_decision(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        fixture_id: UUID | None,
        disposition: str,
        reason: str,
        evidence: Mapping[str, Any],
    ) -> UUID:
        semantic = sha256_json(
            {
                "provider": self.provider_code,
                "match": row.provider_match_id,
                "fixture": str(fixture_id) if fixture_id else None,
                "disposition": disposition,
                "reason": reason,
                "evidence": evidence,
                "snapshot": str(snapshot_id),
            }
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO football.product_provider_mapping_decisions (
                       semantic_sha256, provider_code, provider_match_id,
                       candidate_fixture_id, disposition, reason, evidence,
                       source_snapshot_id, observed_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (semantic_sha256) DO NOTHING RETURNING decision_id""",
                (
                    semantic,
                    self.provider_code,
                    row.provider_match_id,
                    fixture_id,
                    disposition,
                    reason,
                    json.dumps(dict(evidence), sort_keys=True),
                    snapshot_id,
                    row.observed_at,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                inserted = cursor.execute(
                    """SELECT decision_id FROM football.product_provider_mapping_decisions
                       WHERE semantic_sha256 = %s""",
                    (semantic,),
                ).fetchone()
            assert inserted is not None
            return cast(UUID, inserted[0])

    def _store_observation(
        self, row: FixtureObservation, snapshot_id: UUID, fixture_id: UUID | None
    ) -> bool:
        provider_status = row.provider_status or None
        semantic = _fixture_observation_sha256(self.provider_code, row, fixture_id)
        cache_expires = getattr(row, "cache_expires_at", None)
        stale_after = max(
            row.observed_at + self.stale_after,
            cache_expires or row.observed_at,
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.product_provider_fixture_observations (
                    semantic_sha256, provider_code, provider_match_id,
                    provider_competition_id, provider_competition_name,
                    provider_home_team_id, provider_home_team_name,
                    provider_away_team_id, provider_away_team_name,
                    canonical_fixture_id, source_snapshot_id,
                    kickoff_at, canonical_status, provider_status, home_score, away_score,
                    match_minute, added_time, period, source_updated_at, observed_at,
                    cache_expires_at, stale_after, last_fetched_at, result_score_basis
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (semantic_sha256) DO UPDATE SET
                    provider_competition_name = COALESCE(
                        football.product_provider_fixture_observations.provider_competition_name,
                        EXCLUDED.provider_competition_name
                    ),
                    provider_home_team_name = COALESCE(
                        football.product_provider_fixture_observations.provider_home_team_name,
                        EXCLUDED.provider_home_team_name
                    ),
                    provider_away_team_name = COALESCE(
                        football.product_provider_fixture_observations.provider_away_team_name,
                        EXCLUDED.provider_away_team_name
                    ),
                    last_fetched_at = GREATEST(
                        football.product_provider_fixture_observations.last_fetched_at,
                        EXCLUDED.last_fetched_at
                    ),
                    cache_expires_at = EXCLUDED.cache_expires_at,
                    stale_after = EXCLUDED.stale_after
                RETURNING xmax = 0
                """,
                (
                    semantic,
                    self.provider_code,
                    row.provider_match_id,
                    row.provider_competition_id,
                    row.provider_competition_name,
                    row.provider_home_team_id,
                    row.home_team_name,
                    row.provider_away_team_id,
                    row.away_team_name,
                    fixture_id,
                    snapshot_id,
                    row.kickoff_at,
                    row.status,
                    provider_status,
                    row.home_score,
                    row.away_score,
                    row.minute,
                    row.added_time,
                    row.period,
                    row.source_updated_at,
                    row.observed_at,
                    cache_expires,
                    stale_after,
                    row.observed_at,
                    row.result_score_basis,
                ),
            )
            result = cursor.fetchone()
            return bool(result and result[0])

    def _update_canonical_fixture(
        self, row: FixtureObservation, fixture_id: UUID, snapshot_id: UUID
    ) -> int:
        if row.status == "FINISHED":
            return self._apply_finished_result(row, fixture_id, snapshot_id)
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        incoming_at = row.source_updated_at or row.observed_at
        with self.connection.cursor() as cursor:
            current = cursor.execute(
                """SELECT status, updated_at,home_score,away_score FROM football.product_fixtures
                    WHERE fixture_id = %s FOR UPDATE""",
                (fixture_id,),
            ).fetchone()
            if current is None or not _valid_transition(current[0], row.status):
                return 0
            if (current[0], current[2], current[3]) == (row.status, row.home_score, row.away_score):
                return 0
            previous, incoming = self._live_update_evidence(row, fixture_id, current)
            if live_update_order(previous, incoming) not in {"NEWER", "SAME"}:
                return 0
            cursor.execute(
                """UPDATE football.product_fixtures
                      SET status = %s, home_score = %s, away_score = %s, updated_at = %s
                    WHERE fixture_id = %s AND status = %s AND updated_at = %s
                      AND (status, home_score, away_score)
                          IS DISTINCT FROM (%s, %s, %s)""",
                (
                    row.status,
                    row.home_score,
                    row.away_score,
                    incoming_at,
                    fixture_id,
                    current[0],
                    current[1],
                    row.status,
                    row.home_score,
                    row.away_score,
                ),
            )
            return cursor.rowcount

    def _live_update_evidence(
        self, row: FixtureObservation, fixture_id: UUID, current: tuple[Any, ...]
    ) -> tuple[LiveUpdate, LiveUpdate]:
        semantic = _fixture_observation_sha256(self.provider_code, row, fixture_id)
        incoming_known = self.connection.execute(
            "SELECT observed_at FROM football.product_provider_fixture_observations "
            "WHERE semantic_sha256=%s",
            (semantic,),
        ).fetchone()
        source = self.connection.execute(
            """SELECT provider_code,canonical_status,
            home_score,away_score,match_minute,added_time,source_updated_at,observed_at,
            provider_status,period
            FROM football.product_provider_fixture_observations
            WHERE (canonical_fixture_id=%s OR (provider_code=%s AND provider_match_id=%s))
                AND kickoff_at=%s
                AND canonical_status=%s AND home_score IS NOT DISTINCT FROM %s
                AND away_score IS NOT DISTINCT FROM %s AND semantic_sha256<>%s
            ORDER BY match_minute DESC NULLS LAST,added_time DESC NULLS LAST,
                CASE WHEN provider_code=%s THEN 0 ELSE 1 END,
                CASE WHEN source_updated_at<=observed_at THEN source_updated_at END
                DESC NULLS LAST,observed_at DESC,observation_id DESC LIMIT 1""",
            (
                fixture_id,
                self.provider_code,
                row.provider_match_id,
                row.kickoff_at,
                current[0],
                current[2],
                current[3],
                semantic,
                self.provider_code,
            ),
        ).fetchone()
        # Without a retained source, the canonical receipt is only an upper bound.
        # It never stands in for a provider football update timestamp.
        previous = LiveUpdate(
            provider=source[0] if source else "",
            status=current[0],
            home_score=current[2],
            away_score=current[3],
            minute=source[4] if source else None,
            added_time=source[5] if source else None,
            source_updated_at=source[6] if source else None,
            known_by=source[7] if source else current[1],
        )
        # Earlier FotMob rows retained the explicit HT marker but called its status LIVE.
        # Reconcile that interpretation without claiming a newer football timestamp.
        if source and source[0] == "fotmob" and source[8] == "HT" and source[9] == "HT":
            previous = replace(previous, status="HALF_TIME")
        incoming = LiveUpdate(
            provider=self.provider_code,
            status=row.status,
            home_score=row.home_score,
            away_score=row.away_score,
            minute=row.minute,
            added_time=row.added_time,
            source_updated_at=row.source_updated_at,
            known_by=incoming_known[0] if incoming_known else row.observed_at,
        )
        return previous, incoming

    def _apply_finished_result(
        self, row: FixtureObservation, fixture_id: UUID, snapshot_id: UUID
    ) -> int:
        if row.home_score is None or row.away_score is None:
            return 0
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, home_score, away_score, updated_at
                FROM football.product_fixtures WHERE fixture_id = %s FOR UPDATE
                """,
                (fixture_id,),
            )
            existing = cursor.fetchone()
            if existing is None:
                return 0
            existing_status, existing_home, existing_away, existing_updated_at = existing
            incoming_at = row.source_updated_at or row.observed_at
            if existing_status != "FINISHED":
                previous, incoming = self._live_update_evidence(
                    row,
                    fixture_id,
                    (existing_status, existing_updated_at, existing_home, existing_away),
                )
                if not _valid_transition(existing_status, row.status) or live_update_order(
                    previous, incoming
                ) not in {"NEWER", "SAME"}:
                    return 0
            if (
                existing_status == "FINISHED"
                and existing_home is not None
                and (existing_home, existing_away) != (row.home_score, row.away_score)
            ):
                conflict = sha256_json(
                    {
                        "fixture_id": str(fixture_id),
                        "existing": [existing_home, existing_away],
                        "incoming": [row.home_score, row.away_score],
                        "provider": self.provider_code,
                        "snapshot": str(snapshot_id),
                    }
                )
                cursor.execute(
                    """
                    SELECT history.source_provider_code, history.source_snapshot_id
                    FROM football.product_team_match_history history
                    WHERE history.fixture_id = %s
                    """,
                    (fixture_id,),
                )
                source = cursor.fetchone()
                if source is not None:
                    cursor.execute(
                        """
                        INSERT INTO football.product_source_result_conflicts (
                            canonical_match_id, existing_provider_code, existing_home_goals,
                            existing_away_goals, existing_snapshot_id, incoming_provider_code,
                            incoming_home_goals, incoming_away_goals, incoming_snapshot_id,
                            conflict_key
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (conflict_key) DO NOTHING
                        """,
                        (
                            fixture_id,
                            source[0],
                            existing_home,
                            existing_away,
                            source[1],
                            self.provider_code,
                            row.home_score,
                            row.away_score,
                            snapshot_id,
                            conflict,
                        ),
                    )
                return 0
            cursor.execute(
                """
                UPDATE football.product_fixtures
                   SET status = 'FINISHED', home_score = %s, away_score = %s,
                       result_score_basis = %s, updated_at = %s
                 WHERE fixture_id = %s
                   AND (status <> 'FINISHED' OR home_score IS NULL OR away_score IS NULL
                        OR (result_score_basis = 'UNKNOWN' AND %s = 'REGULATION_90'
                            AND home_score = %s AND away_score = %s))
                """,
                (
                    row.home_score,
                    row.away_score,
                    row.result_score_basis,
                    incoming_at,
                    fixture_id,
                    row.result_score_basis,
                    row.home_score,
                    row.away_score,
                ),
            )
            return cursor.rowcount

    def _load_geographic_scopes(self) -> None:
        if self._geographic_scopes is None:
            self._geographic_scopes = verified_geographic_scopes(
                self.connection, self.data_root, self.provider_code
            )

    def _store_resource(
        self,
        provider_match_id: str,
        fixture_id: UUID | None,
        resource_type: str,
        payload: Mapping[str, Any] | list[Any],
        response: FotmobResponse | PitchApiResponse,
        snapshot_id: UUID,
        *,
        eligibility: str,
    ) -> int:
        semantic = hashlib.sha256(
            canonical_json(
                {
                    "provider": self.provider_code,
                    "match": provider_match_id,
                    "resource": resource_type,
                    "payload": payload,
                    "source_checksum": response.sha256,
                }
            )
        ).hexdigest()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.product_provider_resource_observations (
                    semantic_sha256, provider_code, provider_match_id,
                    canonical_fixture_id, resource_type, availability_status,
                    source_snapshot_id, source_checksum, observed_at, known_at,
                    point_in_time_eligibility, development_only, payload, last_fetched_at
                ) VALUES (%s, %s, %s, %s, %s, 'AVAILABLE', %s, %s, %s, %s, %s, true, %s, %s)
                ON CONFLICT (semantic_sha256) DO UPDATE SET
                    last_fetched_at = GREATEST(
                        football.product_provider_resource_observations.last_fetched_at,
                        EXCLUDED.last_fetched_at
                    )
                """,
                (
                    semantic,
                    self.provider_code,
                    provider_match_id,
                    fixture_id,
                    resource_type,
                    snapshot_id,
                    response.sha256,
                    response.fetched_at,
                    response.fetched_at,
                    eligibility,
                    json.dumps(payload, sort_keys=True),
                    response.fetched_at,
                ),
            )
            return cursor.rowcount

    def _claim_refresh(self, name: str) -> datetime | None:
        row = self.connection.execute(
            """INSERT INTO football.product_provider_refresh_state (
                   provider_code,resource_name,last_attempt_at,next_attempt_at)
               VALUES (%s,%s,clock_timestamp(),clock_timestamp()+%s)
               ON CONFLICT (provider_code,resource_name) DO UPDATE
               SET last_attempt_at=EXCLUDED.last_attempt_at,
                   next_attempt_at=EXCLUDED.next_attempt_at
               WHERE football.product_provider_refresh_state.next_attempt_at <= clock_timestamp()
               RETURNING last_attempt_at""",
            (self.provider_code, name, self.stale_after),
        ).fetchone()
        self.connection.commit()
        return cast(datetime, row[0]) if row is not None else None

    def _complete_refresh(
        self, name: str, claimed: datetime, item: DetailCounts, *, error: str | None = None
    ) -> None:
        self.connection.execute(
            """UPDATE football.product_provider_refresh_state
               SET last_success_at=CASE WHEN %s = 0 THEN clock_timestamp() ELSE last_success_at END,
                   next_attempt_at=GREATEST(clock_timestamp()+%s,%s),
                   failed_requests=%s,last_error=CASE WHEN %s > 0 THEN %s END
               WHERE provider_code=%s AND resource_name=%s AND last_attempt_at=%s""",
            (
                item.failed_requests,
                timedelta(days=1) if error == "RECOVERY_FIXTURES_MISSING" else self.stale_after,
                item.fresh_until if item.failed_requests == 0 else None,
                item.failed_requests,
                item.failed_requests,
                error or "DETAIL_REQUEST_FAILED",
                self.provider_code,
                name,
                claimed,
            ),
        )
        self.connection.commit()

    def _record_failed_observation(
        self, row: FixtureObservation, snapshot_id: UUID, reason: str
    ) -> None:
        with self.connection.transaction():
            self._store_observation(row, snapshot_id, None)
            self._record_mapping_decision(
                row,
                snapshot_id,
                None,
                "REVIEW_REQUIRED",
                "historical admission failed",
                {
                    "error": reason,
                    "kickoff_at": row.kickoff_at.isoformat(),
                    "provider_competition_id": row.provider_competition_id,
                },
            )
            self.connection.execute("SELECT football.check_provider_scope_work()")

    def _sync_diagnostics(self, sync_started: datetime, from_date: date) -> dict[str, object]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT reason, count(*)
                     FROM football.product_provider_mapping_decisions
                    WHERE provider_code = %s AND observed_at >= %s
                      AND disposition IN ('REVIEW_REQUIRED', 'CONTRADICTORY')
                    GROUP BY reason ORDER BY reason""",
                (self.provider_code, sync_started),
            )
            reasons = {reason: count for reason, count in cursor.fetchall()}
            cursor.execute(
                """SELECT observed_at, last_fetched_at, stale_after
                     FROM football.product_provider_fixture_observations
                    WHERE provider_code = %s
                    ORDER BY last_fetched_at DESC, observation_id DESC LIMIT 1""",
                (self.provider_code,),
            )
            freshness = cursor.fetchone()
        capabilities = [
            "fixtures",
            "live_scores",
            "match_details",
            "statistics",
            "shots",
            "lineups",
            "player_ratings",
            "h2h",
        ]
        if self.provider_code == "pitchapi":
            capabilities.extend(("events", "momentum"))
        return {
            "unmatched_reasons": reasons,
            "effective_capabilities": capabilities,
            "latest_observed_at": freshness[0].isoformat() if freshness else None,
            "latest_fetched_at": freshness[1].isoformat() if freshness else None,
            "latest_stale_after": freshness[2].isoformat() if freshness else None,
            "lifecycle_recovery": self._lifecycle_diagnostics(from_date),
        }

    def _lifecycle_diagnostics(self, from_date: date) -> dict[str, int]:
        row = self.connection.execute(
            """WITH unresolved AS (
                 SELECT fixture_id FROM football.product_fixtures f
                 WHERE status IN (
                     'SCHEDULED','LIVE','HALF_TIME','SUSPENDED','INTERRUPTED','POSTPONED')
                   AND kickoff_at < (%s::date::timestamp AT TIME ZONE 'UTC')
                   AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions resolution
                                   WHERE resolution.member_fixture_id=f.fixture_id
                                     AND resolution.active))
               SELECT (SELECT count(*) FROM unresolved),
                      (SELECT count(DISTINCT fixture_id) FROM football.product_recoverable_fixtures
                       WHERE provider_code=%s
                         AND fixture_id IN (SELECT fixture_id FROM unresolved)),
                      (SELECT count(*) FROM unresolved u WHERE NOT EXISTS (
                          SELECT 1 FROM football.product_recoverable_fixtures r
                          WHERE r.fixture_id=u.fixture_id)),
                      (SELECT count(*) FROM football.product_provider_refresh_state
                       WHERE provider_code=%s AND next_attempt_at>clock_timestamp()),
                      (SELECT count(*) FROM football.product_provider_refresh_state
                       WHERE provider_code=%s AND failed_requests>0)""",
            (from_date, self.provider_code, self.provider_code, self.provider_code),
        ).fetchone()
        assert row is not None
        return dict(
            zip(
                (
                    "unresolved_outside_window",
                    "recoverable_for_provider",
                    "without_verified_supported_provider",
                    "cooldown_resources",
                    "failed_refresh_resources",
                ),
                row,
                strict=True,
            )
        )
