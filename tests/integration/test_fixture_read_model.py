import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import Connection, sql


@pytest.fixture
def projection() -> Iterator[tuple[Connection[Any], UUID, UUID]]:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection,
        connection.transaction(force_rollback=True),
    ):
        competition, season, home, away, fixture, member = [uuid4() for _ in range(6)]
        connection.execute("INSERT INTO football.competitions(id) VALUES (%s)", (competition,))
        connection.execute(
            "INSERT INTO football.seasons(id,competition_id) VALUES (%s,%s)",
            (season, competition),
        )
        connection.execute("INSERT INTO football.teams(id) VALUES (%s),(%s)", (home, away))
        connection.execute(
            """INSERT INTO football.product_competitions(
            competition_id,name,country,continent,competition_type,season_label,
            availability_status,source_roles,updated_at)
            VALUES (%s,'Projection','England','Europe','LEAGUE','2026',
            'NOT_ENOUGH_HISTORY','{}',clock_timestamp())""",
            (competition,),
        )
        connection.execute(
            """INSERT INTO football.product_teams(team_id,name,updated_at)
            VALUES (%s,'Home',clock_timestamp()),(%s,'Away',clock_timestamp())""",
            (home, away),
        )
        for identity in (fixture, member):
            connection.execute(
                """INSERT INTO football.matches(id,competition_id,season_id)
                VALUES (%s,%s,%s)""",
                (identity, competition, season),
            )
            connection.execute(
                """INSERT INTO football.product_fixtures(
                fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,
                forecast_availability,updated_at)
                VALUES (%s,%s,%s,%s,clock_timestamp()+interval '1 day','SCHEDULED',
                'NOT_ENOUGH_HISTORY',clock_timestamp())""",
                (identity, competition, home, away),
            )
        yield connection, fixture, member


def _refresh(connection: Connection[Any]) -> None:
    connection.execute("REFRESH MATERIALIZED VIEW football.fixture_read_model")


def _rows(connection: Connection[Any], relation: str) -> list[tuple[Any, ...]]:

    return connection.execute(
        sql.SQL("SELECT * FROM football.{} ORDER BY fixture_id").format(sql.Identifier(relation))
    ).fetchall()


def test_unbuilt_projection_is_explicit_and_does_not_replace_serving_baseline(
    projection: tuple[Connection[Any], UUID, UUID],
) -> None:
    connection, fixture, member = projection
    assert connection.execute(
        "SELECT relispopulated FROM pg_class WHERE oid='football.fixture_read_model'::regclass"
    ).fetchone() == (False,)
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), connection.transaction():
        connection.execute("SELECT * FROM football.fixture_read_model")
    assert {fixture, member} <= {row[0] for row in _rows(connection, "product_serving_fixtures")}


def test_rebuild_preserves_baseline_fields_and_is_repeatable(
    projection: tuple[Connection[Any], UUID, UUID],
) -> None:
    connection, _, _ = projection
    baseline = _rows(connection, "product_serving_fixtures")
    _refresh(connection)
    assert _rows(connection, "fixture_read_model") == baseline
    _refresh(connection)
    assert _rows(connection, "fixture_read_model") == baseline


def test_source_change_requires_an_explicit_projection_rebuild(
    projection: tuple[Connection[Any], UUID, UUID],
) -> None:
    connection, fixture, _ = projection
    _refresh(connection)
    old = _rows(connection, "fixture_read_model")
    connection.execute(
        "UPDATE football.product_fixtures SET venue='Changed' WHERE fixture_id=%s", (fixture,)
    )
    assert _rows(connection, "fixture_read_model") == old
    _refresh(connection)
    assert _rows(connection, "fixture_read_model") == _rows(connection, "product_serving_fixtures")
    assert _rows(connection, "fixture_read_model") != old


def test_projection_refresh_rolls_back_atomically(
    projection: tuple[Connection[Any], UUID, UUID],
) -> None:
    connection, fixture, _ = projection
    _refresh(connection)
    before = _rows(connection, "fixture_read_model")
    with connection.transaction(force_rollback=True):
        connection.execute(
            "UPDATE football.product_fixtures SET venue='Rolled back' WHERE fixture_id=%s",
            (fixture,),
        )
        _refresh(connection)
        assert _rows(connection, "fixture_read_model") != before
    assert _rows(connection, "fixture_read_model") == before
    assert _rows(connection, "product_serving_fixtures") == before


def test_proven_duplicate_is_suppressed_without_losing_historical_ids(
    projection: tuple[Connection[Any], UUID, UUID],
) -> None:
    connection, fixture, member = projection
    connection.execute(
        """INSERT INTO football.fixture_identity_resolutions(
        canonical_real_fixture_id,member_fixture_id,representative_fixture_id,
        resolution_status,resolution_reason,evidence_json,evidence_sha256,
        resolution_version,active,created_at)
        VALUES (%s,%s,%s,'DUPLICATE_RESOLVED','Explicit test identity','{}',%s,
        'fixture-projection:test',true,clock_timestamp())""",
        (fixture, member, fixture, "a" * 64),
    )
    _refresh(connection)
    assert [
        row[0] for row in _rows(connection, "fixture_read_model") if row[0] in (fixture, member)
    ] == [fixture]
    assert connection.execute(
        "SELECT fixture_id FROM football.product_fixtures "
        "WHERE fixture_id=ANY(%s) ORDER BY fixture_id",
        ([fixture, member],),
    ).fetchall() == [(identity,) for identity in sorted((fixture, member))]
    assert connection.execute(
        "SELECT id FROM football.matches WHERE id=ANY(%s) ORDER BY id", ([fixture, member],)
    ).fetchall() == [(identity,) for identity in sorted((fixture, member))]


def test_projection_can_be_discarded_and_rebuilt_from_unchanged_source(
    projection: tuple[Connection[Any], UUID, UUID],
) -> None:
    connection, _, _ = projection
    before = _rows(connection, "product_serving_fixtures")
    _refresh(connection)
    connection.execute("REFRESH MATERIALIZED VIEW football.fixture_read_model WITH NO DATA")
    _refresh(connection)
    assert _rows(connection, "fixture_read_model") == before
    assert _rows(connection, "product_serving_fixtures") == before


def test_projection_rows_cannot_be_edited_as_authoritative_facts(
    projection: tuple[Connection[Any], UUID, UUID],
) -> None:
    connection, _, _ = projection
    _refresh(connection)
    with pytest.raises(psycopg.errors.WrongObjectType), connection.transaction():
        connection.execute("UPDATE football.fixture_read_model SET venue='Invented'")
    assert _rows(connection, "fixture_read_model") == _rows(connection, "product_serving_fixtures")
