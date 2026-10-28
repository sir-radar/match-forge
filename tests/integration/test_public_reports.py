"""Read reports use shared work, immutable bytes and current source fingerprints."""

import hashlib
import json
import os
import subprocess
from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from football.product.public_reports import run_pending_context_reports, run_public_reports
from psycopg.errors import RaiseException

from tests.integration.test_live_context import (
    AWAY,
    COMPETITION,
    FIXTURE,
    HOME,
    KICKOFF,
    SNAPSHOT,
    _insert_forecast,
    _seed_fixture,
)
from tests.integration.test_product_analytics import _revision
from tests.integration.test_team_identity_correction import isolated_database

PREDICTION = UUID(int=9010)


@pytest.fixture
def report_database() -> Iterator[str]:
    with isolated_database() as url:
        with psycopg.connect(url) as connection:
            _seed_fixture(connection)
            _insert_forecast(connection, uuid4(), "a" * 64, "b" * 64)
            _revision(connection, 1)
            connection.execute(
                """UPDATE football.product_fixtures SET status='FINISHED',
                home_score=2,away_score=1,result_score_basis='REGULATION_90',identity_status='VERIFIED'
                WHERE fixture_id=%s""",
                (FIXTURE,),
            )
            connection.execute(
                """INSERT INTO football.external_predictions
                (prediction_id,revision_sha256,source_code,source_page,prediction_date,
                 original_date_text,collected_at,fixture_id,competition_text,home_team_text,
                 away_team_text,market,selection,match_status)
                VALUES(%s,%s,'r2bet','synthetic',CURRENT_DATE,'synthetic',clock_timestamp(),%s,
                 'Test','Home','Away','RESULT_1X2','HOME_WIN','MATCHED')""",
                (PREDICTION, "e" * 64, FIXTURE),
            )
        yield url


def build(url: str, kind: str, scope: UUID, *, timezone: str = "UTC", **changes):
    with psycopg.connect(url) as connection:
        connection.execute("SELECT set_config('TimeZone',%s,false)", (timezone,))
        connection.commit()
        return run_public_reports(
            connection,
            **{
                "report_kind": kind,
                "scope_ids": (scope,),
                "horizon": "LATEST",
                "limit": 1,
                "lease_duration": timedelta(minutes=5),
                "code_commit_sha": "f" * 40,
                "dependency_lock_sha256": "d" * 64,
                **changes,
            },
        )


def test_reports_retry_exactly_and_leave_forecasts_unchanged(report_database):
    url = report_database
    with psycopg.connect(url) as connection:
        before = connection.execute(
            "SELECT to_jsonb(f) FROM football.product_forecasts f ORDER BY forecast_id"
        ).fetchall()
    for kind, scope in (
        ("PERFORMANCE", COMPETITION),
        ("CONTEXT", FIXTURE),
        ("COMPARISON", PREDICTION),
    ):
        assert build(url, kind, scope)["published"] == 1
        assert build(url, kind, scope, timezone="Pacific/Auckland")["busy_or_complete"] == 1
    with psycopg.connect(url) as connection:
        rows = connection.execute(
            "SELECT report_kind,input_bytes,input_sha256,record_bytes,record_sha256 "
            "FROM football.product_read_reports ORDER BY report_kind"
        ).fetchall()
        assert len(rows) == 3
        reports = {}
        for kind, inputs, digest, payload, result_digest in rows:
            assert hashlib.sha256(bytes(inputs)).hexdigest() == digest
            assert hashlib.sha256(bytes(payload)).hexdigest() == result_digest
            reports[kind] = json.loads(bytes(payload))
        assert reports["PERFORMANCE"]["forecasts"] == 1
        assert reports["COMPARISON"]["agreement"] == "AGREES"
        assert reports["COMPARISON"]["matchforge_probability"] == 0.6
        assert reports["CONTEXT"]["home_form"] == []
        assert (
            connection.execute(
                "SELECT to_jsonb(f) FROM football.product_forecasts f ORDER BY forecast_id"
            ).fetchall()
            == before
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM football.work_items "
                "WHERE work_type='READ_MODEL_PROJECTION' AND state='SUCCEEDED'"
            ).fetchone()[0]
            == 3
        )


