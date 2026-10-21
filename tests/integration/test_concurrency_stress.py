"""Real overlapping workers, bounded waits and whole-transaction retry evidence."""

import hashlib
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from time import monotonic, sleep
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.product.api_football import ApiFootballClient
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.football_data_uk import parse_csv_resource
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest
from football.product.identity_admission import admit_provider_mappings
from football.product.identity_correction import correct_team_identity
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.provider_history_scopes import enqueue_seasons, run_scopes
from football.product.sync import ProductSync
from football.storage.locks import LockClass, LockRequest, acquire_locks
from football.storage.raw import ImmutableFileStore
from football.work.contracts import RetryClassification, RetryPolicy, WorkRequest, WorkType
from football.work.storage import WorkLeaseLost, WorkRegistry
from psycopg import Connection, IsolationLevel

from tests.integration.test_product_forecast_worklist import _forecast_fixture
from tests.integration.test_team_identity_correction import isolated_database, seed


@pytest.fixture
def stress_database() -> Iterator[str]:
    with isolated_database() as url:
        yield url


def _product(connection: Connection[Any], root: Path) -> ProductSync:
    return ProductSync(connection, ApiFootballClient("offline"), root, MODEL_ARTIFACT_PATH)


def _history(connection: Connection[Any], root: Path) -> tuple[list[UUID], UUID, UUID]:
    raw = (
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG\n"
        + "".join(
            f"E0,{day:02}/08/2026,15:00,Stress home,Stress away,2,1\n" for day in range(1, 11)
        )
    ).encode()
    stamp = datetime(2026, 9, 1, tzinfo=UTC)
    manifest = publish_manifest(
        root,
        provider="football_data_uk",
        source_identity="stress.csv",
        source_revision="test",
        acquired_at=stamp,
        resources=[("stress.csv", "raw/stress.csv", raw)],
    )
    store = HistoricalBackfillStore(
        connection, "football_data_uk", "Football Data", "test-v1", data_root=root
    )
    snapshot = store.ensure_snapshot(
        source_identity="stress.csv",
        source_revision="test",
        acquired_at=stamp,
        manifest_path=manifest,
    )
    store.record_resource(
        snapshot_id=snapshot,
        provider_path="stress.csv",
        payload=raw,
        media_type="text/csv",
        acquired_at=stamp,
    )
    for match in parse_csv_resource(
        raw, source_path="stress.csv", season="2026", country_hint="England"
    ):
        assert store.import_match(match, snapshot, stamp) == "inserted"
    admit_provider_mappings(connection, root, "football_data_uk")
    rows = connection.execute(
        "SELECT fixture_id,home_team_id,away_team_id FROM football.product_team_match_history"
    ).fetchall()
    connection.commit()
    return [row[0] for row in rows], rows[0][1], rows[0][2]


def _use_teams(url: str, fixture: UUID, home: UUID, away: UUID) -> None:
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE football.product_fixtures SET "
            "home_team_id=%s,away_team_id=%s WHERE fixture_id=%s",
            (home, away, fixture),
        )


def _wait_for_lock(url: str, pid: int) -> None:
    deadline = monotonic() + 8
    with psycopg.connect(url, autocommit=True) as observer:
        while monotonic() < deadline:
            if observer.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND NOT granted)", (pid,)
            ).fetchone()[0]:
                return
            sleep(0.01)
    pytest.fail("controlled contender did not reach its expected database lock")


