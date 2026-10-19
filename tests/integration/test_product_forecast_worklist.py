import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from football.forecasting.pitchapi_v3 import TransferableParametersV1
from football.product.api_football import ApiFootballClient
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.sync import ProductSync
from psycopg.errors import LockNotAvailable


def test_refresh_claim_serializes_fixture_changes_without_losing_new_work(tmp_path: Path) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    competition, season, home, away, fixture = [uuid4() for _ in range(5)]
    with psycopg.connect(database_url, autocommit=True) as owner:
        with owner.transaction():
            owner.execute("INSERT INTO football.competitions (id) VALUES (%s)", (competition,))
            owner.execute(
                "INSERT INTO football.seasons (id, competition_id) VALUES (%s,%s)",
                (season, competition),
            )
            owner.execute("INSERT INTO football.teams (id) VALUES (%s),(%s)", (home, away))
            owner.execute(
                """INSERT INTO football.product_competitions (
                       competition_id,name,country,continent,competition_type,season_label,
                       availability_status,source_roles,updated_at)
                   VALUES (%s,'Refresh test','England','Europe','LEAGUE','2026',
                           'NOT_ENOUGH_HISTORY','{}',clock_timestamp())""",
                (competition,),
            )
            owner.execute(
                """INSERT INTO football.product_teams (team_id,name,updated_at)
                   VALUES (%s,'Home',clock_timestamp()),(%s,'Away',clock_timestamp())""",
                (home, away),
            )
            owner.execute(
                "INSERT INTO football.matches (id,competition_id,season_id) VALUES (%s,%s,%s)",
                (fixture, competition, season),
            )
            owner.execute(
                """INSERT INTO football.product_fixtures (
                       fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,
                       status,forecast_availability,updated_at)
                   VALUES (%s,%s,%s,%s,clock_timestamp()+interval '2 days','SCHEDULED',
                           'NOT_ENOUGH_HISTORY',clock_timestamp())""",
                (fixture, competition, home, away),
            )
        try:
            with psycopg.connect(database_url) as first, psycopg.connect(database_url) as second:
                first_product = ProductSync(
                    first, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH
                )
                second_product = ProductSync(
                    second, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH
                )
                assert first_product.refresh_pending_forecasts()["fixtures_processed"] == 1
                assert second_product.refresh_pending_forecasts()["fixtures_processed"] == 0
                second.rollback()
                owner.execute("SET lock_timeout = '100ms'")
                with pytest.raises(LockNotAvailable):
                    owner.execute(
                        """UPDATE football.product_fixtures
                           SET kickoff_at = kickoff_at + interval '1 hour' WHERE fixture_id = %s""",
                        (fixture,),
                    )
                first.commit()
                owner.execute("SET lock_timeout = 0")
                owner.execute(
                    """UPDATE football.product_fixtures
                       SET kickoff_at = kickoff_at + interval '1 hour' WHERE fixture_id = %s""",
                    (fixture,),
                )
                assert owner.execute(
                    """SELECT generation > completed_generation
                       FROM football.product_forecast_refresh_work WHERE fixture_id = %s""",
                    (fixture,),
                ).fetchone() == (True,)
                assert second_product.refresh_pending_forecasts()["fixtures_processed"] == 1
                second.commit()
        finally:
            owner.execute("SET lock_timeout = 0")
            with owner.transaction():
                owner.execute(
                    "DELETE FROM football.product_forecast_refresh_work WHERE fixture_id = %s",
                    (fixture,),
                )
                owner.execute(
                    "DELETE FROM football.product_fixtures WHERE fixture_id = %s", (fixture,)
                )
                owner.execute("DELETE FROM football.matches WHERE id = %s", (fixture,))
                owner.execute(
                    "DELETE FROM football.product_teams WHERE team_id IN (%s,%s)", (home, away)
                )
                owner.execute("DELETE FROM football.teams WHERE id IN (%s,%s)", (home, away))
                owner.execute(
                    "DELETE FROM football.product_competitions WHERE competition_id = %s",
                    (competition,),
                )
                owner.execute("DELETE FROM football.seasons WHERE id = %s", (season,))
                owner.execute("DELETE FROM football.competitions WHERE id = %s", (competition,))


