"""Idempotent operational fixture sync for FotMob and PitchAPI."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast
from uuid import UUID

from psycopg import Connection, Error

from football.product.competition_geography import (
    refresh_competition_geography,
    verified_geographic_scopes,
)
from football.product.domain import (
    canonical_json,
    fixture_identity,
    normalize_team_name,
    sha256_json,
    stable_id,
)
from football.product.external_predictions import settle_external_predictions
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.identity_admission import (
    admit_provider_mappings,
    fixture_identity_blockers,
    verify_source_identifier,
)
from football.product.identity_crosswalks import OPERATIONAL_COMPETITION_CROSSWALKS
from football.product.live_resources import normalize_events, normalize_statistics
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
from football.storage.locks import FIXTURE_CROSSWALK_LOCK, IDENTITY_ADMISSION_LOCK, acquire_locks
from football.storage.raw import ImmutableFileStore

FixtureObservation = FotmobLiveScore | PitchApiFixture


@dataclass(slots=True)
class SyncCounts:
    failure_reasons: dict[str, int] = field(default_factory=dict)
    attempted_requests: int = 0
    successful_requests: int = 0
    fetched: int = 0
    matched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    unmatched: int = 0
    failed: int = 0
    resources: int = 0
    canonical_fixtures_created: int = 0
    history_inserted: int = 0
    stored_observations_reconciled: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "attempted_requests": self.attempted_requests,
            "successful_requests": self.successful_requests,
            "fetched": self.fetched,
            "matched": self.matched,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "unmatched": self.unmatched,
            "failed": self.failed,
            "failure_reasons": self.failure_reasons,
            "resources": self.resources,
            "canonical_fixtures_created": self.canonical_fixtures_created,
            "history_inserted": self.history_inserted,
            "stored_observations_reconciled": self.stored_observations_reconciled,
        }


@dataclass(frozen=True, slots=True)
class DetailCounts:
    attempted_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    resources: int = 0
    fresh_until: datetime | None = None


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
        kickoff_tolerance_minutes: int = 30,
    ) -> None:
        if stale_after_seconds <= 0 or not 0 <= kickoff_tolerance_minutes <= 60:
            raise ValueError("invalid operational provider sync limits")
        self.connection = connection
        self.data_root = data_root
        self.provider_code = provider_code
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.kickoff_tolerance = timedelta(minutes=kickoff_tolerance_minutes)
        self.pacer = RequestPacer(minimum_interval_seconds)
        self._geographic_scopes: dict[str, str | None] | None = None

    def apply_reviewed_mapping(
        self,
        provider_match_id: str,
        fixture_id: UUID,
        *,
        source_snapshot_id: UUID | None = None,
        competition_only: bool = False,
    ) -> None:
        """Apply an explicit operator-reviewed fixture mapping using stored evidence."""
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT provider_competition_id, provider_competition_name,
                          provider_home_team_id, provider_home_team_name,
                          provider_away_team_id, provider_away_team_name,
                          kickoff_at, canonical_status, provider_status,
                          home_score, away_score, match_minute, added_time, period,
                          source_updated_at, observed_at, source_snapshot_id,
                          result_score_basis, canonical_fixture_id
                     FROM football.product_provider_fixture_observations
                    WHERE provider_code = %s AND provider_match_id = %s
                      AND (%s::uuid IS NULL OR source_snapshot_id=%s)
                    ORDER BY observed_at DESC, observation_id DESC LIMIT 1""",
                (self.provider_code, provider_match_id, source_snapshot_id, source_snapshot_id),
            )
            source = cursor.fetchone()
            if source is None or any(source[index] is None for index in (0, 1, 2, 3, 4, 5)):
                raise ValueError("stored provider identity evidence is incomplete")
            cursor.execute(
                """SELECT fixture.fixture_id, fixture.competition_id,
                          fixture.home_team_id, fixture.away_team_id,
                          competition.name, home.name, away.name,
                          fixture.status, fixture.home_score, fixture.away_score,
                          fixture.kickoff_at,
                          fixture.identity_status,
                          COALESCE((SELECT source_kickoff_precision
                            FROM football.product_team_match_history h
                            WHERE h.fixture_id=fixture.fixture_id),'EXACT')
                     FROM football.product_effective_fixtures fixture
                     JOIN football.product_competitions competition
                       ON competition.competition_id = fixture.competition_id
                     JOIN football.product_teams home ON home.team_id = fixture.home_team_id
                     JOIN football.product_teams away ON away.team_id = fixture.away_team_id
                    WHERE fixture.fixture_id = %s""",
                (fixture_id,),
            )
            candidate = cursor.fetchone()
            if candidate is None:
                raise ValueError("reviewed canonical fixture does not exist")
            if candidate[11] != "VERIFIED":
                raise ValueError("reviewed target must be a verified canonical fixture")
        row = PitchApiFixture(
            provider_match_id=provider_match_id,
            provider_competition_id=source[0],
            provider_home_team_id=source[2],
            provider_away_team_id=source[4],
            home_team_name=source[3],
            away_team_name=source[5],
            kickoff_at=source[6],
            status=source[7],
            provider_status=source[8] or "",
            home_score=source[9],
            away_score=source[10],
            minute=source[11],
            added_time=source[12],
            period=source[13],
            source_updated_at=source[14],
            observed_at=source[15],
            provider_competition_name=source[1],
            result_score_basis=source[17],
        )
        snapshot_id = cast(UUID, source[16])
        self._validate_reviewed_context(row, candidate)
        for entity_type, identifier in (
            ("competition", row.provider_competition_id),
            ("team", row.provider_home_team_id),
            ("team", row.provider_away_team_id),
        ):
            if (
                verify_source_identifier(
                    self.connection,
                    self.data_root,
                    snapshot_id,
                    self.provider_code,
                    entity_type,
                    identifier,
                    None,
                )
                is None
            ):
                raise ValueError("reviewed mapping requires verified retained provider identifiers")
        members = self._retained_fixture_members(row)
        self._persist_deterministic_mapping(
            row,
            snapshot_id,
            candidate,
            mapping_method="manual",
            competition_only=competition_only,
        )
        review = self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "MANUAL_ACCEPTED",
            "operator explicitly accepted mapping",
            {
                "reviewed_fixture_id": str(fixture_id),
                "competition_only": competition_only,
            },
        )
        admit_provider_mappings(
            self.connection,
            self.data_root,
            self.provider_code,
            snapshot_id,
            entity_types=("competition",) if competition_only else ("competition", "team"),
        )
        if competition_only:
            return
        for member in members:
            self._resolve_reviewed_member(member, candidate, row, snapshot_id, review)
        self._update_canonical_fixture(row, fixture_id, snapshot_id)
        self._insert_qualified_history(row, fixture_id, snapshot_id)

    def _validate_reviewed_context(
        self,
        row: FixtureObservation,
        candidate: tuple[Any, ...],
    ) -> None:
        date_score_match = (
            candidate[12] == "DATE_ONLY"
            and row.status == candidate[7] == "FINISHED"
            and row.kickoff_at.astimezone(UTC).date() == candidate[10].astimezone(UTC).date()
            and (row.home_score, row.away_score) == (candidate[8], candidate[9])
            and row.result_score_basis == "REGULATION_90"
        )
        if not date_score_match and abs(row.kickoff_at - candidate[10]) > self.kickoff_tolerance:
            raise ValueError("reviewed fixture kickoff contradicts retained provider context")
        if (
            row.status == candidate[7] == "FINISHED"
            and candidate[8] is not None
            and (candidate[8], candidate[9]) != (row.home_score, row.away_score)
        ):
            raise ValueError("reviewed fixture result contradicts retained provider context")

    def _retained_fixture_members(self, row: FixtureObservation) -> list[UUID]:
        members = self.connection.execute(
            """SELECT DISTINCT canonical_fixture_id
               FROM football.product_provider_fixture_observations
               WHERE provider_code=%s AND provider_match_id=%s
                 AND provider_competition_id=%s AND provider_home_team_id=%s
                 AND provider_away_team_id=%s AND kickoff_at=%s
                 AND canonical_fixture_id IS NOT NULL""",
            (
                self.provider_code,
                row.provider_match_id,
                row.provider_competition_id,
                row.provider_home_team_id,
                row.provider_away_team_id,
                row.kickoff_at,
            ),
        ).fetchall()
        return [member[0] for member in members]

    def _resolve_reviewed_member(
        self,
        original: UUID | None,
        target: tuple[Any, ...],
        row: FixtureObservation,
        snapshot: UUID,
        review: UUID,
    ) -> None:
        if original is None or original == target[0]:
            return
        evidence = {
            "provider_mapping_decision_id": str(review),
            "provider": self.provider_code,
            "provider_match_id": row.provider_match_id,
            "source_snapshot_id": str(snapshot),
            "original_fixture_id": str(original),
            "reviewed_fixture_id": str(target[0]),
        }
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK, FIXTURE_CROSSWALK_LOCK))
        provisional = self.connection.execute(
            "SELECT identity_status,kickoff_at,status,home_score,away_score "
            "FROM football.product_fixtures "
            "WHERE fixture_id = %s FOR UPDATE",
            (original,),
        ).fetchone()
        if provisional is None or provisional[0] not in {"PROVISIONAL", "VERIFIED"}:
            return
        if provisional[1] != row.kickoff_at or (
            provisional[2] == row.status == "FINISHED"
            and (provisional[3], provisional[4]) != (row.home_score, row.away_score)
        ):
            raise ValueError("retained fixture member contradicts reviewed context")
        if self.connection.execute(
            """SELECT 1 FROM football.fixture_identity_resolutions
               WHERE member_fixture_id=%s AND representative_fixture_id=%s
                 AND resolution_status='DUPLICATE_RESOLVED' AND active""",
            (original, target[0]),
        ).fetchone():
            return
        self.connection.execute(
            """UPDATE football.fixture_identity_resolutions SET active = false
               WHERE member_fixture_id = %s AND active""",
            (original,),
        )
        self.connection.execute(
            """INSERT INTO football.fixture_identity_resolutions (
                   canonical_real_fixture_id, member_fixture_id, representative_fixture_id,
                   resolution_status, selected_competition_id, resolution_reason, evidence_json,
                   evidence_sha256, resolution_version, active, created_at)
               VALUES (%s, %s, %s, 'DUPLICATE_RESOLVED', %s,
                       'Reviewed retained provider IDs and fixture context',
                       %s::jsonb, %s, %s, true, clock_timestamp())""",
            (
                target[0],
                original,
                target[0],
                target[1],
                json.dumps(evidence),
                sha256_json(evidence),
                f"operator-review:{review}",
            ),
        )

    def sync_fotmob(
        self,
        client: FotmobClient,
        from_date: date,
        through_date: date,
        *,
        details_limit: int = 10,
        live_details_limit: int = 10,
        competition_id: str | None = None,
    ) -> dict[str, object]:
        return self._sync_dates(
            from_date,
            through_date,
            fetch=client.matches_by_date,
            normalize=normalize_daily_matches,
            detail=lambda item: self._fotmob_details(client, item),
            details_limit=details_limit,
            live_details_limit=live_details_limit,
            competition_id=competition_id,
        )

    def sync_pitchapi(
        self,
        client: PitchApiClient,
        from_date: date,
        through_date: date,
        *,
        details_limit: int = 10,
        live_details_limit: int = 10,
        competition_id: str | None = None,
    ) -> dict[str, object]:
        return self._sync_dates(
            from_date,
            through_date,
            fetch=lambda day: client.matches_by_date(day, status="all"),
            normalize=normalize_pitchapi_matches,
            detail=lambda item: self._pitchapi_details(client, item),
            details_limit=details_limit,
            live_details_limit=live_details_limit,
            competition_id=competition_id,
        )

    def backfill_pitchapi_league(
        self, client: PitchApiClient, league_id: str, season: str
    ) -> dict[str, object]:
        """Import one bounded PitchAPI played-season scope through the normal path."""
        self.pacer.wait()
        response = client.league_matches(league_id, season=season, status="played")
        return self.backfill_league_response(league_id, season, response, network_acquired=True)

    def backfill_league_response(
        self,
        league_id: str,
        season: str,
        response: PitchApiResponse | FotmobResponse,
        *,
        network_acquired: bool = False,
    ) -> dict[str, object]:
        """Replay an immutable league snapshot through the existing ingestion path."""
        snapshot_id = self._record_response(f"league-{league_id}-{season}", response)
        self.connection.commit()
        counts = SyncCounts(
            attempted_requests=int(network_acquired), successful_requests=int(network_acquired)
        )
        rows: Sequence[FixtureObservation] = (
            _fotmob_season_rows(response, league_id, season)
            if isinstance(response, FotmobResponse)
            else normalize_pitchapi_matches(response)
        )
        counts.fetched = len(rows)
        for row in rows:
            try:
                created = inserted = matched = updated = history_inserted = 0
                unmatched = skipped = 0
                with self.connection.transaction():
                    acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
                    fixture_id = self._resolve_fixture(row, snapshot_id)
                    if fixture_id is None:
                        fixture_id = self._create_provider_scoped_fixture(
                            row, snapshot_id, season_label=season
                        )
                        created = int(fixture_id is not None)
                    observation_inserted = self._store_observation(row, snapshot_id, fixture_id)
                    inserted = int(observation_inserted)
                    skipped = int(not observation_inserted)
                    if fixture_id is None:
                        unmatched = 1
                    else:
                        matched = 1
                        self._set_verified_league_season(row, fixture_id, season)
                        updated = self._update_canonical_fixture(row, fixture_id, snapshot_id)
                        self._reconcile_retained_members(row, fixture_id, snapshot_id)
                        history_inserted = self._insert_qualified_history(
                            row, fixture_id, snapshot_id
                        )
                counts.canonical_fixtures_created += created
                counts.inserted += inserted
                counts.skipped += skipped
                counts.unmatched += unmatched
                counts.matched += matched
                counts.updated += updated
                counts.history_inserted += history_inserted
            except (Error, ValueError) as error:
                counts.failed += 1
                reason = str(error).splitlines()[0]
                counts.failure_reasons[reason] = counts.failure_reasons.get(reason, 0) + 1
                self._record_failed_observation(row, snapshot_id, reason)
        geography = refresh_competition_geography(
            self.connection, self.data_root, self.provider_code
        )
        self.connection.commit()
        qualification = self._season_qualification(snapshot_id, rows, counts)
        return {
            "provider": self.provider_code,
            "competition_geography": geography,
            "league_id": league_id,
            "season": season,
            "status": "COMPLETED_WITH_ERRORS"
            if counts.failed or geography["invalid_snapshots"]
            else qualification["status"],
            "qualification": qualification,
            **counts.to_dict(),
        }

    def _reconcile_retained_members(
        self, row: FixtureObservation, fixture_id: UUID, snapshot: UUID
    ) -> None:
        """Reconcile earlier copies only after native competition and team IDs qualify."""
        if not self._verified_provider_entities(row):
            return
        target = self.connection.execute(
            """SELECT fixture_id,competition_id,home_team_id,away_team_id
               FROM football.product_effective_fixtures WHERE fixture_id=%s
                 AND identity_status='VERIFIED' AND kickoff_at=%s""",
            (fixture_id, row.kickoff_at),
        ).fetchone()
        if target is None or self._candidate_mapping_conflict(row, target) is not None:
            return
        members = [member for member in self._retained_fixture_members(row) if member != fixture_id]
        quarantine = self.connection.execute(
            """SELECT canonical_real_fixture_id,evidence_sha256
               FROM football.fixture_identity_resolutions WHERE member_fixture_id=%s AND active
                 AND resolution_status='AMBIGUOUS_QUARANTINED'
                 AND resolution_reason='PROVISIONAL_PROVIDER_IDENTITY'
                 AND evidence_json->'member_fixture_ids'=jsonb_build_array(%s::text)""",
            (fixture_id, fixture_id),
        ).fetchone()
        if not members and quarantine is None:
            return
        decision = self._record_mapping_decision(
            row,
            snapshot,
            fixture_id,
            "AUTO_ACCEPTED",
            "admitted native IDs identify retained fixture members",
            {"rule": "admitted_competition_home_away_exact_kickoff_native_fixture_id"},
        )
        for member in members:
            self._resolve_reviewed_member(member, target, row, snapshot, decision)
        if quarantine is not None:
            evidence = {
                "provider_mapping_decision_id": str(decision),
                "source_snapshot_id": str(snapshot),
                "previous_evidence_sha256": quarantine[1],
            }
            self.connection.execute(
                """UPDATE football.fixture_identity_resolutions SET active=false
                   WHERE member_fixture_id=%s AND active""",
                (fixture_id,),
            )
            self.connection.execute(
                """INSERT INTO football.fixture_identity_resolutions (
                     canonical_real_fixture_id,member_fixture_id,representative_fixture_id,
                     resolution_status,selected_competition_id,resolution_reason,evidence_json,
                     evidence_sha256,resolution_version,active,created_at)
                   VALUES (%s,%s,%s,'UNIQUE',%s,'Admitted native provider identities',
                           %s::jsonb,%s,%s,true,clock_timestamp())""",
                (
                    quarantine[0],
                    fixture_id,
                    fixture_id,
                    target[1],
                    json.dumps(evidence),
                    sha256_json(evidence),
                    f"admitted-native-ids:{decision}",
                ),
            )

    def _season_qualification(
        self, snapshot: UUID, rows: Sequence[FixtureObservation], counts: SyncCounts
    ) -> dict[str, object]:
        if not rows:
            return {"status": "ADVERTISED_BUT_UNUSABLE", "qualified_results": 0}
        registered = self.connection.execute(
            """SELECT clock_timestamp() FROM football.source_snapshots s
               JOIN football.providers p ON p.id=s.provider_id
               WHERE s.id=%s AND s.status='validated' AND p.code=%s""",
            (snapshot, self.provider_code),
        ).fetchone()
        if registered is None:
            return {
                "status": "BLOCKED_IDENTITY",
                "qualified_results": 0,
                "reason": "RETAINED_SOURCE_EVIDENCE_REQUIRED",
            }
        results = [row for row in rows if row.status == "FINISHED"]
        # Identical retained facts can keep an earlier observation snapshot. Match
        # their native context rather than requiring acquisition-specific duplicates.
        contexts = [
            {
                "match_id": row.provider_match_id,
                "competition": row.provider_competition_id,
                "home": row.provider_home_team_id,
                "away": row.provider_away_team_id,
                "kickoff": row.kickoff_at.isoformat(),
                "status": row.status,
                "home_score": row.home_score,
                "away_score": row.away_score,
                "basis": row.result_score_basis,
            }
            for row in rows
        ]
        observed = self.connection.execute(
            """WITH context AS (SELECT * FROM jsonb_to_recordset(%s::jsonb) AS c(
                 match_id text,competition text,home text,away text,kickoff timestamptz,
                 status text,home_score smallint,away_score smallint,basis text))
               SELECT DISTINCT o.provider_match_id,f.fixture_id,f.identity_status,
                   c.status='FINISHED' AND c.basis='REGULATION_90' AND EXISTS (
                       SELECT 1 FROM football.product_eligible_fixture_history_at(
                           %s,ARRAY[f.fixture_id]) h
                       WHERE (h.home_goals,h.away_goals)=(o.home_score,o.away_score)) qualified,
                   EXISTS (SELECT 1 FROM football.product_team_match_history h
                       WHERE h.fixture_id=f.fixture_id AND c.status='FINISHED'
                         AND (h.home_goals,h.away_goals)<>
                             (o.home_score,o.away_score)) result_conflict
               FROM context c JOIN football.product_provider_fixture_observations o
                 ON o.provider_code=%s AND o.provider_match_id=c.match_id
                AND o.provider_competition_id=c.competition
                AND o.provider_home_team_id=c.home AND o.provider_away_team_id=c.away
                AND o.kickoff_at=c.kickoff AND o.canonical_status=c.status
                AND o.home_score IS NOT DISTINCT FROM c.home_score
                AND o.away_score IS NOT DISTINCT FROM c.away_score
                AND o.result_score_basis=c.basis
               JOIN football.product_effective_fixtures f
                 ON f.fixture_id=o.canonical_fixture_id
               WHERE NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
                   WHERE r.member_fixture_id=f.fixture_id AND r.active
                     AND r.representative_fixture_id<>r.member_fixture_id)""",
            (json.dumps(contexts), registered[0], self.provider_code),
        ).fetchall()
        count = len({o[0] for o in observed if o[3]})
        fixtures = [(o[1], o[2]) for o in observed]
        blockers = fixture_identity_blockers(
            self.connection,
            [f[0] for f in fixtures],
            registered[0],
            provider_code=self.provider_code,
        )
        status = "COMPLETED"
        if (
            counts.unmatched
            or len({o[0] for o in observed}) < len(rows)
            or any(f[1] != "VERIFIED" for f in fixtures)
            or any(blockers.values())
        ):
            status = "BLOCKED_IDENTITY"
        elif any(row.result_score_basis != "REGULATION_90" for row in results):
            status = "BLOCKED_SCORE_BASIS"
        elif any(o[4] for o in observed):
            status = "BLOCKED_RESULT_CONFLICT"
        elif count < len(results):
            status = "BLOCKED_HISTORY_ADMISSION"
        return {"status": status, "qualified_results": count, "provider_results": len(results)}

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
        recovery = self._recover_unresolved(
            from_date, fetch, normalize, details_limit, counts, competition_id
        )
        bulk_batch = {
            key: value
            for key, value in resolved_batch.items()
            if value[0].status not in {"LIVE", "HALF_TIME", "INTERRUPTED", "SUSPENDED"}
        }
        recovery = [item for item in recovery if item[0].provider_match_id not in resolved_batch]
        bulk_batch.update((row.provider_match_id, (row, fixture)) for row, fixture in recovery)
        bulk_counts, _, _ = self._fetch_prioritized_details(
            tuple(bulk_batch.values()),
            detail,
            bulk_limit=details_limit,
            live_limit=0,
            recovery_ids=frozenset(row.provider_match_id for row, _ in recovery),
        )
        self._add_detail_counts(counts, bulk_counts)
        settled = settle_external_predictions(self.connection, datetime.now(UTC))
        diagnostics = self._sync_diagnostics(sync_started, from_date)
        geography = refresh_competition_geography(
            self.connection, self.data_root, self.provider_code
        )
        self.connection.commit()
        return {
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

    @staticmethod
    def _record_missing_recovery(counts: SyncCounts, missing: set[str]) -> None:
        if missing:
            reason = "UNRESOLVED_FIXTURE_NOT_IN_PROVIDER_RESPONSE"
            counts.failed += len(missing)
            counts.failure_reasons[reason] = counts.failure_reasons.get(reason, 0) + len(missing)

    @staticmethod
    def _add_detail_counts(counts: SyncCounts, item: DetailCounts) -> None:
        counts.attempted_requests += item.attempted_requests
        counts.successful_requests += item.successful_requests
        counts.failed += item.failed_requests
        counts.resources += item.resources

    def _ingest_observations(
        self, rows: Sequence[FixtureObservation], snapshot_id: UUID, counts: SyncCounts
    ) -> list[tuple[FixtureObservation, UUID | None]]:
        resolved: list[tuple[FixtureObservation, UUID | None]] = []
        for row in rows:
            try:
                created = inserted = matched = updated = history_inserted = 0
                unmatched = skipped = 0
                with self.connection.transaction():
                    acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
                    fixture_id = self._resolve_fixture(row, snapshot_id)
                    if fixture_id is None:
                        fixture_id = self._create_provider_scoped_fixture(row, snapshot_id)
                        created = int(fixture_id is not None)
                    observation_inserted = self._store_observation(row, snapshot_id, fixture_id)
                    inserted = int(observation_inserted)
                    skipped = int(not observation_inserted)
                    if fixture_id is None:
                        unmatched = 1
                    else:
                        matched = 1
                        updated = self._update_canonical_fixture(row, fixture_id, snapshot_id)
                        history_inserted = self._insert_qualified_history(
                            row, fixture_id, snapshot_id
                        )
                resolved.append((row, fixture_id))
                counts.canonical_fixtures_created += created
                counts.inserted += inserted
                counts.skipped += skipped
                counts.unmatched += unmatched
                counts.matched += matched
                counts.updated += updated
                counts.history_inserted += history_inserted
            except (Error, ValueError) as error:
                counts.failed += 1
                reason = str(error).splitlines()[0]
                counts.failure_reasons[reason] = counts.failure_reasons.get(reason, 0) + 1
                self._record_failed_observation(row, snapshot_id, reason)
        return resolved

    def _record_failed_observation(
        self, row: FixtureObservation, snapshot_id: UUID, reason: str
    ) -> None:
        with self.connection.transaction():
            self._store_observation(row, snapshot_id, None)
            self._record_mapping_decision(
                row,
                snapshot_id,
                None,
                "REVIEW_REQUIRED",
                "historical admission failed",
                {
                    "error": reason,
                    "kickoff_at": row.kickoff_at.isoformat(),
                    "provider_competition_id": row.provider_competition_id,
                },
            )

    def reconcile_stored_observations(self, *, create_missing: bool = False) -> int:
        """Retry deterministic mappings from immutable stored observations."""
        self._restore_legacy_pitchapi_identity()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT DISTINCT ON (provider_match_id)
                          provider_match_id, provider_competition_id,
                          provider_home_team_id, provider_away_team_id,
                          provider_home_team_name, provider_away_team_name,
                          kickoff_at, canonical_status, provider_status,
                          home_score, away_score, match_minute, added_time, period,
                          source_updated_at, observed_at, provider_competition_name,
                          source_snapshot_id, result_score_basis
                     FROM football.product_provider_fixture_observations
                    WHERE provider_code = %s AND (canonical_fixture_id IS NULL OR EXISTS (
                        SELECT 1 FROM football.product_effective_fixtures fixture
                        WHERE fixture.fixture_id = canonical_fixture_id
                          AND fixture.identity_status = 'PROVISIONAL'
                    ))
                      AND provider_competition_id IS NOT NULL
                      AND provider_home_team_id IS NOT NULL
                      AND provider_away_team_id IS NOT NULL
                      AND provider_home_team_name IS NOT NULL
                      AND provider_away_team_name IS NOT NULL
                    ORDER BY provider_match_id, observed_at DESC, observation_id DESC""",
                (self.provider_code,),
            )
            stored = cursor.fetchall()
        self.connection.commit()
        reconciled = 0
        for source in stored:
            basis = source[18]
            if basis == "UNKNOWN" and self.provider_code == "fotmob":
                label = (source[8] or "").upper()
                if label in {"FT", "FULL TIME", "FULL-TIME"}:
                    basis = "REGULATION_90"
            row = PitchApiFixture(
                provider_match_id=source[0],
                provider_competition_id=source[1],
                provider_home_team_id=source[2],
                provider_away_team_id=source[3],
                home_team_name=source[4],
                away_team_name=source[5],
                kickoff_at=source[6],
                status=source[7],
                provider_status=source[8] or "",
                home_score=source[9],
                away_score=source[10],
                minute=source[11],
                added_time=source[12],
                period=source[13],
                source_updated_at=source[14],
                observed_at=source[15],
                provider_competition_name=source[16],
                result_score_basis=basis,
            )
            snapshot_id = cast(UUID, source[17])
            try:
                with self.connection.transaction():
                    acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
                    fixture_id = self._resolve_fixture(row, snapshot_id)
                    if fixture_id is None and create_missing:
                        fixture_id = self._create_provider_scoped_fixture(row, snapshot_id)
                    if fixture_id is None:
                        continue
                    reconciled += 1
                    self._store_observation(row, snapshot_id, fixture_id)
                    self._update_canonical_fixture(row, fixture_id, snapshot_id)
                    self._reconcile_retained_members(row, fixture_id, snapshot_id)
                    self._insert_qualified_history(row, fixture_id, snapshot_id)
            except (Error, ValueError) as failure:
                self._record_failed_observation(row, snapshot_id, str(failure).splitlines()[0])
        return reconciled

    def _restore_legacy_pitchapi_identity(self) -> None:
        if self.provider_code != "pitchapi":
            return
        stored = self.connection.execute(
            """SELECT snapshot.id, snapshot.manifest_path, snapshot.manifest_sha256,
                      snapshot.acquired_at, array_agg(observation.provider_match_id)
               FROM football.product_provider_fixture_observations observation
               JOIN football.source_snapshots snapshot
                 ON snapshot.id = observation.source_snapshot_id
               WHERE observation.provider_code = 'pitchapi'
                 AND observation.canonical_fixture_id IS NULL
                 AND (observation.provider_home_team_name IS NULL
                      OR observation.provider_away_team_name IS NULL)
               GROUP BY snapshot.id"""
        ).fetchall()
        self.connection.commit()
        for snapshot_id, path, checksum, acquired_at, match_ids in stored:
            raw = (self.data_root / path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != checksum:
                raise ValueError("legacy PitchAPI snapshot checksum mismatch")
            response = PitchApiResponse(
                "/v1/date/stored-replay", acquired_at, checksum, raw, json.loads(raw)["data"]
            )
            with self.connection.transaction():
                for row in normalize_pitchapi_matches(response):
                    if row.provider_match_id in match_ids:
                        self._store_observation(row, snapshot_id, None)
                        self.connection.execute(
                            """UPDATE football.product_provider_fixture_observations SET
                               provider_competition_name = COALESCE(provider_competition_name, %s),
                               provider_home_team_name = COALESCE(provider_home_team_name, %s),
                               provider_away_team_name = COALESCE(provider_away_team_name, %s)
                               WHERE provider_code = 'pitchapi' AND provider_match_id = %s
                                 AND source_snapshot_id = %s""",
                            (
                                row.provider_competition_name,
                                row.home_team_name,
                                row.away_team_name,
                                row.provider_match_id,
                                snapshot_id,
                            ),
                        )

    def backfill_stored_history(self) -> dict[str, object]:
        """Create canonical fixtures and history from already captured provider data."""
        before = self._stored_backfill_counts()
        processed = self.reconcile_stored_observations(create_missing=True)
        after = self._stored_backfill_counts()
        return {
            "provider": self.provider_code,
            "stored_observations_processed": processed,
            "canonical_fixtures_created": after[0] - before[0],
            "history_matches_inserted": after[1] - before[1],
            "remaining_unmatched_observations": after[2],
        }

    def _stored_backfill_counts(self) -> tuple[int, int, int]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                       (SELECT count(*) FROM football.match_provider_mappings mapping
                         JOIN football.providers provider ON provider.id = mapping.provider_id
                        WHERE provider.code = %s),
                       (SELECT count(*) FROM football.product_team_match_history
                        WHERE source_provider_code = %s),
                       (SELECT count(*) FROM football.product_provider_fixture_observations
                        WHERE provider_code = %s AND canonical_fixture_id IS NULL)""",
                (self.provider_code, self.provider_code, self.provider_code),
            )
            row = cursor.fetchone()
        if row is None:
            return 0, 0, 0
        return cast(tuple[int, int, int], tuple(row))

    def _fetch_prioritized_details(
        self,
        resolved: Sequence[tuple[FixtureObservation, UUID | None]],
        detail: Any,
        *,
        bulk_limit: int,
        live_limit: int,
        recovery_ids: frozenset[str] = frozenset(),
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
            attempted += item.attempted_requests
            successful += item.successful_requests
            failed += item.failed_requests
            resources += item.resources
        return DetailCounts(attempted, successful, failed, resources), used_bulk, used_live

    def _claim_refresh(self, name: str) -> datetime | None:
        row = self.connection.execute(
            """INSERT INTO football.product_provider_refresh_state (
                   provider_code,resource_name,last_attempt_at,next_attempt_at)
               VALUES (%s,%s,clock_timestamp(),clock_timestamp()+%s)
               ON CONFLICT (provider_code,resource_name) DO UPDATE
               SET last_attempt_at=EXCLUDED.last_attempt_at,
                   next_attempt_at=EXCLUDED.next_attempt_at
               WHERE football.product_provider_refresh_state.next_attempt_at <= clock_timestamp()
               RETURNING last_attempt_at""",
            (self.provider_code, name, self.stale_after),
        ).fetchone()
        self.connection.commit()
        return cast(datetime, row[0]) if row is not None else None

    def _complete_refresh(
        self, name: str, claimed: datetime, item: DetailCounts, *, error: str | None = None
    ) -> None:
        self.connection.execute(
            """UPDATE football.product_provider_refresh_state
               SET last_success_at=CASE WHEN %s = 0 THEN clock_timestamp() ELSE last_success_at END,
                   next_attempt_at=GREATEST(clock_timestamp()+%s,%s),
                   failed_requests=%s,last_error=CASE WHEN %s > 0 THEN %s END
               WHERE provider_code=%s AND resource_name=%s AND last_attempt_at=%s""",
            (
                item.failed_requests,
                self.stale_after,
                item.fresh_until if item.failed_requests == 0 else None,
                item.failed_requests,
                item.failed_requests,
                error or "DETAIL_REQUEST_FAILED",
                self.provider_code,
                name,
                claimed,
            ),
        )
        self.connection.commit()

    def _sync_diagnostics(self, sync_started: datetime, from_date: date) -> dict[str, object]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT reason, count(*)
                     FROM football.product_provider_mapping_decisions
                    WHERE provider_code = %s AND observed_at >= %s
                      AND disposition IN ('REVIEW_REQUIRED', 'CONTRADICTORY')
                    GROUP BY reason ORDER BY reason""",
                (self.provider_code, sync_started),
            )
            reasons = {reason: count for reason, count in cursor.fetchall()}
            cursor.execute(
                """SELECT observed_at, last_fetched_at, stale_after
                     FROM football.product_provider_fixture_observations
                    WHERE provider_code = %s
                    ORDER BY last_fetched_at DESC, observation_id DESC LIMIT 1""",
                (self.provider_code,),
            )
            freshness = cursor.fetchone()
        capabilities = [
            "fixtures",
            "live_scores",
            "match_details",
            "statistics",
            "shots",
            "lineups",
            "player_ratings",
            "h2h",
        ]
        if self.provider_code == "pitchapi":
            capabilities.extend(("events", "momentum"))
        return {
            "unmatched_reasons": reasons,
            "effective_capabilities": capabilities,
            "latest_observed_at": freshness[0].isoformat() if freshness else None,
            "latest_fetched_at": freshness[1].isoformat() if freshness else None,
            "latest_stale_after": freshness[2].isoformat() if freshness else None,
            "lifecycle_recovery": self._lifecycle_diagnostics(from_date),
        }

    def _lifecycle_diagnostics(self, from_date: date) -> dict[str, int]:
        row = self.connection.execute(
            """WITH unresolved AS (
                 SELECT fixture_id FROM football.product_fixtures f
                 WHERE status IN (
                     'SCHEDULED','LIVE','HALF_TIME','SUSPENDED','INTERRUPTED','POSTPONED')
                   AND kickoff_at < (%s::date::timestamp AT TIME ZONE 'UTC')
                   AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions resolution
                                   WHERE resolution.member_fixture_id=f.fixture_id
                                     AND resolution.active))
               SELECT (SELECT count(*) FROM unresolved),
                      (SELECT count(DISTINCT fixture_id) FROM football.product_recoverable_fixtures
                       WHERE provider_code=%s
                         AND fixture_id IN (SELECT fixture_id FROM unresolved)),
                      (SELECT count(*) FROM unresolved u WHERE NOT EXISTS (
                          SELECT 1 FROM football.product_recoverable_fixtures r
                          WHERE r.fixture_id=u.fixture_id)),
                      (SELECT count(*) FROM football.product_provider_refresh_state
                       WHERE provider_code=%s AND next_attempt_at>clock_timestamp()),
                      (SELECT count(*) FROM football.product_provider_refresh_state
                       WHERE provider_code=%s AND failed_requests>0)""",
            (from_date, self.provider_code, self.provider_code, self.provider_code),
        ).fetchone()
        assert row is not None
        return dict(
            zip(
                (
                    "unresolved_outside_window",
                    "recoverable_for_provider",
                    "without_verified_supported_provider",
                    "cooldown_resources",
                    "failed_refresh_resources",
                ),
                row,
                strict=True,
            )
        )

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
        ImmutableFileStore(self.data_root).publish(str(relative), response.raw)
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
            if cursor.rowcount:
                self._geographic_scopes = None
        return snapshot_id

    def _resolve_fixture(
        self, row: FixtureObservation, snapshot_id: UUID | None = None
    ) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.match_id
                FROM football.match_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = %s AND mapping.provider_match_id = %s
                  AND mapping.valid_to IS NULL
                  AND mapping.mapping_method IN ('explicit_crosswalk', 'manual', 'deterministic')
                  AND mapping.mapping_confidence = 1
                """,
                (self.provider_code, row.provider_match_id),
            )
            direct = cursor.fetchall()
            if (
                len(direct) == 1
                and self._trusted_direct_fixture(direct[0][0], row)
                and direct[0][0]
                != stable_id("provider-scoped-match", self.provider_code, row.provider_match_id)
            ):
                return cast(UUID, direct[0][0])
            cursor.execute(
                """
                SELECT fixture.fixture_id, fixture.competition_id,
                       fixture.home_team_id, fixture.away_team_id
                FROM (
                    SELECT fixture_id, competition_id, home_team_id, away_team_id,
                           kickoff_at, 'EXACT' AS source_kickoff_precision,
                           home_score, away_score
                    FROM football.product_effective_fixtures WHERE identity_status = 'VERIFIED'
                    UNION ALL
                    SELECT history.fixture_id, history.competition_id, history.home_team_id,
                           history.away_team_id, history.kickoff_at,
                           history.source_kickoff_precision, history.home_goals, history.away_goals
                    FROM football.product_eligible_fixture_history_at(
                        statement_timestamp(), ARRAY(
                            SELECT h.fixture_id FROM football.product_team_match_history h
                            WHERE h.kickoff_at BETWEEN %s AND %s
                        )) history
                    WHERE NOT EXISTS (SELECT 1 FROM football.product_fixtures existing
                                      WHERE existing.fixture_id = history.fixture_id)
                ) fixture
                JOIN football.product_effective_team_aliases home
                  ON home.team_id = fixture.home_team_id
                 AND home.provider_code = %s AND home.provider_team_id = %s
                JOIN football.product_effective_team_aliases away
                  ON away.team_id = fixture.away_team_id
                 AND away.provider_code = %s AND away.provider_team_id = %s
                JOIN football.competition_provider_mappings competition_mapping
                  ON competition_mapping.competition_id = fixture.competition_id
                JOIN football.providers provider
                  ON provider.id = competition_mapping.provider_id AND provider.code = %s
                WHERE competition_mapping.provider_competition_id = %s
                  AND competition_mapping.valid_to IS NULL
                  AND competition_mapping.mapping_method IN (
                      'explicit_crosswalk', 'manual', 'deterministic'
                  )
                  AND competition_mapping.mapping_confidence = 1
                  AND football.product_mapping_trusted(
                      'competition', competition_mapping.id, competition_mapping.competition_id)
                  AND EXISTS (SELECT 1 FROM football.product_effective_team_mappings hm
                      WHERE hm.provider_id = provider.id AND hm.provider_team_id = %s
                        AND hm.effective_team_id = fixture.home_team_id AND hm.valid_to IS NULL
                        AND football.product_mapping_trusted('team', hm.id, hm.effective_team_id))
                  AND EXISTS (SELECT 1 FROM football.product_effective_team_mappings am
                      WHERE am.provider_id = provider.id AND am.provider_team_id = %s
                        AND am.effective_team_id = fixture.away_team_id AND am.valid_to IS NULL
                        AND football.product_mapping_trusted('team', am.id, am.effective_team_id))
                  AND ((fixture.source_kickoff_precision = 'EXACT'
                        AND fixture.kickoff_at BETWEEN %s AND %s)
                       OR (fixture.source_kickoff_precision = 'DATE_ONLY'
                           AND fixture.kickoff_at::date = %s::date
                           AND fixture.home_score = %s AND fixture.away_score = %s))
                ORDER BY fixture.fixture_id
                """,
                (
                    row.kickoff_at - timedelta(days=1),
                    row.kickoff_at + timedelta(days=1),
                    self.provider_code,
                    row.provider_home_team_id,
                    self.provider_code,
                    row.provider_away_team_id,
                    self.provider_code,
                    row.provider_competition_id,
                    row.provider_home_team_id,
                    row.provider_away_team_id,
                    row.kickoff_at - self.kickoff_tolerance,
                    row.kickoff_at + self.kickoff_tolerance,
                    row.kickoff_at,
                    row.home_score,
                    row.away_score,
                ),
            )
            candidates = cursor.fetchall()
        if len(candidates) == 1:
            self._materialize_history_fixture(candidates[0][0], row.observed_at)
            if snapshot_id is not None:
                self._persist_deterministic_mapping(
                    row, snapshot_id, candidates[0], mapping_method="explicit_crosswalk"
                )
                self._record_mapping_decision(
                    row,
                    snapshot_id,
                    candidates[0][0],
                    "AUTO_ACCEPTED",
                    "verified provider IDs and kickoff matched",
                    {"rule": "verified_competition_team_ids_unique_kickoff_or_date_score"},
                )
            return cast(UUID, candidates[0][0])
        if snapshot_id is None:
            return None
        reconciled = self._reconcile_exact_fixture(row, snapshot_id)
        if reconciled is None and len(direct) == 1 and self._verified_provider_entities(row):
            return None
        provisional_id = stable_id(
            "provider-scoped-match", self.provider_code, row.provider_match_id
        )
        return reconciled or (
            provisional_id if any(item[0] == provisional_id for item in direct) else None
        )

    def _trusted_direct_fixture(self, fixture_id: UUID, row: FixtureObservation) -> bool:
        if not self._verified_provider_entities(row):
            return False
        candidate = self.connection.execute(
            """SELECT fixture_id, competition_id, home_team_id, away_team_id
               FROM football.product_fixtures WHERE fixture_id = %s
                 AND kickoff_at BETWEEN %s AND %s""",
            (
                fixture_id,
                row.kickoff_at - self.kickoff_tolerance,
                row.kickoff_at + self.kickoff_tolerance,
            ),
        ).fetchone()
        return candidate is not None and self._candidate_mapping_conflict(row, candidate) is None

    def _verified_provider_entities(self, row: FixtureObservation) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.competition_id, competition.metadata_status
                   FROM football.competition_provider_mappings mapping
                   JOIN football.providers provider ON provider.id = mapping.provider_id
                   JOIN football.product_competitions competition
                     ON competition.competition_id = mapping.competition_id
                   WHERE provider.code = %s AND mapping.provider_competition_id = %s
                     AND mapping.valid_to IS NULL AND mapping.mapping_confidence = 1
                     AND football.product_mapping_trusted(
                         'competition', mapping.id, mapping.competition_id)
                     AND (SELECT count(DISTINCT tm.provider_team_id)
                          FROM football.product_effective_team_mappings tm
                          WHERE tm.provider_id = provider.id AND tm.valid_to IS NULL
                            AND tm.provider_team_id IN (%s, %s)
                            AND football.product_mapping_trusted(
                                'team', tm.id, tm.effective_team_id)) = 2""",
                (
                    self.provider_code,
                    row.provider_competition_id,
                    row.provider_home_team_id,
                    row.provider_away_team_id,
                ),
            )
            competition = cursor.fetchone()
        return (
            competition is not None
            and competition[1] == "VERIFIED"
            and competition[0]
            != self._provider_scoped_identity(
                "competition_provider_mappings", row.provider_competition_id
            )
            and all(
                self._mapped_or_scoped_team(team)
                != self._provider_scoped_identity("team_provider_mappings", team)
                for team in (row.provider_home_team_id, row.provider_away_team_id)
            )
        )

    def _reconcile_exact_fixture(self, row: FixtureObservation, snapshot_id: UUID) -> UUID | None:
        competition_name = row.provider_competition_name
        if competition_name is None:
            self._record_mapping_decision(
                row, snapshot_id, None, "REVIEW_REQUIRED", "provider competition name missing", {}
            )
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture.fixture_id, fixture.competition_id,
                       fixture.home_team_id, fixture.away_team_id,
                       competition.name, home.name, away.name,
                       fixture.status, fixture.home_score, fixture.away_score
                FROM (
                    SELECT fixture_id, competition_id, home_team_id, away_team_id,
                           kickoff_at, status, home_score, away_score
                    FROM football.product_effective_fixtures WHERE identity_status = 'VERIFIED'
                    UNION ALL
                    SELECT history.fixture_id, history.competition_id, history.home_team_id,
                           history.away_team_id, history.kickoff_at, 'FINISHED',
                           history.home_goals, history.away_goals
                    FROM football.product_eligible_fixture_history_at(
                        statement_timestamp(), ARRAY(
                            SELECT h.fixture_id FROM football.product_team_match_history h
                            WHERE h.kickoff_at BETWEEN %s AND %s
                        )) history
                    WHERE NOT EXISTS (SELECT 1 FROM football.product_fixtures existing
                                      WHERE existing.fixture_id = history.fixture_id)
                      AND history.source_kickoff_precision = 'EXACT'
                ) fixture
                JOIN football.product_competitions competition
                  ON competition.competition_id = fixture.competition_id
                JOIN football.product_teams home ON home.team_id = fixture.home_team_id
                JOIN football.product_teams away ON away.team_id = fixture.away_team_id
                WHERE fixture.kickoff_at BETWEEN %s AND %s
                ORDER BY fixture.fixture_id
                """,
                (
                    row.kickoff_at - self.kickoff_tolerance,
                    row.kickoff_at + self.kickoff_tolerance,
                    row.kickoff_at - self.kickoff_tolerance,
                    row.kickoff_at + self.kickoff_tolerance,
                ),
            )
            nearby = cursor.fetchall()
        exact = [
            candidate
            for candidate in nearby
            if _normalize_competition_name(candidate[4])
            == _normalize_competition_name(competition_name)
            and normalize_team_name(candidate[5]) == normalize_team_name(row.home_team_name)
            and normalize_team_name(candidate[6]) == normalize_team_name(row.away_team_name)
        ]
        evidence = {
            "rule": "unique_exact_competition_home_away_utc_kickoff_v1",
            "kickoff_tolerance_seconds": int(self.kickoff_tolerance.total_seconds()),
            "provider_competition": competition_name,
            "provider_home_team": row.home_team_name,
            "provider_away_team": row.away_team_name,
            "nearby_candidates": len(nearby),
            "exact_candidates": [str(item[0]) for item in exact],
        }
        if len(exact) != 1:
            reason = "no exact canonical candidate" if not exact else "ambiguous exact candidates"
            self._record_mapping_decision(
                row, snapshot_id, None, "REVIEW_REQUIRED", reason, evidence
            )
            return None
        candidate = exact[0]
        fixture_id = cast(UUID, candidate[0])
        self._materialize_history_fixture(fixture_id, row.observed_at)
        mapping_conflict = self._candidate_mapping_conflict(row, candidate)
        if mapping_conflict is not None:
            self._record_mapping_decision(
                row,
                snapshot_id,
                fixture_id,
                "CONTRADICTORY",
                mapping_conflict,
                evidence,
            )
            return None
        if (
            row.status == "FINISHED"
            and candidate[7] == "FINISHED"
            and candidate[8] is not None
            and (candidate[8], candidate[9]) != (row.home_score, row.away_score)
        ):
            self._record_mapping_decision(
                row,
                snapshot_id,
                fixture_id,
                "CONTRADICTORY",
                "finished score contradicts canonical result",
                evidence
                | {
                    "canonical_score": [candidate[8], candidate[9]],
                    "provider_score": [row.home_score, row.away_score],
                },
            )
            return None
        self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "REVIEW_REQUIRED",
            "explicit cross-provider evidence required",
            evidence,
        )
        return None

    def _materialize_history_fixture(self, fixture_id: UUID, observed_at: datetime) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO football.product_fixtures (
                       fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                       status, home_score, away_score, forecast_availability, updated_at,
                       result_score_basis
                   ) SELECT fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                            'FINISHED', home_goals, away_goals, 'NOT_ENOUGH_HISTORY', %s,
                            'REGULATION_90'
                       FROM football.product_eligible_match_history WHERE fixture_id = %s
                   ON CONFLICT (fixture_id) DO NOTHING""",
                (observed_at, fixture_id),
            )

    def _candidate_mapping_conflict(
        self, row: FixtureObservation, candidate: Sequence[Any]
    ) -> str | None:
        provider_values = (
            (
                "competition_provider_mappings",
                "provider_competition_id",
                "competition_id",
                row.provider_competition_id,
                candidate[1],
            ),
            (
                "team_provider_mappings",
                "provider_team_id",
                "team_id",
                row.provider_home_team_id,
                candidate[2],
            ),
            (
                "team_provider_mappings",
                "provider_team_id",
                "team_id",
                row.provider_away_team_id,
                candidate[3],
            ),
        )
        with self.connection.cursor() as cursor:
            for (
                table,
                provider_column,
                canonical_column,
                provider_value,
                candidate_value,
            ) in provider_values:
                read_table = (
                    "product_effective_team_mappings"
                    if table == "team_provider_mappings"
                    else table
                )
                read_column = (
                    "effective_team_id" if table == "team_provider_mappings" else canonical_column
                )
                cursor.execute(
                    f"""SELECT mapping.{read_column}
                          FROM football.{read_table} mapping
                          JOIN football.providers provider ON provider.id = mapping.provider_id
                         WHERE provider.code = %s
                           AND mapping.{provider_column} = %s
                           AND mapping.valid_to IS NULL""",
                    (self.provider_code, provider_value),
                )
                existing = cursor.fetchone()
                if (
                    existing is not None
                    and existing[0] != candidate_value
                    and existing[0] != self._provider_scoped_identity(table, provider_value)
                ):
                    return f"verified {table} contradicts exact-name candidate"
        return None

    def _persist_deterministic_mapping(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        candidate: Sequence[Any],
        *,
        mapping_method: str = "deterministic",
        competition_only: bool = False,
    ) -> None:
        fixture_id, competition_id, home_team_id, away_team_id = candidate[:4]
        mapping_at = (
            datetime.now(UTC)
            if mapping_method in {"manual", "explicit_crosswalk"}
            else row.observed_at
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM football.providers WHERE code = %s", (self.provider_code,)
            )
            provider = cursor.fetchone()
            if provider is None:
                raise ValueError("provider registration missing")
            provider_id = provider[0]
            preserve_observations = False
            entities = (
                (
                    "competition_provider_mappings",
                    "provider_competition_id",
                    "competition_id",
                    row.provider_competition_id,
                    competition_id,
                ),
                (
                    "team_provider_mappings",
                    "provider_team_id",
                    "team_id",
                    row.provider_home_team_id,
                    home_team_id,
                ),
                (
                    "team_provider_mappings",
                    "provider_team_id",
                    "team_id",
                    row.provider_away_team_id,
                    away_team_id,
                ),
                (
                    "match_provider_mappings",
                    "provider_match_id",
                    "match_id",
                    row.provider_match_id,
                    fixture_id,
                ),
            )
            for table, identity_column, canonical_column, provider_value, canonical_value in (
                entities[:1] if competition_only else entities
            ):
                read_table = (
                    "product_effective_team_mappings"
                    if table == "team_provider_mappings"
                    else table
                )
                read_column = (
                    "effective_team_id" if table == "team_provider_mappings" else canonical_column
                )
                trust = (
                    f"football.product_mapping_trusted('team',id,{read_column})"
                    if table == "team_provider_mappings"
                    else f"football.product_mapping_trusted('competition',id,{read_column})"
                    if table == "competition_provider_mappings"
                    else "false"
                )
                cursor.execute(
                    f"""SELECT {read_column}, mapping_method, {canonical_column}, {trust}
                         FROM football.{read_table}
                         WHERE provider_id = %s AND {identity_column} = %s AND valid_to IS NULL""",
                    (provider_id, provider_value),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    corrected = existing[0] != existing[2]
                    preserve_observations |= corrected
                    admitted = existing[3]
                    if corrected and existing[0] != canonical_value:
                        raise ValueError(
                            "linked correction conflicts with requested fixture mapping"
                        )
                    if existing[0] != canonical_value or (
                        mapping_method == "manual"
                        and existing[1] != "manual"
                        and not corrected
                        and not admitted
                    ):
                        provisional_id = self._provider_scoped_identity(table, provider_value)
                        if mapping_method != "manual" and (
                            mapping_method != "explicit_crosswalk" or existing[0] != provisional_id
                        ):
                            raise ValueError(f"contradictory existing {table} mapping")
                        cursor.execute(
                            f"""UPDATE football.{table}
                                   SET valid_to = %s, last_seen_at = GREATEST(last_seen_at, %s)
                                 WHERE provider_id = %s AND {identity_column} = %s
                                   AND valid_to IS NULL""",
                            (mapping_at, mapping_at, provider_id, provider_value),
                        )
                    else:
                        cursor.execute(
                            f"""UPDATE football.{table}
                                   SET last_seen_at = GREATEST(last_seen_at, %s)
                                 WHERE provider_id = %s AND {identity_column} = %s
                                   AND valid_to IS NULL""",
                            (row.observed_at, provider_id, provider_value),
                        )
                        continue
                cursor.execute(
                    f"""INSERT INTO football.{table} (
                            {canonical_column}, provider_id, {identity_column},
                            valid_from, first_seen_at, last_seen_at,
                            mapping_method, mapping_confidence, source_snapshot_id
                         ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)""",
                    (
                        canonical_value,
                        provider_id,
                        provider_value,
                        mapping_at if mapping_method in {"manual", "explicit_crosswalk"} else None,
                        mapping_at,
                        max(mapping_at, row.observed_at),
                        mapping_method,
                        snapshot_id,
                    ),
                )
            team_aliases = (
                (row.provider_home_team_id, row.home_team_name, home_team_id),
                (row.provider_away_team_id, row.away_team_name, away_team_id),
            )
            for provider_team_id, team_name, team_id in () if competition_only else team_aliases:
                cursor.execute(
                    """INSERT INTO football.product_team_aliases (
                           provider_code, provider_team_id, normalized_name, team_id
                       ) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (provider_code, provider_team_id) DO UPDATE SET
                           normalized_name = EXCLUDED.normalized_name,
                           team_id = CASE WHEN %s IN ('manual', 'explicit_crosswalk')
                               THEN EXCLUDED.team_id
                               ELSE football.product_team_aliases.team_id END""",
                    (
                        self.provider_code,
                        provider_team_id,
                        normalize_team_name(team_name),
                        team_id,
                        mapping_method,
                    ),
                )
            if not preserve_observations and not competition_only:
                cursor.execute(
                    """UPDATE football.product_provider_resource_observations
                      SET canonical_fixture_id = %s,
                          known_at = CASE WHEN point_in_time_eligibility = 'UNKNOWN'
                              THEN GREATEST(COALESCE(known_at, observed_at), %s)
                              ELSE known_at END,
                          point_in_time_eligibility = CASE
                              WHEN point_in_time_eligibility = 'UNKNOWN' THEN 'ELIGIBLE'
                              ELSE point_in_time_eligibility END
                    WHERE provider_code = %s AND provider_match_id = %s""",
                    (fixture_id, mapping_at, self.provider_code, row.provider_match_id),
                )
        self._store_observation(row, snapshot_id, fixture_id)

    def _provider_scoped_identity(self, table: str, provider_value: str) -> UUID:
        if table == "competition_provider_mappings":
            return stable_id("provider-scoped-competition", self.provider_code, provider_value)
        if table == "team_provider_mappings":
            return stable_id("provider-scoped-team", self.provider_code, provider_value)
        if table == "match_provider_mappings":
            return stable_id("provider-scoped-match", self.provider_code, provider_value)
        raise ValueError(f"unsupported provider mapping table: {table}")

    def _create_provider_scoped_fixture(
        self, row: FixtureObservation, snapshot_id: UUID, *, season_label: str | None = None
    ) -> UUID | None:
        """Create a non-forecastable fixture when provider identity is complete."""
        if row.provider_competition_name is None:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.competition_id
                     FROM football.competition_provider_mappings mapping
                     JOIN football.providers provider ON provider.id = mapping.provider_id
                    WHERE provider.code = %s
                      AND mapping.provider_competition_id = %s
                      AND mapping.valid_to IS NULL
                      AND mapping.mapping_confidence = 1""",
                (self.provider_code, row.provider_competition_id),
            )
            mapped_competition = cursor.fetchone()
        competition_id = (
            cast(UUID, mapped_competition[0])
            if mapped_competition is not None
            else stable_id(
                "provider-scoped-competition", self.provider_code, row.provider_competition_id
            )
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT season_label, metadata_status, geographic_scope
                   FROM football.product_competitions
                   WHERE competition_id = %s""",
                (competition_id,),
            )
            metadata = cursor.fetchone()
        if self._geographic_scopes is None:
            self._geographic_scopes = verified_geographic_scopes(
                self.connection, self.data_root, self.provider_code
            )
        geographic_scope = self._geographic_scopes.get(row.provider_competition_id)
        if metadata is not None and metadata[2] is not None:
            if geographic_scope is not None and geographic_scope != metadata[2]:
                raise ValueError("CONFLICTING_COMPETITION_GEOGRAPHY")
            geographic_scope = metadata[2]
        if geographic_scope is None:
            self._record_mapping_decision(
                row,
                snapshot_id,
                None,
                "REVIEW_REQUIRED",
                "CANONICAL_FIXTURE_GEOGRAPHY_REQUIRED",
                {},
            )
            return None
        season_label = season_label or "Unknown"
        source_season_label = season_label
        crosswalk = OPERATIONAL_COMPETITION_CROSSWALKS.get(
            (self.provider_code, row.provider_competition_id)
        )
        if (
            metadata is not None
            and metadata[1] == "VERIFIED"
            and crosswalk is not None
            and crosswalk[0] == "api_football"
            and re.fullmatch(r"\d{4}/\d{4}", season_label)
        ):
            start, end = (int(year) for year in season_label.split("/"))
            if end != start + 1:
                raise ValueError("crosswalk league season years must be consecutive")
            season_label = str(start)
        season_id = stable_id("season", competition_id, season_label)
        home_id = self._mapped_or_scoped_team(row.provider_home_team_id)
        away_id = self._mapped_or_scoped_team(row.provider_away_team_id)
        verified = (
            metadata is not None
            and metadata[1] == "VERIFIED"
            and competition_id
            != stable_id(
                "provider-scoped-competition", self.provider_code, row.provider_competition_id
            )
            and season_label != "Unknown"
            and home_id
            != stable_id("provider-scoped-team", self.provider_code, row.provider_home_team_id)
            and away_id
            != stable_id("provider-scoped-team", self.provider_code, row.provider_away_team_id)
        )
        fixture_id = (
            fixture_identity(competition_id, season_label, row.kickoff_at, home_id, away_id)
            if verified
            else stable_id("provider-scoped-match", self.provider_code, row.provider_match_id)
        )
        if home_id == away_id:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO football.competitions (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (competition_id,),
            )
            cursor.execute(
                """INSERT INTO football.product_competitions (
                       competition_id, name, country, continent, division,
                       competition_type, season_label, fixtures_available,
                       results_available, availability_status, source_roles, updated_at,
                       metadata_status, geographic_scope
                   ) VALUES (%s, %s, 'Unknown', 'Unknown', NULL, 'UNKNOWN', %s, true, %s,
                       'SOURCE_DATA_INCOMPLETE', %s::jsonb, %s, 'PROVISIONAL', %s)
                   ON CONFLICT (competition_id) DO UPDATE SET
                       geographic_scope = COALESCE(
                           football.product_competitions.geographic_scope,
                           EXCLUDED.geographic_scope),
                       updated_at = GREATEST(
                           football.product_competitions.updated_at, EXCLUDED.updated_at
                       )""",
                (
                    competition_id,
                    row.provider_competition_name,
                    season_label,
                    row.status == "FINISHED" and row.home_score is not None,
                    json.dumps(
                        {
                            "fixtures": [self.provider_code],
                            "results": [self.provider_code],
                            "standings": [],
                            "h2h": [],
                            "team_stats": [],
                        },
                        sort_keys=True,
                    ),
                    row.observed_at,
                    geographic_scope,
                ),
            )
            cursor.execute(
                """INSERT INTO football.seasons (id, competition_id)
                   VALUES (%s, %s) ON CONFLICT DO NOTHING""",
                (season_id, competition_id),
            )
            for team_id, name in ((home_id, row.home_team_name), (away_id, row.away_team_name)):
                cursor.execute(
                    """INSERT INTO football.teams (id, entity_kind)
                       VALUES (%s, 'club') ON CONFLICT DO NOTHING""",
                    (team_id,),
                )
                cursor.execute(
                    """INSERT INTO football.product_teams (team_id, name, updated_at)
                       VALUES (%s, %s, %s) ON CONFLICT (team_id) DO UPDATE SET
                           updated_at = GREATEST(
                               football.product_teams.updated_at, EXCLUDED.updated_at
                           )""",
                    (team_id, name, row.observed_at),
                )
            cursor.execute(
                """INSERT INTO football.matches (id, competition_id, season_id)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                (fixture_id, competition_id, season_id),
            )
            cursor.execute(
                """INSERT INTO football.product_fixtures (
                       fixture_id, competition_id, home_team_id, away_team_id,
                       kickoff_at, status, home_score, away_score,
                       forecast_availability, updated_at, result_score_basis, identity_status
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s)
                   ON CONFLICT (fixture_id) DO NOTHING""",
                (
                    fixture_id,
                    competition_id,
                    home_id,
                    away_id,
                    row.kickoff_at,
                    row.status,
                    row.home_score,
                    row.away_score,
                    "NOT_ENOUGH_HISTORY" if verified else "SOURCE_DATA_INCOMPLETE",
                    row.source_updated_at or row.observed_at,
                    row.result_score_basis,
                    "VERIFIED" if verified else "PROVISIONAL",
                ),
            )
            created = cursor.rowcount == 1
        candidate = (
            fixture_id,
            competition_id,
            home_id,
            away_id,
            row.provider_competition_name,
            row.home_team_name,
            row.away_team_name,
            row.status,
            row.home_score,
            row.away_score,
        )
        self._persist_deterministic_mapping(
            row,
            snapshot_id,
            candidate,
            mapping_method="explicit_crosswalk" if verified else "deterministic",
        )
        self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "AUTO_ACCEPTED",
            "provider-scoped canonical fixture created",
            {
                "identity_scope": "verified_provider_ids" if verified else "provider",
                "forecast_eligible": verified,
                "season_label": season_label,
                "source_season_label": source_season_label,
            },
        )
        return fixture_id if created else fixture_id

    def _set_verified_league_season(
        self, row: FixtureObservation, fixture_id: UUID, season_label: str
    ) -> None:
        crosswalk = OPERATIONAL_COMPETITION_CROSSWALKS.get(
            (self.provider_code, row.provider_competition_id)
        )
        if crosswalk is None or crosswalk[0] != "api_football":
            return
        from football.product.provider_history_scopes import normalize_seasons

        years = normalize_seasons([season_label])[0].split(" - ", 1)[0].split("/")
        start = int(years[0])
        if len(years) == 2 and int(years[1]) != start + 1:
            raise ValueError("crosswalk league season years must be consecutive")
        with self.connection.cursor() as cursor:
            fixture = cursor.execute(
                """SELECT competition_id FROM football.product_fixtures
                   WHERE fixture_id = %s AND identity_status = 'VERIFIED'""",
                (fixture_id,),
            ).fetchone()
            if fixture is None:
                return
            season_id = self._reviewed_league_season(
                row.provider_competition_id, season_label, fixture[0]
            )
            if season_id is None:
                if " - " in season_label:
                    return
                season_id = stable_id("season", fixture[0], start)
            cursor.execute(
                "INSERT INTO football.seasons (id, competition_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (season_id, fixture[0]),
            )
            cursor.execute(
                "UPDATE football.matches SET season_id = %s WHERE id = %s",
                (season_id, fixture_id),
            )

    def _reviewed_league_season(
        self, competition: str, label: str, canonical_competition: UUID
    ) -> UUID | None:
        """Use only the exact prospectively reviewed native label; never extrapolate years."""
        mappings = self.connection.execute(
            """SELECT mapping.provider_season_id, mapping.season_id,
                      season.competition_id, mapping.mapping_confidence,
                      mapping.mapping_method, snapshot.status
               FROM football.season_provider_mappings mapping
               JOIN football.providers provider ON provider.id = mapping.provider_id
               JOIN football.seasons season ON season.id = mapping.season_id
               JOIN football.source_snapshots snapshot ON snapshot.id = mapping.source_snapshot_id
               WHERE provider.code = %s AND mapping.provider_competition_id = %s
                 AND mapping.valid_to IS NULL AND mapping.created_at <= clock_timestamp()
                 AND (mapping.valid_from IS NULL OR mapping.valid_from <= clock_timestamp())""",
            (self.provider_code, competition),
        ).fetchall()
        if not mappings:
            return None
        for native_label, season, target, confidence, method, status in mappings:
            if native_label != label:
                continue
            if (
                target != canonical_competition
                or confidence != 1
                or method != "manual"
                or status != "validated"
            ):
                raise ValueError("provider season correspondence is not independently reviewed")
            return cast(UUID, season)
        raise ValueError("explicit provider season correspondence required for this label")

    def _mapped_or_scoped_team(self, provider_team_id: str) -> UUID:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.effective_team_id
                     FROM football.product_effective_team_mappings mapping
                     JOIN football.providers provider ON provider.id = mapping.provider_id
                    WHERE provider.code = %s AND mapping.provider_team_id = %s
                      AND mapping.valid_to IS NULL AND mapping.mapping_confidence = 1""",
                (self.provider_code, provider_team_id),
            )
            mapped = cursor.fetchone()
        if mapped is not None:
            return cast(UUID, mapped[0])
        return stable_id("provider-scoped-team", self.provider_code, provider_team_id)

    def _insert_qualified_history(
        self, row: FixtureObservation, fixture_id: UUID, snapshot_id: UUID
    ) -> int:
        if row.status != "FINISHED" or row.home_score is None or row.away_score is None:
            return 0
        with self.connection.cursor() as cursor:
            if row.result_score_basis != "REGULATION_90":
                if self.provider_code != "pitchapi":
                    return 0
                cursor.execute(
                    """SELECT competition.competition_type,
                              fixture.forecast_availability
                         FROM football.product_effective_fixtures fixture
                         JOIN football.product_competitions competition
                           ON competition.competition_id = fixture.competition_id
                        WHERE fixture.fixture_id = %s""",
                    (fixture_id,),
                )
                qualification = cursor.fetchone()
                if (
                    qualification is None
                    or qualification[0] != "LEAGUE"
                    or qualification[1] == "SOURCE_DATA_INCOMPLETE"
                ):
                    return 0
            cursor.execute(
                """INSERT INTO football.product_team_match_history (
                       fixture_id, competition_id, home_team_id, away_team_id,
                       kickoff_at, home_goals, away_goals, source_provider_code,
                       source_snapshot_id, source_kickoff_precision
                   ) SELECT fixture_id, competition_id, home_team_id, away_team_id,
                            kickoff_at, %s, %s, %s, %s, 'EXACT'
                       FROM football.product_effective_fixtures WHERE fixture_id = %s
                   ON CONFLICT (fixture_id) DO UPDATE SET
                       competition_id=EXCLUDED.competition_id,
                       home_team_id=EXCLUDED.home_team_id,away_team_id=EXCLUDED.away_team_id,
                       kickoff_at=EXCLUDED.kickoff_at,
                       source_provider_code=EXCLUDED.source_provider_code,
                       source_snapshot_id=EXCLUDED.source_snapshot_id,
                       source_kickoff_precision=EXCLUDED.source_kickoff_precision
                   WHERE %s AND
                     (football.product_team_match_history.home_goals,
                      football.product_team_match_history.away_goals)=
                     (EXCLUDED.home_goals,EXCLUDED.away_goals)
                     AND NOT EXISTS (SELECT 1 FROM football.product_eligible_fixture_history_at(
                         statement_timestamp(),ARRAY[EXCLUDED.fixture_id]))
                     AND (football.product_team_match_history.source_provider_code,
                          football.product_team_match_history.source_snapshot_id)
                         IS DISTINCT FROM
                         (EXCLUDED.source_provider_code,EXCLUDED.source_snapshot_id)""",
                (
                    row.home_score,
                    row.away_score,
                    self.provider_code,
                    snapshot_id,
                    fixture_id,
                    self._verified_provider_entities(row),
                ),
            )
            return cursor.rowcount

    def _record_mapping_decision(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        fixture_id: UUID | None,
        disposition: str,
        reason: str,
        evidence: Mapping[str, Any],
    ) -> UUID:
        semantic = sha256_json(
            {
                "provider": self.provider_code,
                "match": row.provider_match_id,
                "fixture": str(fixture_id) if fixture_id else None,
                "disposition": disposition,
                "reason": reason,
                "evidence": evidence,
                "snapshot": str(snapshot_id),
            }
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO football.product_provider_mapping_decisions (
                       semantic_sha256, provider_code, provider_match_id,
                       candidate_fixture_id, disposition, reason, evidence,
                       source_snapshot_id, observed_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (semantic_sha256) DO NOTHING RETURNING decision_id""",
                (
                    semantic,
                    self.provider_code,
                    row.provider_match_id,
                    fixture_id,
                    disposition,
                    reason,
                    json.dumps(dict(evidence), sort_keys=True),
                    snapshot_id,
                    row.observed_at,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                inserted = cursor.execute(
                    """SELECT decision_id FROM football.product_provider_mapping_decisions
                       WHERE semantic_sha256 = %s""",
                    (semantic,),
                ).fetchone()
            assert inserted is not None
            return cast(UUID, inserted[0])

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
                "result_score_basis": row.result_score_basis,
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
                    provider_competition_id, provider_competition_name,
                    provider_home_team_id, provider_home_team_name,
                    provider_away_team_id, provider_away_team_name,
                    canonical_fixture_id, source_snapshot_id,
                    kickoff_at, canonical_status, provider_status, home_score, away_score,
                    match_minute, added_time, period, source_updated_at, observed_at,
                    cache_expires_at, stale_after, last_fetched_at, result_score_basis
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (semantic_sha256) DO UPDATE SET
                    provider_competition_name = COALESCE(
                        football.product_provider_fixture_observations.provider_competition_name,
                        EXCLUDED.provider_competition_name
                    ),
                    provider_home_team_name = COALESCE(
                        football.product_provider_fixture_observations.provider_home_team_name,
                        EXCLUDED.provider_home_team_name
                    ),
                    provider_away_team_name = COALESCE(
                        football.product_provider_fixture_observations.provider_away_team_name,
                        EXCLUDED.provider_away_team_name
                    ),
                    last_fetched_at = GREATEST(
                        football.product_provider_fixture_observations.last_fetched_at,
                        EXCLUDED.last_fetched_at
                    ),
                    cache_expires_at = EXCLUDED.cache_expires_at,
                    stale_after = EXCLUDED.stale_after
                RETURNING xmax = 0
                """,
                (
                    semantic,
                    self.provider_code,
                    row.provider_match_id,
                    row.provider_competition_id,
                    row.provider_competition_name,
                    row.provider_home_team_id,
                    row.home_team_name,
                    row.provider_away_team_id,
                    row.away_team_name,
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
                    row.observed_at,
                    row.result_score_basis,
                ),
            )
            result = cursor.fetchone()
            return bool(result and result[0])

    def _update_canonical_fixture(
        self, row: FixtureObservation, fixture_id: UUID, snapshot_id: UUID
    ) -> int:
        if row.status == "FINISHED":
            return self._apply_finished_result(row, fixture_id, snapshot_id)
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        incoming_at = row.source_updated_at or row.observed_at
        with self.connection.cursor() as cursor:
            current = cursor.execute(
                """SELECT status, updated_at FROM football.product_fixtures
                    WHERE fixture_id = %s FOR UPDATE""",
                (fixture_id,),
            ).fetchone()
            if (
                current is None
                or incoming_at < current[1]
                or not _valid_transition(current[0], row.status)
            ):
                return 0
            cursor.execute(
                """UPDATE football.product_fixtures
                      SET status = %s, home_score = %s, away_score = %s, updated_at = %s
                    WHERE fixture_id = %s AND status = %s AND updated_at = %s
                      AND (status, home_score, away_score)
                          IS DISTINCT FROM (%s, %s, %s)""",
                (
                    row.status,
                    row.home_score,
                    row.away_score,
                    incoming_at,
                    fixture_id,
                    current[0],
                    current[1],
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
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, home_score, away_score, updated_at
                FROM football.product_fixtures WHERE fixture_id = %s FOR UPDATE
                """,
                (fixture_id,),
            )
            existing = cursor.fetchone()
            if existing is None:
                return 0
            existing_status, existing_home, existing_away, existing_updated_at = existing
            incoming_at = row.source_updated_at or row.observed_at
            if incoming_at < existing_updated_at:
                return 0
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
                   SET status = 'FINISHED', home_score = %s, away_score = %s,
                       result_score_basis = %s, updated_at = %s
                 WHERE fixture_id = %s
                   AND (status <> 'FINISHED' OR home_score IS NULL OR away_score IS NULL
                        OR (result_score_basis = 'UNKNOWN' AND %s = 'REGULATION_90'
                            AND home_score = %s AND away_score = %s))
                """,
                (
                    row.home_score,
                    row.away_score,
                    row.result_score_basis,
                    incoming_at,
                    fixture_id,
                    row.result_score_basis,
                    row.home_score,
                    row.away_score,
                ),
            )
            return cursor.rowcount

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
                    point_in_time_eligibility, development_only, payload, last_fetched_at
                ) VALUES (%s, %s, %s, %s, %s, 'AVAILABLE', %s, %s, %s, %s, %s, true, %s, %s)
                ON CONFLICT (semantic_sha256) DO UPDATE SET
                    last_fetched_at = GREATEST(
                        football.product_provider_resource_observations.last_fetched_at,
                        EXCLUDED.last_fetched_at
                    )
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
                    response.fetched_at,
                    eligibility,
                    json.dumps(payload, sort_keys=True),
                    response.fetched_at,
                ),
            )
            return cursor.rowcount

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


def _fotmob_season_rows(
    response: FotmobResponse, league_id: str, season: str
) -> tuple[FotmobLiveScore, ...]:
    if not isinstance(response.data, Mapping):
        raise ValueError("FotMob league response must be an object")
    details = response.data.get("details", {})
    fixtures = response.data.get("fixtures", {})
    if not isinstance(details, Mapping) or not isinstance(fixtures, Mapping):
        raise ValueError("FotMob league metadata or fixtures missing")
    from football.product.provider_history_scopes import normalize_seasons

    selected = details.get("selectedSeason", response.data.get("selectedSeason"))
    if str(details.get("id")) != league_id:
        raise ValueError("FotMob fixture competition ID mismatch")
    if normalize_seasons([selected]) != normalize_seasons([season]):
        raise ValueError("FotMob selected season does not match requested season")
    if not isinstance(fixtures.get("allMatches"), list):
        raise ValueError("FotMob league fixture list missing")
    return normalize_daily_matches(
        replace(
            response,
            data={
                "leagues": [
                    {
                        "id": league_id,
                        "name": details.get("name"),
                        "matches": fixtures["allMatches"],
                    }
                ]
            },
        )
    )


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
    match_facts = source.get("matchFacts")
    if isinstance(match_facts, Mapping):
        events = match_facts.get("events")
        if isinstance(events, (Mapping, list)):
            resources["EVENTS"] = events
    return resources


def _valid_transition(current: str, incoming: str) -> bool:
    terminal = {"FINISHED", "CANCELLED", "ABANDONED", "AWARDED"}
    if current in terminal:
        return current == incoming
    allowed = {
        "SCHEDULED": {"SCHEDULED", "LIVE", "HALF_TIME", "POSTPONED", *terminal},
        "POSTPONED": {"POSTPONED", "SCHEDULED", "LIVE", *terminal},
        "LIVE": {"LIVE", "HALF_TIME", "SUSPENDED", "INTERRUPTED", *terminal},
        "HALF_TIME": {"HALF_TIME", "LIVE", "SUSPENDED", "INTERRUPTED", *terminal},
        "SUSPENDED": {"SUSPENDED", "INTERRUPTED", "LIVE", "HALF_TIME", *terminal},
        "INTERRUPTED": {"INTERRUPTED", "SUSPENDED", "LIVE", "HALF_TIME", *terminal},
    }
    return incoming in allowed.get(current, set())


def _cache_fresh_until(response: FotmobResponse | PitchApiResponse) -> datetime | None:
    if isinstance(response, FotmobResponse) and response.cache_max_age_seconds is not None:
        return response.fetched_at + timedelta(seconds=response.cache_max_age_seconds)
    return None


def _newer_calendar_row(
    row: FixtureObservation, selected: Mapping[str, tuple[FixtureObservation, UUID | None]]
) -> bool:
    previous = selected.get(row.provider_match_id)
    if previous is None:
        return True
    # Retain the current-day observation when the older calendar cannot prove
    # newer source information. Both immutable listing snapshots are retained.
    return (
        row.source_updated_at is not None
        and previous[0].source_updated_at is not None
        and row.source_updated_at > previous[0].source_updated_at
    )


def _detail_priority(item: FixtureObservation, fixture_id: UUID | None) -> tuple[int, float, str]:
    mapped = fixture_id is not None
    if item.status == "LIVE":
        rank = 0 if mapped else 1
    elif item.status in {"HALF_TIME", "INTERRUPTED", "SUSPENDED"}:
        rank = 2 if mapped else 5
    elif item.status == "FINISHED" and mapped:
        rank = 3
    elif item.status == "SCHEDULED" and mapped:
        rank = 4
    else:
        rank = 5
    return rank, abs((item.kickoff_at - item.observed_at).total_seconds()), item.provider_match_id


def _normalize_competition_name(value: str) -> str:
    normalized = normalize_team_name(value)
    normalized = re.sub(r"\blaliga\b", "la liga", normalized)
    normalized = re.sub(r"\bj league 2\b", "j2 league", normalized)
    normalized = re.sub(r"\bj league\b", "j1 league", normalized)
    normalized = re.sub(r"\bliga nacional apertura\b", "liga nacional", normalized)
    return normalized
