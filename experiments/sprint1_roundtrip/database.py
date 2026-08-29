from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import Connection, Cursor
from psycopg.types.json import Jsonb

from experiments.sprint1_roundtrip import NORMALIZER_VERSION
from experiments.sprint1_roundtrip.core import (
    PROJECT_ROOT,
    Finding,
    canonical_json_bytes,
    sha256_bytes,
    stable_uuid,
    utc_now,
)

DEFAULT_DATABASE_URL = "postgresql://football:football@127.0.0.1:55432/football_prototype"
MIGRATION_PATH = PROJECT_ROOT / "infrastructure" / "migrations" / "202608290001_gate_a_contract.sql"


class InjectedPrototypeFailure(RuntimeError):
    pass


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class PrototypeDatabase:
    def __init__(self, database_url: str = DEFAULT_DATABASE_URL) -> None:
        self.database_url = database_url

    @contextmanager
    def connection(self) -> Iterator[Connection[Any]]:
        with psycopg.connect(self.database_url) as connection:
            yield connection

    def migrate(self) -> None:
        migration = MIGRATION_PATH.read_text(encoding="utf-8")
        up_sql = migration.split("-- +goose Up", 1)[1].split("-- +goose Down", 1)[0]
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(up_sql)

    def register_source(
        self,
        manifest: dict[str, Any],
        manifest_sha256: str,
    ) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
        provider_id = stable_uuid("provider", manifest["provider"])
        snapshot_id = stable_uuid("source_snapshot", manifest["source_git_sha"])
        acquired_at = parse_utc(str(manifest["acquired_at"]))
        resources: dict[str, uuid.UUID] = {}
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gate_a.providers (id, slug, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (slug) DO NOTHING
                """,
                (provider_id, manifest["provider"], "StatsBomb Open Data"),
            )
            cursor.execute(
                """
                INSERT INTO gate_a.source_snapshots
                    (id, provider_id, source_repository, source_revision,
                     acquired_at, manifest_sha256)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (provider_id, source_revision) DO NOTHING
                """,
                (
                    snapshot_id,
                    provider_id,
                    manifest["repository"],
                    manifest["source_git_sha"],
                    acquired_at,
                    manifest_sha256,
                ),
            )
            for resource in manifest["resources"]:
                resource_id = stable_uuid(
                    "source_resource",
                    f"{manifest['source_git_sha']}:{resource['path']}",
                )
                resources[str(resource["path"])] = resource_id
                cursor.execute(
                    """
                    INSERT INTO gate_a.source_resources
                        (id, source_snapshot_id, provider_path, sha256,
                         size_bytes, raw_path, acquired_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
                    """,
                    (
                        resource_id,
                        snapshot_id,
                        resource["path"],
                        resource["sha256"],
                        resource["size_bytes"],
                        resource["raw_path"],
                        acquired_at,
                    ),
                )
        return snapshot_id, resources

    @staticmethod
    def _entity(
        cursor: Cursor[Any],
        entity_type: str,
        provider_entity_id: str | int,
        display_name: str,
        provider_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> uuid.UUID:
        canonical_id = stable_uuid(entity_type, provider_entity_id)
        mapping_id = stable_uuid("provider_mapping", f"{entity_type}:{provider_entity_id}")
        cursor.execute(
            """
            INSERT INTO gate_a.canonical_entities (id, entity_type, display_name, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (canonical_id, entity_type, display_name, utc_now()),
        )
        cursor.execute(
            """
            INSERT INTO gate_a.provider_mappings
                (id, provider_id, entity_type, provider_entity_id,
                 canonical_entity_id, source_snapshot_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_id, entity_type, provider_entity_id) DO NOTHING
            """,
            (
                mapping_id,
                provider_id,
                entity_type,
                str(provider_entity_id),
                canonical_id,
                snapshot_id,
            ),
        )
        return canonical_id

    def ingest_relational(
        self,
        competition: dict[str, Any],
        match: dict[str, Any],
        events: list[dict[str, Any]],
        lineups: list[dict[str, Any]],
        snapshot_id: uuid.UUID,
        resource_ids: dict[str, uuid.UUID],
        acquired_at: datetime,
    ) -> dict[str, Any]:
        provider_id = stable_uuid("provider", "statsbomb_open_data")
        provider_match_id = int(match["match_id"])
        match_id = stable_uuid("match", provider_match_id)
        created: dict[str, int] = {}

        with self.connection() as connection, connection.cursor() as cursor:
            competition_id = self._entity(
                cursor,
                "competition",
                competition["competition_id"],
                competition["competition_name"],
                provider_id,
                snapshot_id,
            )
            season_provider_id = f"{competition['competition_id']}:{competition['season_id']}"
            season_id = self._entity(
                cursor,
                "season",
                season_provider_id,
                competition["season_name"],
                provider_id,
                snapshot_id,
            )
            home = match["home_team"]
            away = match["away_team"]
            home_id = self._entity(
                cursor,
                "team",
                home["home_team_id"],
                home["home_team_name"],
                provider_id,
                snapshot_id,
            )
            away_id = self._entity(
                cursor,
                "team",
                away["away_team_id"],
                away["away_team_name"],
                provider_id,
                snapshot_id,
            )
            match_id = self._entity(
                cursor,
                "match",
                provider_match_id,
                f"{home['home_team_name']} vs {away['away_team_name']}",
                provider_id,
                snapshot_id,
            )
            for team_id, side in ((home_id, "home"), (away_id, "away")):
                cursor.execute(
                    """
                    INSERT INTO gate_a.match_teams (canonical_match_id, canonical_team_id, side)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (match_id, team_id, side),
                )

            observation_id = stable_uuid(
                "match_observation",
                f"{snapshot_id}:{provider_match_id}:source",
            )
            observation_payload = {
                "competition_id": str(competition_id),
                "season_id": str(season_id),
                "match_date": match.get("match_date"),
                "kick_off_local": match.get("kick_off"),
                "kickoff_timezone": None,
                "kickoff_at": None,
                "home_score": match.get("home_score"),
                "away_score": match.get("away_score"),
                "provider_last_updated": match.get("last_updated"),
            }
            cursor.execute(
                """
                INSERT INTO gate_a.match_observations
                    (id, canonical_match_id, source_snapshot_id, source_resource_id,
                     provider_match_id, observation_kind, payload,
                     valid_from, known_from)
                VALUES (%s, %s, %s, %s, %s, 'statsbomb_source', %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    observation_id,
                    match_id,
                    snapshot_id,
                    resource_ids["data/matches/43/106.json"],
                    str(provider_match_id),
                    Jsonb(observation_payload),
                    acquired_at,
                    acquired_at,
                ),
            )

            player_count = 0
            stint_count = 0
            for team in lineups:
                team_id = self._entity(
                    cursor,
                    "team",
                    team["team_id"],
                    team["team_name"],
                    provider_id,
                    snapshot_id,
                )
                for player in team["lineup"]:
                    player_id = self._entity(
                        cursor,
                        "player",
                        player["player_id"],
                        player["player_name"],
                        provider_id,
                        snapshot_id,
                    )
                    positions = player.get("positions", [])
                    starter = bool(positions and positions[0].get("start_reason") == "Starting XI")
                    cursor.execute(
                        """
                        INSERT INTO gate_a.match_players
                            (canonical_match_id, canonical_team_id, canonical_player_id,
                             provider_player_id, jersey_number, starter)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            match_id,
                            team_id,
                            player_id,
                            str(player["player_id"]),
                            player.get("jersey_number"),
                            starter,
                        ),
                    )
                    player_count += 1
                    for index, position in enumerate(positions):
                        stint_id = stable_uuid(
                            "position_stint",
                            f"{provider_match_id}:{player['player_id']}:{index}",
                        )
                        cursor.execute(
                            """
                            INSERT INTO gate_a.position_stints
                                (id, canonical_match_id, canonical_team_id, canonical_player_id,
                                 stint_index, provider_position_id, provider_position_name,
                                 from_minute, to_minute, start_reason, end_reason)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                stint_id,
                                match_id,
                                team_id,
                                player_id,
                                index,
                                str(position.get("position_id"))
                                if position.get("position_id") is not None
                                else None,
                                position.get("position"),
                                _minute(position.get("from")),
                                _minute(position.get("to")),
                                position.get("start_reason"),
                                position.get("end_reason"),
                            ),
                        )
                        stint_count += 1

            for event in sorted(events, key=lambda item: int(item["index"])):
                event_id = self._entity(
                    cursor,
                    "event",
                    str(event["id"]),
                    str(event["type"]["name"]),
                    provider_id,
                    snapshot_id,
                )
                cursor.execute(
                    """
                    INSERT INTO gate_a.event_catalogue
                        (canonical_event_id, canonical_match_id, source_snapshot_id,
                         source_resource_id, provider_event_id, event_index)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        event_id,
                        match_id,
                        snapshot_id,
                        resource_ids["data/events/3869685.json"],
                        str(event["id"]),
                        int(event["index"]),
                    ),
                )

            for component in ("metadata", "lineup", "events", "360"):
                cursor.execute(
                    """
                    INSERT INTO gate_a.ingestion_components
                        (source_snapshot_id, canonical_match_id, component,
                         normalizer_version, status, attempt_count, updated_at)
                    VALUES (%s, %s, %s, %s, 'succeeded', 1, %s)
                    ON CONFLICT (
                        source_snapshot_id, canonical_match_id, component, normalizer_version
                    )
                    DO UPDATE SET status = EXCLUDED.status,
                                  attempt_count = gate_a.ingestion_components.attempt_count + 1,
                                  updated_at = EXCLUDED.updated_at
                    """,
                    (snapshot_id, match_id, component, NORMALIZER_VERSION, utc_now()),
                )

            created = {
                "lineup_players_seen": player_count,
                "position_stints_seen": stint_count,
                "events_seen": len(events),
            }
        return created

    def table_counts(self) -> dict[str, int]:
        tables = (
            "providers",
            "source_snapshots",
            "source_resources",
            "canonical_entities",
            "provider_mappings",
            "match_observations",
            "match_teams",
            "match_players",
            "position_stints",
            "event_catalogue",
            "dataset_versions",
            "dataset_files",
        )
        counts: dict[str, int] = {}
        with self.connection() as connection, connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"SELECT count(*) FROM gate_a.{table}")
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(table)
                counts[table] = int(row[0])
        return counts

    def provider_mapping(self, entity_type: str, provider_entity_id: str) -> uuid.UUID:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_entity_id
                FROM gate_a.provider_mappings
                WHERE provider_id = %s AND entity_type = %s AND provider_entity_id = %s
                """,
                (
                    stable_uuid("provider", "statsbomb_open_data"),
                    entity_type,
                    provider_entity_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError((entity_type, provider_entity_id))
            return uuid.UUID(str(row[0]))

    def prove_lineup_rollback(self, match_id: uuid.UUID, team_id: uuid.UUID) -> bool:
        probe_player = stable_uuid("player", "prototype-rollback-probe")
        try:
            with self.connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO gate_a.canonical_entities
                        (id, entity_type, display_name, created_at)
                    VALUES (%s, 'player', 'Prototype rollback probe', %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (probe_player, utc_now()),
                )
                cursor.execute(
                    """
                    INSERT INTO gate_a.match_players
                        (canonical_match_id, canonical_team_id, canonical_player_id,
                         provider_player_id, jersey_number, starter)
                    VALUES (%s, %s, %s, 'prototype-rollback-probe', 0, false)
                    ON CONFLICT DO NOTHING
                    """,
                    (match_id, team_id, probe_player),
                )
                raise InjectedPrototypeFailure("injected before transaction commit")
        except InjectedPrototypeFailure:
            pass

        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM gate_a.match_players WHERE canonical_player_id = %s",
                (probe_player,),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(probe_player)
            return int(row[0]) == 0

    def prove_temporal_queries(self, match_id: uuid.UUID) -> dict[str, Any]:
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = datetime(2024, 2, 1, tzinfo=UTC)
        a_id = stable_uuid("temporal_fixture", "match-a")
        b_id = stable_uuid("temporal_fixture", "match-b")
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gate_a.match_observations
                    (id, canonical_match_id, provider_match_id, observation_kind, payload,
                     valid_from, known_from, known_to)
                VALUES (%s, %s, '3869685', 'prototype_temporal_fixture', %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET known_to = EXCLUDED.known_to
                """,
                (a_id, match_id, Jsonb({"value": "A"}), t1, t1, t2),
            )
            cursor.execute(
                """
                INSERT INTO gate_a.match_observations
                    (id, canonical_match_id, provider_match_id, observation_kind, payload,
                     valid_from, known_from)
                VALUES (%s, %s, '3869685', 'prototype_temporal_fixture', %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (b_id, match_id, Jsonb({"value": "B"}), t1, t2),
            )

        before = self._observation_as_of(match_id, datetime(2024, 1, 15, tzinfo=UTC))
        after = self._observation_as_of(match_id, datetime(2024, 2, 15, tzinfo=UTC))
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload->>'value'
                FROM gate_a.match_observations
                WHERE canonical_match_id = %s
                  AND observation_kind = 'prototype_temporal_fixture'
                  AND known_to IS NULL
                """,
                (match_id,),
            )
            latest_row = cursor.fetchone()
            if latest_row is None:
                raise LookupError("latest temporal fixture")
            latest_for_historical_query = str(latest_row[0])
        return {
            "before_revision": before,
            "after_revision": after,
            "latest_only_trap": latest_for_historical_query,
            "future_observation_leakage": before != "A" or after != "B",
        }

    def _observation_as_of(self, match_id: uuid.UUID, as_of: datetime) -> str:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload->>'value'
                FROM gate_a.match_observations
                WHERE canonical_match_id = %s
                  AND observation_kind = 'prototype_temporal_fixture'
                  AND known_from <= %s
                  AND (known_to IS NULL OR known_to > %s)
                ORDER BY known_from DESC
                LIMIT 1
                """,
                (match_id, as_of, as_of),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(as_of)
            return str(row[0])

    def register_dataset(
        self,
        dataset_id: uuid.UUID,
        dataset_name: str,
        identity_hash: str,
        schema_version: str,
        schema_hash: str,
        snapshot_id: uuid.UUID,
        relative_path: str,
        physical_hash: str,
        logical_hash: str,
        row_count: int,
        size_bytes: int,
    ) -> None:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gate_a.dataset_versions
                    (id, dataset_name, layer, identity_hash, schema_version, schema_sha256,
                     normalizer_version, source_snapshot_id, status, created_at)
                VALUES (%s, %s, 'normalized', %s, %s, %s, %s, %s, 'published', %s)
                ON CONFLICT (identity_hash) DO NOTHING
                """,
                (
                    dataset_id,
                    dataset_name,
                    identity_hash,
                    schema_version,
                    schema_hash,
                    NORMALIZER_VERSION,
                    snapshot_id,
                    utc_now(),
                ),
            )
            file_id = stable_uuid("dataset_file", f"{dataset_id}:{relative_path}")
            cursor.execute(
                """
                INSERT INTO gate_a.dataset_files
                    (id, dataset_version_id, relative_path, physical_sha256,
                     logical_sha256, row_count, size_bytes, schema_sha256)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_version_id, relative_path) DO NOTHING
                """,
                (
                    file_id,
                    dataset_id,
                    relative_path,
                    physical_hash,
                    logical_hash,
                    row_count,
                    size_bytes,
                    schema_hash,
                ),
            )

    def dataset_file_registered(self, dataset_id: uuid.UUID, relative_path: str) -> bool:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM gate_a.dataset_files
                WHERE dataset_version_id = %s AND relative_path = %s
                """,
                (dataset_id, relative_path),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError((dataset_id, relative_path))
            return int(row[0]) == 1

    def record_findings(self, run_id: uuid.UUID, findings: list[Finding]) -> None:
        with self.connection() as connection, connection.cursor() as cursor:
            for item in findings:
                payload = item.to_dict()
                finding_key = sha256_bytes(canonical_json_bytes({"run": str(run_id), **payload}))
                finding_id = stable_uuid("finding", finding_key)
                cursor.execute(
                    """
                    INSERT INTO gate_a.validation_findings
                        (id, run_id, finding_key, rule_code, severity, action, scope_type,
                         provider_entity_id, field_path, message, evidence, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (finding_key) DO NOTHING
                    """,
                    (
                        finding_id,
                        run_id,
                        finding_key,
                        item.rule_code,
                        item.severity,
                        item.action,
                        item.scope_type,
                        item.provider_entity_id,
                        item.field_path,
                        item.message,
                        Jsonb(item.evidence),
                        utc_now(),
                    ),
                )


def _minute(value: str | None) -> int | None:
    if value is None:
        return None
    return int(value.split(":", 1)[0])
