"""Recover missing results through the existing operational ingestion owners."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection, Error

from football.product.api_football import ApiFootballError
from football.product.domain import stable_id
from football.product.external_predictions import settle_external_predictions
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.history_requests import HistoryDeferred
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.operational_support import (
    DetailCounts,
    FixtureObservation,
    SyncCounts,
    _cache_fresh_until,
)
from football.product.sync import ProductSync
from football.product.sync_support import _mapping
from football.providers.base import ProviderFetchError
from football.providers.fotmob import FotmobResponse
from football.providers.pitchapi import PitchApiResponse
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks

Calendar = FotmobResponse | PitchApiResponse


def _due_dates(
    connection: Connection[Any],
    provider: str,
    limit: int,
    day: date | None,
    fixture_id: UUID | None,
) -> list[tuple[date, list[str]]]:
    return connection.execute(
        """WITH due AS (
            SELECT (f.kickoff_at AT TIME ZONE 'UTC')::date AS day,
                   m.provider_match_id, state.last_attempt_at
            FROM football.product_fixtures f
            JOIN football.match_provider_mappings m ON m.match_id=f.fixture_id
              AND m.valid_to IS NULL AND m.mapping_confidence=1
              AND (m.valid_from IS NULL OR m.valid_from<=statement_timestamp())
              AND m.mapping_method IN ('deterministic','explicit_crosswalk','manual')
            JOIN football.providers p ON p.id=m.provider_id
            LEFT JOIN football.product_provider_refresh_state state
              ON state.provider_code=p.code AND state.resource_name=
                 'result-recovery-' || to_char(f.kickoff_at AT TIME ZONE 'UTC','YYYY-MM-DD')
            WHERE p.code=%s AND f.identity_status='VERIFIED'
              AND (%s::date IS NULL OR
                   (f.kickoff_at AT TIME ZONE 'UTC')::date=%s)
              AND (%s::uuid IS NULL OR f.fixture_id=%s)
              AND (EXISTS (SELECT 1 FROM football.product_result_recovery_candidates c
                           WHERE c.fixture_id=f.fixture_id)
                   OR (%s::uuid IS NOT NULL AND f.status='FINISHED' AND NOT EXISTS (
                       SELECT 1 FROM football.fixture_identity_resolutions r
                       WHERE r.member_fixture_id=f.fixture_id AND r.active
                         AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                              OR r.representative_fixture_id<>f.fixture_id)
                   )))
              AND (state.next_attempt_at IS NULL OR state.next_attempt_at<=statement_timestamp())
        )
        SELECT day,array_agg(DISTINCT provider_match_id ORDER BY provider_match_id)
        FROM due GROUP BY day ORDER BY min(last_attempt_at) NULLS FIRST,day LIMIT %s""",
        (provider, day, day, fixture_id, fixture_id, fixture_id, limit),
    ).fetchall()


def _replay_retained(
    sync: OperationalProviderSync, provider_ids: list[str], counts: SyncCounts
) -> list[str]:
    sources = sync.connection.execute(
        """SELECT DISTINCT ON (o.provider_match_id)
            o.provider_match_id,o.provider_competition_id,o.provider_home_team_id,
            o.provider_away_team_id,o.provider_home_team_name,o.provider_away_team_name,
            o.kickoff_at,o.canonical_status,o.provider_status,o.home_score,o.away_score,
            o.match_minute,o.added_time,o.period,o.source_updated_at,o.observed_at,
            o.provider_competition_name,o.source_snapshot_id,o.result_score_basis
        FROM football.product_provider_fixture_observations o
        JOIN football.source_snapshots s ON s.id=o.source_snapshot_id AND s.status='validated'
        WHERE o.provider_code=%s AND o.provider_match_id=ANY(%s)
          AND s.acquired_at<=statement_timestamp() AND o.observed_at<=statement_timestamp()
          AND (o.source_updated_at IS NULL OR o.source_updated_at<=o.observed_at)
          AND o.canonical_status='FINISHED' AND o.result_score_basis='REGULATION_90'
          AND o.home_score IS NOT NULL AND o.away_score IS NOT NULL
          AND o.provider_home_team_id IS NOT NULL AND o.provider_away_team_id IS NOT NULL
          AND o.provider_home_team_name IS NOT NULL AND o.provider_away_team_name IS NOT NULL
        ORDER BY o.provider_match_id,o.source_updated_at DESC NULLS LAST,o.observed_at DESC,
                 o.observation_id DESC""",
        (sync.provider_code, provider_ids),
    ).fetchall()
    sync.connection.commit()
    replayed = 0
    for source in sources:
        with sync.connection.transaction():
            replayed += int(sync.reconcile_retained_observation(source) is not None)
    counts.stored_observations_reconciled += replayed
    if not replayed:
        return provider_ids
    unresolved = sync.connection.execute(
        """SELECT DISTINCT m.provider_match_id
           FROM football.product_result_recovery_candidates f
           JOIN football.match_provider_mappings m ON m.match_id=f.fixture_id
           JOIN football.providers p ON p.id=m.provider_id
           WHERE p.code=%s AND m.valid_to IS NULL AND m.provider_match_id=ANY(%s)
           ORDER BY m.provider_match_id""",
        (sync.provider_code, provider_ids),
    ).fetchall()
    sync.connection.commit()
    return [row[0] for row in unresolved]


def _retry_delay(day: date, now: datetime, minimum: timedelta) -> timedelta:
    # Older unresolved dates change less often. Keep trying, with the existing
    # one-day ceiling for missing calendar results and the configured minimum.
    age = max((now.date() - day).days, 0)
    return max(minimum, min(timedelta(days=1), minimum * (age + 1)))


def _recover_date(
    sync: OperationalProviderSync,
    fetch: Callable[[date], Calendar],
    normalize: Callable[[Any], Sequence[FixtureObservation]],
    day: date,
    provider_ids: list[str],
    counts: SyncCounts,
    recheck: bool,
) -> bool:
    resource = f"result-recovery-{day.isoformat()}"
    claimed = sync._claim_refresh(resource)
    if claimed is None:
        return True
    response = None
    error = None
    retry_after = None
    try:
        if not recheck:
            provider_ids = _replay_retained(sync, provider_ids, counts)
            if not provider_ids:
                sync._complete_refresh(resource, claimed, DetailCounts())
                return True
        counts.attempted_requests += 1
        sync.pacer.wait()
        response = fetch(day)
        counts.successful_requests += 1
        snapshot = sync._record_response(f"fixtures-{day.isoformat()}", response)
        sync.connection.commit()
        requested = frozenset(provider_ids)
        rows = tuple(row for row in normalize(response) if row.provider_match_id in requested)
        counts.fetched += len(rows)
        sync._ingest_observations(rows, snapshot, counts, create_missing=False)
        sync.connection.commit()
        missing = requested - {row.provider_match_id for row in rows}
        if missing:
            error = "RECOVERY_FIXTURES_MISSING"
    except HistoryDeferred as deferred:
        retry_after, error = deferred.until, str(deferred)
    except (Error, ProviderFetchError, OSError, ValueError) as failure:
        error = str(failure).splitlines()[0]
    if error:
        sync.connection.rollback()
        counts.failed += 1
        counts.failure_reasons[error] = counts.failure_reasons.get(error, 0) + 1
    retry_delay = (
        sync.stale_after if retry_after else _retry_delay(day, datetime.now(UTC), sync.stale_after)
    )
    sync._complete_refresh(
        resource,
        claimed,
        DetailCounts(
            1,
            int(response is not None),
            int(error is not None),
            fresh_until=_cache_fresh_until(response) if response is not None else None,
        ),
        error=error,
        retry_after=retry_after,
        retry_delay=retry_delay,
    )
    return retry_after is None


def recover_provider_results(
    sync: OperationalProviderSync,
    fetch: Callable[[date], Calendar],
    normalize: Callable[[Any], Sequence[FixtureObservation]],
    *,
    limit: int,
    day: date | None = None,
    fixture_id: UUID | None = None,
) -> dict[str, object]:
    """Group exact mapped fixtures by UTC source date and share per-day work claims."""
    counts = SyncCounts()
    targets = _due_dates(sync.connection, sync.provider_code, limit, day, fixture_id)
    sync.connection.commit()
    for target_day, provider_ids in targets:
        if not _recover_date(
            sync, fetch, normalize, target_day, provider_ids, counts, recheck=fixture_id is not None
        ):
            break
    if counts.updated or counts.history_inserted or counts.stored_observations_reconciled:
        with sync.connection.transaction():
            reconcile_product_fixtures(sync.connection)
    return {
        "status": "COMPLETED_WITH_ERRORS" if counts.failed else "COMPLETED",
        **counts.to_dict(),
    }


def _api_football_terminal_rows(
    sync: ProductSync,
    rows: Sequence[Mapping[str, Any]],
    provider_ids: list[str],
    observed_at: datetime,
) -> list[Mapping[str, Any]]:
    """Select exact mapped final scores. Never create identity from a recovery request."""
    eligible = []
    for row in rows:
        fixture = _mapping(row, "fixture")
        if str(fixture.get("id")) not in provider_ids:
            continue
        if _mapping(fixture, "status").get("short") not in {"FT", "AET", "PEN"}:
            continue
        goals = _mapping(row, "goals")
        if goals.get("home") is None or goals.get("away") is None:
            continue
        league = _mapping(row, "league")
        teams = _mapping(row, "teams")
        proof = sync.connection.execute(
            """SELECT f.fixture_id,f.competition_id,match.season_id
               FROM football.product_fixtures f
               JOIN football.matches match ON match.id=f.fixture_id
               JOIN football.match_provider_mappings m ON m.match_id=f.fixture_id
               JOIN football.providers p ON p.id=m.provider_id AND p.code='api_football'
               JOIN football.competition_provider_mappings cm ON cm.provider_id=p.id
                 AND cm.competition_id=f.competition_id AND cm.provider_competition_id=%s
                 AND cm.valid_to IS NULL AND football.product_mapping_trusted(
                     'competition', cm.id, cm.competition_id)
               JOIN football.team_provider_mappings h ON h.provider_id=p.id
                 AND h.team_id=f.home_team_id AND h.provider_team_id=%s
                 AND h.valid_to IS NULL
                 AND football.product_mapping_trusted('team', h.id, h.team_id)
               JOIN football.team_provider_mappings a ON a.provider_id=p.id
                 AND a.team_id=f.away_team_id AND a.provider_team_id=%s
                 AND a.valid_to IS NULL
                 AND football.product_mapping_trusted('team', a.id, a.team_id)
               WHERE m.provider_match_id=%s AND m.valid_to IS NULL AND m.mapping_confidence=1
                 AND (m.valid_from IS NULL OR m.valid_from<=statement_timestamp())
                 AND m.mapping_method IN ('deterministic','explicit_crosswalk','manual')
                 AND f.identity_status='VERIFIED' AND f.kickoff_at=%s::timestamptz
                 AND f.updated_at <= %s
                 AND (f.status IN ('SCHEDULED','LIVE','HALF_TIME','SUSPENDED',
                                   'INTERRUPTED','POSTPONED')
                      OR (f.status='FINISHED' AND (
                          (f.home_score=%s AND f.away_score=%s)
                          OR (%s='FT' AND f.result_score_basis='REGULATION_90' AND EXISTS (
                              SELECT 1 FROM football.product_team_match_history h
                              JOIN football.source_snapshots s ON s.id=h.source_snapshot_id
                              WHERE h.fixture_id=f.fixture_id
                                AND h.source_provider_code='api_football'
                                AND (h.home_goals,h.away_goals)=(f.home_score,f.away_score)
                                AND s.acquired_at<%s
                          ))
                      )))""",
            (
                str(league.get("id")),
                str(_mapping(teams, "home").get("id")),
                str(_mapping(teams, "away").get("id")),
                str(fixture["id"]),
                fixture.get("date"),
                observed_at,
                goals["home"],
                goals["away"],
                _mapping(fixture, "status")["short"],
                observed_at,
            ),
        ).fetchall()
        if len(proof) == 1 and proof[0][2] == stable_id(
            "season", proof[0][1], int(league["season"])
        ):
            eligible.append(row)
    return eligible


def recover_api_football_results(
    sync: ProductSync,
    refresh: OperationalProviderSync,
    *,
    limit: int,
    day: date | None,
    fixture_id: UUID | None,
) -> dict[str, object]:
    counts = SyncCounts()
    targets = _due_dates(sync.connection, "api_football", limit, day, fixture_id)
    sync.connection.commit()
    for target_day, provider_ids in targets:
        resource = f"result-recovery-{target_day.isoformat()}"
        claimed = refresh._claim_refresh(resource)
        if claimed is None:
            continue
        counts.attempted_requests += 1
        try:
            refresh.pacer.wait()
            response = sync.client.fixtures_for_date(target_day)
            counts.successful_requests += 1
            counts.fetched += len(response.rows)
        except ApiFootballError as error:
            counts.failed += 1
            reason = "PROVIDER_COOLDOWN" if error.retry_after else "PROVIDER_REQUEST_FAILED"
            counts.failure_reasons[reason] = counts.failure_reasons.get(reason, 0) + 1
            refresh._complete_refresh(
                resource,
                claimed,
                DetailCounts(1, 0, 1),
                error=reason,
                retry_after=error.retry_after,
            )
            if error.retry_after:
                break
            continue
        snapshot = sync._record_response(f"fixtures-{target_day.isoformat()}", response)
        original = sync.connection.execute(
            "SELECT acquired_at FROM football.source_snapshots WHERE id=%s", (snapshot,)
        ).fetchone()
        assert original is not None
        sync.connection.commit()
        with sync.connection.transaction():
            acquire_locks(sync.connection, (IDENTITY_ADMISSION_LOCK,))
            eligible = _api_football_terminal_rows(sync, response.rows, provider_ids, original[0])
            stored = sync._store_fixtures(eligible, snapshot, original[0])
            counts.matched += len(stored)
            counts.updated += len(stored)
            counts.history_inserted += sync._qualify_finished_history(stored, snapshot, original[0])
        refresh._complete_refresh(
            resource,
            claimed,
            DetailCounts(1, 1),
            retry_delay=_retry_delay(target_day, datetime.now(UTC), refresh.stale_after),
        )
    if counts.updated:
        with sync.connection.transaction():
            reconcile_product_fixtures(sync.connection)
    return {
        "status": "COMPLETED_WITH_ERRORS" if counts.failed else "COMPLETED",
        **counts.to_dict(),
    }


def finish_result_recovery(connection: Connection[Any]) -> dict[str, object]:
    """Use the existing settlement queue and report current recovery dispositions."""
    settled = settle_external_predictions(connection, datetime.now(UTC))
    row = connection.execute(
        """SELECT count(*) AS candidates,
                  count(*) FILTER (WHERE f.status<>'FINISHED') AS overdue,
                  count(*) FILTER (WHERE f.identity_status<>'VERIFIED') AS identity_pending,
                  count(*) FILTER (WHERE f.identity_status='VERIFIED' AND NOT EXISTS (
                      SELECT 1 FROM football.match_provider_mappings m
                      JOIN football.providers p ON p.id=m.provider_id
                      WHERE m.match_id=f.fixture_id AND m.valid_to IS NULL
                        AND m.mapping_confidence=1
                        AND p.code IN ('fotmob','pitchapi','api_football')
                        AND m.mapping_method IN ('deterministic','explicit_crosswalk','manual')
                  )) AS no_operational_route
           FROM football.product_result_recovery_candidates f"""
    ).fetchone()
    assert row is not None
    connection.commit()
    return {
        "candidates": row[0],
        "overdue": row[1],
        "identity_pending": row[2],
        "no_operational_route": row[3],
        "settled_external_predictions": settled,
    }
