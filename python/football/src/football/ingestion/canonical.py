from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection, Cursor, sql
from psycopg.errors import DeadlockDetected, ExclusionViolation, SerializationFailure

from football.contracts.source import canonical_json_bytes
from football.ingestion.acquisition import AcquisitionResult
from football.ingestion.errors import CanonicalIngestionError, RetryableIngestionError
from football.ingestion.registration import (
    PostgresSourceRegistry,
    RegisteredSource,
    VerifiedSource,
    verify_acquisition,
)
from football.ingestion.statsbomb_contracts import (
    CompetitionSeason,
    EventEntity,
    LineupPlayer,
    LineupTeam,
    Match,
    MatchEvents,
    MatchLineup,
    PlayerCard,
    PositionStint,
    StatsBombBundle,
    Team,
    parse_statsbomb_bundle,
)


@dataclass(frozen=True)
class CanonicalIngestionResult:
    source_snapshot_id: UUID
    competitions_seen: int
    seasons_seen: int
    teams_seen: int
    players_seen: int
    matches_seen: int
    lineup_players_seen: int
    position_stints_seen: int
    cards_seen: int
    events_seen: int


@dataclass(frozen=True)
class _IdentitySpec:
    canonical_table: str
    mapping_table: str
    canonical_id_column: str
    provider_id_columns: tuple[str, ...]


class StatsBombCanonicalIngestor:
    def __init__(self, connection: Connection[Any], data_root: Path) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()

    def ingest(self, acquisition: AcquisitionResult) -> CanonicalIngestionResult:
        source = verify_acquisition(self._data_root, acquisition)
        bundle = parse_statsbomb_bundle(source)
        try:
            with self._connection.transaction(), self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"canonical-provider:{source.manifest.snapshot.provider}",),
                )
                registered = PostgresSourceRegistry().register(cursor, source)
                writer = _CanonicalWriter(cursor, registered, source)
                result = writer.ingest(bundle)
                _mark_processed(cursor, registered, bundle.processed_paths)
                return result
        except (DeadlockDetected, ExclusionViolation, SerializationFailure) as error:
            raise RetryableIngestionError(
                "concurrent canonical identity publication aborted; retry whole ingestion"
            ) from error


