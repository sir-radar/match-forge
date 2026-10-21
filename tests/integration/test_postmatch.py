"""Production-only monitoring uses eligible results, immutable snapshots and fenced work."""

import io
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from football.cli.main import run
from football.forecasting import postmatch_storage as storage
from football.forecasting.pitchapi_v3 import _poisson_forecast
from football.forecasting.runtime_models import CURRENT_CHAMPION_HASH
from football.work.contracts import WorkType
from football.work.storage import WorkLeaseLost, WorkRegistry
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from tests.integration.test_live_context import COMPETITION, FIXTURE, _seed_fixture
from tests.integration.test_team_identity_correction import isolated_database


@pytest.fixture
def monitored_database() -> Iterator[tuple[str, datetime]]:
    with isolated_database() as url:
        with psycopg.connect(url) as connection:
            _seed_fixture(connection)
            now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
            kickoff = now - timedelta(days=1)
            issued = kickoff - timedelta(hours=25)
            connection.execute(
                """UPDATE football.product_fixtures SET kickoff_at=%s,
                status='FINISHED',home_score=7,away_score=0,result_score_basis='REGULATION_90',
                identity_status='VERIFIED',updated_at=%s WHERE fixture_id=%s""",
                (kickoff, kickoff + timedelta(hours=2), FIXTURE),
            )
            goal = _poisson_forecast(1.4, 1.0)
            matrix = [
                {"home_goals": h, "away_goals": a, "probability": p}
                for h, row in enumerate(goal.score_matrix.probabilities)
                for a, p in enumerate(row)
            ]
            probabilities = {
                "home": goal.markets.home_win,
                "draw": goal.markets.draw,
                "away": goal.markets.away_win,
            }
            connection.execute(
                """INSERT INTO football.product_forecasts (
                forecast_id,semantic_sha256,fixture_id,model_label,model_algorithm_version,
                model_artifact_sha256,created_at,football_cutoff,knowledge_cutoff,knowledge_mode,
                expected_home_goals,expected_away_goals,probabilities,score_matrix,payload_sha256,
                publication_mode,forecast_horizon,score_matrix_version,
                predictive_input_snapshot_sha256,context_snapshot_sha256,
                revision_reason_codes,new_information_ids)
                VALUES(%s,%s,%s,'MVP_FORECAST','transferable-rolling-goals-poisson-v1',%s,
                %s,%s,%s,'bitemporal',1.4,1.0,%s,%s,%s,'MVP_OWNER_AUTHORIZED',
                '3D','compact-buckets-v2',%s,%s,'["INITIAL_FORECAST"]'::jsonb,'[]'::jsonb)""",
                (
                    uuid4(),
                    "a" * 64,
                    FIXTURE,
                    CURRENT_CHAMPION_HASH,
                    issued,
                    issued,
                    issued,
                    Jsonb(probabilities),
                    Jsonb(matrix),
                    "b" * 64,
                    "c" * 64,
                    "d" * 64,
                ),
            )
        yield url, kickoff


def _run(url: str, kickoff: datetime, code_commit_sha: str = "f" * 40) -> dict[str, Any]:
    with psycopg.connect(url) as connection:
        return storage.run_postmatch(
            connection,
            competitions=(COMPETITION,),
            window_start=kickoff - timedelta(hours=1),
            window_end=kickoff + timedelta(hours=1),
            horizon="LATEST",
            limit=10,
            lease_duration=timedelta(minutes=30),
            code_commit_sha=code_commit_sha,
            dependency_lock_sha256="d" * 64,
        )


