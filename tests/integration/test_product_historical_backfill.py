from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.product.api_football import ApiFootballClient, ApiResponse
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
    assert (
        store.import_match(
            HistoricalMatch(
                provider_match_id="forecast-unlock-unrelated",
                provider_competition_id="test.9",
                competition_name="Forecast Test League 2026",
                country="Testland",
                division=1,
                season="2026",
                home_team_id="Unrelated Home FC",
                home_team_name="Unrelated Home FC",
                away_team_id="Unrelated Away FC",
                away_team_name="Unrelated Away FC",
                kickoff_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
                kickoff_precision="EXACT",
                home_goals=1,
                away_goals=0,
                source_path="2026/test.9.json",
            ),
            snapshot,
            observed_at,
        )
        == "inserted"
    )

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

    product = ProductSync(
        connection,
        ApiFootballClient("stored-data-only"),
        PROJECT_ROOT / ".local" / "football-data",
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    )
    relevant_history = product._history_before(
        datetime(2026, 10, 10, 15, tzinfo=UTC), home_id, away_id
    )
    created = product.refresh_forecasts(observed_at)

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
    assert len(relevant_history) == 20
    assert all(
        home_id in (match.home_team_id, match.away_team_id)
        or away_id in (match.home_team_id, match.away_team_id)
        for match in relevant_history
    )
    assert availability == "FORECAST_AVAILABLE"
    assert forecast_count == 1


