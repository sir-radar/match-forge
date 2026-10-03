from datetime import date

from football.product.sync import _fixture_sync_dates


def test_fixture_sync_dates_include_previous_day_for_result_updates() -> None:
    assert _fixture_sync_dates(date(2026, 10, 3)) == (
        date(2026, 10, 2),
        date(2026, 10, 3),
    )