def _monitor(
    url: str, kickoff: datetime, knowledge_cutoff: datetime | None = None
) -> dict[str, Any]:
    with psycopg.connect(url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        known = knowledge_cutoff or connection.execute("SELECT clock_timestamp()").fetchone()[0]
        return storage.monitor_postmatch(
            connection,
            competitions=(COMPETITION,),
            window_start=kickoff - timedelta(hours=1),
            window_end=kickoff + timedelta(hours=1),
            knowledge_cutoff=known,
            horizon="LATEST",
            review_limits={},
        )


def test_published_forecast_final_result_work_and_monitoring_converge(
    monitored_database: tuple[str, datetime], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        original = connection.execute(
            "SELECT to_jsonb(f) FROM football.product_forecasts f"
        ).fetchall()
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    actual = storage.evaluate_postmatch

    def compute(inputs: dict[str, Any], forecast: dict[str, Any]) -> dict[str, Any]:
        with psycopg.connect(url) as inspector:
            assert inspector.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted "
                "AND pid<>pg_backend_pid() AND database=(SELECT oid FROM pg_database "
                "WHERE datname=current_database())"
            ).fetchone() == (0,)
        return actual(inputs, forecast)

    monkeypatch.setattr(storage, "evaluate_postmatch", compute)
    assert _run(url, kickoff)["published"] == 1
    assert _run(url, kickoff)["selected"] == 0
    assert _monitor(url, kickoff, before)["overall"]["coverage"]["selected"] == 0
    report = _monitor(url, kickoff)
    assert report["overall"]["coverage"] == {
        "selected": 1,
        "scored": 1,
        "ratio": 1.0,
        "crps_scored": 1,
    }
    assert report["overall"]["status"] == "MONITORING"
    assert report["segments"][0]["data_quality_tier"] == "UNKNOWN"
    assert report["segments"][0]["competition_id"] == str(COMPETITION)
    with psycopg.connect(url) as connection:
        assert (
            connection.execute("SELECT to_jsonb(f) FROM football.product_forecasts f").fetchall()
            == original
        )
        assert connection.execute(
            "SELECT state,work_type FROM football.work_items "
            "WHERE work_type='POST_MATCH_EVALUATION'"
        ).fetchall() == [("SUCCEEDED", "POST_MATCH_EVALUATION")]
        assert connection.execute(
            "SELECT registered_at>outcome_known_at FROM football.post_match_evaluation_inputs"
        ).fetchone() == (True,)


@pytest.mark.parametrize("basis", ["UNKNOWN", "EXTRA_TIME", "PENALTY_SHOOTOUT"])
def test_incompatible_final_results_are_not_loaded(
    monitored_database: tuple[str, datetime], basis: str
) -> None:
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE football.product_fixtures SET result_score_basis=%s", (basis,))
    assert _run(url, kickoff)["selected"] == 0


def test_future_result_knowledge_is_excluded(monitored_database: tuple[str, datetime]) -> None:
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE football.product_fixtures SET updated_at=clock_timestamp()+interval '1 day'"
        )
    assert _run(url, kickoff)["selected"] == 0


def test_corrected_result_is_a_new_snapshot_and_old_knowledge_stays_readable(
    monitored_database: tuple[str, datetime],
) -> None:
    url, kickoff = monitored_database
    assert _run(url, kickoff)["published"] == 1
    with psycopg.connect(url) as connection:
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    old = _monitor(url, kickoff, before)
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE football.product_fixtures SET home_score=0,away_score=1,"
            "updated_at=clock_timestamp()"
        )
    assert _run(url, kickoff)["published"] == 1
    assert _monitor(url, kickoff, before) == old
    current = _monitor(url, kickoff)
    assert current["overall"]["coverage"]["selected"] == 1
    assert current["overall"]["metrics"]["log_loss"] != old["overall"]["metrics"]["log_loss"]
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM football.post_match_evaluations"
        ).fetchone() == (2,)


def test_changed_result_before_publication_cancels_stale_work(
    monitored_database: tuple[str, datetime], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, kickoff = monitored_database
    actual = storage.evaluate_postmatch

    def change(inputs: dict[str, Any], forecast: dict[str, Any]) -> dict[str, Any]:
        result = actual(inputs, forecast)
        with psycopg.connect(url) as control:
            control.execute(
                "UPDATE football.product_fixtures SET home_score=0,away_score=1,"
                "updated_at=clock_timestamp()"
            )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(storage, "evaluate_postmatch", change)
        assert _run(url, kickoff)["stale"] == 1
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM football.post_match_evaluations"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state FROM football.work_items WHERE work_type='POST_MATCH_EVALUATION'"
        ).fetchone() == ("CANCELLED",)
    assert _run(url, kickoff)["published"] == 1


def test_independent_workers_publish_once(monitored_database: tuple[str, datetime]) -> None:
    url, kickoff = monitored_database
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _: _run(url, kickoff), range(2)))
    assert sum(report["published"] for report in reports) == 1
    assert _monitor(url, kickoff)["overall"]["coverage"]["selected"] == 1


def test_cancelled_worker_cannot_publish(monitored_database: tuple[str, datetime]) -> None:
    url, kickoff = monitored_database
    with psycopg.connect(url) as worker:
        row = storage._candidates(
            worker,
            (COMPETITION,),
            "LATEST",
            kickoff - timedelta(hours=1),
            kickoff + timedelta(hours=1),
            1,
            "f" * 40,
            "d" * 64,
        )[0]
        inputs = storage._inputs(row, "LATEST", "f" * 40, "d" * 64)
        request = storage._register(worker, inputs)
        claim = WorkRegistry(worker).claim(
            "stale",
            timedelta(minutes=1),
            (WorkType.POST_MATCH_EVALUATION,),
            work_ids=(request.work_id,),
        )
        assert claim is not None
        with psycopg.connect(url) as control:
            WorkRegistry(control).cancel(request.work_id)
        with pytest.raises(WorkLeaseLost):
            storage.publish_postmatch(
                worker, claim, inputs, storage.evaluate_postmatch(inputs, row)
            )
        assert worker.info.transaction_status == TransactionStatus.IDLE
    assert _monitor(url, kickoff)["overall"]["coverage"]["selected"] == 0


