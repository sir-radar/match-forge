"""Calendar and detail synchronisation for the operational provider sync."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from football.product.competition_geography import (
    refresh_competition_geography,
)
from football.product.external_predictions import settle_external_predictions
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.live_resources import (
    normalize_events,
    normalize_statistics,
)
from football.product.operational_observations import OperationalObservationMixin
from football.product.operational_support import (
    DetailCounts,
    FixtureObservation,
    SyncCounts,
    _cache_fresh_until,
    _detail_priority,
    _fotmob_resources,
    _newer_calendar_row,
)
from football.providers.fotmob import (
    FotmobClient,
    FotmobLiveScore,
    FotmobResponse,
)
from football.providers.pitchapi import (
    PitchApiClient,
    PitchApiFixture,
    PitchApiResponse,
)


class OperationalDetailMixin(OperationalObservationMixin):
    """Fetch calendars and prioritized match details for live sync runs."""

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
            self._store_normalized_resource(row, resource_type, payload, response, snapshot)
        self.connection.commit()
        return DetailCounts(
            attempted_requests=1,
            successful_requests=1,
            resources=len(resources),
            fresh_until=_cache_fresh_until(response),
        )

    def _pitchapi_details(self, client: PitchApiClient, row: PitchApiFixture) -> DetailCounts:
        fixture_id = self._resolve_fixture(row)
        self.connection.commit()
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
            self._store_normalized_resource(row, resource_type, response.data, response, snapshot)
            self.connection.commit()
        return DetailCounts(attempted, successful, failed, resources)

    def _store_normalized_resource(
        self,
        row: FixtureObservation,
        resource_type: str,
        payload: Mapping[str, Any] | list[Any],
        response: FotmobResponse | PitchApiResponse,
        snapshot_id: UUID,
    ) -> None:
        if resource_type == "EVENTS":
            normalized = normalize_events(
                self.provider_code,
                row.provider_match_id,
                payload,
                home_provider_team_id=row.provider_home_team_id,
                away_provider_team_id=row.provider_away_team_id,
            )
            normalized_type = "NORMALIZED_EVENTS"
        elif resource_type == "STATISTICS":
            normalized = normalize_statistics(self.provider_code, payload)
            normalized_type = "NORMALIZED_STATISTICS"
        else:
            return
        self._store_resource(
            row.provider_match_id,
            self._resolve_fixture(row),
            normalized_type,
            normalized,
            response,
            snapshot_id,
            eligibility="ELIGIBLE",
        )

    def _fetch_prioritized_details(
        self,
        resolved: Sequence[tuple[FixtureObservation, UUID | None]],
        detail: Any,
        *,
        bulk_limit: int,
        live_limit: int,
        recovery_ids: frozenset[str] = frozenset(),
        acquisition_counts: SyncCounts | None = None,
        recovery_counts: SyncCounts | None = None,
    ) -> tuple[DetailCounts, int, int]:
        attempted = successful = failed = resources = used_bulk = used_live = 0
        names = [f"match-{row.provider_match_id}-details" for row, _ in resolved]
        states = dict(
            self.connection.execute(
                """SELECT resource_name,last_attempt_at FROM football.product_provider_refresh_state
               WHERE provider_code = %s AND resource_name = ANY(%s)""",
                (self.provider_code, names),
            ).fetchall()
        )
        oldest = datetime.min.replace(tzinfo=UTC)
        for row, _fixture_id in sorted(
            resolved,
            key=lambda item: (
                not (
                    item[0].status in {"LIVE", "HALF_TIME", "INTERRUPTED", "SUSPENDED"}
                    and item[0].provider_match_id not in recovery_ids
                ),
                states.get(f"match-{item[0].provider_match_id}-details", oldest),
                _detail_priority(item[0], item[1]),
            ),
        ):
            is_live = (
                row.status in {"LIVE", "HALF_TIME", "INTERRUPTED", "SUSPENDED"}
                and row.provider_match_id not in recovery_ids
            )
            if is_live and used_live >= live_limit:
                continue
            if not is_live and used_bulk >= bulk_limit:
                continue
            name = f"match-{row.provider_match_id}-details"
            claimed = self._claim_refresh(name)
            if claimed is None:
                continue
            used_live += int(is_live)
            used_bulk += int(not is_live)
            item = cast(DetailCounts, detail(row))
            self._complete_refresh(name, claimed, item)
            scope = recovery_counts if row.provider_match_id in recovery_ids else acquisition_counts
            if scope is not None:
                self._add_detail_counts(scope, item)
            attempted += item.attempted_requests
            successful += item.successful_requests
            failed += item.failed_requests
            resources += item.resources
        return DetailCounts(attempted, successful, failed, resources), used_bulk, used_live

    @staticmethod
    def _add_detail_counts(counts: SyncCounts, item: DetailCounts) -> None:
        counts.attempted_requests += item.attempted_requests
        counts.successful_requests += item.successful_requests
        counts.failed += item.failed_requests
        counts.resources += item.resources

    @staticmethod
    def _record_missing_recovery(counts: SyncCounts, missing: set[str]) -> None:
        if missing:
            reason = "UNRESOLVED_FIXTURE_NOT_IN_PROVIDER_RESPONSE"
            counts.failed += len(missing)
            counts.failure_reasons[reason] = counts.failure_reasons.get(reason, 0) + len(missing)

    def _recover_unresolved(
        self,
        from_date: date,
        fetch: Any,
        normalize: Any,
        limit: int,
        counts: SyncCounts,
        competition_id: str | None,
    ) -> list[tuple[FixtureObservation, UUID | None]]:
        targets = self.connection.execute(
            """SELECT (f.kickoff_at AT TIME ZONE 'UTC')::date,f.provider_match_id
               FROM football.product_recoverable_fixtures f
               LEFT JOIN football.product_provider_refresh_state state
                 ON state.provider_code=f.provider_code AND state.resource_name=
                     'fixtures-' || to_char(f.kickoff_at AT TIME ZONE 'UTC','YYYY-MM-DD')
               WHERE f.provider_code=%s
                 AND (%s::text IS NULL OR EXISTS (
                     SELECT 1 FROM football.competition_provider_mappings cm
                     JOIN football.providers p ON p.id=cm.provider_id AND p.code=f.provider_code
                     WHERE cm.competition_id=f.competition_id AND cm.provider_competition_id=%s
                       AND cm.valid_to IS NULL AND cm.mapping_confidence=1
                       AND football.product_mapping_trusted('competition',cm.id,cm.competition_id)))
                 AND f.kickoff_at < (%s::date::timestamp AT TIME ZONE 'UTC')
                 AND NOT EXISTS (SELECT 1 FROM football.product_provider_fixture_observations o
                                 WHERE o.canonical_fixture_id=f.fixture_id
                                   AND o.provider_code=f.provider_code
                                   AND o.last_fetched_at>clock_timestamp()-%s)
                 AND (state.next_attempt_at IS NULL OR state.next_attempt_at<=clock_timestamp())
               ORDER BY state.last_attempt_at NULLS FIRST,f.kickoff_at,f.fixture_id
               LIMIT %s""",
            (
                self.provider_code,
                competition_id,
                competition_id,
                from_date,
                self.stale_after,
                limit,
            ),
        ).fetchall()
        days: dict[date, set[str]] = {}
        for day, match_id in targets:
            days.setdefault(day, set()).add(match_id)
        resolved: list[tuple[FixtureObservation, UUID | None]] = []
        for day, ids in days.items():
            name = f"fixtures-{day.isoformat()}"
            claimed = self._claim_refresh(name)
            if claimed is None:
                continue
            successful = 0
            counts.attempted_requests += 1
            try:
                self.pacer.wait()
                response = fetch(day)
                successful = 1
                counts.successful_requests += 1
                snapshot = self._record_response(name, response)
                self.connection.commit()
                rows = tuple(
                    row
                    for row in normalize(response)
                    if row.provider_match_id in ids
                    and (competition_id is None or row.provider_competition_id == competition_id)
                )
                counts.fetched += len(rows)
                resolved.extend(self._ingest_observations(rows, snapshot, counts))
                missing = ids - {row.provider_match_id for row in rows}
                self._record_missing_recovery(counts, missing)
            except (OSError, RuntimeError, ValueError) as error:
                counts.failed += 1
                reason = str(error).splitlines()[0]
                counts.failure_reasons[reason] = counts.failure_reasons.get(reason, 0) + 1
                self._complete_refresh(name, claimed, DetailCounts(1, successful, 1))
            else:
                self._complete_refresh(
                    name,
                    claimed,
                    DetailCounts(
                        1, 1, int(bool(missing)), fresh_until=_cache_fresh_until(response)
                    ),
                    error="RECOVERY_FIXTURES_MISSING" if missing else None,
                )
        with self.connection.transaction():
            reconcile_product_fixtures(self.connection)
        return resolved

    def _sync_dates(
        self,
        from_date: date,
        through_date: date,
        *,
        fetch: Any,
        normalize: Any,
        detail: Any,
        details_limit: int,
        live_details_limit: int,
        competition_id: str | None,
    ) -> dict[str, object]:
        if through_date < from_date or (through_date - from_date).days > 366:
            raise ValueError("provider sync date range must be ordered and at most 367 days")
        if not 0 <= details_limit <= 100 or not 0 <= live_details_limit <= 100:
            raise ValueError("details limits must be between 0 and 100")
        sync_started = datetime.now(UTC)
        counts = SyncCounts()
        resolved_batch: dict[str, tuple[FixtureObservation, UUID | None]] = {}
        day = through_date
        while day >= from_date:
            self.pacer.wait()
            counts.attempted_requests += 1
            response = fetch(day)
            counts.successful_requests += 1
            snapshot_id = self._record_response(f"fixtures-{day.isoformat()}", response)
            self.connection.commit()
            rows: Sequence[FixtureObservation] = normalize(response)
            if competition_id is not None:
                rows = tuple(row for row in rows if row.provider_competition_id == competition_id)
            rows = tuple(row for row in rows if _newer_calendar_row(row, resolved_batch))
            counts.fetched += len(rows)
            resolved = self._ingest_observations(rows, snapshot_id, counts)
            resolved_batch.update(
                (row.provider_match_id, (row, fixture)) for row, fixture in resolved
            )
            self.connection.commit()
            with self.connection.transaction():
                reconcile_product_fixtures(self.connection)
            day -= timedelta(days=1)
        detail_counts, _, _ = self._fetch_prioritized_details(
            tuple(resolved_batch.values()),
            detail,
            bulk_limit=0,
            live_limit=live_details_limit,
        )
        self._add_detail_counts(counts, detail_counts)
        recovery_counts = SyncCounts()
        recovery = self._recover_unresolved(
            from_date, fetch, normalize, details_limit, recovery_counts, competition_id
        )
        bulk_batch = {
            key: value
            for key, value in resolved_batch.items()
            if value[0].status not in {"LIVE", "HALF_TIME", "INTERRUPTED", "SUSPENDED"}
        }
        recovery = [item for item in recovery if item[0].provider_match_id not in resolved_batch]
        bulk_batch.update((row.provider_match_id, (row, fixture)) for row, fixture in recovery)
        self._fetch_prioritized_details(
            tuple(bulk_batch.values()),
            detail,
            bulk_limit=details_limit,
            live_limit=0,
            recovery_ids=frozenset(row.provider_match_id for row, _ in recovery),
            acquisition_counts=counts,
            recovery_counts=recovery_counts,
        )
        settled = settle_external_predictions(self.connection, datetime.now(UTC))
        diagnostics = self._sync_diagnostics(sync_started, from_date)
        self.connection.commit()
        geography = refresh_competition_geography(
            self.connection, self.data_root, self.provider_code
        )
        self.connection.commit()
        acquisition = {
            "status": "COMPLETED_WITH_ERRORS"
            if counts.failed or geography["invalid_snapshots"]
            else "COMPLETED",
            **counts.to_dict(),
        }
        counts.add(recovery_counts)
        return {
            "current_acquisition": acquisition,
            "historical_recovery": {
                "status": "COMPLETED_WITH_ERRORS" if recovery_counts.failed else "COMPLETED",
                **recovery_counts.to_dict(),
            },
            "status": "COMPLETED_WITH_ERRORS"
            if counts.failed or geography["invalid_snapshots"]
            else "COMPLETED",
            "provider": self.provider_code,
            "from_date": from_date.isoformat(),
            "through_date": through_date.isoformat(),
            "settled_external_predictions": settled,
            "competition_geography": geography,
            **diagnostics,
            **counts.to_dict(),
        }
