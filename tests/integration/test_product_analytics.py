from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.product.identity_admission import admit_provider_mappings
from psycopg.types.json import Jsonb

from tests.integration.test_live_context import (
    COMPETITION,
    FIXTURE,
    KICKOFF,
    OBSERVED,
    _insert_forecast,
    _seed_fixture,
)
from tests.integration.test_product_historical_backfill import DATABASE_URL
from tests.integration.test_product_identity_admission import _cutoff, _history


def _revision(
    connection: psycopg.Connection[Any],
    issued_hours: float,
    knowledge_lag_seconds: int = 0,
    *,
    probabilities: dict[str, float] | None = None,
) -> UUID:
    revision = uuid4()
    checksum = revision.hex * 2
    issued = KICKOFF - timedelta(hours=issued_hours)
    connection.execute(
        """INSERT INTO football.product_forecasts (
               forecast_id,semantic_sha256,fixture_id,model_label,model_algorithm_version,
               model_artifact_sha256,created_at,football_cutoff,knowledge_cutoff,knowledge_mode,
               expected_home_goals,expected_away_goals,probabilities,score_matrix,payload_sha256,
               publication_mode,forecast_horizon,predictive_input_snapshot_sha256,
               context_snapshot_sha256,revision_reason_codes,new_information_ids,score_matrix_version)
           SELECT %s,%s,fixture_id,model_label,model_algorithm_version,model_artifact_sha256,
                  %s,%s,%s,knowledge_mode,expected_home_goals,expected_away_goals,
                  %s::jsonb,score_matrix,%s,publication_mode,forecast_horizon,%s,
                  context_snapshot_sha256,revision_reason_codes,new_information_ids,score_matrix_version
           FROM football.product_forecasts WHERE fixture_id=%s LIMIT 1""",
        (
            revision,
            checksum,
            issued,
            issued,
            issued - timedelta(seconds=knowledge_lag_seconds),
            Jsonb(
                probabilities
                if probabilities is not None
                else {
                    "home": 0.6,
                    "draw": 0.2,
                    "away": 0.2,
                    "total_over_2_5": 0.6,
                    "btts_yes": 0.6,
                }
            ),
            checksum,
            checksum,
            FIXTURE,
        ),
    )
    return revision


def _selected(connection: psycopg.Connection[Any], horizon: int = 0) -> list[tuple[object, ...]]:
    return connection.execute(
        """SELECT fixture_id,forecast_id,issued_at,score_matrix_version
           FROM football.product_performance_forecasts(ARRAY[%s::uuid],%s)""",
        (COMPETITION, horizon),
    ).fetchall()


def test_revision_selection_horizon_boundaries_and_immutable_evidence() -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _seed_fixture(connection)
        _insert_forecast(connection, uuid4(), "1" * 64, "2" * 64)
        at_boundary = _revision(connection, 24)
        latest = max(_revision(connection, 1), _revision(connection, 1, knowledge_lag_seconds=1))
        connection.execute(
            "UPDATE football.product_fixtures SET kickoff_at=%s WHERE fixture_id=%s",
            (KICKOFF + timedelta(hours=2), FIXTURE),
        )
        _revision(connection, 0)  # retained revision after an earlier rescheduled kickoff
        _revision(connection, -1)  # legacy post-kickoff row must never qualify
        connection.execute(
            """UPDATE football.product_fixtures SET status='FINISHED',home_score=2,away_score=1,
                      result_score_basis='REGULATION_90',identity_status='VERIFIED',kickoff_at=%s,updated_at=%s
               WHERE fixture_id=%s""",
            (KICKOFF, KICKOFF + timedelta(hours=2), FIXTURE),
        )
        original = connection.execute(
            "SELECT to_jsonb(f) FROM football.product_forecasts f ORDER BY forecast_id"
        ).fetchall()
        assert _selected(connection) == [
            (FIXTURE, latest, KICKOFF - timedelta(hours=1), "legacy-compact-index-v1")
        ]
        assert _selected(connection, 86400)[0][1] == at_boundary
        assert _selected(connection, 86401)[0][2] == OBSERVED
        assert _selected(connection, 90001) == []
        assert (
            connection.execute(
                "SELECT to_jsonb(f) FROM football.product_forecasts f ORDER BY forecast_id"
            ).fetchall()
            == original
        )
        assert connection.execute(
            "SELECT count(*) FROM football.product_forecasts WHERE fixture_id=%s", (FIXTURE,)
        ).fetchone() == (6,)


