"""Persist real MVP fixtures, context, standings, and pre-match forecasts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from football.product.api_football import (
    ApiFootballError,
)
from football.product.context_ingestion import ContextObservationStore
from football.product.context_sync import (
    ContextResource,
    FixtureContextTarget,
    plan_context_requests,
)
from football.product.external_predictions import settle_external_predictions
from football.product.identity_admission import admit_provider_mappings
from football.product.sync_forecasts import ProductForecastMixin
from football.product.sync_history import ProductHistoryMixin
from football.product.sync_support import (
    FALLBACK_PROVIDER_CODE,
    HISTORY_JOB_LEASE,
    PRODUCT_FORECAST_ALGORITHM_VERSION,
    PROVIDER_CODE,
    HistoryWorkerFactory,
    _fixture_sync_dates,
    _history_sync_candidates,
    _league_seasons,
)

__all__ = [
    "FALLBACK_PROVIDER_CODE",
    "HISTORY_JOB_LEASE",
    "PRODUCT_FORECAST_ALGORITHM_VERSION",
    "PROVIDER_CODE",
    "HistoryWorkerFactory",
    "ProductSync",
]


class ProductSync(ProductHistoryMixin, ProductForecastMixin):
    def run(
        self,
        requested_date: date,
        *,
        fixture_from_date: date | None = None,
        history_concurrency: int = 3,
        refresh: bool = True,
    ) -> dict[str, int | str]:
        if history_concurrency <= 0:
            raise ValueError("history_concurrency must be positive")
        fixture_dates = _fixture_sync_dates(requested_date, fixture_from_date)
        fixture_history_start = fixture_from_date or fixture_dates[0]
        competition_count, remaining, discovery_error = self._sync_competitions()
        fixture_count, league_seasons = self._sync_fixtures(fixture_dates)
        context_observations = self.sync_context(remaining) if discovery_error is None else 0
        self._recover_abandoned_history_jobs()
        self.connection.commit()
        self._enqueue_history_jobs(league_seasons)
        self.connection.commit()
        queue_result = self._process_history_queue(history_concurrency)
        for provider in (PROVIDER_CODE, FALLBACK_PROVIDER_CODE):
            admit_provider_mappings(self.connection, self.data_root, provider, commit_each=True)
        completed_at = self._database_now()
        history_fixture_count = self.backfill_fixtures_from_history(
            fixture_history_start, requested_date, completed_at
        )
        settled_count = self._settle_external_predictions(completed_at)
        self.connection.commit()
        forecast_count = (
            self.refresh_forecasts(completed_at, admit_mappings=False, commit_batches=True)
            if refresh
            else 0
        )
        self.connection.commit()
        result: dict[str, int | str] = {
            "competitions": competition_count,
            "fixtures": fixture_count,
            "context_observations": context_observations,
            "fixtures_from_history": history_fixture_count,
            "history_matches": queue_result["history_matches"],
            "standings_rows": queue_result["standings_rows"],
            "forecasts": forecast_count,
            "settled_external_predictions": settled_count,
            "history_queue_total": queue_result["total"],
            "history_queue_processed": queue_result["processed"],
            "history_queue_succeeded": queue_result["succeeded"],
            "history_queue_failed": queue_result["failed"],
            "history_queue_pending_retry": queue_result["pending_retry"],
            "history_queue_peak_concurrency": queue_result["peak_concurrency"],
        }
        if discovery_error is not None:
            result["competition_discovery_error"] = discovery_error
        return result

    def _sync_competitions(self) -> tuple[int, int | None, str | None]:
        try:
            response = self.client.competitions()
        except ApiFootballError as error:
            if self.history_fallback is None:
                raise
            return 0, None, str(error)
        snapshot = self._record_response("competitions", response)
        count = self._store_competitions(response.rows, snapshot, response.fetched_at)
        self.connection.commit()
        return count, response.remaining_day, None

    def sync_context(self, remaining_day: int | None, now: datetime | None = None) -> int:
        """Fetch enabled pre-match context without letting provider failures break fixture sync."""
        now = now or datetime.now(UTC)
        if not self.context_config.context_enabled:
            return 0
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture.fixture_id, mapping.provider_match_id, fixture.kickoff_at,
                       injury.status, lineup.status,
                       (SELECT max(snapshot.acquired_at)
                          FROM football.source_snapshots snapshot
                         WHERE snapshot.provider_id = provider.id
                           AND snapshot.source_identity =
                               'fixture-' || mapping.provider_match_id || '-injuries'),
                       (SELECT max(snapshot.acquired_at)
                          FROM football.source_snapshots snapshot
                         WHERE snapshot.provider_id = provider.id
                           AND snapshot.source_identity =
                               'fixture-' || mapping.provider_match_id || '-lineups'),
                       (SELECT count(DISTINCT team_id) = 2
                          FROM football.product_lineup_observations observation
                         WHERE observation.fixture_id = fixture.fixture_id
                           AND observation.lineup_mode = 'CONFIRMED'),
                       fixture.home_team_id, fixture.away_team_id
                FROM football.product_fixtures fixture
                JOIN football.match_provider_mappings mapping
                  ON mapping.match_id = fixture.fixture_id
                JOIN football.providers provider ON provider.id = mapping.provider_id
                JOIN football.product_context_capabilities injury
                  ON injury.competition_id = fixture.competition_id
                 AND injury.provider = 'api_football' AND injury.resource = 'INJURIES'
                JOIN football.product_context_capabilities lineup
                  ON lineup.competition_id = fixture.competition_id
                 AND lineup.provider = 'api_football' AND lineup.resource = 'LINEUPS'
                WHERE provider.code = 'api_football' AND fixture.status = 'SCHEDULED'
                  AND fixture.kickoff_at > %s
                  AND fixture.kickoff_at <= %s + interval '72 hours'
                ORDER BY fixture.kickoff_at, fixture.fixture_id
                """,
                (now, now),
            )
            rows = cursor.fetchall()
        targets = tuple(
            FixtureContextTarget(str(row[1]), row[2], row[3], row[4], row[5], row[6], row[7])
            for row in rows
        )
        by_provider_id = {str(row[1]): (row[0], row[2]) for row in rows}
        requests = plan_context_requests(targets, now, remaining_day, self.context_config)
        store = ContextObservationStore(self.connection)
        count = 0
        for request in requests:
            self.connection.commit()
            fixture_id, kickoff_at = by_provider_id[request.provider_fixture_id]
            try:
                if request.resource is ContextResource.INJURIES:
                    response = self.client.injuries(int(request.provider_fixture_id))
                    snapshot_id = self._record_response(
                        f"fixture-{request.provider_fixture_id}-injuries", response
                    )
                    count += store.persist_availability(fixture_id, response, snapshot_id)
                else:
                    response = self.client.lineups(int(request.provider_fixture_id))
                    snapshot_id = self._record_response(
                        f"fixture-{request.provider_fixture_id}-lineups", response
                    )
                    count += store.persist_lineups(fixture_id, kickoff_at, response, snapshot_id)
            except ApiFootballError as error:
                if error.capability_status is not None:
                    affected_resources = (
                        ("INJURIES", "SUSPENSIONS")
                        if request.resource is ContextResource.INJURIES
                        else (request.resource.value,)
                    )
                    for resource in affected_resources:
                        with self.connection.cursor() as cursor:
                            cursor.execute(
                                """
                                UPDATE football.product_context_capabilities capability
                                SET status = %s, observed_at = %s
                                FROM football.product_fixtures fixture
                                WHERE fixture.fixture_id = %s
                                  AND capability.competition_id = fixture.competition_id
                                  AND capability.provider = 'api_football'
                                  AND capability.resource = %s
                                """,
                                (
                                    error.capability_status.value,
                                    now,
                                    fixture_id,
                                    resource,
                                ),
                            )
                continue
            except ValueError:
                continue
        fixtures = tuple((row[0], row[2], row[8], row[9]) for row in rows)
        count += store.persist_predicted_lineups(fixtures, now)
        store.persist_context_snapshots(fixtures, now)
        return count

    def _sync_fixtures(
        self,
        fixture_dates: Sequence[date],
    ) -> tuple[int, list[tuple[int, int]]]:
        fixture_count = 0
        league_seasons: set[tuple[int, int]] = set()
        for fixture_date in fixture_dates:
            self.connection.commit()
            stored_count, stored_leagues = self._store_requested_fixtures(fixture_date)
            fixture_count += stored_count
            league_seasons.update(stored_leagues)
            self.connection.commit()
        league_seasons.update(self._scheduled_history_leagues())
        ordered_leagues = _history_sync_candidates(
            league_seasons,
            self._history_sync_attempts(league_seasons),
        )
        return fixture_count, ordered_leagues

    def _store_requested_fixtures(self, requested_date: date) -> tuple[int, list[tuple[int, int]]]:
        try:
            response = self.client.fixtures_for_date(requested_date)
        except RuntimeError:
            response = None
        if response is not None and response.rows:
            snapshot = self._record_response(f"fixtures-{requested_date}", response)
            fixtures = self._store_fixtures(response.rows, snapshot, response.fetched_at)
            return len(fixtures), _league_seasons(fixtures)
        fallback = self._fallback_fixtures(requested_date)
        if fallback is not None:
            snapshot = self._record_fallback_response(f"fixtures-{requested_date}", fallback)
            return self._store_fallback_fixtures(fallback.rows, snapshot, fallback.fetched_at)
        if response is not None:
            self._record_response(f"fixtures-{requested_date}", response)
            return 0, []
        raise ValueError("fixture providers unavailable")

    def _settle_external_predictions(self, settled_at: datetime) -> int:
        return settle_external_predictions(self.connection, settled_at)
