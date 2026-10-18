import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from football.product.api_football import ApiResponse
from football.product.football_data_org import FootballDataResponse
from psycopg.pq import TransactionStatus

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def history_database() -> Iterator[str]:
    from tests.integration.test_team_identity_correction import isolated_database

    with isolated_database() as url:
        yield url


@pytest.mark.parametrize("provider", ["api_football", "football_data_org"])
def test_provider_file_preparation_and_sql_registration_have_separate_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    from football.product.domain import stable_id
    from football.product.sync import ProductSync
    from football.storage.raw import ImmutableFileStore, ImmutableWrite

    raw = b'{"response":[],"matches":[]}'
    fetched_at = datetime(2026, 9, 1, tzinfo=UTC)
    resource = f"prepared-history-{uuid4()}"
    response = (
        ApiResponse("/fixtures", fetched_at, raw, (), None)
        if provider == "api_football"
        else FootballDataResponse("/competitions/PL/matches", fetched_at, raw, ())
    )
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        sync = ProductSync(connection, cast(Any, object()), tmp_path, tmp_path / "unused-artifact")
        prepared = sync._prepare_response(provider, response)
        assert isinstance(prepared, ImmutableWrite)
        assert connection.info.transaction_status == TransactionStatus.IDLE
        assert prepared.path.read_bytes() == raw
        digest = hashlib.sha256(raw).hexdigest()
        assert prepared.sha256 == digest and prepared.size_bytes == len(raw)
        assert prepared.relative_path == f"mvp/{provider}/2026/09/01/{digest}.json"

        def forbidden_publish(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("SQL registration performed file publication")

        monkeypatch.setattr(ImmutableFileStore, "publish", forbidden_publish)
        with connection.transaction(force_rollback=True):
            register = (
                sync._register_response
                if provider == "api_football"
                else sync._register_fallback_response
            )
            snapshot = register(resource, response, prepared)
            assert snapshot == stable_id("source-snapshot", provider, resource, digest)
            assert connection.execute(
                """SELECT snapshot.manifest_path,snapshot.manifest_sha256,snapshot.acquired_at,
                resource.provider_path,resource.sha256,resource.size_bytes
                FROM football.source_snapshots snapshot JOIN football.source_resources resource
                ON resource.source_snapshot_id=snapshot.id WHERE snapshot.id=%s""",
                (snapshot,),
            ).fetchone() == (
                prepared.relative_path,
                digest,
                fetched_at,
                response.path.lstrip("/"),
                digest,
                len(raw),
            )


@pytest.mark.parametrize(("autocommit", "delay"), [(True, 0), (False, 0), (False, 1.1)])
def test_shared_history_worker_matches_legacy_requests_and_publishes_an_exact_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    history_database: str,
    autocommit: bool,
    delay: float,
) -> None:
    import json
    from time import sleep

    from football.product import history_worker as worker_module
    from football.product.history_worker import HistorySyncWorker
    from football.product.sync import ProductSync
    from football.storage.raw import ImmutableFileStore
    from football.work.storage import WorkRegistry

    monkeypatch.setattr(worker_module, "HISTORY_JOB_LEASE", timedelta(seconds=2))
    league = uuid4().int % 1_000_000_000 + 1_000_000_000
    fetched_at = datetime(2026, 9, 1, tzinfo=UTC)
    fixture = {
        "fixture": {
            "id": league + 1,
            "date": "2026-08-01T15:00:00+00:00",
            "status": {"short": "FT"},
            "venue": {},
        },
        "league": {"id": league, "name": f"History {league}", "country": "England", "season": 2026},
        "teams": {
            "home": {"id": league + 2, "name": f"Home {league}"},
            "away": {"id": league + 3, "name": f"Away {league}"},
        },
        "goals": {"home": 2, "away": 1},
    }
    raw = json.dumps({"response": [fixture]}).encode()

    class Client:
        def __init__(self, connection: Any, require_idle: bool) -> None:
            self.connection = connection
            self.require_idle = require_idle
            self.calls: list[tuple[str, int, int]] = []

        def finished_fixtures(self, league_id: int, season: int) -> ApiResponse:
            if self.require_idle:
                assert self.connection.info.transaction_status == TransactionStatus.IDLE
            self.calls.append(("history", league_id, season))
            sleep(delay)
            return ApiResponse("/fixtures", fetched_at, raw, (fixture,), None)

        def standings(self, league_id: int, season: int) -> ApiResponse:
            if self.require_idle:
                assert self.connection.info.transaction_status == TransactionStatus.IDLE
            self.calls.append(("standings", league_id, season))
            sleep(delay)
            return ApiResponse("/standings", fetched_at, b'{"response":[]}', (), None)

    with psycopg.connect(history_database, autocommit=True) as legacy_connection:
        legacy_client = Client(legacy_connection, False)
        with legacy_connection.transaction(force_rollback=True):
            legacy = ProductSync(
                legacy_connection,
                cast(Any, legacy_client),
                tmp_path / "legacy",
                tmp_path / "unused",
            )
            expected = legacy._sync_history_job(league, 2026)

    with psycopg.connect(history_database, autocommit=True) as connection:
        client = Client(connection, True)
        worker = HistorySyncWorker(
            connection, cast(Any, client), tmp_path / "shared", tmp_path / "unused"
        )
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2026) RETURNING job_id""",
            (str(league),),
        ).fetchone()[0]
        batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        connection.autocommit = autocommit
        original_publish = ImmutableFileStore.publish

        def publish_idle(store: Any, *args: Any, **kwargs: Any) -> Any:
            assert connection.info.transaction_status == TransactionStatus.IDLE
            return original_publish(store, *args, **kwargs)

        monkeypatch.setattr(ImmutableFileStore, "publish", publish_idle)
        try:
            claimed = worker._claim_history_job(batch)
            assert claimed is not None and claimed[0] == job
            with connection.transaction():
                started = connection.execute(
                    "SELECT started_at FROM football.product_history_sync_queue WHERE job_id=%s",
                    (job,),
                ).fetchone()[0]
            assert worker._sync_history_job(league, 2026) == expected
            assert client.calls == legacy_client.calls
            worker._complete_history_job(job)
            assert connection.info.transaction_status == TransactionStatus.IDLE
            with connection.transaction():
                work_id, state, digest, exceeded = connection.execute(
                    """SELECT work.work_id,work.state,work.result_hash,
                    work.finished_at-work.started_at>interval '2 seconds'
                    FROM football.product_history_work binding
                    JOIN football.work_items work USING (work_id) WHERE binding.job_id=%s""",
                    (job,),
                ).fetchone()
                assert connection.execute(
                    "SELECT started_at FROM football.product_history_sync_queue WHERE job_id=%s",
                    (job,),
                ).fetchone() == (started,)
            assert state == "SUCCEEDED"
            if delay:
                assert exceeded
            receipt = (tmp_path / "shared" / "work" / "history" / f"{digest}.json").read_bytes()
            assert hashlib.sha256(receipt).hexdigest() == digest
            result = json.loads(receipt)
            assert result["work_id"] == str(work_id)
            assert (result["history_matches"], result["standings_rows"]) == expected
            assert result["source_snapshot_ids"] and result["source_resources"]
            assert connection.info.transaction_status == TransactionStatus.IDLE
        finally:
            connection.rollback()
            with connection.transaction():
                identities = connection.execute(
                    "SELECT work_id FROM football.product_history_work WHERE job_id=%s",
                    (job,),
                ).fetchall()
            for (identity,) in identities:
                WorkRegistry(connection).cancel(identity)
            with connection.transaction():
                connection.execute(
                    "DELETE FROM football.product_history_sync_queue WHERE job_id=%s",
                    (job,),
                )


def test_cancelled_provider_worker_cannot_register_its_response(
    tmp_path: Path,
    history_database: str,
) -> None:
    from football.product.history_work import cancel_history_request
    from football.product.history_worker import HistorySyncWorker
    from football.work.storage import WorkLeaseLost, WorkRegistry

    league = uuid4().int % 1_000_000_000 + 1_000_000_000
    worker: Any = None

    class Client:
        def finished_fixtures(self, _league: int, _season: int) -> ApiResponse:
            assert connection.info.transaction_status == TransactionStatus.IDLE
            with psycopg.connect(history_database, autocommit=True) as control:
                cancel_history_request(control, worker._owned().work_id)
            return ApiResponse(
                "/fixtures", datetime(2026, 9, 1, tzinfo=UTC), b'{"response":[]}', (), None
            )

    with psycopg.connect(history_database, autocommit=True) as connection:
        job = connection.execute(
            """INSERT INTO football.product_history_sync_queue (provider_competition_id,season)
            VALUES (%s,2026) RETURNING job_id""",
            (str(league),),
        ).fetchone()[0]
        worker = HistorySyncWorker(
            connection, cast(Any, Client()), tmp_path / "raw", tmp_path / "unused"
        )
        batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        assert worker._claim_history_job(batch) is not None
        identity = worker._owned().work_id
        try:
            with pytest.raises(WorkLeaseLost):
                worker._sync_history_job(league, 2026)
            assert connection.execute(
                "SELECT count(*) FROM football.source_snapshots"
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT job_status FROM football.product_history_sync_queue WHERE job_id=%s",
                (job,),
            ).fetchone() == ("FAILED",)
            assert not (tmp_path / "raw").exists()
        finally:
            WorkRegistry(connection).cancel(identity)


class _FallbackParityPrimary:
    def __init__(
        self, calls: list[tuple[str, int]], connection: Any, idle: bool, response_clock: datetime
    ) -> None:
        self.calls, self.connection, self.idle = calls, connection, idle
        self.fetched_at = response_clock

    def finished_fixtures(self, _league: int, season: int) -> ApiResponse:
        if self.idle:
            assert self.connection.info.transaction_status == TransactionStatus.IDLE
        self.calls.append(("api-history", season))
        return ApiResponse("/fixtures", self.fetched_at, b'{"response":[]}', (), None)

    def standings(self, _league: int, season: int) -> ApiResponse:
        if self.idle:
            assert self.connection.info.transaction_status == TransactionStatus.IDLE
        self.calls.append(("api-standings", season))
        return ApiResponse("/standings", self.fetched_at, b'{"response":[]}', (), None)


class _FallbackParityFallback:
    def __init__(
        self, calls: list[tuple[str, int]], connection: Any, idle: bool, response_clock: datetime
    ) -> None:
        self.calls, self.connection, self.idle = calls, connection, idle
        self.fetched_at = response_clock

    def finished_matches(self, competition: str, season: int) -> FootballDataResponse:
        assert competition == "PL"
        if self.idle:
            assert self.connection.info.transaction_status == TransactionStatus.IDLE
        self.calls.append(("fallback-history", season))
        return FootballDataResponse(f"/matches/{season}", self.fetched_at, b'{"matches":[]}', ())

    def standings(self, competition: str, season: int) -> FootballDataResponse:
        assert competition == "PL"
        if self.idle:
            assert self.connection.info.transaction_status == TransactionStatus.IDLE
        self.calls.append(("fallback-standings", season))
        return FootballDataResponse("/standings", self.fetched_at, b'{"standings":[]}', ())


@pytest.mark.parametrize("stop_after_first", [False, True])
def test_shared_history_worker_preserves_fallback_order_and_early_stop(
    tmp_path: Path,
    history_database: str,
    monkeypatch: pytest.MonkeyPatch,
    stop_after_first: bool,
) -> None:
    from football.product.history_worker import HistorySyncWorker
    from football.product.sync import ProductSync

    fetched_at = datetime(2026, 9, 1, tzinfo=UTC)

    old_calls: list[tuple[str, int]] = []
    with (
        psycopg.connect(history_database, autocommit=True) as legacy_connection,
        legacy_connection.transaction(force_rollback=True),
    ):
        legacy = ProductSync(
            legacy_connection,
            cast(Any, _FallbackParityPrimary(old_calls, legacy_connection, False, fetched_at)),
            tmp_path / "legacy",
            tmp_path / "unused",
            cast(Any, _FallbackParityFallback(old_calls, legacy_connection, False, fetched_at)),
            api_football_max_history_season=2024,
        )
        # Identical eligibility decisions isolate transport/fallback parity.
        monkeypatch.setattr(legacy, "_local_history_result", lambda *_: None)
        monkeypatch.setattr(legacy, "_history_sufficient", lambda *_: stop_after_first)
        expected = legacy._sync_history_job(39, 2026)
    calls: list[tuple[str, int]] = []
    with psycopg.connect(history_database, autocommit=True) as connection:
        worker = HistorySyncWorker(
            connection,
            cast(Any, _FallbackParityPrimary(calls, connection, True, fetched_at)),
            tmp_path / "shared",
            tmp_path / "unused",
            cast(Any, _FallbackParityFallback(calls, connection, True, fetched_at)),
            api_football_max_history_season=2024,
        )
        monkeypatch.setattr(worker, "_local_history_result", lambda *_: None)
        monkeypatch.setattr(worker, "_history_sufficient", lambda *_: stop_after_first)
        job = connection.execute(
            "INSERT INTO football.product_history_sync_queue (provider_competition_id,season) "
            "VALUES ('39',2026) RETURNING job_id",
        ).fetchone()[0]
        batch = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        assert worker._claim_history_job(batch) is not None
        assert worker._sync_history_job(39, 2026) == expected
        worker._complete_history_job(job)
        assert calls == old_calls
        history_calls = [call for call in calls if call[0].endswith("history")]
        assert history_calls == (
            [("fallback-history", 2026)]
            if stop_after_first
            else [("fallback-history", 2026), ("fallback-history", 2025), ("api-history", 2024)]
        )


def test_cli_history_factory_runs_shared_workers_concurrently(
    tmp_path: Path,
    history_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    from football.product import cli
    from football.product.history_worker import HistorySyncWorker
    from football.product.sync import ProductSync

    barrier = threading.Barrier(2)
    fetched_at = datetime(2026, 9, 1, tzinfo=UTC)

    class Client:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def finished_fixtures(self, league: int, season: int) -> ApiResponse:
            barrier.wait(timeout=10)
            return ApiResponse(
                f"/fixtures/{league}/{season}", fetched_at, b'{"response":[]}', (), None
            )

        def standings(self, league: int, season: int) -> ApiResponse:
            return ApiResponse(
                f"/standings/{league}/{season}", fetched_at, b'{"response":[]}', (), None
            )

    monkeypatch.setattr(cli, "ApiFootballClient", Client)
    monkeypatch.delenv("API_FOOTBALL_MAX_HISTORY_SEASON", raising=False)
    factory = cli._history_worker_factory(history_database, "test", "", tmp_path, None)
    with factory() as worker:
        assert isinstance(worker, HistorySyncWorker)
        assert worker.connection.info.transaction_status == TransactionStatus.IDLE
    with psycopg.connect(history_database) as connection:
        with connection.transaction():
            connection.execute(
                """INSERT INTO football.product_history_sync_queue
                (provider_competition_id,season) VALUES ('1234567',2026),('1234568',2026)"""
            )
        parent = ProductSync(
            connection,
            cast(Any, object()),
            tmp_path,
            tmp_path / "unused",
            history_worker_factory=factory,
        )
        result = parent._process_history_queue(2)
        assert result == {
            "total": 2,
            "peak_concurrency": 2,
            "processed": 2,
            "succeeded": 2,
            "failed": 0,
            "pending_retry": 0,
            "history_matches": 0,
            "standings_rows": 0,
        }
        with connection.transaction():
            rows = connection.execute(
                """SELECT queue.job_status,work.state,work.attempt_count,work.result_hash
                FROM football.product_history_sync_queue queue
                JOIN football.product_history_work binding USING (job_id)
                JOIN football.work_items work USING (work_id)"""
            ).fetchall()
        assert len(rows) == 2
        assert all(row[:3] == ("SUCCEEDED", "SUCCEEDED", 1) for row in rows)
        assert all((tmp_path / "work" / "history" / f"{row[3]}.json").is_file() for row in rows)
        assert connection.info.transaction_status == TransactionStatus.IDLE


@pytest.mark.parametrize("retryable", [True, False])
def test_parent_history_queue_projects_provider_failure_through_shared_work(
    tmp_path: Path,
    history_database: str,
    monkeypatch: pytest.MonkeyPatch,
    retryable: bool,
) -> None:
    from football.product import cli
    from football.product.api_football import ApiFootballError
    from football.product.sync import ProductSync

    class Client:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def finished_fixtures(self, *_args: Any) -> ApiResponse:
            if retryable:
                raise ApiFootballError("provider temporarily unavailable")
            raise ValueError("invalid provider result")

    monkeypatch.setattr(cli, "ApiFootballClient", Client)
    monkeypatch.delenv("API_FOOTBALL_MAX_HISTORY_SEASON", raising=False)
    with psycopg.connect(history_database) as connection:
        with connection.transaction():
            connection.execute(
                """INSERT INTO football.product_history_sync_queue
                (provider_competition_id,season) VALUES ('1234567',2026)"""
            )
        parent = ProductSync(
            connection,
            cast(Any, object()),
            tmp_path,
            tmp_path / "unused",
            history_worker_factory=cli._history_worker_factory(
                history_database, "test", "", tmp_path, None
            ),
        )
        result = parent._process_history_queue(1)
        assert result["processed"] == 1 and result["succeeded"] == 0
        assert result["pending_retry"] == int(retryable)
        assert result["failed"] == int(not retryable)
        with connection.transaction():
            row = connection.execute(
                """SELECT queue.job_status,work.state,work.attempt_count,
                queue.next_attempt_at=work.available_at,queue.last_error,
                extract(epoch FROM work.available_at-queue.updated_at)
                FROM football.product_history_sync_queue queue
                JOIN football.product_history_work binding USING (job_id)
                JOIN football.work_items work USING (work_id)"""
            ).fetchone()
        assert row is not None and row[2] == 1
        if retryable:
            assert row[:2] == ("PENDING", "RETRY_WAIT") and row[3]
            assert 59 <= row[5] <= 61
        else:
            assert row[:2] == ("FAILED", "FAILED")
        assert row[4] and not list(tmp_path.rglob("*.json"))


def test_parent_history_queue_does_not_fail_a_cancelled_claim(
    tmp_path: Path,
    history_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football.product import cli
    from football.product.history_work import cancel_history_request
    from football.product.history_worker import HistorySyncWorker
    from football.product.sync import ProductSync
    from football.work.storage import WorkLeaseLost

    class Client:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def finished_fixtures(self, *_args: Any) -> ApiResponse:
            with psycopg.connect(history_database, autocommit=True) as control:
                identity = control.execute(
                    "SELECT work_id FROM football.product_history_work"
                ).fetchone()[0]
                cancel_history_request(control, identity)
            return ApiResponse("/fixtures", datetime.now(UTC), b'{"response":[]}', (), None)

    def forbidden_failure(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("parent tried to fail a claim whose ownership was revoked")

    monkeypatch.setattr(cli, "ApiFootballClient", Client)
    monkeypatch.setattr(HistorySyncWorker, "_fail_history_job", forbidden_failure)
    monkeypatch.setattr(HistorySyncWorker, "_retry_history_job", forbidden_failure)
    monkeypatch.delenv("API_FOOTBALL_MAX_HISTORY_SEASON", raising=False)
    with psycopg.connect(history_database) as connection:
        with connection.transaction():
            connection.execute(
                """INSERT INTO football.product_history_sync_queue
                (provider_competition_id,season) VALUES ('1234567',2026)"""
            )
        parent = ProductSync(
            connection,
            cast(Any, object()),
            tmp_path,
            tmp_path / "unused",
            history_worker_factory=cli._history_worker_factory(
                history_database, "test", "", tmp_path, None
            ),
        )
        with pytest.raises(WorkLeaseLost):
            parent._process_history_queue(1)
        with connection.transaction():
            assert connection.execute("SELECT state FROM football.work_items").fetchall() == [
                ("CANCELLED",)
            ]
        assert not list(tmp_path.rglob("*.json"))
