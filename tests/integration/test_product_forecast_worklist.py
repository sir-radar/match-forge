import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
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
