from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.product.api_football import ApiFootballClient
from football.product.domain import MODEL_ARTIFACT_PATH, stable_id
from football.product.historical_backfill import HistoricalBackfillStore, HistoricalMatch
from football.product.sync import ProductSync
from psycopg import Connection

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _first(row: Any | None) -> Any:
    assert row is not None
    return row[0]


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


def test_bulk_sources_share_one_match_and_preserve_score_conflict(
    connection: Connection[Any],
) -> None:
    observed_at = datetime(2026, 9, 30, tzinfo=UTC)
    openfootball = HistoricalBackfillStore(
        connection, "openfootball", "OpenFootball", "test-open-v1"
    )
    football_data = HistoricalBackfillStore(
        connection, "football_data_uk", "Football-Data.co.uk", "test-fd-v1"
    )
    open_snapshot = openfootball.ensure_snapshot(
        source_identity="test/openfootball",
        source_revision="a" * 40,
        acquired_at=observed_at,
        manifest_path="openfootball/test/catalog.json",
    )
    data_snapshot = football_data.ensure_snapshot(
        source_identity="test/football-data.csv",
        source_revision="b" * 64,
        acquired_at=observed_at,
        manifest_path="football_data_uk/test.csv",
    )
    source_match = HistoricalMatch(
        provider_match_id="2025-26/test.1.json#1",
        provider_competition_id="test.1",
        competition_name="Test Premier Division 2025/26",
        country="Testland",
        division=1,
        season="2025-2026",
        home_team_id="Home FC",
        home_team_name="Home FC",
        away_team_id="Away FC",
        away_team_name="Away FC",
        kickoff_at=datetime(2026, 1, 10, 15, tzinfo=UTC),
        kickoff_precision="EXACT",
        home_goals=2,
        away_goals=1,
        source_path="2025-26/test.1.json",
    )

    assert openfootball.import_match(source_match, open_snapshot, observed_at) == "inserted"
    second_source = replace(
        source_match,
        provider_match_id="archive/2526/TEST.csv#2",
        provider_competition_id="TEST",
        competition_name="Test Premier Division",
        home_team_id="Home",
        away_team_id="Away",
        source_path="archive/2526/TEST.csv",
    )
    assert football_data.import_match(second_source, data_snapshot, observed_at) == "existing"
    assert (
        football_data.import_match(
            replace(second_source, provider_match_id="archive/2526/TEST.csv#3", home_goals=1),
            data_snapshot,
            observed_at,
        )
        == "conflict"
    )

    with connection.cursor() as cursor:
        historical_matches = _first(
            cursor.execute(
                """
            SELECT count(*) FROM football.product_team_match_history
            WHERE source_snapshot_id = %s
            """,
                (open_snapshot,),
            ).fetchone()
        )
        provider_mappings = _first(
            cursor.execute(
                """
            SELECT count(DISTINCT provider.code)
            FROM football.match_provider_mappings mapping
            JOIN football.providers provider ON provider.id = mapping.provider_id
            JOIN football.product_team_match_history history
              ON history.fixture_id = mapping.match_id
            WHERE history.source_snapshot_id = %s
              AND provider.code IN ('openfootball', 'football_data_uk')
            """,
                (open_snapshot,),
            ).fetchone()
        )
        conflicts = _first(
            cursor.execute(
                """
            SELECT count(*) FROM football.product_source_result_conflicts
            WHERE incoming_snapshot_id = %s
            """,
                (data_snapshot,),
            ).fetchone()
        )
        canonical_score = cursor.execute(
            """
            SELECT home_goals, away_goals FROM football.product_team_match_history
            WHERE source_snapshot_id = %s
            """,
            (open_snapshot,),
        ).fetchone()

    assert historical_matches == 1
    assert provider_mappings == 2
    assert conflicts == 1
    assert canonical_score == (2, 1)


def test_backfill_history_unlocks_missing_forecast(connection: Connection[Any]) -> None:
    observed_at = datetime(2026, 9, 30, tzinfo=UTC)
    store = HistoricalBackfillStore(connection, "openfootball", "OpenFootball", "test-open-v1")
    snapshot = store.ensure_snapshot(
        source_identity="test/forecast-unlock",
        source_revision="c" * 40,
        acquired_at=observed_at,
        manifest_path="openfootball/test/forecast-unlock.json",
    )
    for index in range(10):
        kickoff = datetime(2026, 8, 1, 12, tzinfo=UTC) + timedelta(days=index)
        for side in ("home", "away"):
            home_name = "Forecast Home FC" if side == "home" else f"Home Opponent {index}"
            away_name = f"Away Opponent {index}" if side == "home" else "Forecast Away FC"
            result = store.import_match(
                HistoricalMatch(
                    provider_match_id=f"forecast-unlock-{side}-{index}",
                    provider_competition_id="test.9",
                    competition_name="Forecast Test League 2026",
                    country="Testland",
                    division=1,
                    season="2026",
                    home_team_id=home_name,
                    home_team_name=home_name,
                    away_team_id=away_name,
                    away_team_name=away_name,
                    kickoff_at=kickoff,
                    kickoff_precision="EXACT",
                    home_goals=2,
                    away_goals=1,
                    source_path="2026/test.9.json",
                ),
                snapshot,
                observed_at,
            )
            assert result == "inserted"

    with connection.cursor() as cursor:
        competition_id = _first(
            cursor.execute(
                """
            SELECT competition_id FROM football.competition_provider_mappings mapping
            JOIN football.providers provider ON provider.id = mapping.provider_id
            WHERE provider.code = 'openfootball'
              AND mapping.provider_competition_id = 'test.9'
            """
            ).fetchone()
        )
        home_id = _first(
            cursor.execute(
                """
            SELECT team_id FROM football.product_team_aliases
            WHERE provider_code = 'openfootball' AND provider_team_id = 'Forecast Home FC'
            """
            ).fetchone()
        )
        away_id = _first(
            cursor.execute(
                """
            SELECT team_id FROM football.product_team_aliases
            WHERE provider_code = 'openfootball' AND provider_team_id = 'Forecast Away FC'
            """
            ).fetchone()
        )
        season_id = stable_id("season", competition_id, "2026")
        fixture_id = stable_id("forecast-unlock-fixture", competition_id, home_id, away_id)
        cursor.execute(
            "INSERT INTO football.matches (id, competition_id, season_id) VALUES (%s, %s, %s)",
            (fixture_id, competition_id, season_id),
        )
        cursor.execute(
            """
            INSERT INTO football.product_fixtures (
                fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                status, forecast_availability, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'SCHEDULED', 'NOT_ENOUGH_HISTORY', %s)
            """,
            (
                fixture_id,
                competition_id,
                home_id,
                away_id,
                datetime(2026, 10, 10, 15, tzinfo=UTC),
                observed_at,
            ),
        )

    created = ProductSync(
        connection,
        ApiFootballClient("stored-data-only"),
        PROJECT_ROOT / ".local" / "football-data",
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    ).refresh_forecasts(observed_at)

    with connection.cursor() as cursor:
        availability = _first(
            cursor.execute(
                "SELECT forecast_availability FROM football.product_fixtures WHERE fixture_id = %s",
                (fixture_id,),
            ).fetchone()
        )
        forecast_count = _first(
            cursor.execute(
                "SELECT count(*) FROM football.product_forecasts WHERE fixture_id = %s",
                (fixture_id,),
            ).fetchone()
        )

    assert created >= 1
    assert availability == "FORECAST_AVAILABLE"
    assert forecast_count == 1
