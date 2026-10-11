from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.product.historical_backfill import HistoricalBackfillStore, HistoricalMatch
from football.product.operational_provider_sync import OperationalProviderSync
from football.providers.pitchapi import PitchApiFixture, PitchApiResponse
from psycopg import Connection

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


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
    history_snapshot = history.ensure_snapshot(
        source_identity="test/operational-sync",
        source_revision="d" * 40,
        acquired_at=acquired,
        manifest_path="openfootball/test/operational-sync.json",
    )
    source_match = HistoricalMatch(
        provider_match_id="2026/test.operational#1",
        provider_competition_id="test.operational",
        competition_name="Operational Test League",
        country="Testland",
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
    raw = b'{"test":"operational-sync"}'
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
    assert resolved == fixture_id, decision
    assert sync._resolve_fixture(live, snapshot_id) == fixture_id
    assert sync._store_observation(live, snapshot_id, fixture_id)
    assert sync._update_canonical_fixture(live, fixture_id, snapshot_id) == 1
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
    assert sync._update_canonical_fixture(finished, fixture_id, snapshot_id) == 1
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
            """SELECT count(*), count(*) FILTER (WHERE mapping_method = 'deterministic')
                 FROM football.match_provider_mappings mapping
                 JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = 'pitchapi' AND provider_match_id = 'm_Test01'"""
        ).fetchone()
        accepted_decisions = cursor.execute(
            """SELECT count(*)
                 FROM football.product_provider_mapping_decisions
                WHERE provider_code = 'pitchapi' AND provider_match_id = 'm_Test01'
                  AND disposition = 'AUTO_ACCEPTED'"""
        ).fetchone()[0]
        conflicts = cursor.execute(
            """SELECT count(*)
                 FROM football.product_source_result_conflicts
                WHERE canonical_match_id = %s AND incoming_provider_code = 'pitchapi'""",
            (fixture_id,),
        ).fetchone()[0]

    assert fixture == ("FINISHED", 2, 1, "REGULATION_90")
    assert mapping_counts == (1, 1)
    assert accepted_decisions == 1
    assert conflicts == 1
