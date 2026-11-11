"""A result first seen by the dated fixture request must reach qualified history."""

import json
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from football.product.api_football import ApiResponse
from football.product.sync import ProductSync

DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture
def database() -> Iterator[str]:
    from tests.integration.test_team_identity_correction import isolated_database

    with isolated_database() as url:
        yield url


def _row(league: int, offset: int, status: str, home: int | None, away: int | None) -> dict:
    return {
        "fixture": {
            "id": league + 10 + offset,
            "date": f"2026-11-0{offset + 1}T15:00:00+00:00",
            "status": {"short": status},
            "venue": {},
        },
        "league": {"id": league, "name": f"Lane {league}", "country": "England", "season": 2026},
        "teams": {
            "home": {"id": league + 2, "name": f"Home {league}"},
            "away": {"id": league + 3, "name": f"Away {league}"},
        },
        "goals": {"home": home, "away": away},
    }


class _Client:
    def __init__(self, rows: tuple[dict, ...], fetched_at: datetime) -> None:
        self.rows, self.fetched_at = rows, fetched_at

    def fixtures_for_date(self, _requested: date) -> ApiResponse:
        raw = json.dumps({"response": list(self.rows), "at": self.fetched_at.isoformat()}).encode()
        return ApiResponse("/fixtures", self.fetched_at, raw, self.rows, None)


def _history(connection: psycopg.Connection[Any], league: int) -> list[tuple[Any, ...]]:
    return connection.execute(
        """SELECT m.provider_match_id,h.home_goals,h.away_goals,h.source_provider_code,
                  (SELECT count(*) FROM football.product_match_history_decisions d
                   WHERE d.fixture_id=h.fixture_id)
           FROM football.product_team_match_history h
           JOIN football.match_provider_mappings m ON m.match_id=h.fixture_id
           WHERE m.provider_match_id::bigint BETWEEN %s AND %s ORDER BY 1""",
        (league + 10, league + 19),
    ).fetchall()


def test_dated_fixture_request_qualifies_finished_regulation_results(
    database: str, tmp_path: Path
) -> None:
    league = uuid4().int % 1_000_000_000 + 1_000_000_000
    rows = (
        _row(league, 0, "FT", 2, 1),
        _row(league, 1, "NS", None, None),
        _row(league, 2, "AET", 1, 1),
        _row(league, 3, "AWD", 3, 0),
    )
    with psycopg.connect(database) as connection:
        sync = ProductSync(
            connection,
            cast(Any, _Client(rows, datetime(2026, 11, 5, tzinfo=UTC))),
            tmp_path,
            tmp_path / "unused",
        )
        stored, leagues = sync._store_requested_fixtures(date(2026, 11, 1))
        connection.commit()
        assert stored == 4 and leagues == [(league, 2026)]
        # Only the regulation-time result is model-eligible played history. The
        # extra-time and awarded rows stay canonical fixtures without a history row.
        assert _history(connection, league) == [(str(league + 10), 2, 1, "api_football", 1)]

        # Replaying the same source rows converges.
        sync._store_requested_fixtures(date(2026, 11, 1))
        assert _history(connection, league) == [(str(league + 10), 2, 1, "api_football", 1)]


def test_dated_fixture_request_matches_the_league_history_request(
    database: str, tmp_path: Path
) -> None:
    league = uuid4().int % 1_000_000_000 + 1_000_000_000
    finished = _row(league, 0, "FT", 0, 3)
    fetched_at = datetime(2026, 11, 5, tzinfo=UTC)
    with psycopg.connect(database) as connection:
        sync = ProductSync(
            connection, cast(Any, _Client((finished,), fetched_at)), tmp_path, tmp_path / "unused"
        )
        with connection.transaction(force_rollback=True):
            snapshot = sync._record_response(
                f"history-{league}-2026",
                ApiResponse("/fixtures", fetched_at, b'{"response":["h"]}', (finished,), None),
            )
            sync._store_history((finished,), snapshot, fetched_at)
            expected = [row[:4] for row in _history(connection, league)]
        assert expected == [(str(league + 10), 0, 3, "api_football")]
        sync._store_requested_fixtures(date(2026, 11, 1))
        assert [row[:4] for row in _history(connection, league)] == expected


def test_same_provider_score_correction_reaches_history_without_rewriting_the_past(
    database: str, tmp_path: Path
) -> None:
    league = uuid4().int % 1_000_000_000 + 1_000_000_000
    with psycopg.connect(database) as connection:
        first = ProductSync(
            connection,
            cast(Any, _Client((_row(league, 0, "FT", 1, 0),), datetime(2026, 11, 2, tzinfo=UTC))),
            tmp_path,
            tmp_path / "unused",
        )
        first._store_requested_fixtures(date(2026, 11, 1))
        connection.commit()
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        corrected = ProductSync(
            connection,
            cast(Any, _Client((_row(league, 0, "FT", 1, 1),), datetime(2026, 11, 3, tzinfo=UTC))),
            tmp_path,
            tmp_path / "unused",
        )
        corrected._store_requested_fixtures(date(2026, 11, 1))
        connection.commit()
        assert _history(connection, league) == [(str(league + 10), 1, 1, "api_football", 2)]
        decisions = connection.execute(
            """SELECT d.home_goals,d.away_goals,d.decided_at<=%s
               FROM football.product_match_history_decisions d
               JOIN football.match_provider_mappings m ON m.match_id=d.fixture_id
               WHERE m.provider_match_id=%s ORDER BY d.decided_at,d.decision_id""",
            (before, str(league + 10)),
        ).fetchall()
        assert decisions == [(1, 0, True), (1, 1, False)]