@pytest.mark.parametrize("basis", ["UNKNOWN", "EXTRA_TIME", "PENALTY_SHOOTOUT"])
def test_incompatible_score_basis_is_excluded(basis: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _seed_fixture(connection)
        _insert_forecast(connection, uuid4(), "3" * 64, "4" * 64)
        connection.execute(
            """UPDATE football.product_fixtures SET status='FINISHED',home_score=2,away_score=1,
               result_score_basis=%s,identity_status='VERIFIED' WHERE fixture_id=%s""",
            (basis, FIXTURE),
        )
        assert _selected(connection) == []


@pytest.mark.parametrize("invalid_cutoff", ["football_cutoff", "knowledge_cutoff"])
def test_forecast_with_future_cutoff_is_excluded(invalid_cutoff: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _seed_fixture(connection)
        _insert_forecast(connection, uuid4(), "5" * 64, "6" * 64)
        # Keep the immutable pre-existing revision and insert an invalid legacy revision.
        issued = KICKOFF - timedelta(hours=1)
        connection.execute(
            """INSERT INTO football.product_forecasts (
               forecast_id,semantic_sha256,fixture_id,model_label,model_algorithm_version,
               model_artifact_sha256,created_at,football_cutoff,knowledge_cutoff,knowledge_mode,
               expected_home_goals,expected_away_goals,probabilities,score_matrix,payload_sha256,
               publication_mode,forecast_horizon,predictive_input_snapshot_sha256,
               context_snapshot_sha256,revision_reason_codes,new_information_ids)
               SELECT uuidv7(),%s,fixture_id,model_label,model_algorithm_version,
                 model_artifact_sha256,%s,%s,%s,knowledge_mode,expected_home_goals,
                 expected_away_goals,probabilities,score_matrix,%s,publication_mode,
                 forecast_horizon,%s,context_snapshot_sha256,revision_reason_codes,new_information_ids
               FROM football.product_forecasts WHERE fixture_id=%s LIMIT 1""",
            (
                "7" * 64,
                issued,
                KICKOFF if invalid_cutoff == "football_cutoff" else issued,
                KICKOFF if invalid_cutoff == "knowledge_cutoff" else issued,
                "8" * 64,
                "9" * 64,
                FIXTURE,
            ),
        )
        connection.execute(
            """UPDATE football.product_fixtures SET status='FINISHED',home_score=1,away_score=0,
               result_score_basis='REGULATION_90',identity_status='VERIFIED'
                       WHERE fixture_id=%s""",
            (FIXTURE,),
        )
        assert _selected(connection)[0][2] == OBSERVED


def test_indexed_team_history_preserves_admission_and_revocation_cutoffs(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        before = _cutoff(connection)
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        admitted = _cutoff(connection)
        team = connection.execute(
            """SELECT h.home_team_id FROM football.product_team_match_history h
               JOIN football.source_snapshots s ON s.id=h.source_snapshot_id
               WHERE h.source_provider_code='football_data_uk'
                 AND s.source_identity='test/season.csv'"""
        ).fetchone()
        assert team is not None

        def selected(cutoff: object) -> list[tuple[object, ...]]:
            return connection.execute(
                "SELECT fixture_id,home_goals,away_goals FROM "
                "football.product_eligible_team_history_at(%s,ARRAY[%s::uuid])",
                (cutoff, team[0]),
            ).fetchall()

        assert selected(before) == []
        original = selected(admitted)
        assert len(original) == 1
        connection.execute("UPDATE football.team_provider_mappings SET mapping_confidence=.5")
        assert selected(_cutoff(connection)) == []
        assert selected(admitted) == original
        assert selected(before) == []


def test_go_performance_batch_scopes_and_cancellation() -> None:
    import os
    import subprocess

    from psycopg.conninfo import make_conninfo
    from psycopg.sql import SQL, Identifier

    from tests.integration.test_product_identity_upgrade import _migrate

    database = "football_analytics_batch_" + uuid4().hex
    url = make_conninfo(DATABASE_URL, dbname=database)
    with psycopg.connect(make_conninfo(DATABASE_URL, dbname="postgres"), autocommit=True) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(database)))
        try:
            _migrate(url, "up")
            with psycopg.connect(url) as connection:
                _seed_fixture(connection)
                connection.execute(
                    "UPDATE football.product_competitions "
                    "SET country='World',geographic_scope='International' WHERE competition_id=%s",
                    (COMPETITION,),
                )
                _insert_forecast(connection, uuid4(), "a" * 64, "b" * 64)
                _revision(connection, 1)
                connection.execute(
                    """UPDATE football.product_fixtures SET status='FINISHED',
                       home_score=2,away_score=1,
                       result_score_basis='REGULATION_90',identity_status='VERIFIED'
                       WHERE fixture_id=%s""",
                    (FIXTURE,),
                )
                connection.execute(
                    "INSERT INTO football.competitions(id) "
                    "SELECT uuidv7() FROM generate_series(1,1466)"
                )
                connection.execute(
                    """INSERT INTO football.product_competitions (
                           competition_id,name,country,continent,competition_type,season_label,
                           availability_status,source_roles,updated_at)
                       SELECT id,'Catalogue '||id::text,'Test','Other','LEAGUE','2030',
                              'NOT_ENOUGH_HISTORY','{}',clock_timestamp()
                       FROM football.competitions WHERE id<>%s""",
                    (COMPETITION,),
                )
            from football.product.public_reports import run_public_reports

            with psycopg.connect(url) as connection:
                assert (
                    run_public_reports(
                        connection,
                        report_kind="PERFORMANCE",
                        scope_ids=(COMPETITION,),
                        horizon="LATEST",
                        limit=1,
                        lease_duration=timedelta(minutes=5),
                        code_commit_sha="f" * 40,
                        dependency_lock_sha256="d" * 64,
                    )["published"]
                    == 1
                )
            result = subprocess.run(
                [
                    "go",
                    "test",
                    "./internal/app",
                    "-run",
                    "TestPerformanceBatchDatabase",
                    "-count=1",
                ],
                cwd="go/api",
                env={**os.environ, "TEST_DATABASE_URL": url},
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(database)))
