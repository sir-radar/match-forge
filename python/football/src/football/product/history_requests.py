"""Reserve provider requests for live work and retain historical fetch checks."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError
from uuid import UUID

from psycopg import Connection

from football.providers.base import ProviderFetchError


class HistoryDeferred(ProviderFetchError):
    def __init__(self, reason: str, until: datetime) -> None:
        super().__init__(reason)
        self.until = until


def history_freshness() -> timedelta:
    seconds = int(os.environ.get("MATCHFORGE_HISTORY_FRESHNESS_SECONDS", "86400"))
    if seconds <= 0:
        raise ValueError("historical freshness must be positive")
    return timedelta(seconds=seconds)


class HistoryRequestBudget:
    def __init__(self, connection: Connection[Any], provider: str) -> None:
        self.connection = connection
        self.provider = provider
        self.window_date = datetime.now(UTC).date()

    def before_request(self) -> None:
        now = datetime.now(UTC)
        self.connection.execute(
            """INSERT INTO football.provider_request_budgets
               (provider_code, window_date, deferred_until)
               VALUES (%s, %s, (SELECT max(deferred_until) FROM football.provider_request_budgets
                              WHERE provider_code = %s)) ON CONFLICT DO NOTHING""",
            (self.provider, now.date(), self.provider),
        )
        state = self.connection.execute(
            """SELECT exhausted, remaining_requests,
                      GREATEST(deferred_until, (SELECT max(previous.deferred_until)
                          FROM football.provider_request_budgets previous
                          WHERE previous.provider_code = %s))
               FROM football.provider_request_budgets
               WHERE provider_code = %s AND window_date = %s FOR UPDATE""",
            (self.provider, self.provider, now.date()),
        ).fetchone()
        live = self.connection.execute(
            """SELECT EXISTS (SELECT 1 FROM football.product_sync_runs
               WHERE sync_type = %s AND status IN ('QUEUED', 'RUNNING'))""",
            ("FOTMOB_SYNC" if self.provider == "fotmob" else "PITCHAPI_SYNC",),
        ).fetchone()
        assert state is not None and live is not None
        reason = None
        until = now + timedelta(hours=1)
        if state[2] and state[2] > now:
            reason, until = "PROVIDER_RETRY_AFTER", state[2]
        elif state[0]:
            reason = "PROVIDER_BUDGET_EXHAUSTED"
        elif state[1] is not None:
            # These providers advertise no daily allowance. Any recorded finite
            # remainder is conserved for live work until its allowance is established.
            reason = "QUOTA_RESERVED_FOR_LIVE"
        elif live[0]:
            reason = "LIVE_SYNC_HAS_PRIORITY"
        if reason:
            self.connection.commit()
            raise HistoryDeferred(reason, until)
        self.connection.execute(
            """UPDATE football.provider_request_budgets
               SET requests_used = requests_used + 1,
                   historical_requests_used = historical_requests_used + 1,
                   updated_at = clock_timestamp()
               WHERE provider_code = %s AND window_date = %s""",
            (self.provider, now.date()),
        )
        self.connection.commit()
        self.window_date = now.date()

    def record_http_error(self, error: HTTPError) -> None:
        if error.code != 429:
            return
        now = datetime.now(UTC)
        retry = error.headers.get("Retry-After") if error.headers else None
        error.close()
        until = retry_after_time(retry, now)
        self.connection.execute(
            """UPDATE football.provider_request_budgets
               SET deferred_until = GREATEST(deferred_until, %s),
                   last_error = 'HTTP 429', updated_at = clock_timestamp()
               WHERE provider_code = %s AND window_date = %s""",
            (until, self.provider, self.window_date),
        )
        self.connection.commit()
        raise HistoryDeferred("PROVIDER_RETRY_AFTER", until)


def retry_after_time(value: str | None, now: datetime) -> datetime:
    if value:
        try:
            seconds = float(value)
            return now + timedelta(seconds=max(seconds, 0))
        except (ValueError, OverflowError):
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is not None:
                    return max(now, parsed)
            except (ValueError, TypeError, OverflowError):
                pass
    return now + timedelta(hours=1)


def record_history_check(
    connection: Connection[Any],
    provider: str,
    resource: str,
    snapshot: UUID,
    *,
    competition: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO football.product_provider_history_discovery (
               provider_code, provider_competition_id, resource_name, source_snapshot_id,
               last_attempt_at, next_attempt_at)
           VALUES (%s, %s, %s, %s, clock_timestamp(), clock_timestamp() + %s)
           ON CONFLICT (provider_code, resource_name) DO UPDATE
           SET source_snapshot_id = EXCLUDED.source_snapshot_id,
               last_attempt_at = EXCLUDED.last_attempt_at,
               next_attempt_at = EXCLUDED.next_attempt_at, last_error = NULL""",
        (provider, competition, resource, snapshot, history_freshness()),
    )
