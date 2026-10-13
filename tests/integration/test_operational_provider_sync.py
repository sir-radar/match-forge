from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.product.api_football import (
    ApiFootballClient,
    ApiFootballError,
    PostgresApiFootballBudget,
)
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.historical_backfill import HistoricalBackfillStore, HistoricalMatch
from football.product.identity_admission import admit_provider_mappings
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.provider_history_scopes import claim_scope, enqueue_seasons
from football.product.sync import ProductSync
from football.providers.pitchapi import PitchApiFixture, PitchApiResponse
from psycopg import Connection
from psycopg.errors import UniqueViolation

from tests.integration.historical_source_fixture import test_snapshot as _test_snapshot

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def test_provider_history_scopes_are_idempotent_fair_and_resumable(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as database:
        sync = OperationalProviderSync(database, tmp_path, provider_code="pitchapi")
        league = "l_Job001"
        try:
            enqueue_seasons(sync, league, ["2025/2026", "2024/2025"])
            enqueue_seasons(sync, league, ["2025/2026", "2024/2025"])
            database.commit()
            assert claim_scope(sync, league, None) == (league, "2025/2026")
            assert claim_scope(sync, league, None) == (league, "2024/2025")
            assert claim_scope(sync, league, None) is None
            database.execute(
                """UPDATE football.product_provider_history_scopes
                   SET claimed_at = now() - interval '31 minutes'
                   WHERE provider_code = 'pitchapi' AND provider_competition_id = %s""",
                (league,),
            )
            database.commit()
            assert claim_scope(sync, league, None) == (league, "2025/2026")
        finally:
            database.rollback()
            database.execute(
                """DELETE FROM football.product_provider_history_scopes
                   WHERE provider_code = 'pitchapi' AND provider_competition_id = %s""",
                (league,),
            )
            database.commit()


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


def test_reconciliation_and_lifecycle_precedence_are_deterministic(
    connection: Connection[Any], tmp_path: Path
) -> None:
    kickoff = datetime(2026, 10, 9, 18, tzinfo=UTC)
    acquired = kickoff + timedelta(hours=3)
    history = HistoricalBackfillStore(
        connection, "openfootball", "OpenFootball", "operational-sync-test-v1"
    )
    history_snapshot = _test_snapshot(
        history,
        tmp_path,
        source_identity="test/operational-sync",
        source_revision="d" * 40,
        acquired_at=acquired,
        manifest_path="2026/test.operational.json",
        payload=(
            b'{"matches":[{"date":"2026-10-09","team1":"Operational Home",'
            b'"team2":"Operational Away","score":{"ft":[0,0]}}]}'
        ),
    )
    source_match = HistoricalMatch(
        provider_match_id="2026/test.operational#1",
        provider_competition_id="test.operational",
        competition_name="Operational Test League",
        country="World",
        division=1,
        season="2026",
        home_team_id="Operational Home",
        home_team_name="Operational Home",
        away_team_id="Operational Away",
        away_team_name="Operational Away",
        kickoff_at=kickoff,
        kickoff_precision="EXACT",
        home_goals=0,
        away_goals=0,
        source_path="2026/test.operational.json",
    )
    assert history.import_match(source_match, history_snapshot, acquired) == "inserted"
    admit_provider_mappings(connection, tmp_path, "openfootball")
    with connection.cursor() as cursor:
        fixture_id = cursor.execute(
            """SELECT mapping.match_id
                 FROM football.match_provider_mappings mapping
                 JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = 'openfootball'
                  AND mapping.provider_match_id = %s""",
            (source_match.provider_match_id,),
        ).fetchone()[0]
        cursor.execute(
            """INSERT INTO football.product_fixtures (
                   fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                   status, home_score, away_score, forecast_availability, updated_at
               )
               SELECT fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                      'FINISHED', home_goals, away_goals, 'NOT_ENOUGH_HISTORY', %s
                 FROM football.product_team_match_history WHERE fixture_id = %s
               ON CONFLICT (fixture_id) DO NOTHING""",
            (acquired, fixture_id),
        )
        cursor.execute(
            """UPDATE football.product_fixtures
                  SET status = 'SCHEDULED', home_score = NULL, away_score = NULL,
                      updated_at = %s
                WHERE fixture_id = %s""",
            (kickoff - timedelta(days=1), fixture_id),
        )

    sync = OperationalProviderSync(
        connection,
        tmp_path,
        provider_code="pitchapi",
        minimum_interval_seconds=0,
    )
    raw = json.dumps(
        {
            "matches": [
                {
                    "id": match,
                    "league": {"id": league, "name": "Operational Test League"},
                    "home_team": {"id": home, "name": "Operational Home"},
                    "away_team": {"id": away, "name": "Operational Away"},
                    "time_utc": kickoff.isoformat(),
                    "status": "live",
                    "score_home": 1,
                    "score_away": 0,
                }
                for match, league, home, away in (
                    ("m_Test01", "l_Test01", "t_Home01", "t_Away01"),
                    (
                        "m_Provisional01",
                        "l_Provisional01",
                        "t_ProvisionalHome01",
                        "t_ProvisionalAway01",
                    ),
                )
            ]
        }
    ).encode()
    response = PitchApiResponse(
        path="/v1/date/2026-10-09",
        fetched_at=acquired,
        sha256=hashlib.sha256(raw).hexdigest(),
        raw=raw,
        data={},
    )
    snapshot_id = sync._record_response("fixtures-2026-10-09", response)
    live = PitchApiFixture(
        provider_match_id="m_Test01",
        provider_competition_id="l_Test01",
        provider_home_team_id="t_Home01",
        provider_away_team_id="t_Away01",
        home_team_name="Operational Home",
        away_team_name="Operational Away",
        kickoff_at=kickoff,
        status="LIVE",
        provider_status="1st Half",
        home_score=1,
        away_score=0,
        minute=20,
        added_time=None,
        period="FIRST_HALF",
        source_updated_at=kickoff + timedelta(minutes=20),
        observed_at=kickoff + timedelta(minutes=21),
        provider_competition_name="Operational Test League",
    )

    resolved = sync._resolve_fixture(live, snapshot_id)
    with connection.cursor() as cursor:
        decision = cursor.execute(
            """SELECT reason, evidence
                 FROM football.product_provider_mapping_decisions
                WHERE provider_code = 'pitchapi' AND provider_match_id = 'm_Test01'
                ORDER BY observed_at DESC LIMIT 1"""
        ).fetchone()
    assert resolved is None, decision
    assert decision[0] == "explicit cross-provider evidence required"
    assert sync._store_observation(live, snapshot_id, None)
    original_provisional = sync._create_provider_scoped_fixture(
        live, snapshot_id, season_label="2026"
    )
    assert original_provisional is not None and original_provisional != fixture_id
    with pytest.raises(ValueError, match="verified canonical fixture"):
        sync.apply_reviewed_mapping(live.provider_match_id, original_provisional)
    sync.apply_reviewed_mapping(live.provider_match_id, fixture_id)
    reconcile_product_fixtures(connection)
    assert connection.execute(
        """SELECT representative_fixture_id, resolution_status
           FROM football.fixture_identity_resolutions WHERE member_fixture_id = %s AND active""",
        (original_provisional,),
    ).fetchone() == (fixture_id, "DUPLICATE_RESOLVED")
    assert connection.execute(
        "SELECT count(*) FROM football.product_fixtures WHERE fixture_id = %s",
        (original_provisional,),
    ).fetchone() == (1,)
    assert sync._resolve_fixture(live, snapshot_id) == fixture_id
    assert sync._update_canonical_fixture(live, fixture_id, snapshot_id) == 0
    assert (
        sync._update_canonical_fixture(
            replace(
                live,
                status="SCHEDULED",
                provider_status="Not Started",
                home_score=None,
                away_score=None,
                minute=None,
                period=None,
                source_updated_at=kickoff - timedelta(minutes=1),
                observed_at=kickoff + timedelta(minutes=22),
            ),
            fixture_id,
            snapshot_id,
        )
        == 0
    )
    half_time = replace(
        live,
        status="HALF_TIME",
        provider_status="Half Time",
        source_updated_at=kickoff + timedelta(minutes=50),
        observed_at=kickoff + timedelta(minutes=51),
        minute=45,
        period="HALF_TIME",
    )
    assert sync._update_canonical_fixture(half_time, fixture_id, snapshot_id) == 1
    second_half = replace(
        half_time,
        status="LIVE",
        provider_status="2nd Half",
        source_updated_at=kickoff + timedelta(minutes=51),
        observed_at=kickoff + timedelta(minutes=52),
        minute=46,
        period="SECOND_HALF",
    )
    assert sync._update_canonical_fixture(second_half, fixture_id, snapshot_id) == 1
    assert (
        sync._update_canonical_fixture(
            replace(
                half_time,
                home_score=0,
                source_updated_at=kickoff + timedelta(minutes=45),
                observed_at=kickoff + timedelta(minutes=55),
            ),
            fixture_id,
            snapshot_id,
        )
        == 0
    )
    suspended = replace(
        second_half,
        status="SUSPENDED",
        provider_status="Suspended",
        source_updated_at=kickoff + timedelta(minutes=60),
        observed_at=kickoff + timedelta(minutes=61),
    )
    assert sync._update_canonical_fixture(suspended, fixture_id, snapshot_id) == 1
    resumed = replace(
        suspended,
        status="LIVE",
        provider_status="Resumed",
        source_updated_at=kickoff + timedelta(minutes=62),
        observed_at=kickoff + timedelta(minutes=63),
        minute=55,
        period="SECOND_HALF",
    )
    assert sync._update_canonical_fixture(resumed, fixture_id, snapshot_id) == 1
    finished = replace(
        resumed,
        status="FINISHED",
        provider_status="Finished",
        home_score=2,
        away_score=1,
        minute=None,
        period="FULL_TIME",
        source_updated_at=kickoff + timedelta(hours=2),
        observed_at=kickoff + timedelta(hours=2, minutes=1),
        result_score_basis="REGULATION_90",
    )
    unknown = replace(finished, result_score_basis="UNKNOWN")
    assert sync._store_observation(unknown, snapshot_id, fixture_id)
    assert sync._update_canonical_fixture(unknown, fixture_id, snapshot_id) == 1
    extra_time = replace(finished, result_score_basis="EXTRA_TIME")
    assert sync._update_canonical_fixture(extra_time, fixture_id, snapshot_id) == 0
    assert sync._store_observation(finished, snapshot_id, fixture_id)
    assert sync._update_canonical_fixture(finished, fixture_id, snapshot_id) == 1
    assert sync._update_canonical_fixture(finished, fixture_id, snapshot_id) == 0
    assert (
        sync._update_canonical_fixture(
            replace(
                finished,
                home_score=3,
                source_updated_at=kickoff + timedelta(hours=2, minutes=5),
                observed_at=kickoff + timedelta(hours=2, minutes=6),
            ),
            fixture_id,
            snapshot_id,
        )
        == 0
    )

    with connection.cursor() as cursor:
        fixture = cursor.execute(
            """SELECT status, home_score, away_score, result_score_basis
                 FROM football.product_fixtures WHERE fixture_id = %s""",
            (fixture_id,),
        ).fetchone()
        mapping_counts = cursor.execute(
            """SELECT count(*), count(*) FILTER (WHERE mapping_method = 'manual')
                 FROM football.match_provider_mappings mapping
                 JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = 'pitchapi' AND provider_match_id = 'm_Test01'"""
        ).fetchone()
        accepted_decisions = cursor.execute(
            """SELECT count(*)
                 FROM football.product_provider_mapping_decisions
                WHERE provider_code = 'pitchapi' AND provider_match_id = 'm_Test01'
                  AND disposition = 'MANUAL_ACCEPTED'"""
        ).fetchone()[0]
        conflicts = cursor.execute(
            """SELECT count(*)
                 FROM football.product_source_result_conflicts
                WHERE canonical_match_id = %s AND incoming_provider_code = 'pitchapi'""",
            (fixture_id,),
        ).fetchone()[0]

    assert fixture == ("FINISHED", 2, 1, "REGULATION_90")
    assert mapping_counts == (2, 1)
    assert accepted_decisions == 1
    assert conflicts == 1

    admitted_at = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    provisional = replace(
        live,
        provider_match_id="m_Provisional01",
        provider_competition_id="l_Provisional01",
        provider_home_team_id="t_ProvisionalHome01",
        provider_away_team_id="t_ProvisionalAway01",
    )
    provisional_fixture_id = sync._create_provider_scoped_fixture(provisional, snapshot_id)
    assert provisional_fixture_id is not None
    assert not sync._store_observation(provisional, snapshot_id, provisional_fixture_id)

    provisional_result = replace(provisional, status="FINISHED", result_score_basis="REGULATION_90")
    assert (
        sync._insert_qualified_history(provisional_result, provisional_fixture_id, snapshot_id) == 1
    )
    with connection.cursor() as cursor:
        assert cursor.execute(
            "SELECT identity_status FROM football.product_fixtures WHERE fixture_id = %s",
            (provisional_fixture_id,),
        ).fetchone() == ("PROVISIONAL",)
        assert cursor.execute(
            "SELECT count(*) FROM football.product_eligible_match_history WHERE fixture_id = %s",
            (provisional_fixture_id,),
        ).fetchone() == (0,)
        assert cursor.execute(
            """SELECT count(*) FROM football.product_eligible_match_history
               WHERE fixture_id = %s AND known_at <= %s""",
            (fixture_id, acquired - timedelta(seconds=1)),
        ).fetchone() == (0,)
        assert cursor.execute(
            """SELECT count(*) FROM football.product_eligible_match_history
               WHERE fixture_id = %s AND known_at <= %s""",
            (fixture_id, acquired),
        ).fetchone() == (0,)
        assert cursor.execute(
            "SELECT count(*) FROM football.product_eligible_history_at(%s) WHERE fixture_id = %s",
            (admitted_at, fixture_id),
        ).fetchone() == (1,)

    canonical_home, canonical_away = connection.execute(
        "SELECT home_team_id, away_team_id FROM football.product_fixtures WHERE fixture_id = %s",
        (fixture_id,),
    ).fetchone()
    product = ProductSync(
        connection, ApiFootballClient("stored-only"), tmp_path, tmp_path / "unused-artifact.json"
    )
    permitted = product._history_before(
        acquired + timedelta(days=1),
        canonical_home,
        canonical_away,
        knowledge_cutoff=admitted_at,
    )
    assert {match.fixture_id for match in permitted} == {fixture_id}
    assert (
        product._history_before(
            acquired + timedelta(days=1),
            canonical_home,
            canonical_away,
            knowledge_cutoff=acquired - timedelta(seconds=1),
        )
        == []
    )

    no_season = sync._create_provider_scoped_fixture(
        replace(
            live,
            provider_match_id="m_Noseas",
            kickoff_at=acquired + timedelta(days=2),
            status="SCHEDULED",
            provider_status="scheduled",
            home_score=None,
            away_score=None,
        ),
        snapshot_id,
    )
    assert connection.execute(
        "SELECT identity_status FROM football.product_fixtures WHERE fixture_id = %s",
        (no_season,),
    ).fetchone() == ("PROVISIONAL",)

    sync.apply_reviewed_mapping(provisional.provider_match_id, fixture_id)

    with connection.cursor() as cursor:
        active_mapping = cursor.execute(
            """SELECT mapping.match_id, mapping.mapping_method
                 FROM football.match_provider_mappings mapping
                 JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = 'pitchapi' AND mapping.provider_match_id = %s
                  AND mapping.valid_to IS NULL""",
            (provisional.provider_match_id,),
        ).fetchone()
        retired_mapping = cursor.execute(
            """SELECT count(*)
                 FROM football.match_provider_mappings mapping
                 JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = 'pitchapi' AND mapping.provider_match_id = %s
                  AND mapping.valid_to IS NOT NULL""",
            (provisional.provider_match_id,),
        ).fetchone()[0]
        observation_fixture = cursor.execute(
            """SELECT canonical_fixture_id
                 FROM football.product_provider_fixture_observations
                WHERE provider_code = 'pitchapi' AND provider_match_id = %s
                ORDER BY observation_id DESC LIMIT 1""",
            (provisional.provider_match_id,),
        ).fetchone()[0]
    assert active_mapping == (fixture_id, "manual")
    assert retired_mapping == 1
    assert observation_fixture == fixture_id
    assert connection.execute(
        """SELECT count(*) FROM football.product_provider_fixture_observations
           WHERE provider_code = 'pitchapi' AND provider_match_id = %s
             AND canonical_fixture_id = %s""",
        (provisional.provider_match_id, provisional_fixture_id),
    ).fetchone() == (1,)


def test_live_provider_lanes_do_not_compete_with_history_backfill(
    connection: Connection[Any],
) -> None:
    with connection.cursor() as cursor:
        for sync_type in ("HISTORY_BACKFILL", "FOTMOB_SYNC", "PITCHAPI_SYNC"):
            cursor.execute(
                "INSERT INTO football.product_sync_runs (sync_type, status) VALUES (%s, 'RUNNING')",
                (sync_type,),
            )

    with (
        pytest.raises(UniqueViolation),
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """INSERT INTO football.product_sync_runs (sync_type, status)
               VALUES ('FOTMOB_SYNC', 'QUEUED')"""
        )


def test_api_football_quota_circuit_persists_across_workers() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            """DELETE FROM football.provider_request_budgets
                WHERE provider_code = 'api_football' AND window_date = CURRENT_DATE"""
        )
    try:
        PostgresApiFootballBudget(DATABASE_URL).before_request()
        PostgresApiFootballBudget(DATABASE_URL).record_rejection("daily request limit reached")

        with pytest.raises(ApiFootballError, match="request suppressed"):
            PostgresApiFootballBudget(DATABASE_URL).before_request()

        with psycopg.connect(DATABASE_URL) as connection:
            assert connection.execute(
                """SELECT requests_used, remaining_requests, exhausted
                     FROM football.provider_request_budgets
                    WHERE provider_code = 'api_football' AND window_date = CURRENT_DATE"""
            ).fetchone() == (1, 0, True)
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                """DELETE FROM football.provider_request_budgets
                    WHERE provider_code = 'api_football' AND window_date = CURRENT_DATE"""
            )