class _CanonicalWriter:
    def __init__(
        self,
        cursor: Cursor[Any],
        registered: RegisteredSource,
        source: VerifiedSource,
    ) -> None:
        self._cursor = cursor
        self._source = registered
        self._known_from = source.manifest.acquired_at
        self._recorded_player_fact_sha256: set[str] = set()

    def ingest(self, bundle: StatsBombBundle) -> CanonicalIngestionResult:
        competitions = self._competitions(bundle.competitions)
        matches = {match.provider_id: self._match(match) for match in bundle.matches}
        for lineup in bundle.lineups:
            self._lineup(lineup, matches.get(lineup.provider_match_id))
        for resource in bundle.events:
            self._events(resource, matches.get(resource.provider_match_id))
        return _result(bundle, self._source.snapshot_id, len(competitions))

    def _competitions(self, rows: tuple[CompetitionSeason, ...]) -> dict[str, UUID]:
        competition_ids: dict[str, UUID] = {}
        competition_facts: dict[str, tuple[object, ...]] = {}
        season_keys: set[tuple[str, str]] = set()
        for row in rows:
            facts = (
                row.competition_name,
                row.country_name,
                row.gender,
                row.is_youth,
                row.is_international,
            )
            if row.competition_id in competition_facts:
                if competition_facts[row.competition_id] != facts:
                    raise CanonicalIngestionError(
                        f"competition {row.competition_id} has conflicting source facts"
                    )
            else:
                competition_ids[row.competition_id] = self._competition(row)
                competition_facts[row.competition_id] = facts
            season_key = (row.competition_id, row.season_id)
            if season_key in season_keys:
                raise CanonicalIngestionError(
                    f"source contains duplicate competition season {season_key}"
                )
            season_keys.add(season_key)
            self._season(row, competition_ids[row.competition_id])
        return competition_ids

    def _competition(self, row: CompetitionSeason) -> UUID:
        competition_id = self._identity(
            _IdentitySpec(
                "competitions",
                "competition_provider_mappings",
                "competition_id",
                ("provider_competition_id",),
            ),
            (row.competition_id,),
            {},
        )
        if self._begin_observation(
            "competition_observations",
            "competition_id",
            competition_id,
            ("provider_competition_id",),
            (row.competition_id,),
        ):
            resource_id = self._source.resource_ids[row.source_path]
            self._cursor.execute(
                """
                INSERT INTO football.competition_observations
                    (competition_id, provider_id, provider_competition_id, name,
                     country_name, gender, is_youth, is_international, known_from,
                     source_snapshot_id, source_resource_id, acquired_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    competition_id,
                    self._source.provider_id,
                    row.competition_id,
                    row.competition_name,
                    row.country_name,
                    row.gender,
                    row.is_youth,
                    row.is_international,
                    self._known_from,
                    self._source.snapshot_id,
                    resource_id,
                    self._known_from,
                ),
            )
        return competition_id

    def _season(self, row: CompetitionSeason, competition_id: UUID) -> UUID:
        season_id = self._identity(
            _IdentitySpec(
                "seasons",
                "season_provider_mappings",
                "season_id",
                ("provider_competition_id", "provider_season_id"),
            ),
            (row.competition_id, row.season_id),
            {"competition_id": competition_id},
        )
        self._require_canonical_values("seasons", season_id, {"competition_id": competition_id})
        if not self._begin_observation(
            "season_observations",
            "season_id",
            season_id,
            ("provider_competition_id", "provider_season_id"),
            (row.competition_id, row.season_id),
        ):
            return season_id
        available_at, available_raw = _provider_datetime(row.provider_available_at_raw)
        updated_at, updated_raw = _provider_datetime(row.provider_updated_at_raw)
        self._cursor.execute(
            """
            INSERT INTO football.season_observations
                (season_id, provider_id, provider_competition_id, provider_season_id,
                 name, known_from, provider_available_at, provider_updated_at,
                 provider_available_at_raw, provider_updated_at_raw,
                 source_snapshot_id, source_resource_id, acquired_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                season_id,
                self._source.provider_id,
                row.competition_id,
                row.season_id,
                row.season_name,
                self._known_from,
                available_at,
                updated_at,
                available_raw,
                updated_raw,
                self._source.snapshot_id,
                self._source.resource_ids[row.source_path],
                self._known_from,
            ),
        )
        return season_id

    def _match(self, row: Match) -> UUID:
        competition_id = self._mapping_id(
            "competition_provider_mappings",
            "competition_id",
            ("provider_competition_id",),
            (row.competition_id,),
        )
        season_id = self._mapping_id(
            "season_provider_mappings",
            "season_id",
            ("provider_competition_id", "provider_season_id"),
            (row.competition_id, row.season_id),
        )
        home_team_id = self._team(row.home_team, row.source_path)
        away_team_id = self._team(row.away_team, row.source_path)
        if home_team_id == away_team_id:
            raise CanonicalIngestionError(f"match {row.provider_id} has the same team twice")
        match_id = self._identity(
            _IdentitySpec(
                "matches",
                "match_provider_mappings",
                "match_id",
                ("provider_match_id",),
            ),
            (row.provider_id,),
            {"competition_id": competition_id, "season_id": season_id},
        )
        self._require_canonical_values(
            "matches",
            match_id,
            {"competition_id": competition_id, "season_id": season_id},
        )
        if self._publish_match_observation(row, match_id, home_team_id, away_team_id):
            self._publish_match_teams(match_id, home_team_id, away_team_id, row.source_path)
        return match_id

    def _team(self, row: Team | LineupTeam, source_path: str) -> UUID:
        team_id = self._identity(
            _IdentitySpec(
                "teams",
                "team_provider_mappings",
                "team_id",
                ("provider_team_id",),
            ),
            (row.provider_id,),
            {"entity_kind": "unknown"},
        )
        incoming_gender = row.gender if isinstance(row, Team) else None
        incoming_country = row.country_provider_id if isinstance(row, Team) else None
        existing = self._snapshot_team_observation(row.provider_id)
        if existing is not None:
            _require_compatible_team(row, incoming_gender, incoming_country, existing)
            return team_id
        if isinstance(row, LineupTeam):
            current = self._current_team_observation(team_id)
            if current is not None:
                _require_compatible_team(row, None, None, current)
                return team_id
        if not self._begin_observation(
            "team_observations",
            "team_id",
            team_id,
            ("provider_team_id",),
            (row.provider_id,),
        ):
            return team_id
        self._cursor.execute(
            """
            INSERT INTO football.team_observations
                (team_id, provider_id, provider_team_id, name, gender,
                 country_provider_id, known_from, source_snapshot_id,
                 source_resource_id, acquired_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                team_id,
                self._source.provider_id,
                row.provider_id,
                row.name,
                incoming_gender,
                incoming_country,
                self._known_from,
                self._source.snapshot_id,
                self._source.resource_ids[source_path],
                self._known_from,
            ),
        )
        return team_id

    def _publish_match_observation(
        self,
        row: Match,
        match_id: UUID,
        home_team_id: UUID,
        away_team_id: UUID,
    ) -> bool:
        if not self._begin_observation(
            "match_observations",
            "match_id",
            match_id,
            ("provider_match_id",),
            (row.provider_id,),
        ):
            return False
        updated_at, updated_raw = _provider_datetime(row.provider_updated_at_raw)
        self._cursor.execute(
            """
            INSERT INTO football.match_observations
                (match_id, provider_id, provider_match_id, match_date, kick_off_local,
                 home_team_id, away_team_id, home_score, away_score, stage, match_week,
                 provider_status, provider_360_status, data_version,
                 shot_fidelity_version, xy_fidelity_version, known_from,
                 provider_updated_at, provider_updated_at_raw, source_snapshot_id,
                 source_resource_id, acquired_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                match_id,
                self._source.provider_id,
                row.provider_id,
                row.match_date,
                row.kick_off_local,
                home_team_id,
                away_team_id,
                row.home_score,
                row.away_score,
                row.stage,
                row.match_week,
                row.provider_status,
                row.provider_360_status,
                row.data_version,
                row.shot_fidelity_version,
                row.xy_fidelity_version,
                self._known_from,
                updated_at,
                updated_raw,
                self._source.snapshot_id,
                self._source.resource_ids[row.source_path],
                self._known_from,
            ),
        )
        return True

    def _publish_match_teams(
        self,
        match_id: UUID,
        home_team_id: UUID,
        away_team_id: UUID,
        source_path: str,
    ) -> None:
        self._assert_newer_than_current_match_team_observations(match_id)
        self._cursor.execute(
            """
            UPDATE football.match_team_participation_observations AS observation
            SET known_to = %s
            FROM football.match_team_participations AS participation
            WHERE observation.match_team_participation_id = participation.id
              AND participation.match_id = %s
              AND observation.provider_id = %s
              AND observation.known_to IS NULL
              AND observation.known_from < %s
            """,
            (self._known_from, match_id, self._source.provider_id, self._known_from),
        )
        for side, team_id in (("home", home_team_id), ("away", away_team_id)):
            participation_id = self._match_team_participation(match_id, team_id)
            self._cursor.execute(
                """
                INSERT INTO football.match_team_participation_observations
                    (match_team_participation_id, match_id, provider_id, side,
                     known_from, source_snapshot_id, source_resource_id, acquired_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_snapshot_id, match_team_participation_id) DO NOTHING
                """,
                (
                    participation_id,
                    match_id,
                    self._source.provider_id,
                    side,
                    self._known_from,
                    self._source.snapshot_id,
                    self._source.resource_ids[source_path],
                    self._known_from,
                ),
            )

    def _lineup(self, lineup: MatchLineup, ingested_match_id: UUID | None) -> None:
        match_id = ingested_match_id or self._mapping_id(
            "match_provider_mappings",
            "match_id",
            ("provider_match_id",),
            (lineup.provider_match_id,),
        )
        expected_teams = self._current_match_teams(match_id)
        lineup_teams = {self._team(team, lineup.source_path): team for team in lineup.teams}
        if set(lineup_teams) != expected_teams:
            unexpected = sorted(
                team.provider_id
                for canonical_id, team in lineup_teams.items()
                if canonical_id not in expected_teams
            )
            if unexpected:
                raise CanonicalIngestionError(
                    f"lineup team {unexpected[0]} does not play in match {lineup.provider_match_id}"
                )
            raise CanonicalIngestionError(
                f"lineup does not contain both teams for match {lineup.provider_match_id}"
            )
        self._close_current_lineup(match_id)
        player_ids: set[str] = set()
        for team_id, team in lineup_teams.items():
            participation_id = self._match_team_participation(match_id, team_id)
            for player in team.players:
                if player.provider_id in player_ids:
                    raise CanonicalIngestionError(
                        f"player {player.provider_id} appears for both lineup teams"
                    )
                player_ids.add(player.provider_id)
                self._lineup_player(player, participation_id, lineup.source_path)

    def _events(self, resource: MatchEvents, ingested_match_id: UUID | None) -> None:
        match_id = ingested_match_id or self._mapping_id(
            "match_provider_mappings",
            "match_id",
            ("provider_match_id",),
            (resource.provider_match_id,),
        )
        match_teams = self._current_match_teams(match_id)
        team_entities: dict[str, EventEntity] = {}
        player_entities: dict[str, EventEntity] = {}
        for event in resource.events:
            for entity in (event.team, event.possession_team):
                _collect_event_entity(team_entities, entity, "team")
            _collect_event_entity(player_entities, event.player, "player")
        team_ids = {
            provider_id: self._event_team(entity, resource.source_path)
            for provider_id, entity in team_entities.items()
        }
        player_ids = {
            provider_id: self._event_player(entity, resource.source_path)
            for provider_id, entity in player_entities.items()
        }
        rows: list[tuple[object, ...]] = []
        for event in resource.events:
            team_id = team_ids.get(event.team.provider_id) if event.team is not None else None
            possession_team_id = (
                team_ids.get(event.possession_team.provider_id)
                if event.possession_team is not None
                else None
            )
            for referenced_team_id in (team_id, possession_team_id):
                if referenced_team_id is not None and referenced_team_id not in match_teams:
                    raise CanonicalIngestionError(
                        f"event {event.provider_id} references a team outside match "
                        f"{resource.provider_match_id}"
                    )
            player_id = (
                player_ids.get(event.player.provider_id) if event.player is not None else None
            )
            rows.append(
                (
                    event.provider_id,
                    resource.provider_match_id,
                    event.event_index,
                    match_id,
                    event.provider_event_type,
                    event.period,
                    event.event_clock,
                    team_id,
                    player_id,
                    possession_team_id,
                    self._source.resource_ids[resource.source_path],
                )
            )
        self._publish_event_batch(resource.provider_match_id, rows)

    def _publish_event_batch(self, provider_match_id: str, rows: list[tuple[object, ...]]) -> None:
        self._prepare_event_stage()
        with self._cursor.copy(
            """
            COPY football_event_stage
                (provider_event_id, provider_match_id, event_index, match_id,
                 provider_event_type, period, event_clock, team_id, player_id,
                 possession_team_id, source_resource_id)
            FROM STDIN
            """
        ) as copy:
            for row in rows:
                copy.write_row(row)
        self._cursor.execute("ANALYZE football_event_stage")
        self._cursor.execute(
            """
            UPDATE football_event_stage AS stage
            SET (mapping_id, event_id, mapped_provider_match_id, mapped_match_id,
                 mapped_last_seen_at) = (
                SELECT mapping.id, mapping.event_id, mapping.provider_match_id,
                       catalog.match_id, mapping.last_seen_at
                FROM football.event_provider_mappings AS mapping
                JOIN football.event_catalog AS catalog ON catalog.id = mapping.event_id
                WHERE mapping.provider_id = %s
                  AND mapping.provider_event_id = stage.provider_event_id
            )
            """,
            (self._source.provider_id,),
        )
        conflict = self._cursor.execute(
            """
            SELECT provider_event_id
            FROM football_event_stage
            WHERE mapping_id IS NOT NULL
              AND (mapped_provider_match_id <> provider_match_id
                   OR mapped_match_id <> match_id)
            ORDER BY provider_event_id
            LIMIT 1
            """
        ).fetchone()
        if conflict is not None:
            raise CanonicalIngestionError(f"event {conflict[0]} maps to a different match")
        self._cursor.execute(
            "UPDATE football_event_stage SET event_id = uuidv7() WHERE event_id IS NULL"
        )
        self._cursor.execute(
            """
            INSERT INTO football.event_catalog (id, match_id)
            SELECT stage.event_id, stage.match_id
            FROM football_event_stage AS stage
            WHERE stage.mapping_id IS NULL
            """
        )
        self._cursor.execute(
            """
            INSERT INTO football.event_provider_mappings
                (event_id, provider_id, provider_match_id, provider_event_id,
                 source_snapshot_id, first_seen_at, last_seen_at)
            SELECT stage.event_id, %s, stage.provider_match_id, stage.provider_event_id,
                   %s, %s, %s
            FROM football_event_stage AS stage
            WHERE stage.mapping_id IS NULL
            """,
            (
                self._source.provider_id,
                self._source.snapshot_id,
                self._known_from,
                self._known_from,
            ),
        )
        stale_mappings = self._cursor.execute(
            """
            SELECT mapping_id
            FROM football_event_stage
            WHERE mapping_id IS NOT NULL AND mapped_last_seen_at < %s
            """,
            (self._known_from,),
        ).fetchall()
        self._cursor.executemany(
            """
            UPDATE football.event_provider_mappings
            SET last_seen_at = %s
            WHERE id = %s
            """,
            ((self._known_from, row[0]) for row in stale_mappings),
        )
        self._cursor.execute(
            """
            UPDATE football_event_stage AS stage
            SET (observation_id, observed_event_id, observed_match_id,
                 observed_event_index, observed_provider_event_type, observed_period,
                 observed_event_clock, observed_team_id, observed_player_id,
                 observed_possession_team_id, observed_source_resource_id) = (
                SELECT observation.id, observation.event_id, observation.match_id,
                       observation.event_index, observation.provider_event_type,
                       observation.period, observation.event_clock, observation.team_id,
                       observation.player_id, observation.possession_team_id,
                       observation.source_resource_id
                FROM football.event_observations AS observation
                WHERE observation.source_snapshot_id = %s
                  AND observation.provider_event_id = stage.provider_event_id
            )
            """,
            (self._source.snapshot_id,),
        )
        conflicting_observation = self._cursor.execute(
            """
            SELECT provider_event_id
            FROM football_event_stage
            WHERE observation_id IS NOT NULL
              AND (observed_event_id IS DISTINCT FROM event_id
                   OR observed_match_id IS DISTINCT FROM match_id
                   OR observed_event_index IS DISTINCT FROM event_index
                   OR observed_provider_event_type IS DISTINCT FROM provider_event_type
                   OR observed_period IS DISTINCT FROM period
                   OR observed_event_clock IS DISTINCT FROM event_clock
                   OR observed_team_id IS DISTINCT FROM team_id
                   OR observed_player_id IS DISTINCT FROM player_id
                   OR observed_possession_team_id IS DISTINCT FROM possession_team_id
                   OR observed_source_resource_id IS DISTINCT FROM source_resource_id)
            ORDER BY provider_event_id
            LIMIT 1
            """
        ).fetchone()
        if conflicting_observation is not None:
            raise CanonicalIngestionError(
                f"event {conflicting_observation[0]} has conflicting source facts"
            )
        self._cursor.execute(
            """
            UPDATE football_event_stage AS stage
            SET (current_observation_id, current_known_from) = (
                SELECT observation.id, observation.known_from
                FROM football.event_observations AS observation
                WHERE observation.event_id = stage.event_id
                  AND observation.provider_id = %s
                  AND observation.known_to IS NULL
                  AND observation.source_snapshot_id <> %s
            )
            WHERE stage.mapping_id IS NOT NULL AND stage.observation_id IS NULL
            """,
            (self._source.provider_id, self._source.snapshot_id),
        )
        newer = self._cursor.execute(
            """
            SELECT provider_event_id
            FROM football_event_stage
            WHERE current_known_from >= %s
            ORDER BY provider_event_id
            LIMIT 1
            """,
            (self._known_from,),
        ).fetchone()
        if newer is not None:
            raise CanonicalIngestionError(
                "source snapshot acquisition time must follow current observation"
            )
        current_observations = self._cursor.execute(
            """
            SELECT current_observation_id
            FROM football_event_stage
            WHERE current_observation_id IS NOT NULL
            """,
        ).fetchall()
        self._cursor.executemany(
            "UPDATE football.event_observations SET known_to = %s WHERE id = %s",
            ((self._known_from, row[0]) for row in current_observations),
        )
        missing_row = self._cursor.execute(
            "SELECT count(*) FROM football_event_stage WHERE observation_id IS NULL"
        ).fetchone()
        missing = int(missing_row[0]) if missing_row is not None else -1
        self._cursor.execute(
            """
            INSERT INTO football.event_observations
                (event_id, match_id, provider_id, provider_match_id, provider_event_id,
                 event_index, provider_event_type, period, event_clock, team_id,
                 player_id, possession_team_id, known_from, source_snapshot_id,
                 source_resource_id, acquired_at)
            SELECT stage.event_id, stage.match_id, %s, stage.provider_match_id,
                   stage.provider_event_id, stage.event_index, stage.provider_event_type,
                   stage.period, stage.event_clock, stage.team_id, stage.player_id,
                   stage.possession_team_id, %s, %s, stage.source_resource_id, %s
            FROM football_event_stage AS stage
            WHERE stage.observation_id IS NULL
            """,
            (
                self._source.provider_id,
                self._known_from,
                self._source.snapshot_id,
                self._known_from,
            ),
        )
        if self._cursor.rowcount != missing:
            raise CanonicalIngestionError(
                f"event batch publication is incomplete for match {provider_match_id}"
            )

    def _prepare_event_stage(self) -> None:
        self._cursor.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS football_event_stage (
                provider_event_id text NOT NULL,
                provider_match_id text NOT NULL,
                event_index integer NOT NULL,
                match_id uuid NOT NULL,
                provider_event_type text NOT NULL,
                period smallint NOT NULL,
                event_clock interval NOT NULL,
                team_id uuid,
                player_id uuid,
                possession_team_id uuid,
                source_resource_id uuid NOT NULL,
                event_id uuid,
                mapping_id uuid,
                mapped_provider_match_id text,
                mapped_match_id uuid,
                mapped_last_seen_at timestamptz,
                observation_id uuid,
                observed_event_id uuid,
                observed_match_id uuid,
                observed_event_index integer,
                observed_provider_event_type text,
                observed_period smallint,
                observed_event_clock interval,
                observed_team_id uuid,
                observed_player_id uuid,
                observed_possession_team_id uuid,
                observed_source_resource_id uuid,
                current_observation_id uuid,
                current_known_from timestamptz
            ) ON COMMIT DROP
            """
        )
        self._cursor.execute("TRUNCATE football_event_stage")

    def _event_team(self, entity: EventEntity | None, source_path: str) -> UUID | None:
        if entity is None:
            return None
        return self._team(
            LineupTeam(provider_id=entity.provider_id, name=entity.name, players=()),
            source_path,
        )

    def _event_player(self, entity: EventEntity | None, source_path: str) -> UUID | None:
        if entity is None:
            return None
        player_id = self._identity(
            _IdentitySpec(
                "players",
                "player_provider_mappings",
                "player_id",
                ("provider_player_id",),
            ),
            (entity.provider_id,),
            {},
        )
        new_fact = self._record_player_fact(
            player_id=player_id,
            provider_player_id=entity.provider_id,
            full_name=entity.name,
            nickname=None,
            country_provider_id=None,
            nickname_observed=False,
            country_observed=False,
            observation_kind="event",
            source_path=source_path,
        )
        existing = self._cursor.execute(
            """
            SELECT id FROM football.player_observations
            WHERE source_snapshot_id = %s AND provider_player_id = %s
            """,
            (self._source.snapshot_id, entity.provider_id),
        ).fetchone()
        if existing is not None:
            if new_fact:
                self._update_player_consensus(entity.provider_id)
            return player_id
        if existing is None:
            existing = self._cursor.execute(
                """
                SELECT full_name FROM football.current_player_observations
                WHERE player_id = %s AND provider_id = %s
                """,
                (player_id, self._source.provider_id),
            ).fetchone()
        if existing is not None:
            if existing[0] not in (None, entity.name):
                raise CanonicalIngestionError(
                    f"player {entity.provider_id} has conflicting source names"
                )
            return player_id
        if not self._begin_observation(
            "player_observations",
            "player_id",
            player_id,
            ("provider_player_id",),
            (entity.provider_id,),
        ):
            return player_id
        self._cursor.execute(
            """
                INSERT INTO football.player_observations
                    (player_id, provider_id, provider_player_id, full_name, known_from,
                     fact_status, source_snapshot_id, source_resource_id, acquired_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                player_id,
                self._source.provider_id,
                entity.provider_id,
                entity.name,
                self._known_from,
                "consistent",
                self._source.snapshot_id,
                self._source.resource_ids[source_path],
                self._known_from,
            ),
        )
        return player_id

    def _lineup_player(
        self,
        player: LineupPlayer,
        match_team_participation_id: UUID,
        source_path: str,
    ) -> None:
        player_id = self._player(player, source_path)
        self._cursor.execute(
            """
            INSERT INTO football.match_player_participations
                (match_team_participation_id, player_id)
            VALUES (%s, %s)
            ON CONFLICT (match_team_participation_id, player_id) DO NOTHING
            """,
            (match_team_participation_id, player_id),
        )
        participation_row = _required_row(
            self._cursor.execute(
                """
                SELECT id FROM football.match_player_participations
                WHERE match_team_participation_id = %s AND player_id = %s
                """,
                (match_team_participation_id, player_id),
            ).fetchone(),
            "match player participation",
        )
        participation_id = participation_row[0]
        existing = self._cursor.execute(
            """
            SELECT id FROM football.match_player_participation_observations
            WHERE source_snapshot_id = %s AND match_player_participation_id = %s
            """,
            (self._source.snapshot_id, participation_id),
        ).fetchone()
        if existing is not None:
            return
        observation_row = _required_row(
            self._cursor.execute(
                """
                INSERT INTO football.match_player_participation_observations
                    (match_player_participation_id, provider_id, jersey_number,
                     was_in_lineup, was_starter, known_from, source_snapshot_id,
                     source_resource_id, acquired_at)
                VALUES (%s, %s, %s, true, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    participation_id,
                    self._source.provider_id,
                    player.jersey_number,
                    player.was_starter,
                    self._known_from,
                    self._source.snapshot_id,
                    self._source.resource_ids[source_path],
                    self._known_from,
                ),
            ).fetchone(),
            "match player observation",
        )
        observation_id = observation_row[0]
        self._position_stints(UUID(str(observation_id)), player.positions)
        self._cards(UUID(str(observation_id)), player.cards)

    def _player(self, row: LineupPlayer, source_path: str) -> UUID:
        player_id = self._identity(
            _IdentitySpec(
                "players",
                "player_provider_mappings",
                "player_id",
                ("provider_player_id",),
            ),
            (row.provider_id,),
            {},
        )
        new_fact = self._record_player_fact(
            player_id=player_id,
            provider_player_id=row.provider_id,
            full_name=row.full_name,
            nickname=row.nickname,
            country_provider_id=row.country_provider_id,
            nickname_observed=True,
            country_observed=True,
            observation_kind="lineup",
            source_path=source_path,
        )
        existing = self._cursor.execute(
            """
            SELECT id
            FROM football.player_observations
            WHERE source_snapshot_id = %s AND provider_player_id = %s
            """,
            (self._source.snapshot_id, row.provider_id),
        ).fetchone()
        if existing is not None:
            if new_fact:
                self._update_player_consensus(row.provider_id)
            return player_id
        if not self._begin_observation(
            "player_observations",
            "player_id",
            player_id,
            ("provider_player_id",),
            (row.provider_id,),
        ):
            return player_id
        full_name, nickname, country_provider_id, fact_status = self._player_consensus(
            row.provider_id
        )
        self._cursor.execute(
            """
            INSERT INTO football.player_observations
                (player_id, provider_id, provider_player_id, full_name, nickname,
                 country_provider_id, known_from, fact_status, source_snapshot_id,
                 source_resource_id, acquired_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                player_id,
                self._source.provider_id,
                row.provider_id,
                full_name,
                nickname,
                country_provider_id,
                self._known_from,
                fact_status,
                self._source.snapshot_id,
                self._source.resource_ids[source_path],
                self._known_from,
            ),
        )
        return player_id

    def _record_player_fact(
        self,
        *,
        player_id: UUID,
        provider_player_id: str,
        full_name: str,
        nickname: str | None,
        country_provider_id: str | None,
        nickname_observed: bool,
        country_observed: bool,
        observation_kind: str,
        source_path: str,
    ) -> bool:
        source_resource_id = self._source.resource_ids[source_path]
        fact_payload = {
            "source_snapshot_id": str(self._source.snapshot_id),
            "source_resource_id": str(source_resource_id),
            "provider_player_id": provider_player_id,
            "full_name": full_name,
            "nickname": nickname,
            "country_provider_id": country_provider_id,
            "nickname_observed": nickname_observed,
            "country_observed": country_observed,
            "observation_kind": observation_kind,
        }
        fact_sha256 = hashlib.sha256(canonical_json_bytes(fact_payload)).hexdigest()
        if fact_sha256 in self._recorded_player_fact_sha256:
            return False
        inserted = self._cursor.execute(
            """
            INSERT INTO football.player_source_facts
                (player_id, provider_id, provider_player_id, full_name, nickname,
                 country_provider_id, nickname_observed, country_observed,
                 observation_kind, fact_sha256, source_snapshot_id,
                 source_resource_id, acquired_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (fact_sha256) DO NOTHING
            """,
            (
                player_id,
                self._source.provider_id,
                provider_player_id,
                full_name,
                nickname,
                country_provider_id,
                nickname_observed,
                country_observed,
                observation_kind,
                fact_sha256,
                self._source.snapshot_id,
                source_resource_id,
                self._known_from,
            ),
        ).rowcount
        stored = self._cursor.execute(
            """
            SELECT player_id, provider_id, provider_player_id, full_name, nickname,
                   country_provider_id, nickname_observed, country_observed,
                   observation_kind, source_snapshot_id, source_resource_id, acquired_at
            FROM football.player_source_facts
            WHERE fact_sha256 = %s
            """,
            (fact_sha256,),
        ).fetchone()
        expected = (
            player_id,
            self._source.provider_id,
            provider_player_id,
            full_name,
            nickname,
            country_provider_id,
            nickname_observed,
            country_observed,
            observation_kind,
            self._source.snapshot_id,
            source_resource_id,
            self._known_from,
        )
        if stored != expected:
            raise CanonicalIngestionError(
                f"player {provider_player_id} source fact conflicts with its checksum"
            )
        self._recorded_player_fact_sha256.add(fact_sha256)
        return inserted == 1

    def _player_consensus(
        self, provider_player_id: str
    ) -> tuple[str | None, str | None, str | None, str]:
        rows = self._cursor.execute(
            """
            SELECT full_name, nickname, country_provider_id,
                   nickname_observed, country_observed
            FROM football.player_source_facts
            WHERE source_snapshot_id = %s AND provider_player_id = %s
            ORDER BY fact_sha256
            """,
            (self._source.snapshot_id, provider_player_id),
        ).fetchall()
        if not rows:
            raise CanonicalIngestionError(
                f"player {provider_player_id} has no preserved source facts"
            )
        full_names = {row[0] for row in rows}
        nicknames = {row[1] for row in rows if row[3]}
        countries = {row[2] for row in rows if row[4]}
        conflicting = any(len(values) > 1 for values in (full_names, nicknames, countries))
        return (
            _consensus_value(full_names),
            _consensus_value(nicknames),
            _consensus_value(countries),
            "conflicting" if conflicting else "consistent",
        )

    def _update_player_consensus(self, provider_player_id: str) -> None:
        full_name, nickname, country_provider_id, fact_status = self._player_consensus(
            provider_player_id
        )
        updated = self._cursor.execute(
            """
            UPDATE football.player_observations
            SET full_name = %s, nickname = %s, country_provider_id = %s,
                fact_status = %s
            WHERE source_snapshot_id = %s AND provider_player_id = %s
            """,
            (
                full_name,
                nickname,
                country_provider_id,
                fact_status,
                self._source.snapshot_id,
                provider_player_id,
            ),
        ).rowcount
        if updated != 1:
            raise CanonicalIngestionError(
                f"player {provider_player_id} consensus observation is missing"
            )

    def _identity(
        self,
        spec: _IdentitySpec,
        provider_values: tuple[str, ...],
        canonical_values: dict[str, object],
    ) -> UUID:
        mapped = self._select_mapping(spec, provider_values)
        if mapped is not None:
            self._touch_mapping(spec, provider_values)
            return mapped
        canonical_id = self._insert_canonical(spec.canonical_table, canonical_values)
        self._insert_mapping(spec, canonical_id, provider_values)
        return canonical_id

    def _select_mapping(self, spec: _IdentitySpec, provider_values: tuple[str, ...]) -> UUID | None:
        where = sql.SQL(" AND ").join(
            sql.SQL("{} = %s").format(sql.Identifier(column)) for column in spec.provider_id_columns
        )
        query = sql.SQL(
            "SELECT {canonical} FROM football.{table} "
            "WHERE provider_id = %s AND {where} AND valid_to IS NULL"
        ).format(
            canonical=sql.Identifier(spec.canonical_id_column),
            table=sql.Identifier(spec.mapping_table),
            where=where,
        )
        row = self._cursor.execute(query, (self._source.provider_id, *provider_values)).fetchone()
        return UUID(str(row[0])) if row is not None else None

    def _touch_mapping(self, spec: _IdentitySpec, provider_values: tuple[str, ...]) -> None:
        where = sql.SQL(" AND ").join(
            sql.SQL("{} = %s").format(sql.Identifier(column)) for column in spec.provider_id_columns
        )
        query = sql.SQL(
            "UPDATE football.{table} SET last_seen_at = GREATEST(last_seen_at, %s) "
            "WHERE provider_id = %s AND {where} AND valid_to IS NULL"
        ).format(table=sql.Identifier(spec.mapping_table), where=where)
        self._cursor.execute(query, (self._known_from, self._source.provider_id, *provider_values))

    def _insert_canonical(self, table: str, canonical_values: dict[str, object]) -> UUID:
        if not canonical_values:
            query = sql.SQL("INSERT INTO football.{} DEFAULT VALUES RETURNING id").format(
                sql.Identifier(table)
            )
            row = _required_row(self._cursor.execute(query).fetchone(), table)
            return UUID(str(row[0]))
        columns = sql.SQL(", ").join(map(sql.Identifier, canonical_values))
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in canonical_values)
        query = sql.SQL(
            "INSERT INTO football.{table} ({columns}) VALUES ({values}) RETURNING id"
        ).format(table=sql.Identifier(table), columns=columns, values=placeholders)
        row = _required_row(
            self._cursor.execute(query, tuple(canonical_values.values())).fetchone(),
            table,
        )
        return UUID(str(row[0]))

    def _insert_mapping(
        self,
        spec: _IdentitySpec,
        canonical_id: UUID,
        provider_values: tuple[str, ...],
    ) -> None:
        columns = (
            spec.canonical_id_column,
            "provider_id",
            *spec.provider_id_columns,
            "first_seen_at",
            "last_seen_at",
            "mapping_method",
            "mapping_confidence",
            "source_snapshot_id",
        )
        values: tuple[object, ...] = (
            canonical_id,
            self._source.provider_id,
            *provider_values,
            self._known_from,
            self._known_from,
            "deterministic",
            1.0,
            self._source.snapshot_id,
        )
        query = sql.SQL("INSERT INTO football.{table} ({columns}) VALUES ({values})").format(
            table=sql.Identifier(spec.mapping_table),
            columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
            values=sql.SQL(", ").join(sql.Placeholder() for _ in values),
        )
        self._cursor.execute(query, values)

    def _mapping_id(
        self,
        table: str,
        canonical_column: str,
        provider_columns: tuple[str, ...],
        provider_values: tuple[str, ...],
    ) -> UUID:
        spec = _IdentitySpec("", table, canonical_column, provider_columns)
        mapped = self._select_mapping(spec, provider_values)
        if mapped is None:
            identity = ":".join(provider_values)
            raise CanonicalIngestionError(f"required provider mapping is missing: {identity}")
        return mapped

    def _begin_observation(
        self,
        table: str,
        canonical_column: str,
        canonical_id: UUID,
        provider_columns: tuple[str, ...],
        provider_values: tuple[str, ...],
    ) -> bool:
        provider_where = sql.SQL(" AND ").join(
            sql.SQL("{} = %s").format(sql.Identifier(column)) for column in provider_columns
        )
        existing_query = sql.SQL(
            "SELECT 1 FROM football.{table} WHERE source_snapshot_id = %s AND {provider_where}"
        ).format(table=sql.Identifier(table), provider_where=provider_where)
        existing = self._cursor.execute(
            existing_query, (self._source.snapshot_id, *provider_values)
        ).fetchone()
        if existing is not None:
            return False
        self._close_current_observation(table, canonical_column, canonical_id)
        return True

    def _close_current_observation(
        self, table: str, canonical_column: str, canonical_id: UUID
    ) -> None:
        current_query = sql.SQL(
            "SELECT known_from FROM football.{table} WHERE {canonical} = %s "
            "AND provider_id = %s AND known_to IS NULL"
        ).format(table=sql.Identifier(table), canonical=sql.Identifier(canonical_column))
        current = self._cursor.execute(
            current_query, (canonical_id, self._source.provider_id)
        ).fetchone()
        if current is None:
            return
        if current[0] >= self._known_from:
            raise CanonicalIngestionError(
                "source snapshot acquisition time must follow current observation"
            )
        update_query = sql.SQL(
            "UPDATE football.{table} SET known_to = %s WHERE {canonical} = %s "
            "AND provider_id = %s AND known_to IS NULL"
        ).format(table=sql.Identifier(table), canonical=sql.Identifier(canonical_column))
        self._cursor.execute(
            update_query, (self._known_from, canonical_id, self._source.provider_id)
        )

    def _require_canonical_values(
        self, table: str, canonical_id: UUID, expected: dict[str, object]
    ) -> None:
        columns = sql.SQL(", ").join(map(sql.Identifier, expected))
        query = sql.SQL("SELECT {columns} FROM football.{table} WHERE id = %s").format(
            columns=columns, table=sql.Identifier(table)
        )
        row = self._cursor.execute(query, (canonical_id,)).fetchone()
        if row is None or row != tuple(expected.values()):
            raise CanonicalIngestionError(f"canonical {table} relationship conflicts")

    def _snapshot_team_observation(self, provider_team_id: str) -> tuple[Any, ...] | None:
        return self._cursor.execute(
            """
            SELECT name, gender, country_provider_id
            FROM football.team_observations
            WHERE source_snapshot_id = %s AND provider_team_id = %s
            """,
            (self._source.snapshot_id, provider_team_id),
        ).fetchone()

    def _current_team_observation(self, team_id: UUID) -> tuple[Any, ...] | None:
        return self._cursor.execute(
            """
            SELECT name, gender, country_provider_id
            FROM football.current_team_observations
            WHERE team_id = %s AND provider_id = %s
            """,
            (team_id, self._source.provider_id),
        ).fetchone()

    def _match_team_participation(self, match_id: UUID, team_id: UUID) -> UUID:
        self._cursor.execute(
            """
            INSERT INTO football.match_team_participations (match_id, team_id)
            VALUES (%s, %s) ON CONFLICT (match_id, team_id) DO NOTHING
            """,
            (match_id, team_id),
        )
        row = _required_row(
            self._cursor.execute(
                """
                SELECT id FROM football.match_team_participations
                WHERE match_id = %s AND team_id = %s
                """,
                (match_id, team_id),
            ).fetchone(),
            "match team participation",
        )
        return UUID(str(row[0]))

    def _assert_newer_than_current_match_team_observations(self, match_id: UUID) -> None:
        row = self._cursor.execute(
            """
            SELECT max(observation.known_from)
            FROM football.match_team_participation_observations AS observation
            JOIN football.match_team_participations AS participation
              ON participation.id = observation.match_team_participation_id
            WHERE participation.match_id = %s AND observation.provider_id = %s
              AND observation.known_to IS NULL
            """,
            (match_id, self._source.provider_id),
        ).fetchone()
        if row is not None and row[0] is not None and row[0] >= self._known_from:
            raise CanonicalIngestionError(
                "source snapshot acquisition time must follow current match teams"
            )

    def _current_match_teams(self, match_id: UUID) -> set[UUID]:
        row = self._cursor.execute(
            """
            SELECT home_team_id, away_team_id
            FROM football.current_match_observations
            WHERE match_id = %s AND provider_id = %s
            """,
            (match_id, self._source.provider_id),
        ).fetchone()
        if row is None or row[0] is None or row[1] is None:
            raise CanonicalIngestionError("lineup requires a current match with both teams")
        return {UUID(str(row[0])), UUID(str(row[1]))}

    def _close_current_lineup(self, match_id: UUID) -> None:
        current_row = _required_row(
            self._cursor.execute(
                """
                SELECT max(observation.known_from),
                       bool_and(observation.source_snapshot_id = %s)
                FROM football.match_player_participation_observations AS observation
                JOIN football.match_player_participations AS player
                  ON player.id = observation.match_player_participation_id
                JOIN football.match_team_participations AS team
                  ON team.id = player.match_team_participation_id
                WHERE team.match_id = %s AND observation.provider_id = %s
                  AND observation.known_to IS NULL
                """,
                (self._source.snapshot_id, match_id, self._source.provider_id),
            ).fetchone(),
            "current lineup",
        )
        current, belongs_to_snapshot = current_row
        if current is not None and current >= self._known_from and not belongs_to_snapshot:
            raise CanonicalIngestionError(
                "source snapshot acquisition time must follow current lineup"
            )
        self._cursor.execute(
            """
            UPDATE football.match_player_participation_observations AS observation
            SET known_to = %s
            FROM football.match_player_participations AS player,
                 football.match_team_participations AS team
            WHERE observation.match_player_participation_id = player.id
              AND player.match_team_participation_id = team.id
              AND team.match_id = %s
              AND observation.provider_id = %s
              AND observation.known_to IS NULL
              AND observation.known_from < %s
            """,
            (self._known_from, match_id, self._source.provider_id, self._known_from),
        )

    def _position_stints(self, observation_id: UUID, stints: tuple[PositionStint, ...]) -> None:
        for sequence, stint in enumerate(stints, start=1):
            self._cursor.execute(
                """
                INSERT INTO football.player_position_stints
                    (match_player_observation_id, provider_position_id, position_name,
                     period_from, clock_from, period_to, clock_to, start_reason,
                     end_reason, sequence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    observation_id,
                    stint.provider_position_id,
                    stint.position_name,
                    stint.period_from,
                    stint.clock_from,
                    stint.period_to,
                    stint.clock_to,
                    stint.start_reason,
                    stint.end_reason,
                    sequence,
                ),
            )

    def _cards(self, observation_id: UUID, cards: tuple[PlayerCard, ...]) -> None:
        for sequence, card in enumerate(cards, start=1):
            self._cursor.execute(
                """
                INSERT INTO football.player_cards
                    (match_player_observation_id, card_type, period, event_clock,
                     reason, sequence)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    observation_id,
                    card.card_type,
                    card.period,
                    card.event_clock,
                    card.reason,
                    sequence,
                ),
            )