@pytest.mark.parametrize("table", ["post_match_evaluation_inputs", "post_match_evaluations"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_monitoring_evidence_is_immutable(
    monitored_database: tuple[str, datetime], table: str, operation: str
) -> None:
    url, kickoff = monitored_database
    _run(url, kickoff)
    statement = {
        "UPDATE": f"UPDATE football.{table} SET record_bytes=record_bytes",
        "DELETE": f"DELETE FROM football.{table}",
        "TRUNCATE": f"TRUNCATE football.{table} CASCADE",
    }[operation]
    with psycopg.connect(url) as connection, pytest.raises(psycopg.Error):
        connection.execute(statement)
    assert _monitor(url, kickoff)["overall"]["coverage"]["selected"] == 1


def test_failed_publication_rolls_back_and_retries_through_shared_work(
    monitored_database: tuple[str, datetime],
) -> None:
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        connection.execute("""CREATE FUNCTION public.postmatch_fail() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'test serialization failure' USING ERRCODE='40001'; END $$""")
        connection.execute(
            "CREATE TRIGGER test_postmatch_fail BEFORE INSERT "
            "ON football.post_match_evaluations FOR EACH ROW "
            "EXECUTE FUNCTION public.postmatch_fail()"
        )
    assert _run(url, kickoff)["failed"] == 1
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM football.post_match_evaluations"
        ).fetchone() == (0,)
        connection.execute("DROP FUNCTION public.postmatch_fail() CASCADE")
    assert _run(url, kickoff)["published"] == 1
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT state,attempt_count FROM football.work_items "
            "WHERE work_type='POST_MATCH_EVALUATION'"
        ).fetchone() == ("SUCCEEDED", 2)


def test_cli_worker_and_read_only_monitor(monitored_database: tuple[str, datetime]) -> None:
    url, kickoff = monitored_database
    scope = [
        "--competition",
        str(COMPETITION),
        "--window-start",
        (kickoff - timedelta(hours=1)).isoformat(),
        "--window-end",
        (kickoff + timedelta(hours=1)).isoformat(),
    ]
    output, errors = io.StringIO(), io.StringIO()
    assert (
        run(
            [
                "--database-url",
                url,
                "--code-commit-sha",
                "f" * 40,
                "--dependency-lock-sha256",
                "d" * 64,
                "models",
                "postmatch-evaluate",
                *scope,
                "--limit",
                "1",
                "--lease-seconds",
                "60",
            ],
            environ={},
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert json.loads(output.getvalue())["published"] == 1
    output = io.StringIO()
    with psycopg.connect(url) as connection:
        cutoff = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    assert (
        run(
            [
                "--database-url",
                url,
                "models",
                "postmatch-monitor",
                *scope,
                "--knowledge-cutoff",
                cutoff.isoformat(),
            ],
            environ={},
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert json.loads(output.getvalue())["overall"]["coverage"]["selected"] == 1
    assert not errors.getvalue()


@pytest.mark.parametrize("table", ["post_match_evaluation_inputs", "post_match_evaluations"])
def test_sql_rejects_corrupted_monitoring_bytes(
    monitored_database: tuple[str, datetime], table: str
) -> None:
    url, kickoff = monitored_database
    _run(url, kickoff)
    with psycopg.connect(url) as connection, pytest.raises(psycopg.errors.CheckViolation):
        if table == "post_match_evaluation_inputs":
            connection.execute("""INSERT INTO football.post_match_evaluation_inputs
                (input_sha256,work_id,forecast_id,fixture_id,horizon,outcome_known_at,
                 home_goals,away_goals,record_bytes)
                SELECT input_sha256,work_id,forecast_id,fixture_id,horizon,outcome_known_at,
                       home_goals,away_goals,convert_to('{}','UTF8')
                FROM football.post_match_evaluation_inputs LIMIT 1""")
        else:
            connection.execute("""INSERT INTO football.post_match_evaluations
                (input_sha256,result_sha256,record_bytes)
                SELECT input_sha256,result_sha256,convert_to('{}','UTF8')
                FROM football.post_match_evaluations LIMIT 1""")
    assert _monitor(url, kickoff)["overall"]["coverage"]["selected"] == 1


def test_scoring_provenance_creates_a_new_immutable_version(
    monitored_database: tuple[str, datetime],
) -> None:
    url, kickoff = monitored_database
    assert _run(url, kickoff)["published"] == 1
    with psycopg.connect(url) as connection:
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        first = connection.execute(
            "SELECT record_bytes FROM football.post_match_evaluations"
        ).fetchone()[0]
    old = _monitor(url, kickoff, before)
    assert _run(url, kickoff, "e" * 40)["published"] == 1
    assert _monitor(url, kickoff, before) == old
    assert _monitor(url, kickoff)["overall"]["coverage"]["selected"] == 1
    with psycopg.connect(url) as connection:
        rows = connection.execute(
            "SELECT record_bytes FROM football.post_match_evaluations"
        ).fetchall()
    assert len(rows) == 2 and any(row[0] == first for row in rows)
    versions = {json.loads(bytes(row[0]))["input"]["code_commit_sha"] for row in rows}
    assert versions == {"e" * 40, "f" * 40}
