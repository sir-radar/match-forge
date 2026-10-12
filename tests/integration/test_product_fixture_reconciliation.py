from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.history.fixture_identity import persist_resolutions
from football.product.api_football import ApiFootballClient, ApiResponse
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.football_data_org import FootballDataResponse
from football.product.sync import ProductSync


@pytest.mark.parametrize("mismatch", [None, "kickoff", "score", "team"])
def test_explicit_crosswalk_resolves_only_verified_fixture_pairs(
    tmp_path: Path, mismatch: str | None
) -> None:
    now = datetime(2026, 10, 11, 6, tzinfo=UTC)
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection,
        connection.transaction(force_rollback=True),
    ):
        sync = ProductSync(connection, ApiFootballClient("test"), tmp_path, tmp_path / "model")
        snapshot = sync._record_response(
            "duplicates-test", ApiResponse("/fixtures", now, b"{}", (), None)
        )
        sync._store_competitions(
            [
                {
                    "league": {"id": 39, "name": "Premier League", "type": "League"},
                    "country": {"name": "England"},
                    "seasons": [{"year": 2026, "current": True}],
                }
            ],
            snapshot,
            now,
        )
        fixture: dict[str, Any] = {
            "fixture": {
                "id": 1557424,
                "date": "2026-10-11T15:30:00+00:00",
                "status": {"short": "NS"},
                "venue": {"name": None},
            },
            "league": {"id": 39, "season": 2026, "country": "England", "round": "1"},
            "teams": {
                "home": {"id": 40, "name": "Liverpool", "logo": None},
                "away": {"id": 50, "name": "Manchester City", "logo": None},
            },
            "goals": {"home": None, "away": None},
        }
        sync._store_fixtures([fixture], snapshot, now)
        response = FootballDataResponse("/matches", now, b'{"test":"fallback"}', ())
        fallback_snapshot = sync._record_fallback_response("duplicates-fallback-test", response)
        sync._store_fallback_fixtures(
            [
                {
                    "id": 560598,
                    "competition": {"code": "PL"},
                    "utcDate": fixture["fixture"]["date"],
                    "status": "SCHEDULED",
                    "homeTeam": {"id": 64, "name": "Liverpool FC"},
                    "awayTeam": {
                        "id": 999 if mismatch == "team" else 65,
                        "name": "Manchester City FC",
                    },
                    "score": {"fullTime": {"home": None, "away": None}},
                }
            ],
            fallback_snapshot,
            now - timedelta(days=1),
        )
        with connection.cursor() as cursor:
            if mismatch == "kickoff":
                cursor.execute(
                    """UPDATE football.product_fixtures
                           SET kickoff_at = kickoff_at + interval '1 hour'
                           WHERE updated_at = %s""",
                    (now - timedelta(days=1),),
                )
            if mismatch == "score":
                cursor.execute(
                    """UPDATE football.product_fixtures
                           SET status='LIVE', home_score=1, away_score=0 WHERE updated_at = %s""",
                    (now,),
                )
                cursor.execute(
                    """UPDATE football.product_fixtures
                           SET status='LIVE', home_score=2, away_score=0 WHERE updated_at = %s""",
                    (now - timedelta(days=1),),
                )
        assert reconcile_product_fixtures(connection) == (1 if mismatch is None else 0)
        assert reconcile_product_fixtures(connection) == (1 if mismatch is None else 0)
        persist_resolutions(connection, [], now)
        with connection.cursor() as cursor:
            active = cursor.execute(
                """SELECT count(*) FROM football.fixture_identity_resolutions
                       WHERE active AND member_fixture_id <> representative_fixture_id"""
            ).fetchone()
            rows = cursor.execute("SELECT count(*) FROM football.product_fixtures").fetchone()
        assert active == (1 if mismatch is None else 0,)
        assert rows == (2,)
