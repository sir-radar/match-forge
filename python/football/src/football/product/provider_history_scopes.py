"""Resumable operational league/season acquisition; never owns live scheduling."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from psycopg import Error

from football.product.history_requests import (
    HistoryDeferred,
    history_freshness,
    record_history_check,
)
from football.product.identity_crosswalks import OPERATIONAL_COMPETITION_CROSSWALKS
from football.product.operational_provider_sync import OperationalProviderSync, _fotmob_season_rows
from football.providers.base import ProviderFetchError
from football.providers.fotmob import FotmobClient, FotmobResponse
from football.providers.pitchapi import PitchApiClient, PitchApiResponse
from football.storage.raw import ImmutableFileStore
from football.storage.transactions import require_idle_connection


def normalize_seasons(values: Any) -> list[str]:
    """Normalize provider season aliases without imposing a historical floor."""
    if not isinstance(values, list) or not values:
        raise ValueError("provider catalogue missing available seasons")
    seasons = set()
    for value in values:
        if type(value) not in (str, int):
            raise ValueError("invalid provider season identifier")
        match = re.fullmatch(
            r"(\d{4})(?:[/-](\d{2}|\d{4}))?( - (?:Apertura|Clausura))?", str(value).strip()
        )
        if match is None:
            raise ValueError("invalid provider season identifier")
        start = int(match[1])
        if match[2] is None:
            seasons.add(f"{start:04d}{match[3] or ''}")
            continue
        end = int(match[2])
        if len(match[2]) == 2:
            end += start // 100 * 100
            if end < start:
                end += 100
        if end <= start:
            raise ValueError("provider season end must follow its start")
        seasons.add(f"{start:04d}/{end:04d}{match[3] or ''}")
    return sorted(seasons, reverse=True)


def cached_response(
    sync: OperationalProviderSync, resource: str, *, freshness: timedelta | None = None
) -> FotmobResponse | PitchApiResponse | None:
    with sync.connection.cursor() as cursor:
        cursor.execute(
            """SELECT snapshot.manifest_path, snapshot.manifest_sha256, snapshot.acquired_at,
                      CASE WHEN discovery.last_error IS NULL
                        THEN COALESCE(discovery.last_attempt_at, snapshot.acquired_at)
                        ELSE snapshot.acquired_at END,
                      resource.sha256, resource.size_bytes, resource.parse_status,
                      resource.validation_status, clock_timestamp()
               FROM football.source_snapshots snapshot
               JOIN football.providers provider ON provider.id = snapshot.provider_id
               JOIN football.source_resources resource ON resource.source_snapshot_id = snapshot.id
                 AND resource.provider_path = %s
               LEFT JOIN football.product_provider_history_discovery discovery
                 ON discovery.provider_code = provider.code AND discovery.resource_name = %s
               WHERE provider.code = %s AND snapshot.source_identity = %s
                 AND snapshot.status = 'validated'
                 AND (discovery.source_snapshot_id IS NULL
                      OR snapshot.id = discovery.source_snapshot_id)
               ORDER BY snapshot.acquired_at DESC LIMIT 1""",
            (resource, resource, sync.provider_code, resource),
        )
        stored = cursor.fetchone()
    if stored is None:
        return None
    now = stored[8]
    if stored[2] > now or stored[3] > now:
        raise ValueError("cached provider acquisition/check timestamp is in the future")
    if freshness is not None and now - stored[3] >= freshness:
        return None
    path = ImmutableFileStore(sync.data_root).path_for(stored[0])
    if path.is_symlink():
        raise ValueError("cached provider snapshot must not be a symlink")
    raw = path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != stored[1]
        or stored[4] != stored[1]
        or len(raw) != stored[5]
        or stored[6] != "parsed"
        or stored[7] not in {"valid", "warnings"}
    ):
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
    response = (
        None
        if refresh
        else cached_response(sync, "league-catalogue", freshness=history_freshness())
    )
    if response is None:
        sync.pacer.wait()
        response = client.leagues()
        snapshot = sync._record_response("league-catalogue", response)
        record_history_check(sync.connection, sync.provider_code, "league-catalogue", snapshot)
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
        seasons = normalize_seasons(league["seasons"])
        snapshot = sync._record_response("league-catalogue", response)
        bind_league_crosswalk(sync, str(league["id"]), league, snapshot)
        enqueue_seasons(sync, str(league["id"]), seasons)
        scopes += len(seasons)
    sync.connection.commit()
    return scopes


def _fotmob_primary_ids(sync: OperationalProviderSync, identifiers: list[str]) -> list[str]:
    """Resolve catalogue requests through retained provider-declared group relationships."""
    resources = sync.connection.execute(
        """SELECT DISTINCT s.source_identity FROM football.source_snapshots s
           JOIN football.providers p ON p.id=s.provider_id
           WHERE p.code='fotmob' AND s.status='validated'
             AND s.source_identity LIKE 'fixtures-%' ORDER BY s.source_identity"""
    ).fetchall()
    relationships: dict[str, set[str]] = {}
    for (resource,) in resources:
        response = cached_response(sync, resource)
        if response is None or not isinstance(response.data, Mapping):
            continue
        for league in response.data.get("leagues", []):
            if not isinstance(league, Mapping):
                continue
            group, primary = league.get("id"), league.get("primaryId")
            if type(group) in (int, str) and type(primary) in (int, str):
                relationships.setdefault(str(group), set()).add(str(primary))
    resolved = []
    for identifier in identifiers:
        targets = relationships.get(identifier, {identifier})
        if len(targets) != 1:
            raise ValueError("conflicting retained FotMob primary competition IDs")
        primary = next(iter(targets))
        if primary not in resolved:
            resolved.append(primary)
    return resolved


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
        leagues = _fotmob_primary_ids(sync, [row[0] for row in cursor.fetchall()])
    requests = scopes = 0
    errors: dict[str, str] = {}
    deferred_scopes: dict[str, str] = {}
    cooling = {
        row[0]
        for row in sync.connection.execute(
            """SELECT provider_competition_id FROM football.product_provider_history_discovery
               WHERE provider_code='fotmob' AND last_error IS NOT NULL
                 AND next_attempt_at>now()"""
        ).fetchall()
    }
    for league_id in leagues:
        sync.connection.commit()
        if league_id in cooling:
            continue
        resource = f"league-catalogue-{league_id}"
        response = (
            None if refresh else cached_response(sync, resource, freshness=history_freshness())
        )
        if response is None:
            if requests >= budget:
                continue
            requests += 1
        try:
            seasons = _fotmob_seasons(sync, client, league_id, resource, response)
            enqueue_seasons(sync, league_id, seasons)
            scopes += len(seasons)
        except HistoryDeferred as deferred:
            sync.connection.rollback()
            deferred_scopes[league_id] = str(deferred)
            break
        except (OSError, ValueError, Error, ProviderFetchError) as failure:
            sync.connection.rollback()
            errors[league_id] = str(failure)
        if response is not None:
            continue
        sync.connection.execute(
            """INSERT INTO football.product_provider_history_discovery
               (provider_code, provider_competition_id, resource_name, last_attempt_at,
                next_attempt_at, last_error)
               VALUES ('fotmob', %s, %s, now(), now() + interval '1 hour', %s)
               ON CONFLICT (provider_code, resource_name) DO UPDATE
               SET last_attempt_at = CASE WHEN EXCLUDED.last_error IS NULL
                       THEN football.product_provider_history_discovery.last_attempt_at
                       ELSE EXCLUDED.last_attempt_at END,
                   next_attempt_at = CASE WHEN EXCLUDED.last_error IS NULL
                       THEN football.product_provider_history_discovery.next_attempt_at
                       ELSE EXCLUDED.next_attempt_at END,
                   last_error = EXCLUDED.last_error""",
            (league_id, resource, errors.get(league_id)),
        )
        sync.connection.commit()
    return {"scopes": scopes, "requests": requests, "errors": errors, "deferred": deferred_scopes}


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
        snapshot = sync._record_response(resource, response)
        record_history_check(
            sync.connection, sync.provider_code, resource, snapshot, competition=league_id
        )
        sync.connection.commit()
    if not isinstance(response.data, Mapping):
        raise ValueError("FotMob catalogue must be an object")
    seasons = response.data.get("allAvailableSeasons")
    seasons = normalize_seasons(seasons)
    snapshot = sync._record_response(resource, response)
    details = response.data.get("details", {})
    if not isinstance(details, Mapping) or str(details.get("id")) != league_id:
        raise ValueError("FotMob catalogue competition ID mismatch")
    bind_league_crosswalk(sync, league_id, details, snapshot)
    return seasons


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
                 AND mapping.valid_to IS NULL AND mapping.mapping_confidence = 1
                 AND football.product_mapping_trusted(
                     %s, mapping.id, mapping.{canonical_column})""",
            (
                target_provider,
                target_id,
                "competition" if table == "competition_provider_mappings" else "team",
            ),
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
    require_idle_connection(sync.connection, "provider scope claim")
    sync.connection.execute("SELECT set_config('matchforge.history_claim_token', '', false)")
    sync.connection.commit()
    with sync.connection.cursor() as cursor:
        cursor.execute(
            """WITH candidate AS (
               SELECT scope.provider_code, scope.provider_competition_id, scope.season_label
               FROM football.product_provider_history_scopes scope
               LEFT JOIN football.product_provider_scope_work binding USING
                   (provider_code,provider_competition_id,season_label)
               WHERE scope.provider_code = %s
                 AND (scope.status IN ('PENDING', 'FAILED', 'DEFERRED')
                      OR (scope.status = 'SUCCEEDED'
                          AND right(split_part(scope.season_label, ' - ', 1), 4)
                              >= extract(year FROM now())::text)
                      OR (scope.status = 'RUNNING'
                          AND ((binding.work_id IS NULL
                                AND scope.claimed_at < now() - interval '30 minutes')
                               OR EXISTS (SELECT 1 FROM football.work_items work
                                   WHERE work.work_id=binding.work_id
                                     AND work.state='RUNNING'
                                     AND work.lease_until<=clock_timestamp()))))
                 AND (scope.status='PENDING' OR NOT EXISTS (
                     SELECT 1 FROM football.work_items cancelled
                     WHERE cancelled.work_id=binding.work_id AND cancelled.state='CANCELLED'))
                 AND scope.next_attempt_at <= now()
                 AND (%s::text IS NULL OR scope.provider_competition_id = %s)
                 AND (%s::text IS NULL OR scope.season_label = %s)
               ORDER BY EXISTS (
                   SELECT 1 FROM football.competition_provider_mappings mapping
                   JOIN football.providers provider ON provider.id = mapping.provider_id
                   JOIN football.product_fixtures fixture
                     ON fixture.competition_id = mapping.competition_id
                   WHERE provider.code = scope.provider_code
                     AND mapping.provider_competition_id = scope.provider_competition_id
                     AND mapping.valid_to IS NULL
                     AND football.product_mapping_trusted(
                         'competition', mapping.id, mapping.competition_id)
                     AND fixture.identity_status = 'VERIFIED'
                     AND fixture.status = 'SCHEDULED' AND fixture.kickoff_at > now()
               ) DESC,
                 (right(split_part(scope.season_label, ' - ', 1), 4)
                     >= extract(year FROM now())::text) DESC,
                 scope.attempts,
                 scope.season_label DESC, scope.provider_competition_id
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
    require_idle_connection(sync.connection, "provider scope execution")
    if refresh:
        sync.connection.execute("SELECT football.authorize_worker_publication()")
        sync.connection.execute(
            """WITH eligible AS MATERIALIZED (
               SELECT provider_code,provider_competition_id,season_label
               FROM football.product_provider_history_scopes
               WHERE provider_code = %s AND status <> 'RUNNING'
                 AND next_attempt_at <= now()
                 AND (%s::text IS NULL OR provider_competition_id = %s)
                 AND (%s::text IS NULL OR season_label = %s)
               ORDER BY provider_code COLLATE "C",provider_competition_id COLLATE "C",
                        season_label COLLATE "C"
               FOR UPDATE
            ) UPDATE football.product_provider_history_scopes scope SET status='PENDING'
              FROM eligible WHERE scope.provider_code=eligible.provider_code
                AND scope.provider_competition_id=eligible.provider_competition_id
                AND scope.season_label=eligible.season_label""",
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
        status = "SUCCEEDED"
        next_attempt = datetime.now(UTC) + history_freshness()
        try:
            response, acquired = _scope_response(
                sync, client, league_id, selected_season, refresh=refresh
            )
            result = sync.backfill_league_response(
                league_id, selected_season, response, network_acquired=acquired
            )
            if result["status"] != "COMPLETED":
                error = str(result["status"])
                status = "FAILED"
        except HistoryDeferred as deferred:
            sync.connection.rollback()
            error, status, next_attempt = str(deferred), "DEFERRED", deferred.until
            result = {
                "provider": sync.provider_code,
                "league_id": league_id,
                "season": selected_season,
                "status": "DEFERRED",
                "reason": error,
                "until": next_attempt.isoformat(),
            }
        except (OSError, ValueError, Error, ProviderFetchError) as failure:
            sync.connection.rollback()
            error = str(failure)
            status = "FAILED"
            next_attempt = datetime.now(UTC) + timedelta(hours=1)
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
                       next_attempt_at = %s,
                       completed_at = CASE WHEN %s = 'SUCCEEDED' THEN clock_timestamp()
                                           ELSE completed_at END
                   WHERE provider_code = %s AND provider_competition_id = %s
                     AND season_label = %s AND status = 'RUNNING'
                     AND claimed_at >= clock_timestamp() - interval '30 minutes'
                     AND claim_token = current_setting('matchforge.history_claim_token')::uuid""",
                (
                    status,
                    error,
                    json.dumps(result),
                    next_attempt,
                    status,
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
        if status == "DEFERRED":
            break
    return results


def _scope_response(
    sync: OperationalProviderSync,
    client: PitchApiClient | FotmobClient,
    league_id: str,
    selected_season: str,
    *,
    refresh: bool,
) -> tuple[FotmobResponse | PitchApiResponse, bool]:
    sync._heartbeat_history_scope()
    resource = f"league-{league_id}-{selected_season}"
    years = selected_season.split(" - ", 1)[0]
    freshness = history_freshness() if int(years[-4:]) >= datetime.now(UTC).year else None
    response = None if refresh else cached_response(sync, resource, freshness=freshness)
    if response is None and not refresh and sync.provider_code == "fotmob":
        catalogue = cached_response(sync, f"league-catalogue-{league_id}", freshness=freshness)
        if catalogue is not None and isinstance(catalogue, FotmobResponse):
            details = (
                catalogue.data.get("details", {}) if isinstance(catalogue.data, Mapping) else {}
            )
            selected = details.get("selectedSeason") if isinstance(details, Mapping) else None
            if selected is not None and normalize_seasons([selected]) == [selected_season]:
                _fotmob_season_rows(catalogue, league_id, selected_season)
                response = catalogue
    acquired = response is None
    if response is None:
        sync.pacer.wait()
        response = (
            client.league_matches(league_id, season=selected_season, status="played")
            if isinstance(client, PitchApiClient)
            else client.league(league_id, selected_season)
        )
    snapshot = sync._record_response(resource, response)
    if acquired:
        record_history_check(
            sync.connection, sync.provider_code, resource, snapshot, competition=league_id
        )
    sync.connection.execute(
        """UPDATE football.product_provider_history_scopes SET source_snapshot_id = %s
           WHERE provider_code = %s AND provider_competition_id = %s
             AND season_label = %s AND status = 'RUNNING'
             AND claim_token = current_setting('matchforge.history_claim_token')::uuid""",
        (snapshot, sync.provider_code, league_id, selected_season),
    )
    sync.connection.execute("SELECT football.check_provider_scope_work()")
    sync.connection.commit()
    return response, acquired
