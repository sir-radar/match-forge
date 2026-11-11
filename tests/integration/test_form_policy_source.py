"""The SQL form source, the independent audit path and served reports agree."""

import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from football.product.form import competition_scope
from football.product.integrity_audit import official_inputs, run

from tests.integration.test_live_context import (
    AWAY,
    COMPETITION,
    FIXTURE,
    HOME,
    KICKOFF,
    OBSERVED,
    SEASON,
    SNAPSHOT,
    _insert_forecast,
    _seed_fixture,
)
from tests.integration.test_public_reports import build
from tests.integration.test_team_identity_correction import isolated_database

CUP = UUID(int=8200)
OTHER = UUID(int=8201)
CUP_SEASON = UUID(int=8202)


def _fixture(
    connection: psycopg.Connection[Any],
    number: int,
    days: int,
    status: str,
    score: tuple[int, int] | None,
    *,
    home: UUID = HOME,
    away: UUID = OTHER,
    competition: UUID = COMPETITION,
    basis: str = "REGULATION_90",
) -> UUID:
    fixture = UUID(int=8300 + number)
    season = SEASON if competition == COMPETITION else CUP_SEASON
    connection.execute(
        "INSERT INTO football.matches (id,competition_id,season_id) VALUES (%s,%s,%s)",
        (fixture, competition, season),
    )
    connection.execute(
        """INSERT INTO football.product_fixtures
           (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,
            home_score,away_score,result_score_basis,forecast_availability,updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'NOT_ENOUGH_HISTORY',
                   clock_timestamp())""",
        (
            fixture,
            competition,
            home,
            away,
            KICKOFF - timedelta(days=days),
            status,
            *(score or (None, None)),
            basis if score else "UNKNOWN",
        ),
    )
    return fixture


@pytest.fixture
def database() -> Iterator[str]:
    with isolated_database() as url:
        with psycopg.connect(url) as connection:
            _seed_fixture(connection)
            connection.execute("INSERT INTO football.competitions (id) VALUES (%s)", (CUP,))
            connection.execute(
                "INSERT INTO football.seasons (id,competition_id) VALUES (%s,%s)",
                (CUP_SEASON, CUP),
            )
            connection.execute(
                """INSERT INTO football.product_competitions
                   (competition_id,name,country,continent,competition_type,season_label,
                    availability_status,source_roles,updated_at)
                   VALUES (%s,'Club Friendlies','Test','Other','CUP','2030',
                    'NOT_ENOUGH_HISTORY','{}'::jsonb,now())""",
                (CUP,),
            )
            connection.execute("INSERT INTO football.teams (id) VALUES (%s)", (OTHER,))
            connection.execute(
                "INSERT INTO football.product_teams (team_id,name,updated_at) "
                "VALUES (%s,'Other',now())",
                (OTHER,),
            )
            _fixture(connection, 1, 3, "FINISHED", (2, 1))
            _fixture(connection, 2, 6, "AWARDED", (0, 3), home=OTHER, away=HOME, basis="UNKNOWN")
            _fixture(connection, 3, 9, "FINISHED", (1, 1), basis="PENALTY_SHOOTOUT")
            _fixture(connection, 4, 12, "FINISHED", (0, 4), competition=CUP)
            _fixture(connection, 5, 2, "SCHEDULED", None, home=AWAY)
            _fixture(connection, 6, 15, "CANCELLED", None)
        yield url


