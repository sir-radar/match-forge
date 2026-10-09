import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from football.product.api_football import ApiFootballError, ApiResponse, CapabilityStatus
from football.product.cli import _api_football_max_history_season, build_parser
from football.product.domain import MINIMUM_HISTORY_MATCHES
from football.product.football_data_org import FootballDataResponse
from football.product.sync import ProductSync, _fixture_sync_dates, _history_sync_candidates


class _Connection:
    def commit(self) -> None:
        pass


def test_fixture_sync_dates_include_previous_day_for_result_updates() -> None:
    assert _fixture_sync_dates(date(2026, 10, 3)) == (
        date(2026, 10, 2),
        date(2026, 10, 3),
    )


def test_fixture_sync_dates_limit_explicit_backfill_to_live_provider_window() -> None:
    assert _fixture_sync_dates(date(2026, 10, 3), date(2026, 9, 29)) == (
        date(2026, 10, 2),
        date(2026, 10, 3),
    )


def test_fixture_sync_dates_reject_backfill_start_after_end() -> None:
    with pytest.raises(ValueError, match="fixture backfill start date"):
        _fixture_sync_dates(date(2026, 10, 3), date(2026, 10, 4))


def test_history_sync_candidates_prioritize_without_truncating() -> None:
    older = datetime(2026, 10, 1, tzinfo=UTC)
    newer = datetime(2026, 10, 2, tzinfo=UTC)
    leagues = {(39, 2026), (40, 2026), (141, 2026), (999, 2026)}

    selected = _history_sync_candidates(
        leagues,
        {(39, 2026): newer, (40, 2026): older},
    )

    assert selected == [(141, 2026), (999, 2026), (40, 2026), (39, 2026)]


def test_mvp_and_all_sync_use_history_concurrency_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MVP_HISTORY_SYNC_CONCURRENCY", "4")
    parser = build_parser()

    assert parser.parse_args(["sync"]).history_concurrency == 4
    assert parser.parse_args(["sync-all"]).history_concurrency == 4
    assert parser.parse_args(["sync", "--history-concurrency", "2"]).history_concurrency == 2


def test_all_227_history_candidates_are_enqueued() -> None:
    statements: list[tuple[str, tuple[object, ...]]] = []

    class Cursor:
        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
            statements.append((statement, parameters))

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    candidates = [(league_id, 2026) for league_id in range(1, 228)]
    sync = ProductSync(cast(Any, Connection()), cast(Any, object()), Path("data"), Path("artifact"))

    sync._enqueue_history_jobs(candidates)

    inserted = [parameters for statement, parameters in statements if "INSERT INTO" in statement]
    assert len(inserted) == 227
    assert {parameters[:2] for parameters in inserted} == {
        (str(league_id), 2026) for league_id in range(1, 228)
    }


def test_history_queue_honors_concurrency_and_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = deque((UUID(int=league_id), league_id, 2026, 1) for league_id in range(1, 10))
    lock = threading.Lock()
    completed: list[int] = []
    failed: list[int] = []
    batch_started_at: list[datetime] = []

    class Connection:
        def rollback(self) -> None:
            pass

    class Worker:
        connection = Connection()

        def _claim_history_job(self, started_at: datetime) -> tuple[UUID, int, int, int] | None:
            batch_started_at.append(started_at)
            with lock:
                return jobs.popleft() if jobs else None

        def _sync_history_job(self, league_id: int, _season: int) -> tuple[int, int]:
            time.sleep(0.01)
            if league_id == 2:
                raise ValueError("bad competition")
            return league_id, 1

        def _complete_history_job(self, job_id: UUID) -> None:
            completed.append(job_id.int)

        def _retry_history_job(self, *_args: object) -> None:
            raise AssertionError("unexpected retry")

        def _fail_history_job(self, job_id: UUID, _error: Exception) -> None:
            failed.append(job_id.int)

    @contextmanager
    def worker_factory() -> Any:
        yield Worker()

    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, object()),
        Path("data"),
        Path("artifact"),
        history_worker_factory=cast(Any, worker_factory),
    )
    monkeypatch.setattr(sync, "_history_queue_total", lambda: 9)

    result = sync._process_history_queue(3)

    assert result["peak_concurrency"] == 3
    assert result["processed"] == 9
    assert result["succeeded"] == 8
    assert result["failed"] == 1
    assert failed == [2]
    assert sorted(completed) == [1, 3, 4, 5, 6, 7, 8, 9]
    assert len(set(batch_started_at)) == 1


