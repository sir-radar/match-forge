"""Idempotent operational fixture sync for FotMob and PitchAPI."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast
from uuid import UUID

from psycopg import Connection

from football.product.domain import canonical_json, sha256_json, stable_id
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
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    unmatched: int = 0
    failed: int = 0
    resources: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "unmatched": self.unmatched,
            "failed": self.failed,
            "resources": self.resources,
        }


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
        counts = SyncCounts()
        detailed = 0
        day = from_date
        while day <= through_date:
            self.pacer.wait()
            response = fetch(day)
            snapshot_id = self._record_response(f"fixtures-{day.isoformat()}", response)
            rows: Sequence[FixtureObservation] = normalize(response)
            if competition_id is not None:
                rows = tuple(row for row in rows if row.provider_competition_id == competition_id)
            counts.fetched += len(rows)
            for row in rows:
                fixture_id = self._resolve_fixture(row)
                inserted = self._store_observation(row, snapshot_id, fixture_id)
                counts.inserted += int(inserted)
                counts.skipped += int(not inserted)
                if fixture_id is None:
                    counts.unmatched += 1
                else:
                    counts.updated += self._update_canonical_fixture(row, fixture_id, snapshot_id)
                if detailed < details_limit:
                    try:
                        detailed += 1
                        counts.resources += detail(row)
                    except (OSError, RuntimeError, ValueError):
                        counts.failed += 1
            self.connection.commit()
            day += timedelta(days=1)
        return {
            "status": "COMPLETED_WITH_ERRORS" if counts.failed else "COMPLETED",
            "provider": self.provider_code,
            "from_date": from_date.isoformat(),
            "through_date": through_date.isoformat(),
            **counts.to_dict(),
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

    def _resolve_fixture(self, row: FixtureObservation) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.match_id
                FROM football.match_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = %s AND mapping.provider_match_id = %s
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
        return cast(UUID, candidates[0][0]) if len(candidates) == 1 else None

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
                    provider_competition_id, canonical_fixture_id, source_snapshot_id,
                    kickoff_at, canonical_status, provider_status, home_score, away_score,
                    match_minute, added_time, period, source_updated_at, observed_at,
                    cache_expires_at, stale_after
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s)
                ON CONFLICT (semantic_sha256) DO NOTHING
                """,
                (
                    semantic,
                    self.provider_code,
                    row.provider_match_id,
                    row.provider_competition_id,
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
                   SET status = 'FINISHED', home_score = %s, away_score = %s, updated_at = %s
                 WHERE fixture_id = %s
                   AND (status <> 'FINISHED' OR home_score IS NULL OR away_score IS NULL)
                """,
                (row.home_score, row.away_score, row.observed_at, fixture_id),
            )
            return cursor.rowcount

    def _fotmob_details(self, client: FotmobClient, row: FotmobLiveScore) -> int:
        self.pacer.wait()
        response = client.match_details(row.provider_match_id)
        snapshot = self._record_response(f"match-{row.provider_match_id}-details", response)
        fixture_id = self._resolve_fixture(row)
        resources = _fotmob_resources(response.data)
        return sum(
            self._store_resource(
                row.provider_match_id,
                fixture_id,
                resource_type,
                payload,
                response,
                snapshot,
                eligibility="UNKNOWN",
            )
            for resource_type, payload in resources.items()
        )

    def _pitchapi_details(self, client: PitchApiClient, row: PitchApiFixture) -> int:
        fixture_id = self._resolve_fixture(row)
        count = 0
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
            response = (
                client.match(row.provider_match_id)
                if not endpoint
                else client.match_resource(row.provider_match_id, endpoint)
            )
            snapshot = self._record_response(
                f"match-{row.provider_match_id}-{endpoint or 'details'}", response
            )
            count += self._store_resource(
                row.provider_match_id,
                fixture_id,
                resource_type,
                response.data,
                response,
                snapshot,
                eligibility="UNKNOWN",
            )
        return count

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
                ) VALUES (%s, %s, %s, %s, %s, 'AVAILABLE', %s, %s, %s, NULL, %s, true, %s)
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