def _v2(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    value = connection.execute("SELECT football.public_context_source_v2(%s)", (FIXTURE,))
    row = value.fetchone()
    assert row is not None
    return dict(row[0])


def test_sql_source_and_audit_select_the_same_official_inputs(database: str) -> None:
    with psycopg.connect(database) as connection:
        sql = _v2(connection)
        base = connection.execute(
            "SELECT football.public_context_source(%s)", (FIXTURE,)
        ).fetchone()[0]
        cutoff = connection.execute("SELECT statement_timestamp()").fetchone()[0]
        independent = official_inputs(connection, base, cutoff)
    assert {key: sql[key] for key in base} == base

    def key(rows: list[dict[str, Any]]) -> list[tuple[str, str, int, int]]:
        return sorted(
            (row["fixture_id"], row["status"], row["home_goals"], row["away_goals"]) for row in rows
        )

    assert key(sql["results"]) == key(independent["results"])
    assert len(sql["results"]) == 4
    assert sorted(row["fixture_id"] for row in sql["pending_results"]) == sorted(
        row["fixture_id"] for row in independent["pending_results"]
    )
    assert [row["team_id"] for row in sql["pending_results"]] == [str(AWAY)]
    assert sql["competition_scopes"] == independent["competition_scopes"]
    assert sql["competition_scopes"][str(CUP)] == "FRIENDLY"


@pytest.mark.parametrize(
    ("competition_type", "name"),
    [
        ("CUP", "Friendlies Clubs"),
        ("UNKNOWN", "Club Friendlies"),
        ("LEAGUE", "Premier League"),
        ("CUP", "Cup"),
        ("UNKNOWN", "Mystery Trophy"),
        ("LEAGUE", "Friendship League"),
    ],
)
def test_competition_scope_sql_and_python_agree(
    database: str, competition_type: str, name: str
) -> None:
    with psycopg.connect(database) as connection:
        row = connection.execute(
            "SELECT football.product_competition_scope(%s,%s)", (competition_type, name)
        ).fetchone()
    assert row == (competition_scope(competition_type, name),)


def test_served_report_uses_the_official_default_window(database: str) -> None:
    assert build(database, "CONTEXT", FIXTURE)["published"] == 1
    with psycopg.connect(database) as connection:
        report = json.loads(
            bytes(
                connection.execute(
                    "SELECT record_bytes FROM football.product_read_reports WHERE scope_id=%s",
                    (FIXTURE,),
                ).fetchone()[0]
            )
        )
    assert (
        "".join(row["result"] for row in report["home_form"]) == "WWD"
    )  # awarded 0-3 away win; shootout is a draw; friendly excluded
    assert [row["result_class"] for row in report["home_form"]] == ["PLAYED", "AWARDED", "PLAYED"]
    home = report["form"]["home"]["windows"]
    assert home["OFFICIAL_ALL_5"]["coverage"] == "PARTIAL"
    assert "UNQUALIFIED_RESULT" in home["OFFICIAL_ALL_5"]["flags"]
    assert home["FORECAST_ELIGIBLE_ALL_5"]["fixture_ids"] == []
    assert "RESULT_PENDING" in report["form"]["away"]["windows"]["OFFICIAL_ALL_5"]["flags"]


def test_result_change_refreshes_later_context_only(database: str) -> None:
    with psycopg.connect(database) as connection:
        connection.execute("DELETE FROM football.product_context_report_refresh_work")
        connection.execute(
            "UPDATE football.product_fixtures SET home_score=3 WHERE fixture_id=%s",
            (UUID(int=8301),),
        )
        refreshed = {
            row[0]
            for row in connection.execute(
                "SELECT fixture_id FROM football.product_context_report_refresh_work"
            ).fetchall()
        }
    assert FIXTURE in refreshed
    assert UUID(int=8304) not in refreshed  # kicked off before the changed result


def test_audit_is_read_only_resumable_and_matches_served_form(
    database: str, tmp_path: Path
) -> None:
    assert build(database, "CONTEXT", FIXTURE)["published"] == 1
    with psycopg.connect(database) as connection:
        before = connection.execute(
            "SELECT count(*), max(registered_at) FROM football.product_read_reports"
        ).fetchone()
    first = run(database, tmp_path, batch_size=1, time_limit=600, max_batches=0)
    assert first["audited_fixtures"] == 0 and not first["complete"]
    summary = run(database, tmp_path, batch_size=1, time_limit=600, max_batches=None)
    assert summary["complete"] and summary["audited_fixtures"] == 1
    assert summary["form_sides"]["MATCHING"] == 2
    # The report is built from the v2 source and serves an awarded, not yet
    # eligible result; it must count as current and traceable.
    assert summary["form_sides"]["report_current"] == 1
    assert summary["form_sides"]["report_source_v2"] == 1
    assert summary["form_sides"]["served_untraceable"] == 0
    assert summary["population"]["context_fixtures"] == 1
    assert "standings" in summary["corpus"]["not_audited"]
    with psycopg.connect(database) as connection:
        after = connection.execute(
            "SELECT count(*), max(registered_at) FROM football.product_read_reports"
        ).fetchone()
    assert before == after


def test_league_coverage_lists_absent_pairings_only_for_near_complete_seasons(
    database: str,
) -> None:
    from football.product.integrity_audit import league_coverage

    extra = UUID(int=8210)
    with psycopg.connect(database) as connection:
        connection.execute("INSERT INTO football.teams (id) VALUES (%s)", (extra,))
        connection.execute(
            "INSERT INTO football.product_teams (team_id,name,updated_at) "
            "VALUES (%s,'Extra',now())",
            (extra,),
        )
        connection.execute(
            """UPDATE football.product_fixtures SET status='CANCELLED',home_score=NULL,
               away_score=NULL WHERE competition_id=%s AND fixture_id<>%s""",
            (COMPETITION, FIXTURE),
        )
        teams = (HOME, AWAY, OTHER, extra)
        number = 20
        for home in teams:
            for away in teams:
                if home == away or (home, away) in ((HOME, AWAY), (OTHER, extra)):
                    continue
                number += 1
                _fixture(connection, number, number, "FINISHED", (1, 0), home=home, away=away)
        summary, records = league_coverage(connection)
    season = next(row for row in records if row["competition_id"] == str(COMPETITION))
    # HOME v AWAY exists as the scheduled target; OTHER v Extra is absent.
    assert season["state"] == "CANDIDATE_MISSING_MATCHES"
    assert season["missing_pairings"] == [[str(OTHER), str(extra)]]
    assert summary["candidate_missing_matches"] == 1


def test_affected_forecasts_count_only_results_known_before_the_cutoff(database: str) -> None:
    from uuid import uuid4

    from football.product.integrity_audit import affected_forecasts

    forecast = uuid4()
    with psycopg.connect(database) as connection:
        _insert_forecast(connection, forecast, "a" * 64, "b" * 64)
        start = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        for number, known in (
            (1, OBSERVED - timedelta(days=1)),
            (3, OBSERVED + timedelta(hours=1)),
        ):
            connection.execute(
                """INSERT INTO football.product_match_history_decisions
                   (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,home_goals,
                    away_goals,source_provider_code,source_snapshot_id,source_kickoff_precision,
                    eligible,reason,source_known_at)
                   SELECT fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,
                          home_score,away_score,'live_context_test',%s,'EXACT',true,
                          'synthetic requalification',%s
                   FROM football.product_fixtures WHERE fixture_id=%s""",
                (SNAPSHOT, known, UUID(int=8300 + number)),
            )
        rows = affected_forecasts(connection, start)
    assert [(row["forecast_id"], row["missing_results"]) for row in rows] == [(str(forecast), 1)]
    assert rows[0]["missing_fixture_ids"] == [str(UUID(int=8301))]
