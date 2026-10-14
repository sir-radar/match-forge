import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from football.product.api_football import (
    ApiFootballError,
    PostgresApiFootballBudget,
    RequestReservation,
)


@pytest.fixture
def budget() -> Iterator[PostgresApiFootballBudget]:
    url = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "DELETE FROM football.provider_request_budgets WHERE provider_code = 'api_football'"
        )
    yield PostgresApiFootballBudget(url)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "DELETE FROM football.provider_request_budgets WHERE provider_code = 'api_football'"
        )


def test_atomic_reservations_and_late_responses_cannot_reopen_exhaustion(
    budget: PostgresApiFootballBudget,
) -> None:
    with psycopg.connect(budget.database_url, autocommit=True) as connection:
        connection.execute(
            """INSERT INTO football.provider_request_budgets (
                   provider_code,window_date,remaining_requests)
               VALUES ('api_football',(clock_timestamp() AT TIME ZONE 'UTC')::date,3)"""
        )

    def reserve(_index: int) -> RequestReservation | None:
        try:
            return budget.before_request()
        except ApiFootballError:
            return None

    with ThreadPoolExecutor(max_workers=12) as pool:
        reservations = [item for item in pool.map(reserve, range(12)) if item is not None]
    assert len(reservations) == 3
    assert {item.sequence for item in reservations} == {1, 2, 3}
    for reservation in sorted(reservations, key=lambda item: -item.sequence):
        budget.record_response(reservation, 100, 100)
    with psycopg.connect(budget.database_url) as connection:
        assert connection.execute(
            """SELECT requests_used,remaining_requests,exhausted
               FROM football.provider_request_budgets WHERE provider_code='api_football'"""
        ).fetchone() == (3, 0, True)


def test_unknown_quota_stays_unknown_and_accounts_for_later_reservations(
    budget: PostgresApiFootballBudget,
) -> None:
    first, second = budget.before_request(), budget.before_request()
    budget.record_response(first, None, None)
    with psycopg.connect(budget.database_url) as connection:
        assert connection.execute(
            """SELECT remaining_requests,exhausted FROM football.provider_request_budgets
               WHERE provider_code='api_football'"""
        ).fetchone() == (None, False)
    budget.record_response(first, 5, None)
    budget.record_response(second, 4, None)
    budget.record_response(first, 50, None)
    with psycopg.connect(budget.database_url) as connection:
        assert connection.execute(
            """SELECT requests_used,remaining_requests,exhausted
               FROM football.provider_request_budgets WHERE provider_code='api_football'"""
        ).fetchone() == (2, 4, False)


def test_known_minute_budget_is_reserved_atomically_without_daily_exhaustion(
    budget: PostgresApiFootballBudget,
) -> None:
    initial = budget.before_request()
    budget.record_response(initial, 100, 3)

    def reserve(_index: int) -> RequestReservation | None:
        try:
            return budget.before_request()
        except ApiFootballError:
            return None

    with ThreadPoolExecutor(max_workers=12) as pool:
        reservations = [item for item in pool.map(reserve, range(12)) if item is not None]
    assert len(reservations) == 3
    for reservation in sorted(reservations, key=lambda item: -item.sequence):
        budget.record_response(reservation, 100, 100)
    with psycopg.connect(budget.database_url) as connection:
        assert connection.execute(
            """SELECT requests_used,remaining_requests,exhausted,minute_remaining
               FROM football.provider_request_budgets WHERE provider_code='api_football'"""
        ).fetchone() == (4, 97, False, 0)


def test_minute_limit_and_retry_after_do_not_exhaust_daily_quota(
    budget: PostgresApiFootballBudget,
) -> None:
    reservation = budget.before_request()
    budget.record_response(reservation, 50, 0)
    budget.record_rejection(reservation, "HTTP 429 rate limit", "120")
    with pytest.raises(ApiFootballError, match="request suppressed"):
        budget.before_request()
    with psycopg.connect(budget.database_url) as connection:
        assert connection.execute(
            """SELECT requests_used,remaining_requests,exhausted,minute_remaining,
                      deferred_until > clock_timestamp()
               FROM football.provider_request_budgets WHERE provider_code='api_football'"""
        ).fetchone() == (1, 50, False, 0, True)


def test_recent_minute_quota_does_not_reset_at_an_assumed_wall_clock_boundary(
    budget: PostgresApiFootballBudget,
) -> None:
    initial = budget.before_request()
    budget.record_response(initial, 100, 1)
    with psycopg.connect(budget.database_url, autocommit=True) as connection:
        connection.execute(
            """UPDATE football.provider_request_budgets
               SET minute_window=clock_timestamp()-interval '50 seconds'
               WHERE provider_code='api_football'"""
        )
    budget.before_request()
    with pytest.raises(ApiFootballError, match="request suppressed"):
        budget.before_request()


def test_utc_rollover_isolated_from_old_responses_and_exhaustion(
    budget: PostgresApiFootballBudget,
) -> None:
    previous = datetime.now(UTC) - timedelta(days=1)
    old = RequestReservation(previous.date(), 1, previous)
    with psycopg.connect(budget.database_url, autocommit=True) as connection:
        connection.execute(
            """INSERT INTO football.provider_request_budgets (
                   provider_code,window_date,requests_used,remaining_requests,exhausted)
               VALUES ('api_football',%s,1,0,true)""",
            (old.window_date,),
        )
    current = budget.before_request()
    assert current.window_date > old.window_date
    budget.record_response(old, 100, 100)
    with psycopg.connect(budget.database_url) as connection:
        rows = connection.execute(
            """SELECT window_date,remaining_requests,exhausted
               FROM football.provider_request_budgets
               WHERE provider_code='api_football' ORDER BY window_date"""
        ).fetchall()
    assert rows == [(old.window_date, 0, True), (current.window_date, None, False)]