def _provider_datetime(raw: str | None) -> tuple[datetime | None, str | None]:
    if raw is None:
        return None, None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, raw
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, raw
    return parsed, raw


def _consensus_value(values: set[str | None]) -> str | None:
    return next(iter(values)) if len(values) == 1 else None


def _collect_event_entity(
    entities: dict[str, EventEntity],
    entity: EventEntity | None,
    entity_kind: str,
) -> None:
    if entity is None:
        return
    existing = entities.get(entity.provider_id)
    if existing is not None and existing.name != entity.name:
        raise CanonicalIngestionError(
            f"{entity_kind} {entity.provider_id} has conflicting source names"
        )
    entities[entity.provider_id] = entity


def _require_compatible_team(
    row: Team | LineupTeam,
    gender: str | None,
    country: str | None,
    existing: tuple[Any, ...],
) -> None:
    if existing[0] != row.name:
        raise CanonicalIngestionError(f"team {row.provider_id} has conflicting source names")
    if gender is not None and existing[1] != gender:
        raise CanonicalIngestionError(f"team {row.provider_id} has conflicting source gender")
    if country is not None and existing[2] != country:
        raise CanonicalIngestionError(f"team {row.provider_id} has conflicting source country")


def _result(
    bundle: StatsBombBundle, snapshot_id: UUID, competitions_seen: int
) -> CanonicalIngestionResult:
    team_ids = {
        team.provider_id for match in bundle.matches for team in (match.home_team, match.away_team)
    }
    team_ids.update(team.provider_id for lineup in bundle.lineups for team in lineup.teams)
    team_ids.update(
        entity.provider_id
        for resource in bundle.events
        for event in resource.events
        for entity in (event.team, event.possession_team)
        if entity is not None
    )
    lineup_players = [
        player for lineup in bundle.lineups for team in lineup.teams for player in team.players
    ]
    event_player_ids = {
        event.player.provider_id
        for resource in bundle.events
        for event in resource.events
        if event.player is not None
    }
    player_ids = {player.provider_id for player in lineup_players} | event_player_ids
    return CanonicalIngestionResult(
        source_snapshot_id=snapshot_id,
        competitions_seen=competitions_seen,
        seasons_seen=len({(row.competition_id, row.season_id) for row in bundle.competitions}),
        teams_seen=len(team_ids),
        players_seen=len(player_ids),
        matches_seen=len(bundle.matches),
        lineup_players_seen=len(lineup_players),
        position_stints_seen=sum(len(player.positions) for player in lineup_players),
        cards_seen=sum(len(player.cards) for player in lineup_players),
        events_seen=sum(len(resource.events) for resource in bundle.events),
    )


def _mark_processed(
    cursor: Cursor[Any], source: RegisteredSource, processed_paths: tuple[str, ...]
) -> None:
    cursor.execute(
        """
        UPDATE football.source_resources
        SET parse_status = 'parsed', validation_status = 'valid'
        WHERE source_snapshot_id = %s AND provider_path = ANY(%s)
        """,
        (source.snapshot_id, list(processed_paths)),
    )
    pending_row = _required_row(
        cursor.execute(
            """
            SELECT count(*) FROM football.source_resources
            WHERE source_snapshot_id = %s
              AND (parse_status = 'pending' OR validation_status = 'pending')
            """,
            (source.snapshot_id,),
        ).fetchone(),
        "source resource status",
    )
    pending = pending_row[0]
    status = "validated" if pending == 0 else "acquired"
    cursor.execute(
        "UPDATE football.source_snapshots SET status = %s WHERE id = %s",
        (status, source.snapshot_id),
    )


def _required_row(row: tuple[Any, ...] | None, label: str) -> tuple[Any, ...]:
    if row is None:
        raise CanonicalIngestionError(f"database did not return expected {label}")
    return row