def test_transient_queue_failure_returns_to_pending_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = deque([(UUID(int=1), 39, 2026, 2)])
    retries: list[tuple[UUID, int, str]] = []

    class Connection:
        def rollback(self) -> None:
            pass

    class Worker:
        connection = Connection()

        def _claim_history_job(
            self, _batch_started_at: datetime
        ) -> tuple[UUID, int, int, int] | None:
            return jobs.popleft() if jobs else None

        def _sync_history_job(self, _league_id: int, _season: int) -> tuple[int, int]:
            raise ApiFootballError("rate limited")

        def _complete_history_job(self, _job_id: UUID) -> None:
            raise AssertionError("unexpected completion")

        def _retry_history_job(self, job_id: UUID, attempt_count: int, error: Exception) -> None:
            retries.append((job_id, attempt_count, str(error)))

        def _fail_history_job(self, *_args: object) -> None:
            raise AssertionError("transient failure must not become FAILED")

    @contextmanager
    def worker_factory() -> Any:
        yield Worker()

    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, object()),
        Path("data"),
        Path("artifact"),
        history_worker_factory=cast(Any, worker_factory),
    )
    monkeypatch.setattr(sync, "_history_queue_total", lambda: 1)

    result = sync._process_history_queue(1)

    assert result["pending_retry"] == 1
    assert result["failed"] == 0
    assert retries == [(UUID(int=1), 2, "rate limited")]


def test_history_queue_migration_enforces_states_deduplication_and_recovery() -> None:
    migration = Path(
        "infrastructure/migrations/202610040400_product_history_sync_queue.sql"
    ).read_text()
    implementation = Path("python/football/src/football/product/sync.py").read_text()

    assert "job_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')" in migration
    assert "UNIQUE (provider_competition_id, season)" in migration
    assert "FOR UPDATE SKIP LOCKED" in implementation
    assert "claimed_at < clock_timestamp()" in implementation
    assert "next_attempt_at = clock_timestamp() + %s * interval '1 second'" in implementation
    assert "queue.updated_at < %s" in implementation
    assert "last_status" not in migration


def test_existing_sync_and_history_status_contracts_are_unchanged() -> None:
    sync_runs = Path(
        "infrastructure/migrations/202609300400_historical_backfill_admin_sync.sql"
    ).read_text()
    history_attempts = Path(
        "infrastructure/migrations/202610040200_product_history_sync_attempts.sql"
    ).read_text()

    assert "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')" in sync_runs
    assert "last_status IN ('STORED', 'EMPTY', 'UNAVAILABLE')" in history_attempts


