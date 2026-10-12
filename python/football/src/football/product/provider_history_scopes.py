"""Resumable operational league/season acquisition; never owns live scheduling."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import Error

from football.product.identity_crosswalks import (
    OPERATIONAL_COMPETITION_CROSSWALKS,
    OPERATIONAL_TEAM_CROSSWALKS,
)
from football.product.operational_provider_sync import OperationalProviderSync
from football.providers.base import ProviderFetchError
from football.providers.fotmob import FotmobClient, FotmobResponse
from football.providers.pitchapi import PitchApiClient, PitchApiResponse


def cached_response(
    sync: OperationalProviderSync, resource: str
) -> FotmobResponse | PitchApiResponse | None:
    with sync.connection.cursor() as cursor:
        cursor.execute(
            """SELECT snapshot.manifest_path, snapshot.manifest_sha256, snapshot.acquired_at
               FROM football.source_snapshots snapshot
               JOIN football.providers provider ON provider.id = snapshot.provider_id
               WHERE provider.code = %s AND snapshot.source_identity = %s
                 AND snapshot.status = 'validated'
               ORDER BY snapshot.acquired_at DESC LIMIT 1""",
            (sync.provider_code, resource),
        )
        stored = cursor.fetchone()
    if stored is None:
        return None
    raw = (sync.data_root / stored[0]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != stored[1]:
        raise ValueError("cached provider snapshot checksum mismatch")
    envelope = json.loads(raw)
    data = envelope if sync.provider_code == "fotmob" else envelope["data"]
    arguments = (resource, stored[2], stored[1], raw, data)
    return (
        FotmobResponse(*arguments)
        if sync.provider_code == "fotmob"
        else PitchApiResponse(*arguments)
    )


def enqueue_seasons(sync: OperationalProviderSync, league_id: str, seasons: list[str]) -> None:
    with sync.connection.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO football.product_provider_history_scopes
               (provider_code, provider_competition_id, season_label)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            [(sync.provider_code, league_id, season) for season in seasons],
        )


def discover_pitchapi(
    sync: OperationalProviderSync, client: PitchApiClient, *, refresh: bool
) -> int:
    response = None if refresh else cached_response(sync, "league-catalogue")
    if response is None:
        sync.pacer.wait()
        response = client.leagues()
        sync._record_response("league-catalogue", response)
        sync.connection.commit()
    if not isinstance(response.data, Mapping):
        raise ValueError("PitchAPI catalogue must be an object")
    data = response.data
    if not isinstance(data, Mapping) or not isinstance(data.get("leagues"), list):
        raise ValueError("PitchAPI catalogue missing leagues")
    scopes = 0
    for league in data["leagues"]:
        if not isinstance(league, Mapping) or not isinstance(league.get("seasons"), list):
            raise ValueError("PitchAPI league missing seasons")
        seasons = [str(season) for season in league["seasons"]]
        snapshot = sync._record_response("league-catalogue", response)
        bind_league_crosswalk(sync, str(league["id"]), league, snapshot)
        enqueue_seasons(sync, str(league["id"]), seasons)
        scopes += len(seasons)
    sync.connection.commit()
    return scopes


def discover_fotmob(
    sync: OperationalProviderSync,
    client: FotmobClient,
    *,
    budget: int,
    refresh: bool,
    competition: str | None = None,
) -> dict[str, object]:
    if budget < 0:
        raise ValueError("provider discovery budget must be nonnegative")
    with sync.connection.cursor() as cursor:
        cursor.execute(
            """SELECT mapping.provider_competition_id
               FROM football.competition_provider_mappings mapping
               JOIN football.providers provider ON provider.id = mapping.provider_id
               LEFT JOIN football.product_fixtures fixture
                 ON fixture.competition_id = mapping.competition_id
               WHERE provider.code = 'fotmob' AND mapping.valid_to IS NULL
                 AND (%s::text IS NULL OR mapping.provider_competition_id = %s)
                 AND NOT EXISTS (
                     SELECT 1 FROM football.product_provider_history_discovery discovery
                     WHERE discovery.provider_code = provider.code
                       AND discovery.provider_competition_id = mapping.provider_competition_id
                       AND discovery.last_error IS NOT NULL AND discovery.next_attempt_at > now()
                 )
               GROUP BY mapping.provider_competition_id
               ORDER BY count(*) FILTER (WHERE fixture.status = 'SCHEDULED'
                   AND fixture.kickoff_at > now()) DESC, mapping.provider_competition_id""",
            (competition, competition),
        )
        leagues = [row[0] for row in cursor.fetchall()]
    requests = scopes = 0
    errors: dict[str, str] = {}
    for league_id in leagues:
        resource = f"league-catalogue-{league_id}"
        response = None if refresh else cached_response(sync, resource)
        if response is None:
            if requests >= budget:
                continue
            requests += 1
        try:
            seasons = _fotmob_seasons(sync, client, league_id, resource, response)
            enqueue_seasons(sync, league_id, seasons)
            scopes += len(seasons)
        except (OSError, ValueError, Error, ProviderFetchError) as failure:
            sync.connection.rollback()
            errors[league_id] = str(failure)
        sync.connection.execute(
            """INSERT INTO football.product_provider_history_discovery
               (provider_code, provider_competition_id, last_attempt_at,
                next_attempt_at, last_error)
               VALUES ('fotmob', %s, now(), now() + interval '1 hour', %s)
               ON CONFLICT (provider_code, provider_competition_id) DO UPDATE
               SET last_attempt_at = EXCLUDED.last_attempt_at,
                   next_attempt_at = EXCLUDED.next_attempt_at, last_error = EXCLUDED.last_error""",
            (league_id, errors.get(league_id)),
        )
        sync.connection.commit()
    return {"scopes": scopes, "requests": requests, "errors": errors}


def _fotmob_seasons(
    sync: OperationalProviderSync,
    client: FotmobClient,
    league_id: str,
    resource: str,
    response: FotmobResponse | PitchApiResponse | None,
) -> list[str]:
    if response is None:
        sync.pacer.wait()
        response = client.league(league_id)
        sync._record_response(resource, response)
        sync.connection.commit()
    if not isinstance(response.data, Mapping):
        raise ValueError("FotMob catalogue must be an object")
    seasons = response.data.get("allAvailableSeasons")
    if not isinstance(seasons, list):
        raise ValueError("FotMob catalogue missing available seasons")
    snapshot = sync._record_response(resource, response)
    details = response.data.get("details", {})
    if isinstance(details, Mapping):
        bind_league_crosswalk(sync, league_id, details, snapshot)
    return [str(season) for season in seasons]


def bind_league_crosswalk(
    sync: OperationalProviderSync, league_id: str, metadata: Mapping[str, Any], snapshot: Any
) -> None:
    crosswalk = OPERATIONAL_COMPETITION_CROSSWALKS.get((sync.provider_code, league_id))
    if crosswalk is None:
        return
    target_provider, target_id, name, country = crosswalk
    source_country = metadata.get("country_code", metadata.get("country"))
    if metadata.get("name") != name or source_country != country:
        raise ValueError("provider catalogue contradicts explicit league crosswalk")
    bind_scoped_mapping(
        sync,
        "competition_provider_mappings",
        "competition_id",
        "provider_competition_id",
        league_id,
        target_provider,
        target_id,
        snapshot,
    )
    for (source_provider, source_id), (
        team_provider,
        team_id,
    ) in OPERATIONAL_TEAM_CROSSWALKS.items():
        if source_provider == sync.provider_code:
            bind_scoped_mapping(
                sync,
                "team_provider_mappings",
                "team_id",
                "provider_team_id",
                source_id,
                team_provider,
                team_id,
                snapshot,
            )


def bind_scoped_mapping(
    sync: OperationalProviderSync,
    table: str,
    canonical_column: str,
    provider_column: str,
    source_id: str,
    target_provider: str,
    target_id: str,
    snapshot: Any,
) -> None:
    with sync.connection.cursor() as cursor:
        target = cursor.execute(
            f"""SELECT mapping.{canonical_column} FROM football.{table} mapping
               JOIN football.providers provider ON provider.id = mapping.provider_id
               WHERE provider.code = %s AND mapping.{provider_column} = %s
                 AND mapping.valid_to IS NULL AND mapping.mapping_confidence = 1""",
            (target_provider, target_id),
        ).fetchone()
        if target is None:
            return
        source = cursor.execute(
            f"""SELECT mapping.{canonical_column} FROM football.{table} mapping
               JOIN football.providers provider ON provider.id = mapping.provider_id
               WHERE provider.code = %s AND mapping.{provider_column} = %s
                 AND mapping.valid_to IS NULL""",
            (sync.provider_code, source_id),
        ).fetchone()
        if source is not None and source[0] == target[0]:
            return
        if source is not None and source[0] != sync._provider_scoped_identity(table, source_id):
            raise ValueError("verified mapping contradicts explicit operational crosswalk")
        cursor.execute(
            f"""UPDATE football.{table} SET valid_to = clock_timestamp()
               WHERE {provider_column} = %s AND valid_to IS NULL
                 AND provider_id = (SELECT id FROM football.providers WHERE code = %s)""",
            (source_id, sync.provider_code),
        )
        cursor.execute(
            f"""INSERT INTO football.{table} (
               {canonical_column}, provider_id, {provider_column}, valid_from, first_seen_at,
               last_seen_at, mapping_method, mapping_confidence, source_snapshot_id)
               SELECT %s, id, %s, clock_timestamp(), clock_timestamp(), clock_timestamp(),
                      'explicit_crosswalk', 1, %s FROM football.providers WHERE code = %s""",
            (target[0], source_id, snapshot, sync.provider_code),
        )
        if table == "team_provider_mappings":
            cursor.execute(
                """UPDATE football.product_team_aliases SET team_id = %s
                   WHERE provider_code = %s AND provider_team_id = %s""",
                (target[0], sync.provider_code, source_id),
            )


def claim_scope(sync: OperationalProviderSync, competition: str | None, season: str | None) -> Any:
    with sync.connection.cursor() as cursor:
        cursor.execute(
            """WITH candidate AS (
               SELECT scope.provider_code, scope.provider_competition_id, scope.season_label
               FROM football.product_provider_history_scopes scope
               WHERE scope.provider_code = %s
                 AND (scope.status IN ('PENDING', 'FAILED')
                      OR (scope.status = 'RUNNING'
                          AND scope.claimed_at < now() - interval '30 minutes'))
                 AND scope.next_attempt_at <= now()
                 AND (%s::text IS NULL OR scope.provider_competition_id = %s)
                 AND (%s::text IS NULL OR scope.season_label = %s)
               ORDER BY scope.attempts, EXISTS (
                   SELECT 1 FROM football.competition_provider_mappings mapping
                   JOIN football.providers provider ON provider.id = mapping.provider_id
                   JOIN football.product_fixtures fixture
                     ON fixture.competition_id = mapping.competition_id
                   WHERE provider.code = scope.provider_code
                     AND mapping.provider_competition_id = scope.provider_competition_id
                     AND mapping.valid_to IS NULL
                     AND fixture.status = 'SCHEDULED' AND fixture.kickoff_at > now()
               ) DESC, scope.season_label DESC, scope.provider_competition_id
               FOR UPDATE OF scope SKIP LOCKED LIMIT 1
            ) UPDATE football.product_provider_history_scopes scope
              SET status = 'RUNNING', attempts = attempts + 1, claimed_at = clock_timestamp(),
                  claim_token = %s
              FROM candidate WHERE scope.provider_code = candidate.provider_code
                AND scope.provider_competition_id = candidate.provider_competition_id
                AND scope.season_label = candidate.season_label
              RETURNING scope.provider_competition_id, scope.season_label, scope.claim_token""",
            (sync.provider_code, competition, competition, season, season, uuid4()),
        )
        result = cursor.fetchone()
    sync.connection.commit()
    sync.connection.execute(
        "SELECT set_config('matchforge.history_claim_token', %s, false)",
        (str(result[2]) if result else "",),
    )
    sync.connection.commit()
    return result[:2] if result else None


def run_scopes(
    sync: OperationalProviderSync,
    client: PitchApiClient | FotmobClient,
    *,
    budget: int,
    competition: str | None = None,
    season: str | None = None,
    refresh: bool = False,
) -> list[dict[str, object]]:
    if budget < 0:
        raise ValueError("provider scope budget must be nonnegative")
    if refresh:
        sync.connection.execute(
            """UPDATE football.product_provider_history_scopes
               SET status = 'PENDING', attempts = 0, next_attempt_at = now()
               WHERE provider_code = %s AND status <> 'RUNNING'
                 AND (%s::text IS NULL OR provider_competition_id = %s)
                 AND (%s::text IS NULL OR season_label = %s)""",
            (sync.provider_code, competition, competition, season, season),
        )
        sync.connection.commit()
    results = []
    for _ in range(budget):
        scope = claim_scope(sync, competition, season)
        if scope is None:
            break
        league_id, selected_season = scope
        error = None
        try:
            response = (
                None if refresh else cached_response(sync, f"league-{league_id}-{selected_season}")
            )
            if response is None:
                sync.pacer.wait()
                response = (
                    client.league_matches(league_id, season=selected_season, status="played")
                    if isinstance(client, PitchApiClient)
                    else client.league(league_id, selected_season)
                )
                snapshot = sync._record_response(f"league-{league_id}-{selected_season}", response)
                with sync.connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE football.product_provider_history_scopes
                           SET source_snapshot_id = %s
                           WHERE provider_code = %s AND provider_competition_id = %s
                             AND season_label = %s AND status = 'RUNNING'
                             AND claim_token = current_setting(
                                 'matchforge.history_claim_token')::uuid""",
                        (snapshot, sync.provider_code, league_id, selected_season),
                    )
                sync.connection.commit()
            result = sync.backfill_league_response(league_id, selected_season, response)
            if result["status"] != "COMPLETED":
                error = "one or more fixture rows failed; replay stored snapshot"
        except (OSError, ValueError, Error, ProviderFetchError) as failure:
            sync.connection.rollback()
            error = str(failure)
            result = {
                "provider": sync.provider_code,
                "league_id": league_id,
                "season": selected_season,
                "status": "FAILED",
                "error": error,
            }
        with sync.connection.cursor() as cursor:
            cursor.execute(
                """UPDATE football.product_provider_history_scopes
                   SET status = %s, last_error = %s, summary = %s::jsonb,
                       next_attempt_at = %s + interval '1 hour'
                   WHERE provider_code = %s AND provider_competition_id = %s
                     AND season_label = %s AND status = 'RUNNING'
                     AND claimed_at >= clock_timestamp() - interval '30 minutes'
                     AND claim_token = current_setting('matchforge.history_claim_token')::uuid""",
                (
                    "FAILED" if error else "SUCCEEDED",
                    error,
                    json.dumps(result),
                    datetime.now(UTC),
                    sync.provider_code,
                    league_id,
                    selected_season,
                ),
            )
            if cursor.rowcount != 1:
                sync.connection.rollback()
                raise RuntimeError("history scope ownership lost")
        sync.connection.execute("SELECT set_config('matchforge.history_claim_token', '', false)")
        sync.connection.commit()
        results.append(result)
    return results
