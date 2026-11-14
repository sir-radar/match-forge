"""Historical match synchronisation for the product sync."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID

import psycopg

from football.product.api_football import (
    ApiFootballError,
    CapabilityStatus,
)
from football.product.domain import (
    MINIMUM_HISTORY_MATCHES,
)
from football.product.football_data_org import (
    FootballDataOrgError,
)
from football.product.identity_crosswalks import FOOTBALL_DATA_COMPETITIONS
from football.product.sync_responses import ProductResponseMixin
from football.product.sync_storage import ProductStorageMixin
from football.product.sync_support import (
    FALLBACK_PROVIDER_CODE,
    HISTORY_JOB_LEASE,
    PROVIDER_CODE,
)
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks
from football.work.storage import WorkLeaseLost


class ProductHistoryMixin(ProductStorageMixin, ProductResponseMixin):
    """Run, queue and record historical match synchronisation."""

    def _sync_history_job(self, league_id: int, season: int) -> tuple[int, int]:
        history_result = self._sync_league_history(league_id, season)
        if history_result is None:
            return 0, 0
        history_snapshot, history_observed_at, stored_history = history_result
        try:
            standings_response = self.client.standings(league_id, season)
        except ApiFootballError:
            standings_response = None
        if standings_response is None or not standings_response.rows:
            competition_id = self._competition_id(str(league_id), history_snapshot)
            fallback_standings = self._fallback_standings(league_id, season)
            if fallback_standings is not None:
                snapshot = self._record_fallback_response(
                    f"standings-{league_id}-{season}", fallback_standings
                )
                standings = self._store_fallback_standings(
                    fallback_standings.rows,
                    competition_id,
                    snapshot,
                    fallback_standings.fetched_at,
                )
            else:
                standings = self._calculate_standings(competition_id, season, history_observed_at)
            return stored_history, standings
        standings_snapshot = self._record_response(
            f"standings-{league_id}-{season}", standings_response
        )
        standings = self._store_standings(
            standings_response.rows, standings_snapshot, standings_response.fetched_at
        )
        return stored_history, standings

    def _sync_league_history(
        self, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        local = self._local_history_result(league_id, season)
        if local is not None:
            self._record_history_sync_attempt(
                league_id, season, local[1], "STORED", ("LOCAL_HISTORY",), ()
            )
            return local

        paths: list[str] = []
        providers: list[str] = []
        latest: tuple[UUID, datetime, int] | None = None
        stored = 0
        sufficient = False
        transient_errors: list[Exception] = []
        for provider_code, provider_season, path in self._history_attempts(league_id, season):
            paths.append(path)
            try:
                result = self._history_attempt(provider_code, league_id, provider_season)
            except ApiFootballError as error:
                if error.capability_status is not CapabilityStatus.PLAN_RESTRICTION:
                    transient_errors.append(error)
                continue
            except (FootballDataOrgError, OSError) as error:
                transient_errors.append(error)
                continue
            if result is not None:
                latest = result
                stored += result[2]
                providers.append(provider_code)
            if self._history_sufficient(league_id, season):
                sufficient = True
                break

        if not sufficient:
            paths.append("INSUFFICIENT_HISTORY")
            if transient_errors:
                raise transient_errors[0]
        return self._finish_history_sync(league_id, season, latest, stored, paths, providers)

    def _history_attempts(self, league_id: int, season: int) -> tuple[tuple[str, int, str], ...]:
        attempts = [(PROVIDER_CODE, season, "API_FOOTBALL_REQUESTED")]
        if self.history_fallback is not None and league_id in FOOTBALL_DATA_COMPETITIONS:
            attempts.extend(
                (
                    (FALLBACK_PROVIDER_CODE, season, "FOOTBALL_DATA_ORG_REQUESTED"),
                    (
                        FALLBACK_PROVIDER_CODE,
                        season - 1,
                        "FOOTBALL_DATA_ORG_PREVIOUS_SEASON",
                    ),
                )
            )
        return tuple(attempts)

    def _history_attempt(
        self, provider_code: str, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        if provider_code == PROVIDER_CODE:
            return self._api_football_history(league_id, season)
        return self._football_data_org_history(league_id, season)

    def _api_football_history(
        self, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        response = self.client.finished_fixtures(league_id, season)
        snapshot = self._record_response(f"history-{league_id}-{season}", response)
        stored = self._store_history(response.rows, snapshot, response.fetched_at)
        return snapshot, response.fetched_at, stored

    def _football_data_org_history(
        self, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        response = self._fallback_history(league_id, season)
        if response is None:
            return None
        snapshot = self._record_fallback_response(f"history-{league_id}-{season}", response)
        competition_id = self._competition_id(str(league_id), snapshot)
        self._fallback_competition_mapping(
            FOOTBALL_DATA_COMPETITIONS[league_id], competition_id, snapshot, response.fetched_at
        )
        stored = self._store_fallback_history(
            response.rows,
            competition_id,
            season,
            snapshot,
            response.fetched_at,
        )
        return snapshot, response.fetched_at, stored

    def _finish_history_sync(
        self,
        league_id: int,
        season: int,
        latest: tuple[UUID, datetime, int] | None,
        stored: int,
        paths: Sequence[str],
        providers: Sequence[str],
    ) -> tuple[UUID, datetime, int] | None:
        attempted_at = latest[1] if latest is not None else datetime.now(UTC)
        status = "UNAVAILABLE" if latest is None else ("STORED" if stored else "EMPTY")
        self._record_history_sync_attempt(
            league_id,
            season,
            attempted_at,
            status,
            tuple(paths),
            tuple(dict.fromkeys(providers)),
        )
        if latest is None:
            return None
        return latest[0], latest[1], stored

    def _local_history_result(
        self, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        if not self._history_sufficient(league_id, season):
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.source_snapshot_id
                FROM football.competition_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = %s
                  AND mapping.provider_competition_id = %s
                  AND mapping.valid_to IS NULL
                ORDER BY mapping.first_seen_at
                LIMIT 1
                """,
                (PROVIDER_CODE, str(league_id)),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return cast(UUID, row[0]), datetime.now(UTC), 0

    def _history_sufficient(self, league_id: int, season: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                WITH targets AS (
                    SELECT fixture.fixture_id, fixture.home_team_id AS team_id,
                           fixture.kickoff_at
                    FROM football.product_fixtures fixture
                    JOIN football.product_competitions competition
                      ON competition.competition_id = fixture.competition_id
                    JOIN football.competition_provider_mappings mapping
                      ON mapping.competition_id = fixture.competition_id
                    JOIN football.providers provider ON provider.id = mapping.provider_id
                    WHERE fixture.status = 'SCHEDULED'
                      AND provider.code = %s
                      AND mapping.provider_competition_id = %s
                      AND competition.season_label = %s
                      AND mapping.valid_to IS NULL
                    UNION ALL
                    SELECT fixture.fixture_id, fixture.away_team_id AS team_id,
                           fixture.kickoff_at
                    FROM football.product_fixtures fixture
                    JOIN football.product_competitions competition
                      ON competition.competition_id = fixture.competition_id
                    JOIN football.competition_provider_mappings mapping
                      ON mapping.competition_id = fixture.competition_id
                    JOIN football.providers provider ON provider.id = mapping.provider_id
                    WHERE fixture.status = 'SCHEDULED'
                      AND provider.code = %s
                      AND mapping.provider_competition_id = %s
                      AND competition.season_label = %s
                      AND mapping.valid_to IS NULL
                ), history_counts AS (
                    SELECT target.fixture_id, target.team_id,
                           count(history.fixture_id) AS match_count
                    FROM targets target
                    LEFT JOIN football.product_team_match_history history
                      ON (history.home_team_id = target.team_id
                          OR history.away_team_id = target.team_id)
                     AND (
                         (history.source_kickoff_precision = 'EXACT'
                          AND history.kickoff_at < target.kickoff_at)
                         OR (history.source_kickoff_precision = 'DATE_ONLY'
                             AND history.kickoff_at::date < target.kickoff_at::date)
                     )
                    GROUP BY target.fixture_id, target.team_id
                )
                SELECT count(*) > 0 AND bool_and(match_count >= %s)
                FROM history_counts
                """,
                (
                    PROVIDER_CODE,
                    str(league_id),
                    str(season),
                    PROVIDER_CODE,
                    str(league_id),
                    str(season),
                    MINIMUM_HISTORY_MATCHES,
                ),
            )
            row = cursor.fetchone()
        return bool(row and row[0])

    def _recover_abandoned_history_jobs(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT football.authorize_worker_publication()")
            cursor.execute(
                """SELECT provider_competition_id,season
                FROM football.product_history_sync_queue
                WHERE job_status='RUNNING' AND claimed_at < clock_timestamp() - %s
                  AND NOT EXISTS (SELECT 1 FROM football.product_history_work binding
                      WHERE binding.job_id=product_history_sync_queue.job_id
                        AND binding.queued_at=product_history_sync_queue.queued_at)
                ORDER BY ('history-queue:'||provider_competition_id||':'||season) COLLATE "C"
                """,
                (HISTORY_JOB_LEASE,),
            )
            for league_id, season in cursor.fetchall():
                cursor.execute(
                    "SELECT football.record_transaction_lock(51,%s)",
                    (f"history-queue:{league_id}:{season}",),
                )
                cursor.execute(
                    """UPDATE football.product_history_sync_queue
                    SET job_status='PENDING',claimed_at=NULL,started_at=NULL,
                        next_attempt_at=NULL,updated_at=clock_timestamp(),
                        last_error=COALESCE(last_error,'worker lease expired')
                    WHERE provider_competition_id=%s AND season=%s
                      AND job_status='RUNNING' AND claimed_at < clock_timestamp() - %s
                      AND NOT EXISTS (SELECT 1 FROM football.product_history_work binding
                          WHERE binding.job_id=product_history_sync_queue.job_id
                            AND binding.queued_at=product_history_sync_queue.queued_at)""",
                    (league_id, season, HISTORY_JOB_LEASE),
                )

    def _enqueue_history_jobs(self, candidates: Sequence[tuple[int, int]]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT football.authorize_worker_publication()")
            requested: dict[tuple[str, int], datetime] = {}
            for league_id, season in candidates:
                key = (str(league_id), season)
                if key not in requested:
                    cursor.execute("SELECT clock_timestamp()")
                    stamp = cursor.fetchone()
                    assert stamp is not None
                    requested[key] = stamp[0]
            backlog: set[tuple[str, int]] = set()
            if self.sync_run_id is not None:
                cursor.execute(
                    """SELECT provider_competition_id,season
                    FROM football.product_history_sync_queue WHERE job_status='PENDING'"""
                )
                backlog.update(cursor.fetchall())
            keys = sorted(
                requested.keys() | backlog, key=lambda key: f"history-queue:{key[0]}:{key[1]}"
            )
            for league_key, season in keys:
                cursor.execute(
                    "SELECT football.record_transaction_lock(51,%s)",
                    (f"history-queue:{league_key}:{season}",),
                )
                if (league_key, season) not in requested:
                    cursor.execute(
                        """UPDATE football.product_history_sync_queue
                        SET sync_run_id=%s,updated_at=clock_timestamp()
                        WHERE provider_competition_id=%s AND season=%s AND job_status='PENDING'""",
                        (self.sync_run_id, league_key, season),
                    )
                    continue
                cursor.execute(
                    """
                    INSERT INTO football.product_history_sync_queue (
                        provider_competition_id, season, sync_run_id, queued_at
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (provider_competition_id, season) DO UPDATE SET
                        sync_run_id = EXCLUDED.sync_run_id,
                        job_status = CASE
                            WHEN football.product_history_sync_queue.job_status IN
                                 ('SUCCEEDED', 'FAILED') THEN 'PENDING'
                            ELSE football.product_history_sync_queue.job_status
                        END,
                        queued_at = CASE
                            WHEN football.product_history_sync_queue.job_status IN
                                 ('SUCCEEDED', 'FAILED') THEN EXCLUDED.queued_at
                            ELSE football.product_history_sync_queue.queued_at
                        END,
                        started_at = CASE
                            WHEN football.product_history_sync_queue.job_status IN
                                 ('SUCCEEDED', 'FAILED') THEN NULL
                            ELSE football.product_history_sync_queue.started_at
                        END,
                        finished_at = CASE
                            WHEN football.product_history_sync_queue.job_status IN
                                 ('SUCCEEDED', 'FAILED') THEN NULL
                            ELSE football.product_history_sync_queue.finished_at
                        END,
                        next_attempt_at = CASE
                            WHEN football.product_history_sync_queue.job_status IN
                                 ('SUCCEEDED', 'FAILED') THEN NULL
                            ELSE football.product_history_sync_queue.next_attempt_at
                        END,
                        last_error = CASE
                            WHEN football.product_history_sync_queue.job_status IN
                                 ('SUCCEEDED', 'FAILED') THEN NULL
                            ELSE football.product_history_sync_queue.last_error
                        END,
                        attempt_count = CASE
                            WHEN football.product_history_sync_queue.job_status IN
                                 ('SUCCEEDED', 'FAILED') THEN 0
                            ELSE football.product_history_sync_queue.attempt_count
                        END,
                        updated_at = clock_timestamp()
                    """,
                    (league_key, season, self.sync_run_id, requested[(league_key, season)]),
                )

    def _process_history_queue(self, concurrency: int) -> dict[str, int]:
        if concurrency > 1 and self.history_worker_factory is None:
            raise ValueError("history_worker_factory is required for concurrent history sync")
        from football.product.history_worker import HistorySyncWorker

        factory = self.history_worker_factory or (
            lambda: nullcontext(
                HistorySyncWorker(
                    self.connection,
                    self.client,
                    self.data_root,
                    self.artifact_path,
                    self.history_fallback,
                    sync_run_id=self.sync_run_id,
                )
            )
        )
        total = self._history_queue_total()
        self.connection.commit()
        batch_started_at = self._database_now()
        self.connection.commit()
        lock = threading.Lock()
        active = 0
        peak = 0

        def consume() -> dict[str, int]:
            nonlocal active, peak
            counts = {
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "pending_retry": 0,
                "history_matches": 0,
                "standings_rows": 0,
            }
            with factory() as worker:
                while (job := worker._claim_history_job(batch_started_at)) is not None:
                    job_id, league_id, season, attempt_count = job
                    with lock:
                        active += 1
                        peak = max(peak, active)
                    try:
                        history_matches, standings_rows = worker._sync_history_job(
                            league_id, season
                        )
                        worker._complete_history_job(job_id)
                    except WorkLeaseLost:
                        worker.connection.rollback()
                        raise
                    except (
                        ApiFootballError,
                        FootballDataOrgError,
                        psycopg.Error,
                        OSError,
                    ) as error:
                        worker.connection.rollback()
                        state = worker._retry_history_job(job_id, attempt_count, error)
                        counts["pending_retry" if state == "RETRY_WAIT" else "failed"] += 1
                    except Exception as error:
                        worker.connection.rollback()
                        worker._fail_history_job(job_id, error)
                        counts["failed"] += 1
                    else:
                        counts["succeeded"] += 1
                        counts["history_matches"] += history_matches
                        counts["standings_rows"] += standings_rows
                    finally:
                        counts["processed"] += 1
                        with lock:
                            active -= 1
            return counts

        results: list[dict[str, int]] = []
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            results = [
                future.result() for future in [executor.submit(consume) for _ in range(concurrency)]
            ]
        return {
            "total": total,
            "peak_concurrency": peak,
            **{
                key: sum(result[key] for result in results)
                for key in (
                    "processed",
                    "succeeded",
                    "failed",
                    "pending_retry",
                    "history_matches",
                    "standings_rows",
                )
            },
        }

    def _history_queue_total(self) -> int:
        with self.connection.cursor() as cursor:
            if self.sync_run_id is None:
                cursor.execute(
                    "SELECT count(*) FROM football.product_history_sync_queue "
                    "WHERE job_status IN ('PENDING', 'RUNNING')"
                )
            else:
                cursor.execute(
                    "SELECT count(*) FROM football.product_history_sync_queue "
                    "WHERE sync_run_id = %s",
                    (self.sync_run_id,),
                )
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def _scheduled_history_leagues(self) -> set[tuple[int, int]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT mapping.provider_competition_id,
                       competition.season_label
                FROM football.product_fixtures fixture
                JOIN football.product_competitions competition
                  ON competition.competition_id = fixture.competition_id
                JOIN football.competition_provider_mappings mapping
                  ON mapping.competition_id = fixture.competition_id
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE fixture.status = 'SCHEDULED'
                  AND fixture.kickoff_at > clock_timestamp()
                  AND provider.code = %s
                  AND mapping.valid_to IS NULL
                  AND mapping.provider_competition_id ~ '^[0-9]+$'
                  AND competition.season_label ~ '^[0-9]+$'
                """,
                (PROVIDER_CODE,),
            )
            return {
                (int(provider_competition_id), int(season))
                for provider_competition_id, season in cursor.fetchall()
            }

    def _history_sync_attempts(
        self, league_seasons: set[tuple[int, int]]
    ) -> dict[tuple[int, int], datetime]:
        if not league_seasons:
            return {}
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT provider_competition_id, season, last_attempted_at
                FROM football.product_history_sync_attempts
                WHERE provider_competition_id = ANY(%s)
                """,
                ([str(league_id) for league_id, _season in league_seasons],),
            )
            return {
                (int(provider_competition_id), int(season)): last_attempted_at
                for provider_competition_id, season, last_attempted_at in cursor.fetchall()
                if (int(provider_competition_id), int(season)) in league_seasons
            }

    def _record_history_sync_attempt(
        self,
        league_id: int,
        season: int,
        attempted_at: datetime,
        status: str,
        resolution_path: Sequence[str],
        provider_codes: Sequence[str],
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.product_history_sync_attempts (
                    provider_competition_id, season, last_attempted_at, last_status,
                    last_resolution_path, last_provider_codes
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (provider_competition_id, season) DO UPDATE SET
                    last_attempted_at = EXCLUDED.last_attempted_at,
                    last_status = EXCLUDED.last_status,
                    last_resolution_path = EXCLUDED.last_resolution_path,
                    last_provider_codes = EXCLUDED.last_provider_codes,
                    attempt_count = football.product_history_sync_attempts.attempt_count + 1
                """,
                (
                    str(league_id),
                    season,
                    attempted_at,
                    status,
                    json.dumps(list(resolution_path)),
                    json.dumps(list(provider_codes)),
                ),
            )

    def backfill_fixtures_from_history(
        self, from_date: date, through_date: date, observed_at: datetime
    ) -> int:
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                WITH matching_results AS (
                    SELECT pf.fixture_id,
                           MIN(history.home_goals) AS home_goals,
                           MIN(history.away_goals) AS away_goals
                    FROM football.product_fixtures pf
                    JOIN football.product_team_match_history history
                      ON history.competition_id = pf.competition_id
                     AND history.home_team_id = pf.home_team_id
                     AND history.away_team_id = pf.away_team_id
                     AND history.kickoff_at::date = pf.kickoff_at::date
                    WHERE pf.kickoff_at::date BETWEEN %s AND %s
                    GROUP BY pf.fixture_id
                    HAVING COUNT(DISTINCT (history.home_goals, history.away_goals)) = 1
                )
                UPDATE football.product_fixtures fixture
                SET status = 'FINISHED',
                    home_score = result.home_goals,
                    away_score = result.away_goals,
                    result_score_basis = 'UNKNOWN',
                    updated_at = %s
                FROM matching_results result
                WHERE fixture.fixture_id = result.fixture_id
                  AND (
                      fixture.status <> 'FINISHED'
                      OR fixture.home_score IS NULL
                      OR fixture.away_score IS NULL
                  )
                """,
                (from_date, through_date, observed_at),
            )
            updated = cursor.rowcount
            cursor.execute(
                """
                INSERT INTO football.product_fixtures (
                    fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                    status, home_score, away_score, forecast_availability, updated_at
                )
                SELECT history.fixture_id, history.competition_id,
                       history.home_team_id, history.away_team_id, history.kickoff_at,
                       'FINISHED', history.home_goals, history.away_goals,
                       'NOT_ENOUGH_HISTORY', %s
                FROM football.product_eligible_match_history history
                WHERE history.kickoff_at::date BETWEEN %s AND %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM football.product_fixtures fixture
                      WHERE fixture.competition_id = history.competition_id
                        AND fixture.home_team_id = history.home_team_id
                        AND fixture.away_team_id = history.away_team_id
                        AND fixture.kickoff_at::date = history.kickoff_at::date
                  )
                ON CONFLICT (fixture_id) DO UPDATE SET
                    status = 'FINISHED',
                    home_score = EXCLUDED.home_score,
                    away_score = EXCLUDED.away_score,
                    result_score_basis = 'UNKNOWN',
                    updated_at = EXCLUDED.updated_at
                WHERE football.product_fixtures.status <> 'FINISHED'
                   OR football.product_fixtures.home_score IS NULL
                   OR football.product_fixtures.away_score IS NULL
                """,
                (observed_at, from_date, through_date),
            )
            return updated + cursor.rowcount