def test_history_sync_uses_api_football_cap_only_after_alternate_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 10, 4, tzinfo=UTC)

    class PrimaryClient:
        def __init__(self) -> None:
            self.seasons: list[int] = []

        def finished_fixtures(self, _league_id: int, season: int) -> ApiResponse:
            self.seasons.append(season)
            return ApiResponse("/fixtures", observed_at, b"{}", ({"fixture": {}},), None)

    class FallbackClient:
        def __init__(self) -> None:
            self.seasons: list[int] = []

        def finished_matches(self, _competition_code: str, season: int) -> FootballDataResponse:
            self.seasons.append(season)
            return FootballDataResponse("/matches", observed_at, b"{}", ())

    client = PrimaryClient()
    fallback = FallbackClient()
    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, client),
        Path("data"),
        Path("artifact"),
        cast(Any, fallback),
        api_football_max_history_season=2024,
    )
    snapshot = UUID("10000000-0000-4000-8000-000000000001")
    monkeypatch.setattr(sync, "_local_history_result", lambda *_args: None)
    monkeypatch.setattr(sync, "_history_sufficient", lambda *_args: False)
    monkeypatch.setattr(sync, "_record_response", lambda *_args: snapshot)
    monkeypatch.setattr(sync, "_record_fallback_response", lambda *_args: snapshot)
    monkeypatch.setattr(sync, "_competition_id", lambda *_args: snapshot)
    monkeypatch.setattr(sync, "_store_history", lambda *_args: 1)
    monkeypatch.setattr(sync, "_store_fallback_history", lambda *_args: 0)
    monkeypatch.setattr(sync, "_record_history_sync_attempt", lambda *_args: None)

    result = sync._sync_league_history(39, 2026)

    assert fallback.seasons == [2026, 2025]
    assert client.seasons == [2024]
    assert result == (snapshot, observed_at, 1)


def test_history_sync_rejects_invalid_api_football_season_cap() -> None:
    with pytest.raises(ValueError, match="api_football_max_history_season"):
        ProductSync(
            cast(Any, _Connection()),
            cast(Any, object()),
            Path("data"),
            Path("artifact"),
            api_football_max_history_season=0,
        )


def test_history_season_cap_is_api_football_specific(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MVP_MAX_HISTORY_SEASON", "2020")
    monkeypatch.setenv("API_FOOTBALL_MAX_HISTORY_SEASON", "2024")

    assert _api_football_max_history_season() == 2024


def test_history_sync_prefers_alternate_current_data_over_capped_api_football(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 10, 4, tzinfo=UTC)

    class PrimaryClient:
        def finished_fixtures(self, _league_id: int, _season: int) -> ApiResponse:
            raise AssertionError("capped API-Football history must remain last fallback")

    class FallbackClient:
        def finished_matches(self, _competition_code: str, season: int) -> FootballDataResponse:
            assert season == 2026
            return FootballDataResponse("/matches", observed_at, b"{}", ({"id": 1},))

    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, PrimaryClient()),
        Path("data"),
        Path("artifact"),
        cast(Any, FallbackClient()),
        api_football_max_history_season=2024,
    )
    snapshot = UUID("10000000-0000-4000-8000-000000000001")
    monkeypatch.setattr(sync, "_local_history_result", lambda *_args: None)
    monkeypatch.setattr(sync, "_history_sufficient", lambda *_args: True)
    monkeypatch.setattr(sync, "_record_fallback_response", lambda *_args: snapshot)
    monkeypatch.setattr(sync, "_competition_id", lambda *_args: snapshot)
    monkeypatch.setattr(sync, "_store_fallback_history", lambda *_args: 1)
    monkeypatch.setattr(sync, "_record_history_sync_attempt", lambda *_args: None)

    assert sync._sync_league_history(39, 2026) == (snapshot, observed_at, 1)


def test_history_sync_uses_alternate_provider_after_transient_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 10, 4, tzinfo=UTC)

    class PrimaryClient:
        def finished_fixtures(self, _league_id: int, _season: int) -> ApiResponse:
            raise ApiFootballError("temporary timeout")

    class FallbackClient:
        def finished_matches(self, _competition_code: str, season: int) -> FootballDataResponse:
            assert season == 2026
            return FootballDataResponse("/matches", observed_at, b"{}", ({"id": 1},))

    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, PrimaryClient()),
        Path("data"),
        Path("artifact"),
        cast(Any, FallbackClient()),
    )
    snapshot = UUID("10000000-0000-4000-8000-000000000001")
    monkeypatch.setattr(sync, "_local_history_result", lambda *_args: None)
    monkeypatch.setattr(sync, "_history_sufficient", lambda *_args: True)
    monkeypatch.setattr(sync, "_record_fallback_response", lambda *_args: snapshot)
    monkeypatch.setattr(sync, "_competition_id", lambda *_args: snapshot)
    monkeypatch.setattr(sync, "_store_fallback_history", lambda *_args: 1)
    monkeypatch.setattr(sync, "_record_history_sync_attempt", lambda *_args: None)

    assert sync._sync_league_history(39, 2026) == (snapshot, observed_at, 1)


