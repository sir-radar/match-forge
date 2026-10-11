"""Idempotent operational fixture sync for FotMob and PitchAPI."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast
from uuid import UUID

from psycopg import Connection

from football.product.domain import canonical_json, normalize_team_name, sha256_json, stable_id
from football.product.external_predictions import settle_external_predictions
from football.providers.fotmob import (
    FotmobClient,
    FotmobLiveScore,
    FotmobResponse,
    normalize_daily_matches,
)
from football.providers.pitchapi import (
    PitchApiClient,
    PitchApiFixture,
    PitchApiResponse,
    normalize_pitchapi_matches,
)

FixtureObservation = FotmobLiveScore | PitchApiFixture


@dataclass(slots=True)
class SyncCounts:
    attempted_requests: int = 0
    successful_requests: int = 0
    fetched: int = 0
    matched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    unmatched: int = 0
    failed: int = 0
    resources: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "attempted_requests": self.attempted_requests,
            "successful_requests": self.successful_requests,
            "fetched": self.fetched,
            "matched": self.matched,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "unmatched": self.unmatched,
            "failed": self.failed,
            "resources": self.resources,
        }


@dataclass(frozen=True, slots=True)
class DetailCounts:
    attempted_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    resources: int = 0


class RequestPacer:
    def __init__(self, minimum_interval_seconds: float) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("provider minimum interval must be non-negative")
        self._interval = minimum_interval_seconds
        self._last: float | None = None

    def wait(self) -> None:
        now = monotonic()
        if self._last is not None:
            remaining = self._interval - (now - self._last)
            if remaining > 0:
                sleep(remaining)
        self._last = monotonic()


class OperationalProviderSync:
    def __init__(
        self,
        connection: Connection[Any],
        data_root: Path,
        *,
        provider_code: str,
        stale_after_seconds: int = 180,
        minimum_interval_seconds: float = 1.0,
        kickoff_tolerance_minutes: int = 10,
    ) -> None:
        if stale_after_seconds <= 0 or not 0 <= kickoff_tolerance_minutes <= 60:
            raise ValueError("invalid operational provider sync limits")
        self.connection = connection
        self.data_root = data_root
        self.provider_code = provider_code
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.kickoff_tolerance = timedelta(minutes=kickoff_tolerance_minutes)
        self.pacer = RequestPacer(minimum_interval_seconds)

    def apply_reviewed_mapping(self, provider_match_id: str, fixture_id: UUID) -> None:
        """Apply an explicit operator-reviewed fixture mapping using stored evidence."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT provider_competition_id, provider_competition_name,
                          provider_home_team_id, provider_home_team_name,
                          provider_away_team_id, provider_away_team_name,
                          kickoff_at, canonical_status, provider_status,
                          home_score, away_score, match_minute, added_time, period,
                          source_updated_at, observed_at, source_snapshot_id
                     FROM football.product_provider_fixture_observations
                    WHERE provider_code = %s AND provider_match_id = %s
                    ORDER BY observed_at DESC, observation_id DESC LIMIT 1""",
                (self.provider_code, provider_match_id),
            )
            source = cursor.fetchone()
            if source is None or any(source[index] is None for index in (0, 1, 2, 3, 4, 5)):
                raise ValueError("stored provider identity evidence is incomplete")
            cursor.execute(
                """SELECT fixture.fixture_id, fixture.competition_id,
                          fixture.home_team_id, fixture.away_team_id,
                          competition.name, home.name, away.name,
                          fixture.status, fixture.home_score, fixture.away_score
                     FROM football.product_fixtures fixture
                     JOIN football.product_competitions competition
                       ON competition.competition_id = fixture.competition_id
                     JOIN football.product_teams home ON home.team_id = fixture.home_team_id
                     JOIN football.product_teams away ON away.team_id = fixture.away_team_id
                    WHERE fixture.fixture_id = %s""",
                (fixture_id,),
            )
            candidate = cursor.fetchone()
            if candidate is None:
                raise ValueError("reviewed canonical fixture does not exist")
        row = PitchApiFixture(
            provider_match_id=provider_match_id,
            provider_competition_id=source[0],
            provider_home_team_id=source[2],
            provider_away_team_id=source[4],
            home_team_name=source[3],
            away_team_name=source[5],
            kickoff_at=source[6],
            status=source[7],
            provider_status=source[8] or "",
            home_score=source[9],
            away_score=source[10],
            minute=source[11],
            added_time=source[12],
            period=source[13],
            source_updated_at=source[14],
            observed_at=source[15],
            provider_competition_name=source[1],
        )
        snapshot_id = cast(UUID, source[16])
        self._persist_deterministic_mapping(row, snapshot_id, candidate, mapping_method="manual")
        self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "MANUAL_ACCEPTED",
            "operator explicitly accepted mapping",
            {"reviewed_fixture_id": str(fixture_id)},
        )

    def sync_fotmob(
        self,
        client: FotmobClient,
        from_date: date,
        through_date: date,
        *,
        details_limit: int = 10,
        competition_id: str | None = None,
    ) -> dict[str, object]:
        return self._sync_dates(
            from_date,
            through_date,
            fetch=client.matches_by_date,
            normalize=normalize_daily_matches,
            detail=lambda item: self._fotmob_details(client, item),
            details_limit=details_limit,
            competition_id=competition_id,
        )

    def sync_pitchapi(
        self,
        client: PitchApiClient,
        from_date: date,
        through_date: date,
        *,
        details_limit: int = 10,
        competition_id: str | None = None,
    ) -> dict[str, object]:
        return self._sync_dates(
            from_date,
            through_date,
            fetch=lambda day: client.matches_by_date(day, status="all"),
            normalize=normalize_pitchapi_matches,
            detail=lambda item: self._pitchapi_details(client, item),
            details_limit=details_limit,
            competition_id=competition_id,
        )

    def _sync_dates(
        self,
        from_date: date,
        through_date: date,
        *,
        fetch: Any,
        normalize: Any,
        detail: Any,
        details_limit: int,
        competition_id: str | None,
    ) -> dict[str, object]:
        if through_date < from_date or (through_date - from_date).days > 366:
            raise ValueError("provider sync date range must be ordered and at most 367 days")
        if not 0 <= details_limit <= 100:
            raise ValueError("details limit must be between 0 and 100")
        sync_started = datetime.now(UTC)
        counts = SyncCounts()
        detailed = 0
        day = from_date
        while day <= through_date:
            self.pacer.wait()
            counts.attempted_requests += 1
            response = fetch(day)
            counts.successful_requests += 1
            snapshot_id = self._record_response(f"fixtures-{day.isoformat()}", response)
            rows: Sequence[FixtureObservation] = normalize(response)
            if competition_id is not None:
                rows = tuple(row for row in rows if row.provider_competition_id == competition_id)
            counts.fetched += len(rows)
            for row in rows:
                fixture_id = self._resolve_fixture(row, snapshot_id)
                inserted = self._store_observation(row, snapshot_id, fixture_id)
                counts.inserted += int(inserted)
                counts.skipped += int(not inserted)
                if fixture_id is None:
                    counts.unmatched += 1
                else:
                    counts.matched += 1
                    counts.updated += self._update_canonical_fixture(row, fixture_id, snapshot_id)
                if detailed < details_limit:
                    detailed += 1
                    detail_counts: DetailCounts = detail(row)
                    counts.attempted_requests += detail_counts.attempted_requests
                    counts.successful_requests += detail_counts.successful_requests
                    counts.failed += detail_counts.failed_requests
                    counts.resources += detail_counts.resources
            self.connection.commit()
            day += timedelta(days=1)
        settled = settle_external_predictions(self.connection, datetime.now(UTC))
        diagnostics = self._sync_diagnostics(sync_started)
        self.connection.commit()
        return {
            "status": "COMPLETED_WITH_ERRORS" if counts.failed else "COMPLETED",
            "provider": self.provider_code,
            "from_date": from_date.isoformat(),
            "through_date": through_date.isoformat(),
            "settled_external_predictions": settled,
            **diagnostics,
            **counts.to_dict(),
        }

    def _sync_diagnostics(self, sync_started: datetime) -> dict[str, object]:
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
                """SELECT observed_at, stale_after
                     FROM football.product_provider_fixture_observations
                    WHERE provider_code = %s
                    ORDER BY observed_at DESC, observation_id DESC LIMIT 1""",
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
            "latest_stale_after": freshness[1].isoformat() if freshness else None,
        }

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
        destination = self.data_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(response.raw)
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
        return snapshot_id

    def _resolve_fixture(
        self, row: FixtureObservation, snapshot_id: UUID | None = None
    ) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.match_id
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
                return cast(UUID, direct[0][0])
            cursor.execute(
                """
                SELECT fixture.fixture_id
                FROM football.product_fixtures fixture
                JOIN football.product_team_aliases home
                  ON home.team_id = fixture.home_team_id
                 AND home.provider_code = %s AND home.provider_team_id = %s
                JOIN football.product_team_aliases away
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
                  AND fixture.kickoff_at BETWEEN %s AND %s
                ORDER BY fixture.fixture_id
                """,
                (
                    self.provider_code,
                    row.provider_home_team_id,
                    self.provider_code,
                    row.provider_away_team_id,
                    self.provider_code,
                    row.provider_competition_id,
                    row.kickoff_at - self.kickoff_tolerance,
                    row.kickoff_at + self.kickoff_tolerance,
                ),
            )
            candidates = cursor.fetchall()
        if len(candidates) == 1:
            return cast(UUID, candidates[0][0])
        if snapshot_id is None:
            return None
        return self._reconcile_exact_fixture(row, snapshot_id)

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
                FROM football.product_fixtures fixture
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
                ),
            )
            nearby = cursor.fetchall()
        exact = [
            candidate
            for candidate in nearby
            if normalize_team_name(candidate[4]) == normalize_team_name(competition_name)
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
        self._persist_deterministic_mapping(row, snapshot_id, candidate)
        self._record_mapping_decision(
            row, snapshot_id, fixture_id, "AUTO_ACCEPTED", "deterministic rule matched", evidence
        )
        return fixture_id

    def _persist_deterministic_mapping(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        candidate: Sequence[Any],
        *,
        mapping_method: str = "deterministic",
    ) -> None:
        fixture_id, competition_id, home_team_id, away_team_id = candidate[:4]
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM football.providers WHERE code = %s", (self.provider_code,)
            )
            provider = cursor.fetchone()
            if provider is None:
                raise ValueError("provider registration missing")
            provider_id = provider[0]
            for table, identity_column, canonical_column, provider_value, canonical_value in (
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
            ):
                cursor.execute(
                    f"""SELECT {canonical_column} FROM football.{table}
                         WHERE provider_id = %s AND {identity_column} = %s AND valid_to IS NULL""",
                    (provider_id, provider_value),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if existing[0] != canonical_value:
                        raise ValueError(f"contradictory existing {table} mapping")
                    cursor.execute(
                        f"""UPDATE football.{table} SET last_seen_at = GREATEST(last_seen_at, %s)
                             WHERE provider_id = %s AND {identity_column} = %s
                               AND valid_to IS NULL""",
                        (row.observed_at, provider_id, provider_value),
                    )
                    continue
                cursor.execute(
                    f"""INSERT INTO football.{table} (
                            {canonical_column}, provider_id, {identity_column},
                            first_seen_at, last_seen_at, mapping_method,
                            mapping_confidence, source_snapshot_id
                         ) VALUES (%s, %s, %s, %s, %s, %s, 1, %s)""",
                    (
                        canonical_value,
                        provider_id,
                        provider_value,
                        row.observed_at,
                        row.observed_at,
                        mapping_method,
                        snapshot_id,
                    ),
                )
            for provider_team_id, team_name, team_id in (
                (row.provider_home_team_id, row.home_team_name, home_team_id),
                (row.provider_away_team_id, row.away_team_name, away_team_id),
            ):
                cursor.execute(
                    """INSERT INTO football.product_team_aliases (
                           provider_code, provider_team_id, normalized_name, team_id
                       ) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (provider_code, provider_team_id) DO NOTHING""",
                    (self.provider_code, provider_team_id, normalize_team_name(team_name), team_id),
                )
            cursor.execute(
                """UPDATE football.product_provider_fixture_observations
                      SET canonical_fixture_id = %s
                    WHERE provider_code = %s AND provider_match_id = %s
                      AND canonical_fixture_id IS NULL""",
                (fixture_id, self.provider_code, row.provider_match_id),
            )
            cursor.execute(
                """UPDATE football.product_provider_resource_observations
                      SET canonical_fixture_id = %s,
                          known_at = COALESCE(known_at, observed_at),
                          point_in_time_eligibility = CASE
                              WHEN point_in_time_eligibility = 'UNKNOWN' THEN 'ELIGIBLE'
                              ELSE point_in_time_eligibility END
                    WHERE provider_code = %s AND provider_match_id = %s""",
                (fixture_id, self.provider_code, row.provider_match_id),
            )

    def _record_mapping_decision(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        fixture_id: UUID | None,
        disposition: str,
        reason: str,
        evidence: Mapping[str, Any],
    ) -> None:
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
                   ON CONFLICT (semantic_sha256) DO NOTHING""",
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

    def _store_observation(
        self, row: FixtureObservation, snapshot_id: UUID, fixture_id: UUID | None
    ) -> bool:
        semantic = sha256_json(
            {
                "provider": self.provider_code,
                "match_id": row.provider_match_id,
                "canonical_fixture_id": str(fixture_id) if fixture_id else None,
                "status": row.status,
                "provider_status": row.provider_status,
                "scores": [row.home_score, row.away_score],
                "clock": [row.minute, row.added_time, row.period],
                "source_updated_at": (
                    row.source_updated_at.isoformat() if row.source_updated_at else None
                ),
            }
        )
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
                    cache_expires_at, stale_after
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (semantic_sha256) DO NOTHING
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
                    row.provider_status,
                    row.home_score,
                    row.away_score,
                    row.minute,
                    row.added_time,
                    row.period,
                    row.source_updated_at,
                    row.observed_at,
                    cache_expires,
                    stale_after,
                ),
            )
            return cursor.rowcount == 1

    def _update_canonical_fixture(
        self, row: FixtureObservation, fixture_id: UUID, snapshot_id: UUID
    ) -> int:
        if row.status == "FINISHED":
            return self._apply_finished_result(row, fixture_id, snapshot_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE football.product_fixtures
                   SET status = %s, home_score = %s, away_score = %s, updated_at = %s
                 WHERE fixture_id = %s AND status <> 'FINISHED'
                   AND CASE status
                       WHEN 'SCHEDULED' THEN 0 WHEN 'POSTPONED' THEN 1
                       WHEN 'LIVE' THEN 2 WHEN 'HALF_TIME' THEN 3
                       WHEN 'SUSPENDED' THEN 4 WHEN 'INTERRUPTED' THEN 4
                       WHEN 'CANCELLED' THEN 5 WHEN 'ABANDONED' THEN 5
                       WHEN 'AWARDED' THEN 5 ELSE 6 END
                       <= CASE %s
                       WHEN 'SCHEDULED' THEN 0 WHEN 'POSTPONED' THEN 1
                       WHEN 'LIVE' THEN 2 WHEN 'HALF_TIME' THEN 3
                       WHEN 'SUSPENDED' THEN 4 WHEN 'INTERRUPTED' THEN 4
                       WHEN 'CANCELLED' THEN 5 WHEN 'ABANDONED' THEN 5
                       WHEN 'AWARDED' THEN 5 ELSE 6 END
                   AND (
                       CASE status
                           WHEN 'SCHEDULED' THEN 0 WHEN 'POSTPONED' THEN 1
                           WHEN 'LIVE' THEN 2 WHEN 'HALF_TIME' THEN 3
                           WHEN 'SUSPENDED' THEN 4 WHEN 'INTERRUPTED' THEN 4
                           WHEN 'CANCELLED' THEN 5 WHEN 'ABANDONED' THEN 5
                           WHEN 'AWARDED' THEN 5 ELSE 6 END
                       < CASE %s
                           WHEN 'SCHEDULED' THEN 0 WHEN 'POSTPONED' THEN 1
                           WHEN 'LIVE' THEN 2 WHEN 'HALF_TIME' THEN 3
                           WHEN 'SUSPENDED' THEN 4 WHEN 'INTERRUPTED' THEN 4
                           WHEN 'CANCELLED' THEN 5 WHEN 'ABANDONED' THEN 5
                           WHEN 'AWARDED' THEN 5 ELSE 6 END
                       OR COALESCE(%s, %s) >= updated_at
                   )
                   AND (status, home_score, away_score)
                       IS DISTINCT FROM (%s, %s, %s)
                """,
                (
                    row.status,
                    row.home_score,
                    row.away_score,
                    row.observed_at,
                    fixture_id,
                    row.status,
                    row.status,
                    row.source_updated_at,
                    row.observed_at,
                    row.status,
                    row.home_score,
                    row.away_score,
                ),
            )
            return cursor.rowcount

    def _apply_finished_result(
        self, row: FixtureObservation, fixture_id: UUID, snapshot_id: UUID
    ) -> int:
        if row.home_score is None or row.away_score is None:
            return 0
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, home_score, away_score
                FROM football.product_fixtures WHERE fixture_id = %s
                """,
                (fixture_id,),
            )
            existing = cursor.fetchone()
            if existing is None:
                return 0
            existing_status, existing_home, existing_away = existing
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
                   AND (status <> 'FINISHED' OR home_score IS NULL OR away_score IS NULL)
                """,
                (
                    row.home_score,
                    row.away_score,
                    row.result_score_basis,
                    row.observed_at,
                    fixture_id,
                ),
            )
            return cursor.rowcount

    def _fotmob_details(self, client: FotmobClient, row: FotmobLiveScore) -> DetailCounts:
        self.pacer.wait()
        try:
            response = client.match_details(row.provider_match_id)
        except (OSError, RuntimeError, ValueError):
            return DetailCounts(attempted_requests=1, failed_requests=1)
        snapshot = self._record_response(f"match-{row.provider_match_id}-details", response)
        fixture_id = self._resolve_fixture(row)
        resources = _fotmob_resources(response.data)
        for resource_type, payload in resources.items():
            self._store_resource(
                row.provider_match_id,
                fixture_id,
                resource_type,
                payload,
                response,
                snapshot,
                eligibility="ELIGIBLE",
            )
        return DetailCounts(
            attempted_requests=1,
            successful_requests=1,
            resources=len(resources),
        )

    def _pitchapi_details(self, client: PitchApiClient, row: PitchApiFixture) -> DetailCounts:
        fixture_id = self._resolve_fixture(row)
        attempted = 0
        successful = 0
        failed = 0
        resources = 0
        for endpoint, resource_type in (
            ("", "MATCH_DETAILS"),
            ("events", "EVENTS"),
            ("stats", "STATISTICS"),
            ("shots", "SHOTS"),
            ("momentum", "MOMENTUM"),
            ("lineups", "LINEUPS"),
            ("players", "PLAYER_RATINGS"),
            ("h2h", "H2H"),
        ):
            self.pacer.wait()
            attempted += 1
            try:
                response = (
                    client.match(row.provider_match_id)
                    if not endpoint
                    else client.match_resource(row.provider_match_id, endpoint)
                )
            except (OSError, RuntimeError, ValueError):
                failed += 1
                continue
            successful += 1
            resources += 1
            snapshot = self._record_response(
                f"match-{row.provider_match_id}-{endpoint or 'details'}", response
            )
            self._store_resource(
                row.provider_match_id,
                fixture_id,
                resource_type,
                response.data,
                response,
                snapshot,
                eligibility="ELIGIBLE",
            )
        return DetailCounts(attempted, successful, failed, resources)

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
                    point_in_time_eligibility, development_only, payload
                ) VALUES (%s, %s, %s, %s, %s, 'AVAILABLE', %s, %s, %s, %s, %s, true, %s)
                ON CONFLICT (semantic_sha256) DO NOTHING
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
                ),
            )
            return cursor.rowcount


def _fotmob_resources(payload: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"MATCH_DETAILS": payload}
    content = payload.get("content")
    source = content if isinstance(content, Mapping) else payload
    aliases = {
        "matchFacts": "MATCH_DETAILS",
        "events": "EVENTS",
        "stats": "STATISTICS",
        "shotmap": "SHOTS",
        "momentum": "MOMENTUM",
        "lineup": "LINEUPS",
        "playerStats": "PLAYER_RATINGS",
        "h2h": "H2H",
    }
    resources = {
        resource_type: source[key]
        for key, resource_type in aliases.items()
        if key in source and isinstance(source[key], (Mapping, list))
    }
    if "MATCH_DETAILS" not in resources:
        resources["MATCH_DETAILS"] = payload
    return resources
