from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from football.product.api_football import ApiResponse
from football.product.football_data_org import FootballDataResponse
from football.product.sync import ProductSync, _fixture_sync_dates


def test_fixture_sync_dates_include_previous_day_for_result_updates() -> None:
    assert _fixture_sync_dates(date(2026, 10, 3)) == (
        date(2026, 10, 2),
        date(2026, 10, 3),
    )


def test_fixture_sync_dates_include_explicit_backfill_range() -> None:
    assert _fixture_sync_dates(date(2026, 10, 3), date(2026, 9, 29)) == (
        date(2026, 9, 29),
        date(2026, 9, 30),
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2026, 10, 3),
    )


def test_fixture_sync_dates_reject_backfill_start_after_end() -> None:
    with pytest.raises(ValueError, match="fixture backfill start date"):
        _fixture_sync_dates(date(2026, 10, 3), date(2026, 10, 4))


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