def test_pending_context_report_worker_publishes_and_completes_current_queue(report_database):
    with psycopg.connect(report_database) as connection:
        result = run_pending_context_reports(
            connection,
            code_commit_sha="f" * 40,
            dependency_lock_sha256="d" * 64,
        )
        assert result["selected"] == 1
        assert result["context_reports_published"] == 1
        assert result["context_reports_pending"] == 0
        assert connection.execute(
            """SELECT generation=completed_generation
            FROM football.product_context_report_refresh_work WHERE fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (True,)


def test_fixture_deletion_cascades_to_context_refresh_work(report_database):
    deleted_fixture = uuid4()
    with psycopg.connect(report_database) as connection:
        clone_fixture(connection, deleted_fixture)
        assert connection.execute(
            "SELECT count(*) FROM football.product_context_report_refresh_work WHERE fixture_id=%s",
            (deleted_fixture,),
        ).fetchone() == (1,)
        connection.execute(
            "DELETE FROM football.product_fixtures WHERE fixture_id=%s",
            (deleted_fixture,),
        )
        assert connection.execute(
            "SELECT count(*) FROM football.product_context_report_refresh_work WHERE fixture_id=%s",
            (deleted_fixture,),
        ).fetchone() == (0,)


def test_eligible_history_change_requeues_later_fixture_context(report_database):
    prior_fixture = uuid4()
    with psycopg.connect(report_database) as connection:
        run_pending_context_reports(
            connection,
            code_commit_sha="f" * 40,
            dependency_lock_sha256="d" * 64,
        )
        clone_fixture(connection, prior_fixture, KICKOFF - timedelta(days=30))
        connection.commit()
        run_pending_context_reports(
            connection,
            code_commit_sha="f" * 40,
            dependency_lock_sha256="d" * 64,
        )
        assert connection.execute(
            """SELECT generation=completed_generation
            FROM football.product_context_report_refresh_work WHERE fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (True,)
        connection.execute(
            """INSERT INTO football.product_match_history_decisions
            (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,home_goals,away_goals,
             source_provider_code,source_snapshot_id,source_kickoff_precision,eligible,reason,source_known_at)
            VALUES(%s,%s,%s,%s,%s,2,1,'live_context_test',%s,'EXACT',true,
                   'synthetic eligible history',clock_timestamp())""",
            (prior_fixture, COMPETITION, HOME, AWAY, KICKOFF - timedelta(days=30), SNAPSHOT),
        )
        assert connection.execute(
            """SELECT generation>completed_generation
            FROM football.product_context_report_refresh_work WHERE fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (True,)


def test_upcoming_fixture_refresh_change_requeues_earlier_context(report_database):
    future_fixture = uuid4()
    with psycopg.connect(report_database) as connection:
        clone_fixture(connection, future_fixture, KICKOFF + timedelta(days=3))
        connection.commit()
        run_pending_context_reports(
            connection,
            code_commit_sha="f" * 40,
            dependency_lock_sha256="d" * 64,
        )
        assert connection.execute(
            """SELECT generation=completed_generation
            FROM football.product_context_report_refresh_work WHERE fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (True,)
        connection.commit()
        connection.execute(
            "UPDATE football.product_fixtures SET updated_at=%s WHERE fixture_id=%s",
            (KICKOFF + timedelta(days=1), future_fixture),
        )
        assert connection.execute(
            """SELECT generation>completed_generation
            FROM football.product_context_report_refresh_work WHERE fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (True,)


def test_historical_team_name_change_requeues_context_with_that_opponent(report_database):
    prior_fixture = uuid4()
    with psycopg.connect(report_database) as connection:
        clone_fixture(connection, prior_fixture, KICKOFF - timedelta(days=30))
        connection.execute(
            """INSERT INTO football.product_match_history_decisions
            (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,home_goals,away_goals,
             source_provider_code,source_snapshot_id,source_kickoff_precision,eligible,reason,source_known_at)
            VALUES(%s,%s,%s,%s,%s,2,1,'live_context_test',%s,'EXACT',true,
                   'synthetic eligible history',clock_timestamp())""",
            (prior_fixture, COMPETITION, HOME, AWAY, KICKOFF - timedelta(days=30), SNAPSHOT),
        )
        connection.commit()
        run_pending_context_reports(
            connection,
            code_commit_sha="f" * 40,
            dependency_lock_sha256="d" * 64,
        )
        assert connection.execute(
            """SELECT generation=completed_generation
            FROM football.product_context_report_refresh_work WHERE fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (True,)
        connection.execute(
            "UPDATE football.product_teams SET name=name || ' United' WHERE team_id=%s",
            (HOME,),
        )
        assert connection.execute(
            """SELECT generation>completed_generation
            FROM football.product_context_report_refresh_work WHERE fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (True,)


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE football.product_read_reports SET horizon='1H'",
        "DELETE FROM football.product_read_reports",
        "TRUNCATE football.product_read_reports",
    ],
)
def test_report_versions_cannot_be_changed_or_deleted(report_database, mutation):
    assert build(report_database, "PERFORMANCE", COMPETITION)["published"] == 1
    with (
        psycopg.connect(report_database) as connection,
        pytest.raises(RaiseException, match="immutable"),
    ):
        connection.execute(mutation)


def test_late_result_correction_invalidates_old_report_without_rewriting_it(report_database):
    url = report_database
    assert build(url, "PERFORMANCE", COMPETITION)["published"] == 1
    with psycopg.connect(url) as connection:
        old = connection.execute(
            "SELECT input_sha256,record_sha256 FROM football.product_read_reports"
        ).fetchone()
        connection.execute(
            "UPDATE football.product_fixtures SET home_score=0,away_score=3 WHERE fixture_id=%s",
            (FIXTURE,),
        )
        assert (
            connection.execute(
                """SELECT count(*) FROM football.product_read_reports r
            JOIN football.public_performance_source(%s,0) s
                ON s.source_fingerprint=r.source_fingerprint""",
                (COMPETITION,),
            ).fetchone()[0]
            == 0
        )
    assert build(url, "PERFORMANCE", COMPETITION)["published"] == 1
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT record_sha256 FROM football.product_read_reports WHERE input_sha256=%s",
            (old[0],),
        ).fetchone() == (old[1],)
        assert (
            connection.execute("SELECT count(*) FROM football.product_read_reports").fetchone()[0]
            == 2
        )


def test_context_source_seals_target_outcomes_even_after_earlier_revision(report_database):
    with psycopg.connect(report_database) as connection:
        connection.execute(
            """INSERT INTO football.product_match_history_decisions
            (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,home_goals,away_goals,
             source_provider_code,source_snapshot_id,source_kickoff_precision,eligible,reason,source_known_at)
            VALUES(%s,%s,%s,%s,clock_timestamp()-interval '30 days',9,8,'live_context_test',%s,
                'EXACT',true,'synthetic earlier target revision',clock_timestamp())""",
            (FIXTURE, COMPETITION, HOME, AWAY, SNAPSHOT),
        )
        cutoff = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        assert connection.execute(
            "SELECT fixture_id FROM football.product_eligible_team_history_at(%s,ARRAY[%s::uuid])",
            (cutoff, HOME),
        ).fetchone() == (FIXTURE,)
        source = connection.execute(
            "SELECT football.public_context_source(%s)", (FIXTURE,)
        ).fetchone()[0]
        assert source["history"] == [] and source["kickoff_at"] == KICKOFF.isoformat()


def test_go_retrieves_python_reports_and_rejects_missing_stale_versions(report_database):
    url = report_database
    canonical_fixture = UUID("00000000-0000-4000-8000-000000001fa8")
    with psycopg.connect(url) as connection:
        clone_fixture(connection, canonical_fixture)
    assert build(url, "CONTEXT", canonical_fixture)["published"] == 1
    for kind, scope in (
        ("PERFORMANCE", COMPETITION),
        ("CONTEXT", FIXTURE),
        ("COMPARISON", PREDICTION),
    ):
        assert build(url, kind, scope)["published"] == 1
    result = subprocess.run(
        [
            "go",
            "test",
            "./internal/app",
            "-run",
            "^TestPublicReadReportsDatabase$",
            "-count=1",
            "-v",
        ],
        cwd="go/api",
        env={**os.environ, "TEST_DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--- PASS: TestPublicReadReportsDatabase" in result.stdout
    print(result.stdout)


def test_failed_publication_rolls_back_report_and_retries_same_work(report_database, monkeypatch):
    from football.product import public_reports

    original = public_reports.acquire_locks

    def fail(*args, **kwargs):
        raise ValueError("synthetic publication failure")

    monkeypatch.setattr(public_reports, "acquire_locks", fail)
    assert build(report_database, "PERFORMANCE", COMPETITION)["failed"] == 1
    with psycopg.connect(report_database) as connection:
        assert (
            connection.execute("SELECT count(*) FROM football.product_read_reports").fetchone()[0]
            == 0
        )
        assert connection.execute("SELECT state FROM football.work_items").fetchone() == (
            "RETRY_WAIT",
        )
    monkeypatch.setattr(public_reports, "acquire_locks", original)
    assert build(report_database, "PERFORMANCE", COMPETITION)["published"] == 1
    with psycopg.connect(report_database) as connection:
        assert connection.execute(
            "SELECT count(*),max(attempt_count) FROM football.work_items"
        ).fetchone() == (1, 2)


def test_cancelled_claim_cannot_publish(report_database, monkeypatch):
    from football.work.storage import WorkRegistry

    original = WorkRegistry.claim

    def cancel_after_claim(self, *args, **kwargs):
        claim = original(self, *args, **kwargs)
        assert claim is not None
        self.cancel(claim.work_id)
        return claim

    monkeypatch.setattr(WorkRegistry, "claim", cancel_after_claim)
    assert build(report_database, "PERFORMANCE", COMPETITION)["lease_lost"] == 1
    with psycopg.connect(report_database) as connection:
        assert (
            connection.execute("SELECT count(*) FROM football.product_read_reports").fetchone()[0]
            == 0
        )
        assert connection.execute("SELECT state FROM football.work_items").fetchone() == (
            "CANCELLED",
        )


def test_operator_command_publishes_through_the_common_registry(report_database):
    import io

    from football.cli.main import run

    output, errors = io.StringIO(), io.StringIO()
    assert (
        run(
            [
                "--database-url",
                report_database,
                "--code-commit-sha",
                "f" * 40,
                "--dependency-lock-sha256",
                "d" * 64,
                "models",
                "public-reports",
                "--report-kind",
                "PERFORMANCE",
                "--scope-id",
                str(COMPETITION),
                "--limit",
                "1",
                "--lease-seconds",
                "300",
            ],
            environ={},
            stdout=output,
            stderr=errors,
        )
        == 0
    ), errors.getvalue()
    assert json.loads(output.getvalue())["published"] == 1


def clone_fixture(connection, fixture, kickoff=None):
    connection.execute(
        "INSERT INTO football.matches(id,competition_id,season_id) "
        "SELECT %s,competition_id,season_id FROM football.matches WHERE id=%s",
        (fixture, FIXTURE),
    )
    connection.execute(
        "INSERT INTO football.product_fixtures "
        "SELECT (jsonb_populate_record(NULL::football.product_fixtures,"
        "to_jsonb(f)||jsonb_build_object("
        "'fixture_id',%s::text,'kickoff_at',coalesce(%s::timestamptz,f.kickoff_at),"
        "'updated_at',statement_timestamp()))).* "
        "FROM football.product_fixtures f WHERE f.fixture_id=%s",
        (fixture, kickoff, FIXTURE),
    )


def test_context_input_retains_coach_lineup_and_upcoming_fixture_references(report_database):
    url = report_database
    prior_fixture, next_fixture = uuid4(), uuid4()
    references = {}
    with psycopg.connect(url) as connection:
        now = connection.execute("SELECT statement_timestamp()").fetchone()[0]
        clone_fixture(connection, prior_fixture, now - timedelta(days=2))
        clone_fixture(connection, next_fixture, KICKOFF + timedelta(days=3))
        for team in (HOME, AWAY):
            coach, observation, lineup = uuid4(), uuid4(), uuid4()
            references[str(team)] = (str(observation), str(lineup))
            connection.execute(
                """INSERT INTO football.product_coach_observations
                (coach_observation_id,team_id,coach_id,effective_at,observed_at,known_at,
                 provider,source_snapshot_id,source_checksum)
                VALUES(%s,%s,%s,%s,%s,%s,'live_context_test',%s,%s)""",
                (observation, team, coach, now - timedelta(days=4), now, now, SNAPSHOT, "1" * 64),
            )
            connection.execute(
                """INSERT INTO football.product_lineup_observations
                (lineup_observation_id,fixture_id,team_id,kickoff_at,lineup_mode,coach_id,
                 observed_at,known_at,provider,source_snapshot_id,source_checksum)
                VALUES(%s,%s,%s,%s,'CONFIRMED',%s,%s,%s,'live_context_test',%s,%s)""",
                (
                    lineup,
                    prior_fixture,
                    team,
                    now - timedelta(days=2),
                    coach,
                    now,
                    now,
                    SNAPSHOT,
                    "2" * 64,
                ),
            )
    assert build(url, "CONTEXT", FIXTURE)["published"] == 1
    with psycopg.connect(url) as connection:
        inputs, payload = connection.execute(
            "SELECT input_bytes,record_bytes FROM football.product_read_reports"
        ).fetchone()
    inputs, report = json.loads(bytes(inputs)), json.loads(bytes(payload))
    for row in inputs["source_manifest"]["coaches"]:
        assert (
            row["coach_observation_id"],
            row["prior_lineups"][0]["lineup_observation_id"],
        ) == references[row["team_id"]]
        assert row["source_snapshot_id"] == str(SNAPSHOT)
        assert row["prior_lineups"][0]["source_snapshot_id"] == str(SNAPSHOT)
    assert [row["team_id"] for row in report["coach_context"]] == [str(HOME), str(AWAY)]
    assert all(row["matches_under_coach"] == 1 for row in report["coach_context"])
    assert all(row["days_to_next_match"] == 3 for row in report["rest_context"].values())
    assert all(
        row["fixture_id"] == str(next_fixture) for row in inputs["source_manifest"]["upcoming"]
    )


def test_current_product_bucket_contract_publishes_a_performance_report(report_database):
    from pathlib import Path

    from football.product.domain import FinishedMatch, forecast_from_history
    from psycopg.types.json import Jsonb

    forecast = forecast_from_history(
        artifact_path=Path(
            "docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json"
        ),
        target_kickoff=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        history=[
            FinishedMatch(uuid4(), KICKOFF - timedelta(days=20 + index), HOME, AWAY, 2, 1)
            for index in range(10)
        ],
    )
    assert forecast is not None
    probabilities = {
        "home": forecast.home_probability,
        "draw": forecast.draw_probability,
        "away": forecast.away_probability,
        "total_over_2_5": sum(forecast.total_goal_distribution[3:]),
        "btts_yes": forecast.btts_yes,
    }
    identity = uuid4()
    with psycopg.connect(report_database) as connection:
        connection.execute(
            """INSERT INTO football.product_forecasts
            SELECT (jsonb_populate_record(NULL::football.product_forecasts,to_jsonb(f)||
                jsonb_build_object('forecast_id',%s::uuid,'semantic_sha256',%s::text,
                    'payload_sha256',%s::text,'predictive_input_snapshot_sha256',%s::text,
                    'created_at',f.created_at+interval '1 minute',
                    'football_cutoff',f.football_cutoff+interval '1 minute',
                    'knowledge_cutoff',f.knowledge_cutoff+interval '1 minute',
                    'probabilities',%s::jsonb,'score_matrix',%s::jsonb,
                    'score_matrix_version','compact-buckets-v2'))).*
            FROM football.product_forecasts f ORDER BY created_at DESC,forecast_id DESC LIMIT 1""",
            (
                identity,
                identity.hex * 2,
                identity.hex * 2,
                identity.hex * 2,
                Jsonb(probabilities),
                Jsonb(list(forecast.score_matrix)),
            ),
        )
    assert build(report_database, "PERFORMANCE", COMPETITION)["published"] == 1
    with psycopg.connect(report_database) as connection:
        inputs, payload = connection.execute(
            "SELECT input_bytes,record_bytes FROM football.product_read_reports"
        ).fetchone()
    assert (
        json.loads(bytes(inputs))["source_manifest"][0]["score_matrix_version"]
        == "compact-buckets-v2"
    )
    assert json.loads(bytes(payload))["forecasts"] == 1
