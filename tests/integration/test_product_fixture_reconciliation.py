from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.history.fixture_identity import (
    audit_canonical_history,
    load_canonical_history,
    persist_resolutions,
)
from football.product.api_football import ApiFootballClient, ApiResponse
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.football_data_org import FootballDataResponse
from football.product.identity_admission import admit_provider_mappings
from football.product.sync import ProductSync


@pytest.mark.parametrize(
    "mismatch",
    [
        None,
        "kickoff",
        "score",
        "team",
        "history",
        "HALF_TIME",
        "INTERRUPTED",
        "SUSPENDED",
        "AWARDED",
    ],
)
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
            "duplicates-test",
            ApiResponse(
                "/fixtures",
                now,
                json.dumps(
                    {"league": {"id": 39}, "teams": {"home": {"id": 40}, "away": {"id": 50}}}
                ).encode(),
                (),
                None,
            ),
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
        response = FootballDataResponse(
            "/matches",
            now,
            json.dumps(
                {
                    "competition": {"code": "PL"},
                    "homeTeam": {"id": 64},
                    "awayTeam": {"id": 999 if mismatch == "team" else 65},
                }
            ).encode(),
            (),
        )
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
        admit_provider_mappings(connection, tmp_path, "api_football")
        admit_provider_mappings(connection, tmp_path, "football_data_org")
        with connection.cursor() as cursor:
            if mismatch in ("HALF_TIME", "INTERRUPTED", "SUSPENDED", "AWARDED"):
                cursor.execute(
                    "UPDATE football.product_fixtures SET status = %s WHERE updated_at = %s",
                    (mismatch, now),
                )
            if mismatch == "history":
                cursor.execute(
                    """UPDATE football.product_fixtures SET status = 'FINISHED',
                       home_score = 0, away_score = 0 WHERE updated_at = %s""",
                    (now,),
                )
                cursor.execute(
                    """INSERT INTO football.product_team_match_history (
                       fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,
                       home_goals,away_goals,source_provider_code,source_snapshot_id)
                       SELECT fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,
                              0,0,'api_football',%s FROM football.product_fixtures
                       WHERE updated_at = %s""",
                    (snapshot, now),
                )
                persist_resolutions(
                    connection,
                    audit_canonical_history(load_canonical_history(connection)).identities,
                    now,
                )
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
        expected = 0 if mismatch in ("kickoff", "score", "team") else 1
        assert reconcile_product_fixtures(connection) == expected
        assert reconcile_product_fixtures(connection) == expected
        persist_resolutions(
            connection,
            audit_canonical_history(load_canonical_history(connection)).identities,
            now,
        )
        with connection.cursor() as cursor:
            active = cursor.execute(
                """SELECT count(*) FROM football.fixture_identity_resolutions
                           WHERE active AND member_fixture_id <> representative_fixture_id
                             AND member_fixture_id IN (
                               SELECT mapping.match_id FROM football.match_provider_mappings mapping
                               JOIN football.providers provider ON provider.id = mapping.provider_id
                               WHERE (provider.code, mapping.provider_match_id) IN (
                                   ('api_football', '1557424'),
                                   ('football_data_org', '560598')) )"""
            ).fetchone()
            rows = cursor.execute(
                """SELECT count(DISTINCT mapping.match_id)
                   FROM football.match_provider_mappings mapping
                   JOIN football.providers provider ON provider.id = mapping.provider_id
                   WHERE (provider.code, mapping.provider_match_id) IN (
                       ('api_football', '1557424'),
                       ('football_data_org', '560598'))"""
            ).fetchone()
            if mismatch == "history":
                assert cursor.execute(
                    """SELECT count(*) FROM football.product_eligible_match_history
                       WHERE source_snapshot_id = %s""",
                    (snapshot,),
                ).fetchone() == (1,)
                assert cursor.execute(
                    """SELECT count(*) FROM football.product_team_match_history
                       WHERE source_snapshot_id = %s""",
                    (snapshot,),
                ).fetchone() == (1,)
        assert active == (expected,)
        assert rows == (2,)