def test_fixture_sync_repairs_zero_history_provider_team_aliases(
    connection: Connection[Any], tmp_path: Path
) -> None:
    observed_at = datetime(2026, 10, 3, 6, tzinfo=UTC)
    sync = ProductSync(
        connection,
        ApiFootballClient("test"),
        tmp_path,
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    )
    api_snapshot = sync._record_response(
        "fixtures-2026-10-10",
        ApiResponse("/fixtures", observed_at, b"{}", (), None),
    )
    competition_id = sync._competition_id("39", api_snapshot)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.product_competitions (
                competition_id, name, country, continent, division, competition_type,
                season_label, fixtures_available, results_available, standings_available,
                h2h_available, forecast_available, xg_available, team_stats_available,
                availability_status, source_roles, updated_at
            ) VALUES (
                %s, 'Premier League', 'England', 'Europe', 1, 'LEAGUE', '2026',
                true, false, false, false, false, false, false,
                'NOT_ENOUGH_HISTORY', '{}'::jsonb, %s
            )
            """,
            (competition_id, observed_at),
        )

    store = HistoricalBackfillStore(
        connection, "football_data_uk", "Football-Data.co.uk", "test-v1"
    )
    history_snapshot = store.ensure_snapshot(
        source_identity="test/premier-league.csv",
        source_revision="d" * 64,
        acquired_at=observed_at,
        manifest_path="football_data_uk/test/premier-league.csv",
    )
    for index in range(10):
        kickoff = datetime(2026, 8, 1, 12, tzinfo=UTC) + timedelta(days=index)
        for side in ("home", "away"):
            home_name = "Canonical Home FC" if side == "home" else f"Home Opponent {index}"
            away_name = f"Away Opponent {index}" if side == "home" else "Canonical Away FC"
            assert (
                store.import_match(
                    HistoricalMatch(
                        provider_match_id=f"history-{side}-{index}",
                        provider_competition_id="E0",
                        competition_name="Premier League",
                        country="England",
                        division=1,
                        season="2026-2027",
                        home_team_id=home_name,
                        home_team_name=home_name,
                        away_team_id=away_name,
                        away_team_name=away_name,
                        kickoff_at=kickoff,
                        kickoff_precision="EXACT",
                        home_goals=2,
                        away_goals=1,
                        source_path="test/premier-league.csv",
                    ),
                    history_snapshot,
                    observed_at,
                )
                == "inserted"
            )

    with connection.cursor() as cursor:
        canonical_home_id = _first(
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = 'football_data_uk'
                  AND provider_team_id = 'Canonical Home FC'
                """
            ).fetchone()
        )
        canonical_away_id = _first(
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = 'football_data_uk'
                  AND provider_team_id = 'Canonical Away FC'
                """
            ).fetchone()
        )
        duplicate_home_id = stable_id("team", "api_football", "1001")
        duplicate_away_id = stable_id("team", "api_football", "1002")
        for team_id, provider_team_id, name in (
            (duplicate_home_id, "1001", "Canonical Home FC"),
            (duplicate_away_id, "1002", "Canonical Away FC"),
        ):
            cursor.execute(
                "INSERT INTO football.teams (id, entity_kind) VALUES (%s, 'club')",
                (team_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.product_teams (team_id, name, country, updated_at)
                VALUES (%s, %s, 'England', %s)
                """,
                (team_id, name, observed_at),
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_aliases (
                    provider_code, provider_team_id, normalized_name, country, team_id
                ) VALUES ('api_football', %s, %s, 'England', %s)
                """,
                (provider_team_id, name.casefold(), team_id),
            )
            cursor.execute(
                """
                INSERT INTO football.team_provider_mappings (
                    team_id, provider_id, provider_team_id, first_seen_at, last_seen_at,
                    mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, id, %s, %s, %s, 'deterministic', 1.0, %s
                FROM football.providers WHERE code = 'api_football'
                """,
                (
                    team_id,
                    provider_team_id,
                    observed_at,
                    observed_at,
                    api_snapshot,
                ),
            )

    fixture = {
        "fixture": {
            "id": 5001,
            "date": "2026-10-10T15:00:00+00:00",
            "status": {"short": "NS"},
            "venue": {"name": "Test Ground"},
        },
        "league": {
            "id": 39,
            "name": "Premier League",
            "country": "England",
            "season": 2026,
            "round": "Regular Season - 1",
        },
        "teams": {
            "home": {"id": 1001, "name": "Canonical Home FC", "logo": None},
            "away": {"id": 1002, "name": "Canonical Away FC", "logo": None},
        },
        "goals": {"home": None, "away": None},
    }
    sync._store_fixture_competition(fixture, competition_id, observed_at)
    season_id = stable_id("season", competition_id, 2026)
    sync._ensure_season(competition_id, season_id)
    fixture_id = stable_id("existing-api-fixture", 5001)
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO football.matches (id, competition_id, season_id) VALUES (%s, %s, %s)",
            (fixture_id, competition_id, season_id),
        )
        sync._ensure_match_mapping(cursor, fixture_id, "5001", api_snapshot, observed_at)
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
                duplicate_home_id,
                duplicate_away_id,
                datetime(2026, 10, 10, 15, tzinfo=UTC),
                observed_at,
            ),
        )

    sync._store_fixtures([fixture], api_snapshot, observed_at)
    created = sync.refresh_forecasts(observed_at)

    with connection.cursor() as cursor:
        stored_fixture = cursor.execute(
            """
            SELECT home_team_id, away_team_id, forecast_availability
            FROM football.product_fixtures WHERE fixture_id = %s
            """,
            (fixture_id,),
        ).fetchone()
        aliases = cursor.execute(
            """
            SELECT provider_team_id, team_id
            FROM football.product_team_aliases
            WHERE provider_code = 'api_football' AND provider_team_id IN ('1001', '1002')
            ORDER BY provider_team_id
            """
        ).fetchall()
        active_mappings = cursor.execute(
            """
            SELECT mapping.provider_team_id, mapping.team_id
            FROM football.team_provider_mappings mapping
            JOIN football.providers provider ON provider.id = mapping.provider_id
            WHERE provider.code = 'api_football'
              AND mapping.provider_team_id IN ('1001', '1002')
              AND mapping.valid_to IS NULL
            ORDER BY mapping.provider_team_id
            """
        ).fetchall()
        closed_mappings = cursor.execute(
            """
            SELECT mapping.provider_team_id, mapping.team_id, mapping.valid_to
            FROM football.team_provider_mappings mapping
            JOIN football.providers provider ON provider.id = mapping.provider_id
            WHERE provider.code = 'api_football'
              AND mapping.provider_team_id IN ('1001', '1002')
              AND mapping.valid_to IS NOT NULL
            ORDER BY mapping.provider_team_id
            """
        ).fetchall()

    assert created == 1
    assert stored_fixture == (
        canonical_home_id,
        canonical_away_id,
        "FORECAST_AVAILABLE",
    )
    assert aliases == [("1001", canonical_home_id), ("1002", canonical_away_id)]
    assert active_mappings == [("1001", canonical_home_id), ("1002", canonical_away_id)]
    assert closed_mappings == [
        ("1001", duplicate_home_id, observed_at),
        ("1002", duplicate_away_id, observed_at),
    ]


def test_fixture_sync_preserves_alias_when_historical_identity_is_ambiguous(
    connection: Connection[Any], tmp_path: Path
) -> None:
    observed_at = datetime(2026, 10, 3, 6, tzinfo=UTC)
    sync = ProductSync(
        connection,
        ApiFootballClient("test"),
        tmp_path,
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    )
    snapshot_id = sync._record_response(
        "fixtures-2026-10-10",
        ApiResponse("/fixtures", observed_at, b"{}", (), None),
    )
    competition_id = sync._competition_id("999001", snapshot_id)
    season_id = stable_id("season", competition_id, 2026)
    sync._ensure_season(competition_id, season_id)

    duplicate_id = stable_id("team", "api_football", "2001")
    candidate_ids = (
        stable_id("team", "openfootball", "shared-club-a"),
        stable_id("team", "football_data_uk", "shared-club-b"),
    )
    opponent_id = stable_id("team", "test", "opponent")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.product_competitions (
                competition_id, name, country, continent, division, competition_type,
                season_label, fixtures_available, results_available, standings_available,
                h2h_available, forecast_available, xg_available, team_stats_available,
                availability_status, source_roles, updated_at
            ) VALUES (
                %s, 'Identity Test League', 'England', 'Europe', 1, 'LEAGUE', '2026',
                true, true, false, false, false, false, false,
                'NOT_ENOUGH_HISTORY', '{}'::jsonb, %s
            )
            """,
            (competition_id, observed_at),
        )
        for team_id, name in (
            (duplicate_id, "Shared Club"),
            (candidate_ids[0], "Shared Club A"),
            (candidate_ids[1], "Shared Club B"),
            (opponent_id, "Opponent"),
        ):
            cursor.execute(
                "INSERT INTO football.teams (id, entity_kind) VALUES (%s, 'club')",
                (team_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.product_teams (team_id, name, country, updated_at)
                VALUES (%s, %s, 'England', %s)
                """,
                (team_id, name, observed_at),
            )
        cursor.execute(
            """
            INSERT INTO football.product_team_aliases (
                provider_code, provider_team_id, normalized_name, country, team_id
            ) VALUES
                ('api_football', '2001', 'shared club', 'England', %s),
                ('openfootball', 'shared-club-a', 'shared club', 'England', %s),
                ('football_data_uk', 'shared-club-b', 'shared club', 'England', %s)
            """,
            (duplicate_id, candidate_ids[0], candidate_ids[1]),
        )
        for index, candidate_id in enumerate(candidate_ids):
            match_id = stable_id("ambiguous-history", index)
            cursor.execute(
                """
                INSERT INTO football.matches (id, competition_id, season_id)
                VALUES (%s, %s, %s)
                """,
                (match_id, competition_id, season_id),
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_match_history (
                    fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                    home_goals, away_goals, source_provider_code, source_snapshot_id,
                    source_kickoff_precision
                ) VALUES (%s, %s, %s, %s, %s, 1, 0, 'api_football', %s, 'EXACT')
                """,
                (
                    match_id,
                    competition_id,
                    candidate_id,
                    opponent_id,
                    datetime(2026, 9, index + 1, 12, tzinfo=UTC),
                    snapshot_id,
                ),
            )

    resolved = sync._team_id(
        {"id": 2001, "name": "Shared Club", "logo": None},
        "England",
        competition_id,
        snapshot_id,
        observed_at,
    )

    with connection.cursor() as cursor:
        alias_team_id = _first(
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = 'api_football' AND provider_team_id = '2001'
                """
            ).fetchone()
        )

    assert resolved == duplicate_id
    assert alias_team_id == duplicate_id


def test_fixture_sync_creates_new_season_for_existing_competition(
    connection: Connection[Any], tmp_path: Path
) -> None:
    observed_at = datetime(2026, 10, 3, 6, tzinfo=UTC)
    sync = ProductSync(
        connection,
        ApiFootballClient("test"),
        tmp_path,
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    )
    snapshot_id = sync._record_response(
        "fixtures-2026-10-03",
        ApiResponse("/fixtures", observed_at, b"{}", (), None),
    )
    provider_competition_id = 987654
    competition_id = sync._competition_id(str(provider_competition_id), snapshot_id)
    old_season_id = stable_id("season", competition_id, 2025)
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO football.seasons (id, competition_id) VALUES (%s, %s)",
            (old_season_id, competition_id),
        )
        cursor.execute(
            """
            INSERT INTO football.product_competitions (
                competition_id, name, country, continent, division, competition_type,
                season_label, fixtures_available, results_available, standings_available,
                h2h_available, forecast_available, xg_available, team_stats_available,
                availability_status, source_roles, updated_at
            ) VALUES (
                %s, 'Premier League', 'England', 'Europe', 1, 'LEAGUE', '2025',
                true, true, true, false, false, false, false,
                'NOT_ENOUGH_HISTORY', '{}'::jsonb, %s
            )
            """,
            (competition_id, observed_at),
        )

    fixture = {
        "fixture": {
            "id": 1001,
            "date": "2026-10-03T15:00:00+00:00",
            "status": {"short": "NS"},
            "venue": {"name": "Test Ground"},
        },
        "league": {
            "id": provider_competition_id,
            "name": "Premier League",
            "country": "England",
            "season": 2026,
            "round": "Regular Season - 1",
        },
        "teams": {
            "home": {"id": 1, "name": "Home FC", "logo": None},
            "away": {"id": 2, "name": "Away FC", "logo": None},
        },
        "goals": {"home": None, "away": None},
    }
    fixtures = sync._store_fixtures([fixture], snapshot_id, observed_at)
    corrected_fixture = {
        **fixture,
        "fixture": {
            **fixture["fixture"],
            "date": "2026-10-03T16:00:00+00:00",
            "status": {"short": "FT"},
        },
        "goals": {"home": 2, "away": 1},
    }
    sync._store_fixtures([corrected_fixture], snapshot_id, observed_at)

    new_season_id = stable_id("season", competition_id, 2026)
    with connection.cursor() as cursor:
        stored_season = cursor.execute(
            "SELECT competition_id FROM football.seasons WHERE id = %s",
            (new_season_id,),
        ).fetchone()
        stored_fixtures = cursor.execute(
            """
            SELECT kickoff_at, status, home_score, away_score
            FROM football.product_fixtures
            WHERE competition_id = %s
            """,
            (competition_id,),
        ).fetchall()

    assert len(fixtures) == 1
    assert stored_season == (competition_id,)
    assert stored_fixtures == [(datetime(2026, 10, 3, 16, tzinfo=UTC), "FINISHED", 2, 1)]


def test_fixture_sync_accepts_successful_empty_provider_response(
    connection: Connection[Any], tmp_path: Path
) -> None:
    client = ApiFootballClient(
        "test",
        transport=lambda _url, _headers: b'{"errors":{},"response":[]}',
    )
    sync = ProductSync(
        connection,
        client,
        tmp_path,
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    )

    fixture_count, league_seasons = sync._store_requested_fixtures(date(2026, 10, 3))

    assert fixture_count == 0
    assert league_seasons == []


def test_fixture_backfill_uses_provider_neutral_historical_result(
    connection: Connection[Any], tmp_path: Path
) -> None:
    observed_at = datetime(2026, 10, 3, 6, tzinfo=UTC)
    store = HistoricalBackfillStore(
        connection, "football_data_uk", "Football-Data.co.uk", "test-v1"
    )
    snapshot_id = store.ensure_snapshot(
        source_identity="test/result.csv",
        source_revision="c" * 64,
        acquired_at=observed_at,
        manifest_path="football_data_uk/test/result.csv",
    )
    result = HistoricalMatch(
        provider_match_id="test-result-1",
        provider_competition_id="E0",
        competition_name="Premier League",
        country="England",
        division=1,
        season="2026-2027",
        home_team_id="Result Home",
        home_team_name="Result Home",
        away_team_id="Result Away",
        away_team_name="Result Away",
        kickoff_at=datetime(2026, 9, 30, 19, 45, tzinfo=UTC),
        kickoff_precision="EXACT",
        home_goals=2,
        away_goals=1,
        source_path="test/result.csv",
    )
    assert store.import_match(result, snapshot_id, observed_at) == "inserted"
    with connection.cursor() as cursor:
        history = cursor.execute(
            """
            SELECT history.competition_id, history.home_team_id, history.away_team_id,
                   history.kickoff_at, m.season_id
            FROM football.product_team_match_history history
            JOIN football.matches m ON m.id = history.fixture_id
            WHERE history.source_snapshot_id = %s
            """,
            (snapshot_id,),
        ).fetchone()
    assert history is not None
    competition_id, home_id, away_id, kickoff_at, season_id = history
    fixture_id = stable_id("scheduled-before-result", competition_id, home_id, away_id)
    with connection.cursor() as cursor:
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
            (fixture_id, competition_id, home_id, away_id, kickoff_at, observed_at),
        )
    sync = ProductSync(
        connection,
        ApiFootballClient("test"),
        tmp_path,
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    )

    changed = sync.backfill_fixtures_from_history(date(2026, 9, 29), date(2026, 10, 1), observed_at)

    with connection.cursor() as cursor:
        stored = cursor.execute(
            """
            SELECT status, home_score, away_score
            FROM football.product_fixtures WHERE fixture_id = %s
            """,
            (fixture_id,),
        ).fetchone()
        logical_count = _first(
            cursor.execute(
                """
                SELECT count(*) FROM football.product_fixtures
                WHERE competition_id = %s AND home_team_id = %s AND away_team_id = %s
                  AND kickoff_at::date = %s
                """,
                (competition_id, home_id, away_id, kickoff_at.date()),
            ).fetchone()
        )
    assert changed == 1
    assert stored == ("FINISHED", 2, 1)
    assert logical_count == 1

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE football.product_fixtures
            SET home_score = 4, away_score = 4
            WHERE fixture_id = %s
            """,
            (fixture_id,),
        )
    assert (
        sync.backfill_fixtures_from_history(date(2026, 9, 29), date(2026, 10, 1), observed_at) == 0
    )
    with connection.cursor() as cursor:
        preserved = cursor.execute(
            """
            SELECT status, home_score, away_score
            FROM football.product_fixtures WHERE fixture_id = %s
            """,
            (fixture_id,),
        ).fetchone()
    assert preserved == ("FINISHED", 4, 4)


def test_standings_refresh_handles_teams_swapping_positions(
    connection: Connection[Any], tmp_path: Path
) -> None:
    observed_at = datetime(2026, 10, 3, 6, tzinfo=UTC)
    sync = ProductSync(
        connection,
        ApiFootballClient("test"),
        tmp_path,
        PROJECT_ROOT / MODEL_ARTIFACT_PATH,
    )
    snapshot_id = sync._record_response(
        "standings-39-2026",
        ApiResponse("/standings", observed_at, b"{}", (), None),
    )
    competition_id = sync._competition_id("39", snapshot_id)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.product_competitions (
                competition_id, name, country, continent, competition_type,
                season_label, fixtures_available, results_available, standings_available,
                h2h_available, forecast_available, xg_available, team_stats_available,
                availability_status, source_roles, updated_at
            ) VALUES (
                %s, 'Premier League', 'England', 'Europe', 'LEAGUE', '2026',
                true, true, true, false, false, false, false,
                'NOT_ENOUGH_HISTORY', '{}'::jsonb, %s
            )
            """,
            (competition_id, observed_at),
        )
    first_team = sync._team_id(
        {"id": 1, "name": "First FC", "logo": None},
        "England",
        competition_id,
        snapshot_id,
        observed_at,
    )
    second_team = sync._team_id(
        {"id": 2, "name": "Second FC", "logo": None},
        "England",
        competition_id,
        snapshot_id,
        observed_at,
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO football.product_standings (
                competition_id, team_id, position, played, won, drawn, lost,
                goals_for, goals_against, goal_difference, points,
                source_provider_code, updated_at
            ) VALUES (%s, %s, %s, 1, 1, 0, 0, 1, 0, 1, 3, 'api_football', %s)
            """,
            (
                (competition_id, first_team, 1, observed_at),
                (competition_id, second_team, 2, observed_at),
            ),
        )
    rows = (
        {
            "league": {
                "id": 39,
                "country": "England",
                "standings": [
                    [
                        {
                            "rank": 1,
                            "team": {"id": 2, "name": "Second FC", "logo": None},
                            "all": {
                                "played": 2,
                                "win": 2,
                                "draw": 0,
                                "lose": 0,
                                "goals": {"for": 3, "against": 0},
                            },
                            "goalsDiff": 3,
                            "points": 6,
                        },
                        {
                            "rank": 2,
                            "team": {"id": 1, "name": "First FC", "logo": None},
                            "all": {
                                "played": 2,
                                "win": 1,
                                "draw": 0,
                                "lose": 1,
                                "goals": {"for": 1, "against": 1},
                            },
                            "goalsDiff": 0,
                            "points": 3,
                        },
                    ]
                ],
            }
        },
    )

    assert sync._store_standings(rows, snapshot_id, observed_at) == 2
    with connection.cursor() as cursor:
        positions = cursor.execute(
            """
            SELECT team_id, position FROM football.product_standings
            WHERE competition_id = %s ORDER BY position
            """,
            (competition_id,),
        ).fetchall()
    assert positions == [(second_team, 1), (first_team, 2)]