def test_history_sync_records_plan_restriction_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[tuple[object, ...]] = []

    class PrimaryClient:
        def finished_fixtures(self, _league_id: int, _season: int) -> ApiResponse:
            raise ApiFootballError(
                "season unavailable on plan",
                capability_status=CapabilityStatus.PLAN_RESTRICTION,
            )

    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, PrimaryClient()),
        Path("data"),
        Path("artifact"),
    )
    monkeypatch.setattr(sync, "_local_history_result", lambda *_args: None)
    monkeypatch.setattr(sync, "_history_sufficient", lambda *_args: False)
    monkeypatch.setattr(
        sync,
        "_record_history_sync_attempt",
        lambda *args: attempts.append(args),
    )

    assert sync._sync_league_history(999, 2026) is None
    assert attempts[0][3:] == (
        "UNAVAILABLE",
        ("API_FOOTBALL_REQUESTED", "INSUFFICIENT_HISTORY"),
        (),
    )


def test_history_sync_uses_cross_competition_local_history_for_promoted_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 10, 4, tzinfo=UTC)
    snapshot = UUID("10000000-0000-4000-8000-000000000001")
    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, object()),
        Path("data"),
        Path("artifact"),
        api_football_max_history_season=2024,
    )
    monkeypatch.setattr(sync, "_local_history_result", lambda *_args: (snapshot, observed_at, 0))
    recorded: list[tuple[object, ...]] = []
    monkeypatch.setattr(sync, "_record_history_sync_attempt", lambda *args: recorded.append(args))

    assert sync._sync_league_history(39, 2026) == (snapshot, observed_at, 0)
    assert recorded[0][-2:] == (("LOCAL_HISTORY",), ())


def test_history_sufficiency_counts_previous_competition_matches() -> None:
    class Cursor:
        statement = ""
        parameters: tuple[object, ...] = ()

        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
            self.statement = statement
            self.parameters = parameters

        def fetchone(self) -> tuple[bool]:
            return (True,)

    cursor = Cursor()

    class Connection:
        def cursor(self) -> Cursor:
            return cursor

    sync = ProductSync(
        cast(Any, Connection()),
        cast(Any, object()),
        Path("data"),
        Path("artifact"),
    )

    assert sync._history_sufficient(39, 2026)
    assert "history.competition_id" not in cursor.statement
    assert cursor.parameters[-1] == MINIMUM_HISTORY_MATCHES


def test_transient_history_failure_does_not_record_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PrimaryClient:
        def finished_fixtures(self, _league_id: int, _season: int) -> ApiResponse:
            raise ApiFootballError("temporary timeout")

    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, PrimaryClient()),
        Path("data"),
        Path("artifact"),
        api_football_max_history_season=2024,
    )
    monkeypatch.setattr(sync, "_local_history_result", lambda *_args: None)
    monkeypatch.setattr(sync, "_history_sufficient", lambda *_args: False)
    recorded: list[tuple[object, ...]] = []
    monkeypatch.setattr(sync, "_record_history_sync_attempt", lambda *args: recorded.append(args))

    with pytest.raises(ApiFootballError, match="temporary timeout"):
        sync._sync_league_history(999, 2026)
    assert recorded == []


def test_history_storage_deduplicates_cross_provider_fixture_and_keeps_xg_separate() -> None:
    migration = Path("infrastructure/migrations/202609290100_mvp_product.sql").read_text()
    implementation = Path("python/football/src/football/product/sync.py").read_text()

    assert "fixture_id uuid PRIMARY KEY" in migration
    assert "ON CONFLICT (fixture_id) DO NOTHING" in implementation
    assert (
        "home_xg"
        not in implementation.split("def _store_fallback_history", 1)[1].split(
            "def _store_fallback_standings", 1
        )[0]
    )


