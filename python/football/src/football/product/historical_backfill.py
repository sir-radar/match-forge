"""Provider-neutral persistence for bulk historical result imports."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from psycopg import Connection

from football.product.domain import normalize_team_name, sha256_json, stable_id
from football.product.identity_crosswalks import COMPETITION_CROSSWALKS

KickoffPrecision = Literal["EXACT", "DATE_ONLY"]


@dataclass(frozen=True, slots=True)
class HistoricalMatch:
    provider_match_id: str
    provider_competition_id: str
    competition_name: str
    country: str
    division: int | None
    season: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    kickoff_at: datetime
    kickoff_precision: KickoffPrecision
    home_goals: int
    away_goals: int
    source_path: str


@dataclass(slots=True)
class BackfillSummary:
    provider: str
    source_revision: str = ""
    resources_discovered: int = 0
    resources_changed: int = 0
    resources_cached: int = 0
    csv_files: int = 0
    zip_files: int = 0
    seasons: int = 0
    competitions: int = 0
    matches_parsed: int = 0
    matches_inserted: int = 0
    matches_existing: int = 0
    team_mappings_created: int = 0
    competition_mappings_created: int = 0
    mapping_failures: int = 0
    result_conflicts: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def cache_resource(source: Path, cache_root: Path, provider: str, revision: str) -> Path:
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    suffix = source.suffix.casefold() or ".bin"
    destination = cache_root / provider / revision / f"{digest}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(source, destination)
    return destination


class HistoricalBackfillStore:
    """Persist complete results while preserving canonical identities and provenance."""

    def __init__(
        self,
        connection: Connection[Any],
        provider_code: str,
        provider_name: str,
        parser_version: str,
    ) -> None:
        self.connection = connection
        self.provider_code = provider_code
        self.provider_name = provider_name
        self.parser_version = parser_version
        self.competition_mappings_created = 0
        self.team_mappings_created = 0

    def ensure_snapshot(
        self,
        *,
        source_identity: str,
        source_revision: str,
        acquired_at: datetime,
        manifest_path: str,
        repository: str | None = None,
        git_sha: str | None = None,
    ) -> UUID:
        provider_id = self._ensure_provider()
        snapshot_id = stable_id(
            "source-snapshot", self.provider_code, source_identity, source_revision
        )
        manifest_sha = hashlib.sha256(manifest_path.encode()).hexdigest()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.source_snapshots (
                    id, provider_id, source_identity, source_revision, repository, git_sha,
                    acquired_at, manifest_path, manifest_sha256, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'validated')
                ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
                """,
                (
                    snapshot_id,
                    provider_id,
                    source_identity,
                    source_revision,
                    repository,
                    git_sha,
                    acquired_at,
                    manifest_path,
                    manifest_sha,
                ),
            )
        return snapshot_id

    def resource_already_imported(self, provider_path: str, sha256: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM football.source_resources resource
                JOIN football.source_snapshots snapshot
                  ON snapshot.id = resource.source_snapshot_id
                JOIN football.providers provider ON provider.id = snapshot.provider_id
                WHERE provider.code = %s AND resource.provider_path = %s
                  AND resource.sha256 = %s AND resource.parse_status = 'parsed'
                  AND resource.validation_status IN ('valid', 'warnings')
                LIMIT 1
                """,
                (self.provider_code, provider_path, sha256),
            )
            return cursor.fetchone() is not None

    def resource_path_already_imported(self, provider_path: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM football.source_resources resource
                JOIN football.source_snapshots snapshot
                  ON snapshot.id = resource.source_snapshot_id
                JOIN football.providers provider ON provider.id = snapshot.provider_id
                WHERE provider.code = %s AND resource.provider_path = %s
                  AND resource.parse_status = 'parsed'
                  AND resource.validation_status IN ('valid', 'warnings')
                LIMIT 1
                """,
                (self.provider_code, provider_path),
            )
            return cursor.fetchone() is not None

    def record_resource(
        self,
        *,
        snapshot_id: UUID,
        provider_path: str,
        payload: bytes,
        media_type: str,
        acquired_at: datetime,
        warnings: bool = False,
    ) -> UUID:
        digest = hashlib.sha256(payload).hexdigest()
        resource_id = stable_id("source-resource", snapshot_id, provider_path, digest)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.source_resources (
                    id, source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                    parse_status, validation_status, acquired_at, parser_version
                ) VALUES (%s, %s, %s, %s, %s, %s, 'parsed', %s, %s, %s)
                ON CONFLICT (source_snapshot_id, provider_path) DO UPDATE SET
                    sha256 = EXCLUDED.sha256,
                    size_bytes = EXCLUDED.size_bytes,
                    media_type = EXCLUDED.media_type,
                    parse_status = EXCLUDED.parse_status,
                    validation_status = EXCLUDED.validation_status,
                    acquired_at = EXCLUDED.acquired_at,
                    parser_version = EXCLUDED.parser_version
                """,
                (
                    resource_id,
                    snapshot_id,
                    provider_path,
                    digest,
                    len(payload),
                    media_type,
                    "warnings" if warnings else "valid",
                    acquired_at,
                    self.parser_version,
                ),
            )
        return resource_id

    def import_match(
        self, match: HistoricalMatch, snapshot_id: UUID, observed_at: datetime
    ) -> Literal["inserted", "existing", "conflict", "mapping_failure"]:
        competition_id, competition_created = self._competition_id(match, snapshot_id, observed_at)
        if competition_id is None:
            return "mapping_failure"
        home_id, _ = self._team_id(
            match.home_team_id,
            match.home_team_name,
            match.country,
            snapshot_id,
            observed_at,
        )
        away_id, _ = self._team_id(
            match.away_team_id,
            match.away_team_name,
            match.country,
            snapshot_id,
            observed_at,
        )
        if home_id is None or away_id is None or home_id == away_id:
            return "mapping_failure"
        season_id = stable_id("season", competition_id, match.season)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.seasons (id, competition_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (season_id, competition_id),
            )
        existing = self._existing_match(match, competition_id, home_id, away_id)
        if existing is not None:
            fixture_id, home_goals, away_goals, provider_code, existing_snapshot = existing
            self._ensure_match_mapping(
                fixture_id, match.provider_match_id, snapshot_id, observed_at
            )
            if (home_goals, away_goals) != (match.home_goals, match.away_goals):
                self._record_conflict(
                    fixture_id,
                    str(provider_code),
                    home_goals,
                    away_goals,
                    existing_snapshot,
                    match,
                    snapshot_id,
                )
                return "conflict"
            return "existing"
        kickoff = match.kickoff_at.astimezone(UTC)
        fixture_id = stable_id(
            "bulk-history-match",
            competition_id,
            match.season,
            kickoff.date() if match.kickoff_precision == "DATE_ONLY" else kickoff.isoformat(),
            home_id,
            away_id,
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.matches (id, competition_id, season_id)
                VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                """,
                (fixture_id, competition_id, season_id),
            )
            self._ensure_match_mapping(
                fixture_id, match.provider_match_id, snapshot_id, observed_at, cursor=cursor
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_match_history (
                    fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                    home_goals, away_goals, source_provider_code, source_snapshot_id,
                    source_kickoff_precision
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (fixture_id) DO NOTHING
                """,
                (
                    fixture_id,
                    competition_id,
                    home_id,
                    away_id,
                    kickoff,
                    match.home_goals,
                    match.away_goals,
                    self.provider_code,
                    snapshot_id,
                    match.kickoff_precision,
                ),
            )
            inserted = cursor.rowcount == 1
            cursor.execute(
                """
                UPDATE football.product_competitions
                SET results_available = true, h2h_available = true,
                    team_stats_available = true,
                    source_roles = jsonb_set(
                        jsonb_set(
                            jsonb_set(source_roles, '{results}',
                                COALESCE(source_roles->'results', '[]'::jsonb)
                                || to_jsonb(%s::text)),
                            '{h2h}', COALESCE(source_roles->'h2h', '[]'::jsonb)
                                || to_jsonb(%s::text)),
                        '{team_stats}', '["matchforge_results"]'::jsonb),
                    updated_at = GREATEST(updated_at, %s)
                WHERE competition_id = %s
                """,
                (self.provider_code, self.provider_code, observed_at, competition_id),
            )
        _ = competition_created
        return "inserted" if inserted else "existing"

    def _competition_id(
        self, match: HistoricalMatch, snapshot_id: UUID, observed_at: datetime
    ) -> tuple[UUID | None, bool]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.competition_id
                FROM football.competition_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = %s AND mapping.provider_competition_id = %s
                ORDER BY mapping.first_seen_at LIMIT 1
                """,
                (self.provider_code, match.provider_competition_id),
            )
            found = cursor.fetchone()
            if found is not None:
                return cast(UUID, found[0]), False
            crosswalk = COMPETITION_CROSSWALKS.get(self.provider_code, {}).get(
                match.provider_competition_id
            )
            if crosswalk is not None:
                cursor.execute(
                    """
                    SELECT mapping.competition_id
                    FROM football.competition_provider_mappings mapping
                    JOIN football.providers provider ON provider.id = mapping.provider_id
                    WHERE provider.code = %s AND mapping.provider_competition_id = %s
                    ORDER BY mapping.first_seen_at LIMIT 1
                    """,
                    crosswalk,
                )
                mapped = cursor.fetchone()
                if mapped is not None:
                    candidates = [
                        (mapped[0], match.competition_name, match.country, match.division)
                    ]
                else:
                    candidates = []
            else:
                candidates = []
        if len(candidates) > 1:
            return None, False
        competition_id = (
            cast(UUID, candidates[0][0])
            if candidates
            else stable_id(
                "competition",
                self.provider_code,
                match.provider_competition_id,
                match.country,
            )
        )
        mapping_method = "explicit_crosswalk" if candidates else "deterministic"
        provider_id = self._provider_id()
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO football.competitions (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (competition_id,),
            )
            if not candidates:
                cursor.execute(
                    """
                    INSERT INTO football.product_competitions (
                        competition_id, name, country, continent, division, competition_type,
                        season_label, results_available, availability_status,
                        source_roles, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 'LEAGUE', %s, true,
                        'NO_FIXTURES', %s::jsonb, %s)
                    ON CONFLICT (competition_id) DO NOTHING
                    """,
                    (
                        competition_id,
                        match.competition_name,
                        match.country or "World",
                        continent_for_country(match.country),
                        match.division,
                        match.season,
                        json.dumps(
                            {
                                "fixtures": [],
                                "results": [self.provider_code],
                                "standings": [],
                                "h2h": [self.provider_code],
                                "team_stats": ["matchforge_results"],
                            }
                        ),
                        observed_at,
                    ),
                )
            cursor.execute(
                """
                INSERT INTO football.competition_provider_mappings (
                    competition_id, provider_id, provider_competition_id, first_seen_at,
                    last_seen_at, mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, %s, %s, %s, %s, %s, 1.0, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM football.competition_provider_mappings
                    WHERE provider_id = %s AND provider_competition_id = %s
                )
                """,
                (
                    competition_id,
                    provider_id,
                    match.provider_competition_id,
                    observed_at,
                    observed_at,
                    mapping_method,
                    snapshot_id,
                    provider_id,
                    match.provider_competition_id,
                ),
            )
            self.competition_mappings_created += cursor.rowcount
        return competition_id, True

    def _team_id(
        self,
        provider_team_id: str,
        name: str,
        country: str,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> tuple[UUID | None, bool]:
        normalized = normalize_team_name(name)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = %s AND provider_team_id = %s
                """,
                (self.provider_code, provider_team_id),
            )
            found = cursor.fetchone()
            if found is not None:
                return cast(UUID, found[0]), False
        team_id = stable_id("team", self.provider_code, provider_team_id, country)
        provider_id = self._provider_id()
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
                INSERT INTO football.product_teams (team_id, name, country, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (team_id) DO UPDATE SET updated_at = EXCLUDED.updated_at
                """,
                (team_id, name, country or None, observed_at),
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_aliases (
                    provider_code, provider_team_id, normalized_name, country, team_id
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider_code, provider_team_id) DO NOTHING
                """,
                (self.provider_code, provider_team_id, normalized, country or None, team_id),
            )
            cursor.execute(
                """
                INSERT INTO football.team_provider_mappings (
                    team_id, provider_id, provider_team_id, first_seen_at, last_seen_at,
                    mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, %s, %s, %s, %s, 'deterministic', 1.0, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM football.team_provider_mappings
                    WHERE provider_id = %s AND provider_team_id = %s
                )
                """,
                (
                    team_id,
                    provider_id,
                    provider_team_id,
                    observed_at,
                    observed_at,
                    snapshot_id,
                    provider_id,
                    provider_team_id,
                ),
            )
            self.team_mappings_created += cursor.rowcount
        return team_id, True

    def _existing_match(
        self, match: HistoricalMatch, competition_id: UUID, home_id: UUID, away_id: UUID
    ) -> tuple[UUID, int, int, str, UUID] | None:
        kickoff = match.kickoff_at.astimezone(UTC)
        with self.connection.cursor() as cursor:
            if match.kickoff_precision == "DATE_ONLY":
                cursor.execute(
                    """
                    SELECT fixture_id, home_goals, away_goals, source_provider_code,
                           source_snapshot_id
                    FROM football.product_team_match_history
                    WHERE competition_id = %s AND home_team_id = %s AND away_team_id = %s
                      AND kickoff_at::date = %s
                    ORDER BY fixture_id
                    """,
                    (competition_id, home_id, away_id, kickoff.date()),
                )
            else:
                cursor.execute(
                    """
                    SELECT fixture_id, home_goals, away_goals, source_provider_code,
                           source_snapshot_id
                    FROM football.product_team_match_history
                    WHERE competition_id = %s AND home_team_id = %s AND away_team_id = %s
                      AND kickoff_at BETWEEN %s AND %s
                    ORDER BY ABS(EXTRACT(EPOCH FROM (kickoff_at - %s))), fixture_id
                    """,
                    (
                        competition_id,
                        home_id,
                        away_id,
                        kickoff - timedelta(hours=3),
                        kickoff + timedelta(hours=3),
                        kickoff,
                    ),
                )
            rows = cursor.fetchall()
        return cast(tuple[UUID, int, int, str, UUID], tuple(rows[0])) if len(rows) == 1 else None

    def _ensure_match_mapping(
        self,
        fixture_id: UUID,
        provider_match_id: str,
        snapshot_id: UUID,
        observed_at: datetime,
        *,
        cursor: Any | None = None,
    ) -> None:
        def execute(active: Any) -> None:
            provider_id = self._provider_id()
            active.execute(
                """
                INSERT INTO football.match_provider_mappings (
                    match_id, provider_id, provider_match_id, first_seen_at, last_seen_at,
                    mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, %s, %s, %s, %s, 'deterministic', 1.0, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM football.match_provider_mappings
                    WHERE provider_id = %s AND provider_match_id = %s
                )
                """,
                (
                    fixture_id,
                    provider_id,
                    provider_match_id,
                    observed_at,
                    observed_at,
                    snapshot_id,
                    provider_id,
                    provider_match_id,
                ),
            )

        if cursor is not None:
            execute(cursor)
        else:
            with self.connection.cursor() as active:
                execute(active)

    def _ensure_provider(self) -> UUID:
        proposed = stable_id("provider", self.provider_code)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.providers (id, code, name, source_type)
                VALUES (%s, %s, %s, %s) ON CONFLICT (code) DO NOTHING
                """,
                (
                    proposed,
                    self.provider_code,
                    self.provider_name,
                    ("git_repository" if self.provider_code == "openfootball" else "file_download"),
                ),
            )
        return self._provider_id()

    def _provider_id(self) -> UUID:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM football.providers WHERE code = %s", (self.provider_code,)
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError(f"provider is not registered: {self.provider_code}")
        return cast(UUID, row[0])

    def _record_conflict(
        self,
        fixture_id: UUID,
        existing_provider: str,
        existing_home: int,
        existing_away: int,
        existing_snapshot: UUID,
        match: HistoricalMatch,
        snapshot_id: UUID,
    ) -> None:
        conflict_key = sha256_json(
            {
                "fixture_id": str(fixture_id),
                "existing_provider": existing_provider,
                "existing_score": [existing_home, existing_away],
                "incoming_provider": self.provider_code,
                "incoming_score": [match.home_goals, match.away_goals],
                "incoming_snapshot": str(snapshot_id),
            }
        )
        with self.connection.cursor() as cursor:
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
                    existing_provider,
                    existing_home,
                    existing_away,
                    existing_snapshot,
                    self.provider_code,
                    match.home_goals,
                    match.away_goals,
                    snapshot_id,
                    conflict_key,
                ),
            )


def date_only_timestamp(value: datetime) -> datetime:
    """Place unknown kickoff at end of day; eligibility still checks precision explicitly."""
    return datetime.combine(value.date(), time.max, tzinfo=UTC)


def continent_for_country(country: str) -> str:
    normalized = country.casefold()
    if normalized in {"argentina", "brazil", "chile", "mexico"}:
        return "South America" if normalized != "mexico" else "North America"
    if normalized in {"china", "japan", "india"}:
        return "Asia"
    if normalized in {"usa", "united states", "canada"}:
        return "North America"
    if normalized in {"australia", "new zealand"}:
        return "Oceania"
    return "Europe" if country and country != "World" else "World"