@contextmanager
def _forecast_fixture(
    database_url: str, *, cleanup: bool = True
) -> Iterator[tuple[UUID, UUID, UUID, UUID]]:
    """Disable row cleanup only inside a disposable database that retains publications."""
    with psycopg.connect(database_url, autocommit=True) as owner:
        with owner.transaction():
            competition, home, away, season = owner.execute(
                """WITH c AS (INSERT INTO football.competitions DEFAULT VALUES RETURNING id),
                   h AS (INSERT INTO football.teams DEFAULT VALUES RETURNING id),
                   a AS (INSERT INTO football.teams DEFAULT VALUES RETURNING id),
                   s AS (INSERT INTO football.seasons(competition_id) SELECT id FROM c RETURNING id)
                   SELECT c.id,h.id,a.id,s.id FROM c,h,a,s"""
            ).fetchone()
            owner.execute(
                """INSERT INTO football.product_competitions(competition_id,name,country,
                       continent,competition_type,season_label,availability_status,
                       source_roles,updated_at)
                   VALUES(%s,'Concurrent refresh','England','Europe','LEAGUE','2026',
                          'NOT_ENOUGH_HISTORY','{}',clock_timestamp())""",
                (competition,),
            )
            owner.execute(
                """INSERT INTO football.product_teams(team_id,name,updated_at)
                   VALUES(%s,'Home',clock_timestamp()),(%s,'Away',clock_timestamp())""",
                (home, away),
            )
            fixture = owner.execute(
                "INSERT INTO football.matches(competition_id,season_id) VALUES(%s,%s) RETURNING id",
                (competition, season),
            ).fetchone()[0]
            owner.execute(
                """INSERT INTO football.product_fixtures(fixture_id,competition_id,
                       home_team_id,away_team_id,kickoff_at,status,forecast_availability,updated_at)
                   VALUES(%s,%s,%s,%s,clock_timestamp()+interval '2 days','SCHEDULED',
                          'NOT_ENOUGH_HISTORY',clock_timestamp())""",
                (fixture, competition, home, away),
            )
        try:
            yield competition, home, away, fixture
        finally:
            if cleanup:
                with owner.transaction():
                    owner.execute(
                        "DELETE FROM football.product_forecast_refresh_work WHERE fixture_id=%s",
                        (fixture,),
                    )
                    owner.execute(
                        "DELETE FROM football.product_fixtures WHERE fixture_id=%s", (fixture,)
                    )
                    owner.execute("DELETE FROM football.matches WHERE id=%s", (fixture,))
                    owner.execute(
                        "DELETE FROM football.product_teams WHERE team_id=ANY(%s)", ([home, away],)
                    )
                    owner.execute("DELETE FROM football.teams WHERE id=ANY(%s)", ([home, away],))
                    owner.execute(
                        "DELETE FROM football.product_competitions WHERE competition_id=%s",
                        (competition,),
                    )
                    owner.execute("DELETE FROM football.seasons WHERE id=%s", (season,))
                    owner.execute("DELETE FROM football.competitions WHERE id=%s", (competition,))