def test_fixture_sync_includes_stored_future_competitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, object()),
        Path("data"),
        Path("artifact"),
    )
    monkeypatch.setattr(sync, "_store_requested_fixtures", lambda _date: (1, [(39, 2026)]))
    monkeypatch.setattr(sync, "_scheduled_history_leagues", lambda: {(999, 2026)})
    monkeypatch.setattr(sync, "_history_sync_attempts", lambda _leagues: {})

    fixture_count, leagues = sync._sync_fixtures((date(2026, 10, 4),))

    assert fixture_count == 1
    assert leagues == [(39, 2026), (999, 2026)]


def test_run_uses_history_for_dates_before_live_provider_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 10, 3, tzinfo=UTC)

    class PrimaryClient:
        def competitions(self) -> ApiResponse:
            return ApiResponse("/leagues", observed_at, b"{}", (), None)

    sync = ProductSync(
        cast(Any, _Connection()),
        cast(Any, PrimaryClient()),
        Path("data"),
        Path("artifact"),
    )
    provider_dates: list[date] = []
    history_ranges: list[tuple[date, date]] = []
    monkeypatch.setattr(
        sync,
        "_record_response",
        lambda *_args: UUID("10000000-0000-4000-8000-000000000001"),
    )
    monkeypatch.setattr(sync, "_store_competitions", lambda *_args: 0)

    def sync_fixtures(dates: tuple[date, ...]) -> tuple[int, list[Any]]:
        provider_dates.extend(dates)
        return 0, []

    def backfill_fixtures(start: date, end: date, _observed_at: datetime) -> int:
        history_ranges.append((start, end))
        return 0

    monkeypatch.setattr(sync, "_sync_fixtures", sync_fixtures)
    monkeypatch.setattr(sync, "_recover_abandoned_history_jobs", lambda: None)
    monkeypatch.setattr(sync, "_enqueue_history_jobs", lambda _candidates: None)
    monkeypatch.setattr(
        sync,
        "_process_history_queue",
        lambda _concurrency: {
            "total": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "pending_retry": 0,
            "peak_concurrency": 0,
            "history_matches": 0,
            "standings_rows": 0,
        },
    )
    monkeypatch.setattr(sync, "backfill_fixtures_from_history", backfill_fixtures)
    monkeypatch.setattr(sync, "_settle_external_predictions", lambda *_args: 0)
    monkeypatch.setattr(sync, "refresh_forecasts", lambda *_args: 0)

    sync.run(date(2026, 10, 3), fixture_from_date=date(2019, 12, 30))

    assert provider_dates == [date(2026, 10, 2), date(2026, 10, 3)]
    assert history_ranges == [(date(2019, 12, 30), date(2026, 10, 3))]


def test_empty_primary_fixture_response_uses_configured_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 10, 3, tzinfo=UTC)

    class PrimaryClient:
        def fixtures_for_date(self, _requested_date: date) -> ApiResponse:
            return ApiResponse("/fixtures", observed_at, b"{}", (), None)

    class FallbackClient:
        def fixtures_for_date(self, _requested_date: date) -> FootballDataResponse:
            return FootballDataResponse("/matches", observed_at, b"{}", ({"id": 1},))

    sync = ProductSync(
        cast(Any, None),
        cast(Any, PrimaryClient()),
        Path("data"),
        Path("artifact"),
        cast(Any, FallbackClient()),
    )
    snapshot_id = UUID("10000000-0000-4000-8000-000000000001")
    monkeypatch.setattr(sync, "_record_fallback_response", lambda *_args: snapshot_id)
    monkeypatch.setattr(
        sync,
        "_store_fallback_fixtures",
        lambda rows, snapshot, fetched_at: (len(rows), [(39, 2026)]),
    )

    assert sync._store_requested_fixtures(date(2026, 10, 3)) == (1, [(39, 2026)])