def test_history_qualification_overlaps_real_forecast_preparation(
    stress_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.product import sync as module

    ready, release = Event(), Event()
    original = module.forecast_from_history
    with psycopg.connect(stress_database) as setup:
        history, home, away = _history(setup, tmp_path)
    with _forecast_fixture(stress_database, cleanup=False) as (_, _, _, fixture):
        _use_teams(stress_database, fixture, home, away)

        def predict(**kwargs: Any) -> Any:
            assert {row.fixture_id for row in kwargs["history"]} == set(history)
            ready.set()
            assert release.wait(8)
            return original(**kwargs)

        def forecast() -> dict[str, object]:
            with psycopg.connect(stress_database) as connection:
                return _product(connection, tmp_path).refresh_pending_forecasts()

        monkeypatch.setattr(module, "forecast_from_history", predict)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(forecast)
            try:
                assert ready.wait(8)
                with psycopg.connect(stress_database) as qualifier:
                    qualifier.execute("SET LOCAL statement_timeout='5s'")
                    qualifier.execute(
                        "SELECT football.record_product_history_decisions(%s)", (history,)
                    )
            finally:
                release.set()
            assert future.result(timeout=10)["forecasts_created"] == 1
        with psycopg.connect(stress_database) as observer:
            assert observer.execute(
                "SELECT count(*) FROM football.product_forecasts WHERE fixture_id=%s", (fixture,)
            ).fetchone() == (1,)
            assert observer.execute(
                "SELECT count(*) FROM football.product_eligible_history_at(clock_timestamp())"
            ).fetchone() == (10,)


def test_identity_correction_waits_for_overlapping_history_then_requalifies(
    stress_database: str, tmp_path: Path
) -> None:
    with psycopg.connect(stress_database) as setup:
        request, _ = seed(setup, tmp_path)
        fixtures = [
            row[0]
            for row in setup.execute("SELECT fixture_id FROM football.product_team_match_history")
        ]
    started = Event()
    pids: list[int] = []

    def correct() -> dict[str, Any]:
        with psycopg.connect(stress_database) as connection:
            connection.execute("SET LOCAL statement_timeout='8s'")
            pids.append(connection.info.backend_pid)
            started.set()
            return correct_team_identity(connection, tmp_path, request)

    with psycopg.connect(stress_database) as qualifier:
        qualifier.execute("SELECT football.record_product_history_decisions(%s)", (fixtures,))
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(correct)
            try:
                assert started.wait(8)
                _wait_for_lock(stress_database, pids[0])
                qualifier.commit()
            finally:
                qualifier.rollback()
            result = future.result(timeout=10)
    assert result["decision_id"]
    with psycopg.connect(stress_database) as observer:
        observer.execute("SELECT football.record_product_history_decisions(%s)", (fixtures,))
        assert observer.execute(
            "SELECT count(*) FROM football.product_identity_admissions WHERE "
            "corrects_decision_id IS NOT NULL"
        ).fetchone() == (1,)


def test_provider_observation_changes_target_during_forecast_preparation(
    stress_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.product import sync as module
    from football.providers.pitchapi import PitchApiFixture, PitchApiResponse

    ready, release = Event(), Event()
    original = module.forecast_from_history
    with psycopg.connect(stress_database) as setup:
        _, home, away = _history(setup, tmp_path)
    with _forecast_fixture(stress_database, cleanup=False) as (_, _, _, fixture):
        _use_teams(stress_database, fixture, home, away)

        def predict(**kwargs: Any) -> Any:
            ready.set()
            assert release.wait(8)
            return original(**kwargs)

        def forecast() -> dict[str, object]:
            with psycopg.connect(stress_database) as connection:
                return _product(connection, tmp_path).refresh_pending_forecasts()

        monkeypatch.setattr(module, "forecast_from_history", predict)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(forecast)
            try:
                assert ready.wait(8)
                with psycopg.connect(stress_database) as provider:
                    kickoff, stamp = provider.execute(
                        "SELECT kickoff_at,clock_timestamp() FROM "
                        "football.product_fixtures WHERE fixture_id=%s",
                        (fixture,),
                    ).fetchone()
                    sync = OperationalProviderSync(provider, tmp_path, provider_code="pitchapi")
                    raw = b'{"data":{}}'
                    snapshot = sync._record_response(
                        "stress-observation",
                        PitchApiResponse("test", stamp, hashlib.sha256(raw).hexdigest(), raw, {}),
                    )
                    row = PitchApiFixture(
                        provider_match_id="m_Stress",
                        provider_competition_id="l_Stress",
                        provider_home_team_id="t_Home",
                        provider_away_team_id="t_Away",
                        home_team_name="Stress home",
                        away_team_name="Stress away",
                        kickoff_at=kickoff,
                        status="POSTPONED",
                        provider_status="postponed",
                        home_score=None,
                        away_score=None,
                        minute=None,
                        added_time=None,
                        period=None,
                        source_updated_at=stamp,
                        observed_at=stamp,
                    )
                    assert sync._store_observation(row, snapshot, fixture)
                    assert sync._update_canonical_fixture(row, fixture, snapshot) == 1
            finally:
                release.set()
            assert future.result(timeout=10)["forecasts_created"] == 0
        with psycopg.connect(stress_database) as observer:
            assert observer.execute(
                "SELECT status FROM football.product_fixtures WHERE fixture_id=%s", (fixture,)
            ).fetchone() == ("POSTPONED",)
            assert observer.execute(
                "SELECT count(*) FROM football.product_forecasts"
            ).fetchone() == (0,)


def test_many_generation_increments_while_worker_publishes_are_not_lost(
    stress_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publishing, release, started = Event(), Event(), Event()
    pids: list[int] = []
    original = ProductSync._publish_prepared_forecast
    with psycopg.connect(stress_database) as setup:
        _, home, away = _history(setup, tmp_path)
    with _forecast_fixture(stress_database, cleanup=False) as (_, _, _, fixture):
        _use_teams(stress_database, fixture, home, away)

        def publish(self: ProductSync, *args: Any, **kwargs: Any) -> int:
            result = original(self, *args, **kwargs)
            publishing.set()
            assert release.wait(8)
            return result

        def refresh() -> dict[str, object]:
            with psycopg.connect(stress_database) as connection:
                return _product(connection, tmp_path).refresh_pending_forecasts()

        def enqueue() -> None:
            assert publishing.wait(8)
            with psycopg.connect(stress_database) as connection:
                connection.execute("SET LOCAL statement_timeout='8s'")
                pids.append(connection.info.backend_pid)
                started.set()
                for _ in range(5):
                    connection.execute(
                        "SELECT football.enqueue_product_forecast_refresh(%s)", (fixture,)
                    )

        with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as executor:
            patch.setattr(ProductSync, "_publish_prepared_forecast", publish)
            worker, producer = executor.submit(refresh), executor.submit(enqueue)
            try:
                assert started.wait(8)
                _wait_for_lock(stress_database, pids[0])
            finally:
                release.set()
            assert worker.result(timeout=10)["forecasts_created"] == 1
            producer.result(timeout=10)
        with psycopg.connect(stress_database) as connection:
            generation, completed = connection.execute(
                "SELECT generation,completed_generation FROM "
                "football.product_forecast_refresh_work WHERE fixture_id=%s",
                (fixture,),
            ).fetchone()
            assert generation - completed == 5
            connection.commit()
            assert (
                _product(connection, tmp_path).refresh_pending_forecasts()["fixtures_processed"]
                == 1
            )
            connection.commit()
            assert connection.execute(
                "SELECT count(*) FROM football.product_forecasts WHERE fixture_id=%s", (fixture,)
            ).fetchone() == (1,)
            assert connection.execute(
                "SELECT generation=completed_generation FROM "
                "football.product_forecast_refresh_work WHERE fixture_id=%s",
                (fixture,),
            ).fetchone() == (True,)


def _request() -> WorkRequest:
    return WorkRequest(
        work_type=WorkType.NORMALIZATION,
        semantic_key=f"stress:{uuid4()}",
        input_hash="a" * 64,
        priority=0,
        available_at=datetime(2026, 1, 1, tzinfo=UTC),
        max_attempts=3,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()),
    )


@pytest.mark.parametrize("revocation", ["crash", "cancel"])
def test_active_worker_is_fenced_before_stale_publication(
    stress_database: str, revocation: str
) -> None:
    item, stale_team, current_team = _request(), uuid4(), uuid4()
    with (
        psycopg.connect(stress_database, autocommit=True) as control,
        psycopg.connect(stress_database) as worker,
    ):
        registry = WorkRegistry(control)
        registry.enqueue(item)
        old = registry.claim(
            "old", timedelta(milliseconds=30), (item.work_type,), work_ids=(item.work_id,)
        )
        assert old is not None
        if revocation == "crash":
            control.execute(
                "SELECT pg_sleep(GREATEST(0,extract(epoch FROM "
                "(%s::timestamptz-clock_timestamp())))+0.01)",
                (old.lease_until,),
            )
            current = registry.claim(
                "replacement", timedelta(seconds=20), (item.work_type,), work_ids=(item.work_id,)
            )
            assert current is not None and current.generation > old.generation
        else:
            registry.cancel(item.work_id)
            current = None
        with (
            pytest.raises(WorkLeaseLost),
            WorkRegistry(worker).publication(old, result_hash="b" * 64),
        ):
            worker.execute("INSERT INTO football.teams(id) VALUES (%s)", (stale_team,))
        assert control.execute(
            "SELECT count(*) FROM football.teams WHERE id=%s", (stale_team,)
        ).fetchone() == (0,)
        if current is not None:
            with WorkRegistry(worker).publication(current, result_hash="b" * 64):
                worker.execute("INSERT INTO football.teams(id) VALUES (%s)", (current_team,))
            assert control.execute(
                "SELECT count(*) FROM football.teams WHERE id=%s", (current_team,)
            ).fetchone() == (1,)


def test_retryable_failure_cannot_bypass_provider_cooldown(stress_database: str) -> None:
    item = _request()
    with psycopg.connect(stress_database, autocommit=True) as connection:
        registry = WorkRegistry(connection)
        registry.enqueue(item)
        claim = registry.claim(
            "provider", timedelta(seconds=10), (item.work_type,), work_ids=(item.work_id,)
        )
        assert claim is not None
        until = connection.execute("SELECT clock_timestamp()+interval '2 seconds'").fetchone()[0]
        registry.fail(
            claim,
            RetryClassification.RETRYABLE,
            error_code="PROVIDER_COOLDOWN",
            error_message="retry later",
            provider_cooldown=until,
        )
        assert (
            registry.claim(
                "early", timedelta(seconds=10), (item.work_type,), work_ids=(item.work_id,)
            )
            is None
        )
        connection.execute("SELECT pg_sleep_until(%s)", (until,))
        replacement = registry.claim(
            "eligible", timedelta(seconds=10), (item.work_type,), work_ids=(item.work_id,)
        )
        assert replacement is not None and replacement.attempt_count == 2
        with registry.publication(replacement, result_hash="b" * 64):
            pass


@pytest.mark.parametrize("failure", ["deadlock", "serialization"])
def test_adversarial_transactions_retry_whole_publications_without_duplicates(
    stress_database: str, tmp_path: Path, failure: str
) -> None:
    items = [_request(), _request()]
    barrier = Barrier(2, timeout=8)
    claimed = Barrier(2, timeout=8)
    completed = [Event(), Event()]
    keys = [f"zz-stress:{uuid4()}", f"zz-stress:{uuid4()}"]
    with psycopg.connect(stress_database, autocommit=True) as setup:
        setup.execute(
            "CREATE TABLE public.stress_publications(work_id uuid PRIMARY KEY,sha256 text NOT NULL)"
        )
        setup.execute(
            "CREATE TABLE public.stress_markers(work_id uuid PRIMARY KEY,ready integer NOT NULL)"
        )
        for item in items:
            WorkRegistry(setup).enqueue(item)
            setup.execute("INSERT INTO public.stress_markers VALUES (%s,0)", (item.work_id,))

    def run(index: int) -> list[str]:
        item = items[index]
        payload = json.dumps({"work_id": str(item.work_id)}, sort_keys=True).encode()
        digest = hashlib.sha256(payload).hexdigest()
        ImmutableFileStore(tmp_path).publish(f"stress/{digest}.json", payload)
        failures = []
        with psycopg.connect(stress_database) as connection:
            connection.execute("SET statement_timeout='8s'")
            connection.commit()
            registry = WorkRegistry(connection)
            claim = registry.claim(
                "worker", timedelta(seconds=30), (item.work_type,), work_ids=(item.work_id,)
            )
            assert claim is not None
            if failure == "serialization":
                connection.isolation_level = IsolationLevel.SERIALIZABLE
            claimed.wait()
            for attempt in range(2):
                try:
                    with registry.publication(claim, result_hash=digest):
                        connection.execute(
                            "SELECT sum(ready) FROM public.stress_markers"
                        ).fetchone()
                        connection.execute(
                            "INSERT INTO public.stress_publications VALUES (%s,%s)",
                            (item.work_id, digest),
                        )
                        if attempt == 0:
                            if failure == "deadlock":
                                connection.execute(
                                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                                    (keys[index],),
                                )
                            barrier.wait()
                            if failure == "deadlock":
                                acquire_locks(
                                    connection, (LockRequest(LockClass.WORK, keys[1 - index]),)
                                )
                        connection.execute(
                            "UPDATE public.stress_markers SET ready=1 WHERE work_id=%s",
                            (item.work_id,),
                        )
                    completed[index].set()
                    return failures
                except (
                    psycopg.errors.DeadlockDetected,
                    psycopg.errors.SerializationFailure,
                ) as error:
                    failures.append(error.sqlstate)
                    # Start a fresh snapshot after the competing publication commits.
                    assert completed[1 - index].wait(8)
            pytest.fail(f"whole-publication retry did not converge: {failures}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, (0, 1)))
    assert [code for codes in results for code in codes] == [
        "40P01" if failure == "deadlock" else "40001"
    ]
    with psycopg.connect(stress_database) as observer:
        assert observer.execute("SELECT count(*) FROM public.stress_publications").fetchone() == (
            2,
        )
        assert observer.execute("SELECT sum(ready) FROM public.stress_markers").fetchone() == (2,)
        assert observer.execute(
            "SELECT count(*) FROM football.work_items WHERE state='SUCCEEDED'"
        ).fetchone() == (2,)
    assert len(list((tmp_path / "stress").glob("*.json"))) == 2


def test_six_independent_fixture_publications_proceed_in_parallel(
    stress_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = Barrier(6, timeout=8)
    original = ProductSync._publish_prepared_forecast

    def publish(self: ProductSync, *args: Any, **kwargs: Any) -> int:
        result = original(self, *args, **kwargs)
        barrier.wait()
        return result

    def refresh() -> dict[str, object]:
        with psycopg.connect(stress_database) as connection:
            connection.execute("SET statement_timeout='8s'")
            return _product(connection, tmp_path).refresh_pending_forecasts(limit=1)

    monkeypatch.setattr(ProductSync, "_publish_prepared_forecast", publish)
    with ExitStack() as stack:
        for _ in range(6):
            stack.enter_context(_forecast_fixture(stress_database, cleanup=False))
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: refresh(), range(6)))
        assert sum(result["fixtures_processed"] for result in results) == 6
        with psycopg.connect(stress_database) as observer:
            assert observer.execute(
                "SELECT bool_and(generation=completed_generation) FROM "
                "football.product_forecast_refresh_work"
            ).fetchone() == (True,)


def test_six_independent_provider_scopes_execute_in_parallel(
    stress_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.product import provider_history_scopes as module

    barrier = Barrier(6, timeout=8)

    def response(*_args: Any, **_kwargs: Any) -> tuple[object, bool]:
        barrier.wait()
        return object(), True

    monkeypatch.setattr(module, "_scope_response", response)
    monkeypatch.setattr(
        OperationalProviderSync,
        "backfill_league_response",
        lambda *_args, **_kwargs: {"status": "COMPLETED"},
    )
    with psycopg.connect(stress_database) as setup:
        sync = OperationalProviderSync(setup, tmp_path, provider_code="pitchapi")
        for index in range(6):
            enqueue_seasons(sync, f"l_Stress{index}", ["2025/2026"])

    def run(index: int) -> list[dict[str, object]]:
        with psycopg.connect(stress_database) as connection:
            sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
            return run_scopes(sync, object(), budget=1, competition=f"l_Stress{index}")

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(run, range(6)))
    assert all(len(rows) == 1 for rows in results)
    with psycopg.connect(stress_database) as observer:
        assert observer.execute(
            "SELECT count(*) FROM football.product_provider_history_scopes WHERE status='SUCCEEDED'"
        ).fetchone() == (6,)
        assert observer.execute(
            "SELECT count(*) FROM football.work_items WHERE state='SUCCEEDED'"
        ).fetchone() == (6,)