@pytest.mark.parametrize("pending_only", [False, True])
def test_refresh_defers_busy_competition_without_claiming_its_fixture(
    tmp_path: Path, pending_only: bool
) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    with (
        _forecast_fixture(database_url) as (competition, home, away, fixture),
        psycopg.connect(database_url) as busy,
        psycopg.connect(database_url) as worker,
    ):
        busy.execute(
            "SELECT 1 FROM football.product_competitions WHERE competition_id=%s FOR UPDATE",
            (competition,),
        )
        worker.execute("SET statement_timeout='2s'")
        sync = ProductSync(worker, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH)
        if pending_only:
            assert sync.refresh_pending_forecasts()["fixtures_processed"] == 0
        else:
            kickoff = worker.execute(
                "SELECT kickoff_at FROM football.product_fixtures WHERE fixture_id=%s",
                (fixture,),
            ).fetchone()[0]
            parameters = TransferableParametersV1(
                **json.loads(MODEL_ARTIFACT_PATH.read_bytes())["parameters"]
            )
            assert (
                sync._publish_forecast(
                    fixture, home, away, kickoff, datetime.now(UTC), [], "a" * 64, parameters
                )
                == 0
            )
        # The busy writer can still change its fixture: no fixture/competition inversion.
        busy.execute("SET lock_timeout='100ms'")
        busy.execute(
            "UPDATE football.product_fixtures SET updated_at=clock_timestamp() WHERE fixture_id=%s",
            (fixture,),
        )
        busy.rollback()
        worker.commit()
        assert sync.refresh_pending_forecasts()["fixtures_processed"] == 1
        worker.commit()
        assert sync.refresh_pending_forecasts()["fixtures_processed"] == 0


def test_busy_competition_does_not_block_an_independent_forecast_batch(tmp_path: Path) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    with (
        _forecast_fixture(database_url) as (competition, _, _, busy_fixture),
        _forecast_fixture(database_url) as (_, _, _, available_fixture),
        psycopg.connect(database_url) as busy,
        psycopg.connect(database_url) as worker,
    ):
        busy.execute(
            "SELECT 1 FROM football.product_competitions WHERE competition_id=%s FOR UPDATE",
            (competition,),
        )
        worker.execute("SET statement_timeout='2s'")
        sync = ProductSync(worker, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH)
        result = sync.refresh_pending_forecasts()
        assert result["fixtures_processed"] == 1
        assert worker.execute(
            "SELECT generation>completed_generation "
            "FROM football.product_forecast_refresh_work WHERE fixture_id=%s",
            (available_fixture,),
        ).fetchone() == (False,)
        assert worker.execute(
            "SELECT generation>completed_generation "
            "FROM football.product_forecast_refresh_work WHERE fixture_id=%s",
            (busy_fixture,),
        ).fetchone() == (True,)
        worker.commit()
        busy.rollback()
        assert sync.refresh_pending_forecasts()["fixtures_processed"] == 1


def test_limited_refresh_does_not_claim_other_competitions(tmp_path: Path) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    with (
        _forecast_fixture(database_url),
        _forecast_fixture(database_url),
        psycopg.connect(database_url) as first,
        psycopg.connect(database_url) as second,
    ):
        left = ProductSync(first, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH)
        right = ProductSync(second, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH)
        assert left.refresh_pending_forecasts(limit=1)["fixtures_processed"] == 1
        assert right.refresh_pending_forecasts(limit=1)["fixtures_processed"] == 1


def test_refresh_defers_busy_work_without_waiting_while_holding_canonical_rows(
    tmp_path: Path,
) -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    with (
        _forecast_fixture(database_url) as (competition, _, _, fixture),
        psycopg.connect(database_url) as history,
        psycopg.connect(database_url) as worker,
    ):
        history.execute(
            "SELECT 1 FROM football.product_forecast_refresh_work WHERE fixture_id=%s FOR UPDATE",
            (fixture,),
        )
        worker.execute("SET statement_timeout='1s'")
        sync = ProductSync(worker, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH)
        result = sync.refresh_pending_forecasts()
        assert result["fixtures_processed"] == 0
        assert result["fixtures_pending"] == 1
        worker.commit()
        history.execute("SET lock_timeout='100ms'")
        history.execute(
            "UPDATE football.product_competitions SET updated_at=clock_timestamp() "
            "WHERE competition_id=%s",
            (competition,),
        )
        history.commit()
        assert sync.refresh_pending_forecasts()["fixtures_processed"] == 1
        worker.commit()
        assert sync.refresh_pending_forecasts()["fixtures_pending"] == 0
