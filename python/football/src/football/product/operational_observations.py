"""Observation ingestion and replay for the operational provider sync."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from psycopg import Error

from football.product.competition_geography import (
    refresh_competition_geography,
)
from football.product.operational_identity import OperationalIdentityMixin
from football.product.operational_support import (
    FixtureObservation,
    SyncCounts,
    _fotmob_season_rows,
)
from football.providers.fotmob import (
    FotmobResponse,
)
from football.providers.pitchapi import (
    PitchApiClient,
    PitchApiFixture,
    PitchApiResponse,
    normalize_pitchapi_matches,
)
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks


class OperationalObservationMixin(OperationalIdentityMixin):
    """Ingest, replay and backfill stored provider observations."""

    def _ingest_observations(
        self,
        rows: Sequence[FixtureObservation],
        snapshot_id: UUID,
        counts: SyncCounts,
        *,
        create_missing: bool = True,
    ) -> list[tuple[FixtureObservation, UUID | None]]:
        resolved: list[tuple[FixtureObservation, UUID | None]] = []
        self._load_geographic_scopes()
        for row in rows:
            try:
                created = inserted = matched = updated = history_inserted = 0
                unmatched = skipped = 0
                with self.connection.transaction():
                    acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
                    fixture_id = self._resolve_fixture(row, snapshot_id)
                    if fixture_id is None and create_missing:
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
                        self._reconcile_retained_members(row, fixture_id, snapshot_id)
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
        self.connection.execute("SELECT football.check_provider_scope_work()")
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
        self._load_geographic_scopes()
        self.connection.commit()
        for row in rows:
            self._heartbeat_history_scope()
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
                    self.connection.execute("SELECT football.check_provider_scope_work()")
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
        self.connection.commit()
        geography = refresh_competition_geography(
            self.connection, self.data_root, self.provider_code
        )
        self.connection.execute("SELECT football.check_provider_scope_work()")
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

    def backfill_pitchapi_league(
        self, client: PitchApiClient, league_id: str, season: str
    ) -> dict[str, object]:
        """Import one bounded PitchAPI played-season scope through the normal path."""
        self.pacer.wait()
        response = client.league_matches(league_id, season=season, status="played")
        return self.backfill_league_response(league_id, season, response, network_acquired=True)

    def _heartbeat_history_scope(self) -> None:
        self.connection.execute("SELECT football.heartbeat_provider_scope_work()")
        self.connection.commit()

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
        self._load_geographic_scopes()
        self.connection.commit()
        reconciled = 0
        for source in stored:
            try:
                with self.connection.transaction():
                    reconciled += int(
                        self.reconcile_retained_observation(source, create_missing=create_missing)
                        is not None
                    )
            except (Error, ValueError) as failure:
                row = self._retained_fixture(source)
                self._record_failed_observation(row, source[17], str(failure).splitlines()[0])
        return reconciled

    def _retained_fixture(self, source: tuple[Any, ...]) -> PitchApiFixture:
        basis = source[18]
        if basis == "UNKNOWN" and self.provider_code == "fotmob":
            label = (source[8] or "").upper()
            if label in {"FT", "FULL TIME", "FULL-TIME"}:
                basis = "REGULATION_90"
        return PitchApiFixture(
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

    def reconcile_retained_observation(
        self, source: tuple[Any, ...], *, create_missing: bool = False
    ) -> UUID | None:
        """Replay one retained observation; caller owns proof, locks and commit."""
        row = self._retained_fixture(source)
        snapshot_id = cast(UUID, source[17])
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        fixture_id = self._resolve_fixture(row, snapshot_id)
        if fixture_id is None and create_missing:
            fixture_id = self._create_provider_scoped_fixture(row, snapshot_id)
        if fixture_id is None:
            return None
        self._store_observation(row, snapshot_id, fixture_id)
        self._update_canonical_fixture(row, fixture_id, snapshot_id)
        self._reconcile_retained_members(row, fixture_id, snapshot_id)
        self._insert_qualified_history(row, fixture_id, snapshot_id)
        return fixture_id

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
