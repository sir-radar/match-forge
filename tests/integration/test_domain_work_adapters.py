"""Controlled queue compatibility, shared ownership and publication boundaries."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from football.product.history_requests import HistoryDeferred
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.provider_history_scopes import claim_scope, enqueue_seasons, run_scopes
from football.work.contracts import WorkState
from football.work.storage import WorkRegistry
from psycopg.errors import LockNotAvailable, ObjectNotInPrerequisiteState


@pytest.fixture
def domain_database() -> Iterator[str]:
    from tests.integration.test_team_identity_correction import isolated_database

    with isolated_database() as url:
        yield url


def test_operator_shared_cancellation_serializes_with_children(domain_database: str) -> None:
    identity = uuid4()
    with (
        psycopg.connect(domain_database, autocommit=True) as control,
        psycopg.connect(domain_database) as worker,
    ):
        control.execute(
            """INSERT INTO football.product_sync_runs
            (run_id,sync_type,status,worker_id,heartbeat_at,log_path)
            VALUES (%s,'FOTMOB_SYNC','QUEUED',%s,clock_timestamp(),'retained.log')""",
            (identity, str(identity)),
        )
        assert WorkRegistry(control).state(identity) == WorkState.PENDING
        control.execute(
            "UPDATE football.product_sync_runs SET status='RUNNING' WHERE run_id=%s",
            (identity,),
        )
        assert WorkRegistry(control).state(identity) == WorkState.RUNNING
        worker.execute("SELECT set_config('matchforge.sync_run_id',%s,false)", (str(identity),))
        worker.execute("SELECT set_config('matchforge.sync_worker_id',%s,false)", (str(identity),))
        worker.commit()
        worker.execute("UPDATE football.product_fixtures SET status=status WHERE false")
        control.execute("SET lock_timeout='100ms'")
        with pytest.raises(LockNotAvailable):
            WorkRegistry(control).cancel(identity)
        worker.commit()
        assert WorkRegistry(control).cancel(identity) == WorkState.CANCELLED
        with pytest.raises(ObjectNotInPrerequisiteState, match="ownership lost"):
            worker.execute("UPDATE football.product_fixtures SET status=status WHERE false")
        worker.rollback()
        control.execute(
            """UPDATE football.product_sync_runs SET status='CANCELLED',error_message='cancelled',
            finished_at=clock_timestamp() WHERE run_id=%s""",
            (identity,),
        )
        assert control.execute(
            "SELECT log_path,status FROM football.product_sync_runs WHERE run_id=%s",
            (identity,),
        ).fetchone() == ("retained.log", "CANCELLED")


@pytest.mark.parametrize("outcome", ["SUCCEEDED", "FAILED", "CANCELLED"])
def test_operator_legacy_and_shared_outcomes_match(domain_database: str, outcome: str) -> None:
    results = []
    with psycopg.connect(domain_database, autocommit=True) as connection:
        for shared in (False, True):
            identity = uuid4()
            if not shared:
                connection.execute(
                    "ALTER TABLE football.product_sync_runs DISABLE TRIGGER z_drive_sync_run_work"
                )
            connection.execute(
                """INSERT INTO football.product_sync_runs
                (run_id,sync_type,status,worker_id,heartbeat_at,log_path,parameters)
                VALUES (%s,'MVP_SYNC','QUEUED',%s,clock_timestamp(),
                        'parity.log','{"date":"test"}')""",
                (identity, str(identity)),
            )
            connection.execute(
                """UPDATE football.product_sync_runs SET status='RUNNING',
                started_at=clock_timestamp() WHERE run_id=%s""",
                (identity,),
            )
            connection.execute(
                """UPDATE football.product_sync_runs SET status=%s,summary='{"processed":2}',
                error_message=%s,finished_at=clock_timestamp() WHERE run_id=%s""",
                (outcome, "failure" if outcome != "SUCCEEDED" else None, identity),
            )
            results.append(
                connection.execute(
                    """SELECT status,summary,error_message,log_path,parameters,
                started_at IS NOT NULL,finished_at IS NOT NULL
                FROM football.product_sync_runs WHERE run_id=%s""",
                    (identity,),
                ).fetchone()
            )
            if shared:
                assert WorkRegistry(connection).state(identity).value == outcome
                assert connection.execute(
                    "SELECT result_hash IS NOT NULL FROM football.work_items WHERE work_id=%s",
                    (identity,),
                ).fetchone() == (outcome == "SUCCEEDED",)
            else:
                connection.execute(
                    "ALTER TABLE football.product_sync_runs ENABLE TRIGGER z_drive_sync_run_work"
                )
        assert results[0] == results[1]


@pytest.mark.parametrize("outcome", ["SUCCEEDED", "FAILED", "DEFERRED"])
def test_provider_scope_execution_preserves_summary_and_cooldown(
    domain_database: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    from football.product import provider_history_scopes as module

    until = datetime.now(UTC) + timedelta(hours=2)

    def response(*_args: Any, **_kwargs: Any) -> Any:
        if outcome == "DEFERRED":
            raise HistoryDeferred("quota", until)
        if outcome == "FAILED":
            raise OSError("provider unavailable")
        return object(), True

    monkeypatch.setattr(module, "_scope_response", response)
    with psycopg.connect(domain_database) as connection:
        sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
        monkeypatch.setattr(
            sync,
            "backfill_league_response",
            lambda *_args, **_kwargs: {
                "status": "COMPLETED",
                "provider": "pitchapi",
                "league_id": "l_Shared",
            },
        )
        enqueue_seasons(sync, "l_Shared", ["2025/2026"])
        connection.commit()
        result = run_scopes(sync, object(), budget=1)
        assert len(result) == 1
        with connection.transaction():
            row = connection.execute(
                """SELECT scope.status,scope.summary,scope.next_attempt_at,work.state,
                work.available_at,work.result_hash,scope.claim_token=work.lease_token
                FROM football.product_provider_history_scopes scope
                JOIN football.product_provider_scope_work binding USING
                    (provider_code,provider_competition_id,season_label)
                JOIN football.work_items work USING(work_id)"""
            ).fetchone()
        assert row is not None and row[0] == outcome and row[1] == result[0]
        assert row[3] == ("SUCCEEDED" if outcome == "SUCCEEDED" else "RETRY_WAIT")
        if outcome == "SUCCEEDED":
            assert row[5] is not None
        else:
            assert row[2] == row[4] and row[5] is None
        if outcome == "DEFERRED":
            assert row[2] == until
        assert claim_scope(sync, "l_Shared", None) is None


def test_expired_scope_rolls_back_its_uncommitted_publication(
    domain_database: str,
    tmp_path: Path,
) -> None:
    team = uuid4()
    with (
        psycopg.connect(domain_database) as worker,
        psycopg.connect(domain_database, autocommit=True) as control,
    ):
        sync = OperationalProviderSync(worker, tmp_path, provider_code="pitchapi")
        enqueue_seasons(sync, "l_Cancel", ["2025/2026"])
        worker.commit()
        assert claim_scope(sync, "l_Cancel", None) == ("l_Cancel", "2025/2026")
        identity = control.execute(
            "SELECT work_id FROM football.product_provider_scope_work"
        ).fetchone()[0]
        with (
            pytest.raises(ObjectNotInPrerequisiteState, match="ownership lost"),
            worker.transaction(),
        ):
            worker.execute("INSERT INTO football.teams (id) VALUES (%s)", (team,))
            control.execute(
                """UPDATE football.work_items SET
                heartbeat_at=clock_timestamp()-interval '2 minutes',
                lease_until=clock_timestamp()-interval '1 minute' WHERE work_id=%s""",
                (identity,),
            )
            worker.execute("SELECT football.check_provider_scope_work()")
        assert control.execute(
            "SELECT count(*) FROM football.teams WHERE id=%s", (team,)
        ).fetchone() == (0,)


def test_cancelled_forecast_work_cannot_complete_its_source_generation(
    tmp_path: Path, domain_database: str
) -> None:
    from football.product.api_football import ApiFootballClient
    from football.product.domain import MODEL_ARTIFACT_PATH
    from football.product.forecast_work import claim_forecast_generations
    from football.product.sync import ProductSync

    from tests.integration.test_product_forecast_worklist import _forecast_fixture

    database_url = domain_database
    with (
        _forecast_fixture(database_url) as (_, _, _, fixture),
        psycopg.connect(database_url) as connection,
    ):
        connection.execute(
            """SELECT 1 FROM football.product_competitions competition
            JOIN football.product_fixtures target USING(competition_id)
            WHERE fixture_id=%s FOR UPDATE OF competition,target""",
            (fixture,),
        )
        claims = claim_forecast_generations(connection, [fixture])
        assert len(claims) == 1
        claim = claims[0][2]
        connection.execute("SELECT football.cancel_work(%s)", (claim.work_id,))
        product = ProductSync(
            connection, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH
        )
        result = product.refresh_pending_forecasts()
        assert result["fixtures_processed"] == 0 and result["fixtures_pending"] >= 1
        assert connection.execute(
            """SELECT generation>completed_generation FROM football.product_forecast_refresh_work
            WHERE fixture_id=%s""",
            (fixture,),
        ).fetchone() == (True,)
        assert WorkRegistry(connection).state(claim.work_id) == WorkState.CANCELLED


def test_scope_cancellation_projects_detail_and_requires_explicit_refresh(
    domain_database: str,
    tmp_path: Path,
) -> None:
    with (
        psycopg.connect(domain_database) as worker,
        psycopg.connect(domain_database, autocommit=True) as control,
    ):
        sync = OperationalProviderSync(worker, tmp_path, provider_code="pitchapi")
        enqueue_seasons(sync, "l_Stopped", ["2025/2026"])
        worker.commit()
        assert claim_scope(sync, "l_Stopped", None) == ("l_Stopped", "2025/2026")
        identity = control.execute(
            "SELECT work_id FROM football.product_provider_scope_work"
        ).fetchone()[0]
        worker.execute("UPDATE football.product_fixtures SET status=status WHERE false")
        control.execute("SET lock_timeout='100ms'")
        with pytest.raises(LockNotAvailable):
            WorkRegistry(control).cancel(identity)
        worker.commit()
        assert WorkRegistry(control).cancel(identity) == WorkState.CANCELLED
        assert control.execute(
            "SELECT status,last_error FROM football.product_provider_history_scopes"
        ).fetchone() == ("FAILED", "Work cancelled; publication rights revoked")
        with pytest.raises(ObjectNotInPrerequisiteState, match="ownership lost"):
            worker.execute("UPDATE football.product_fixtures SET status=status WHERE false")
        worker.rollback()
        assert claim_scope(sync, "l_Stopped", None) is None
        assert run_scopes(sync, object(), budget=0, competition="l_Stopped", refresh=True) == []
        assert claim_scope(sync, "l_Stopped", None) == ("l_Stopped", "2025/2026")
        replacement = control.execute(
            "SELECT work_id FROM football.product_provider_scope_work"
        ).fetchone()[0]
        assert replacement != identity
        assert WorkRegistry(control).state(replacement) == WorkState.RUNNING


def test_expired_operator_work_cannot_renew_or_publish_success(domain_database: str) -> None:
    identity = uuid4()
    with psycopg.connect(domain_database, autocommit=True) as control:
        control.execute(
            """INSERT INTO football.product_sync_runs
            (run_id,sync_type,status,worker_id,heartbeat_at)
            VALUES (%s,'FOTMOB_SYNC','RUNNING',%s,clock_timestamp())""",
            (identity, str(identity)),
        )
        control.execute(
            """UPDATE football.work_items SET
            heartbeat_at=clock_timestamp()-interval '3 minutes',
            lease_until=clock_timestamp()-interval '1 minute' WHERE work_id=%s""",
            (identity,),
        )
        with pytest.raises(ObjectNotInPrerequisiteState):
            control.execute(
                "UPDATE football.product_sync_runs SET heartbeat_at=clock_timestamp() "
                "WHERE run_id=%s",
                (identity,),
            )
        with pytest.raises(ObjectNotInPrerequisiteState):
            control.execute(
                """UPDATE football.product_sync_runs SET status='SUCCEEDED',summary='{}',
                finished_at=clock_timestamp() WHERE run_id=%s""",
                (identity,),
            )
        control.execute(
            """UPDATE football.product_sync_runs SET status='FAILED',
            error_message='worker lease expired',finished_at=clock_timestamp() WHERE run_id=%s""",
            (identity,),
        )
        assert WorkRegistry(control).state(identity) == WorkState.FAILED


@pytest.mark.parametrize("outcome", ["SUCCEEDED", "FAILED"])
def test_terminal_operator_records_keep_nullable_legacy_fields(
    domain_database: str,
    outcome: str,
) -> None:
    identity = uuid4()
    with psycopg.connect(domain_database, autocommit=True) as connection:
        connection.execute(
            """INSERT INTO football.product_sync_runs
            (run_id,sync_type,status,finished_at,error_message)
            VALUES (%s,'MVP_SYNC',%s,clock_timestamp(),%s)""",
            (identity, outcome, "failure" if outcome == "FAILED" else None),
        )
        assert connection.execute(
            "SELECT status,worker_id,summary FROM football.product_sync_runs WHERE run_id=%s",
            (identity,),
        ).fetchone() == (outcome, None, None)
        assert WorkRegistry(connection).state(identity).value == outcome


def test_superseded_forecast_generation_is_cancelled_without_losing_new_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    domain_database: str,
) -> None:
    from football.product.api_football import ApiFootballClient
    from football.product.domain import MODEL_ARTIFACT_PATH
    from football.product.forecast_work import claim_forecast_generations
    from football.product.sync import ProductSync

    from tests.integration.test_product_forecast_worklist import _forecast_fixture

    database_url = domain_database
    original_enqueue = WorkRegistry.enqueue
    identities = []
    with (
        _forecast_fixture(database_url) as (_, _, _, fixture),
        psycopg.connect(database_url) as worker,
        psycopg.connect(database_url, autocommit=True) as upstream,
    ):

        def enqueue(registry: Any, request: Any) -> Any:
            identity = original_enqueue(registry, request)
            identities.append(identity)
            upstream.execute("SELECT football.enqueue_product_forecast_refresh(%s)", (fixture,))
            return identity

        worker.execute(
            """SELECT 1 FROM football.product_competitions competition
            JOIN football.product_fixtures target USING(competition_id)
            WHERE fixture_id=%s FOR UPDATE OF competition,target""",
            (fixture,),
        )
        with monkeypatch.context() as context:
            context.setattr(WorkRegistry, "enqueue", enqueue)
            assert claim_forecast_generations(worker, [fixture]) == []
        assert len(identities) == 1
        assert WorkRegistry(worker).state(identities[0]) == WorkState.CANCELLED
        worker.commit()
        product = ProductSync(
            worker, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH
        )
        assert product.refresh_pending_forecasts()["fixtures_processed"] == 1
        worker.commit()
        assert worker.execute(
            """SELECT generation=completed_generation FROM football.product_forecast_refresh_work
            WHERE fixture_id=%s""",
            (fixture,),
        ).fetchone() == (True,)
