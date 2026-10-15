import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import psycopg
import pytest
from football.product.history_requests import (
    HistoryDeferred,
    HistoryRequestBudget,
    record_history_check,
)
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.provider_history_scopes import (
    cached_response,
    claim_scope,
    discover_pitchapi,
    enqueue_seasons,
    run_scopes,
)
from football.providers.pitchapi import PitchApiClient, PitchApiHttpResponse, PitchApiResponse

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def test_history_scope_claim_recovers_abandoned_owner(tmp_path: Path) -> None:
    league = "l_Claim01"
    with psycopg.connect(DATABASE_URL) as first, psycopg.connect(DATABASE_URL) as second:
        owner = OperationalProviderSync(first, tmp_path, provider_code="pitchapi")
        contender = OperationalProviderSync(second, tmp_path, provider_code="pitchapi")
        try:
            enqueue_seasons(owner, league, ["2021"])
            first.commit()
            assert claim_scope(owner, league, "2021") == (league, "2021")
            first_token = first.execute(
                "SELECT current_setting('matchforge.history_claim_token')"
            ).fetchone()[0]
            assert claim_scope(contender, league, "2021") is None
            first.execute(
                """UPDATE football.product_provider_history_scopes
                   SET claimed_at = now() - interval '31 minutes'
                   WHERE provider_competition_id = %s AND season_label = '2021'""",
                (league,),
            )
            first.commit()
            assert claim_scope(contender, league, "2021") == (league, "2021")
            second_token = second.execute(
                "SELECT current_setting('matchforge.history_claim_token')"
            ).fetchone()[0]
            assert first_token != second_token
            assert first.execute(
                """SELECT count(*) FROM football.product_provider_history_scopes
                   WHERE provider_competition_id = %s AND claim_token = %s""",
                (league, first_token),
            ).fetchone() == (0,)
        finally:
            first.rollback()
            first.execute(
                "DELETE FROM football.product_provider_history_scopes "
                "WHERE provider_competition_id = %s",
                (league,),
            )
            first.commit()


def test_cache_check_preserves_original_source_time_and_detects_tampering(tmp_path: Path) -> None:
    raw = b'{"data":{"matches":[]}}'
    acquired = datetime.now(UTC) - timedelta(days=2)
    response = PitchApiResponse(
        "/test", acquired, hashlib.sha256(raw).hexdigest(), raw, {"matches": []}
    )
    with psycopg.connect(DATABASE_URL) as connection:
        sync = OperationalProviderSync(
            connection, tmp_path, provider_code="pitchapi", minimum_interval_seconds=0
        )
        snapshot = sync._record_response("league-catalogue-test-cache", response)
        connection.commit()
        assert (
            cached_response(sync, "league-catalogue-test-cache", freshness=timedelta(days=1))
            is None
        )
        record_history_check(connection, "pitchapi", "league-catalogue-test-cache", snapshot)
        connection.commit()
        cached = cached_response(sync, "league-catalogue-test-cache", freshness=timedelta(days=1))
        assert cached is not None and cached.fetched_at == acquired
        assert connection.execute(
            "SELECT acquired_at FROM football.source_snapshots WHERE id = %s", (snapshot,)
        ).fetchone() == (acquired,)
        relative = connection.execute(
            "SELECT manifest_path FROM football.source_snapshots WHERE id = %s", (snapshot,)
        ).fetchone()[0]
        (tmp_path / relative).write_bytes(b"tampered")
        with pytest.raises(ValueError, match="checksum mismatch"):
            cached_response(sync, "league-catalogue-test-cache", freshness=timedelta(days=1))
        connection.rollback()


class EmptyLeagueTransport:
    def __init__(self) -> None:
        self.calls = 0
        self.seasons = [str(datetime.now(UTC).year)]
        self.matches: list[dict[str, Any]] = []

    def get(self, _url: str, **_kwargs: Any) -> PitchApiHttpResponse:
        self.calls += 1
        return PitchApiHttpResponse(
            json.dumps(
                {"data": {"leagues": [{"id": "l_Grow01", "seasons": self.seasons}]}}
                if _url.endswith("/v1/leagues")
                else {"data": {"matches": self.matches}}
            ).encode(),
            "application/json",
        )


def test_bounded_scopes_reuse_closed_history_and_refresh_changing_history(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        sync = OperationalProviderSync(
            connection, tmp_path, provider_code="pitchapi", minimum_interval_seconds=0
        )
        league = "l_Cach01"
        transport = EmptyLeagueTransport()
        client = PitchApiClient("test", transport=transport)
        try:
            enqueue_seasons(sync, league, ["2021", "2022", "2099"])
            connection.commit()
            first = run_scopes(sync, client, budget=2, competition=league)
            assert len(first) == transport.calls == 2
            assert {scope["status"] for scope in first} == {"ADVERTISED_BUT_UNUSABLE"}
            assert connection.execute(
                "SELECT count(*) FROM football.product_provider_history_scopes "
                "WHERE provider_competition_id=%s AND status='SUCCEEDED'",
                (league,),
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*)"
                " FROM football.product_provider_history_scopes"
                " WHERE provider_competition_id = %s AND status = 'PENDING'",
                (league,),
            ).fetchone() == (1,)
            assert len(run_scopes(sync, client, budget=2, competition=league)) == 1
            assert transport.calls == 3
            assert run_scopes(sync, client, budget=2, competition=league) == []
            connection.execute(
                "UPDATE football.product_provider_history_scopes"
                " SET status = 'PENDING', next_attempt_at = now()"
                " WHERE provider_competition_id = %s AND season_label = '2021'",
                (league,),
            )
            connection.commit()
            replay = run_scopes(sync, client, budget=2, competition=league)
            assert len(replay) == 1 and replay[0]["attempted_requests"] == 0
            assert transport.calls == 3
            connection.execute(
                "UPDATE football.product_provider_history_scopes SET next_attempt_at = now()"
                " WHERE provider_competition_id = %s AND season_label = '2099'",
                (league,),
            )
            connection.execute(
                "UPDATE football.product_provider_history_discovery"
                " SET last_attempt_at = now() - interval '25 hours'"
                " WHERE resource_name = %s",
                (f"league-{league}-2099",),
            )
            connection.commit()

            assert len(run_scopes(sync, client, budget=2, competition=league)) == 1
            assert transport.calls == 4
        finally:
            connection.rollback()
            connection.execute(
                "DELETE"
                " FROM football.product_provider_history_scopes WHERE provider_competition_id = %s",
                (league,),
            )
            connection.commit()


def test_due_catalogue_discovers_new_season_without_refetching_fresh_catalogue(
    tmp_path: Path,
) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        sync = OperationalProviderSync(
            connection, tmp_path, provider_code="pitchapi", minimum_interval_seconds=0
        )
        transport = EmptyLeagueTransport()
        client = PitchApiClient("test", transport=transport)
        try:
            assert discover_pitchapi(sync, client, refresh=False) == 1
            assert discover_pitchapi(sync, client, refresh=False) == 1
            assert transport.calls == 1
            transport.seasons.append(str(datetime.now(UTC).year + 1))
            connection.execute(
                "UPDATE football.product_provider_history_discovery"
                " SET last_attempt_at = now() - interval '25 hours'"
                " WHERE provider_code = 'pitchapi' AND resource_name = 'league-catalogue'"
            )
            connection.commit()
            assert discover_pitchapi(sync, client, refresh=False) == 2
            assert transport.calls == 2
            assert connection.execute(
                "SELECT count(*) FROM football.product_provider_history_scopes "
                "WHERE provider_competition_id = 'l_Grow01'"
            ).fetchone() == (2,)
        finally:
            connection.rollback()
            connection.execute(
                "DELETE"
                " FROM football.product_provider_history_scopes"
                " WHERE provider_competition_id = 'l_Grow01'"
            )
            connection.execute(
                "DELETE"
                " FROM football.product_provider_history_discovery"
                " WHERE provider_code = 'pitchapi' AND resource_name = 'league-catalogue'"
            )
            connection.commit()


def test_history_budget_counts_attempts_and_defers_retry_after() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        budget = HistoryRequestBudget(connection, "pitchapi")
        try:
            connection.execute(
                "DELETE FROM football.provider_request_budgets WHERE provider_code = 'pitchapi'"
            )
            connection.commit()

            budget.before_request()
            headers = Message()
            headers["Retry-After"] = "7200"
            with pytest.raises(HistoryDeferred) as failure:
                budget.record_http_error(
                    HTTPError("https://example.invalid", 429, "limited", headers, None)
                )
            assert failure.value.until > datetime.now(UTC) + timedelta(minutes=119)
            with pytest.raises(HistoryDeferred, match="RETRY_AFTER"):
                budget.before_request()
            assert connection.execute(
                "SELECT requests_used, historical_requests_used"
                " FROM football.provider_request_budgets WHERE provider_code = 'pitchapi'"
            ).fetchone() == (1, 1)
            connection.execute(
                "UPDATE football.provider_request_budgets"
                " SET deferred_until = NULL, remaining_requests = 3"
                " WHERE provider_code = 'pitchapi'"
            )
            connection.commit()
            with pytest.raises(HistoryDeferred, match="RESERVED_FOR_LIVE"):
                budget.before_request()
        finally:
            connection.rollback()
            connection.execute(
                "DELETE FROM football.provider_request_budgets WHERE provider_code = 'pitchapi'"
            )
            connection.commit()


def test_live_sync_has_priority_over_history_requests() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        run = connection.execute(
            """INSERT INTO football.product_sync_runs (sync_type, status)
               VALUES ('PITCHAPI_SYNC', 'QUEUED') RETURNING run_id"""
        ).fetchone()[0]
        connection.commit()
        try:
            with pytest.raises(HistoryDeferred, match="LIVE_SYNC_HAS_PRIORITY"):
                HistoryRequestBudget(connection, "pitchapi").before_request()
            assert connection.execute(
                """SELECT requests_used FROM football.provider_request_budgets
                   WHERE provider_code = 'pitchapi' AND window_date = %s""",
                (datetime.now(UTC).date(),),
            ).fetchone() == (0,)
        finally:
            connection.rollback()
            connection.execute("DELETE FROM football.product_sync_runs WHERE run_id = %s", (run,))
            connection.execute(
                "DELETE FROM football.provider_request_budgets WHERE provider_code = 'pitchapi'"
            )
            connection.commit()


def test_retry_after_crosses_utc_midnight_without_resetting_the_deferral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Clock(datetime):
        instant = datetime.now(UTC).replace(hour=23, minute=59, second=59)

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return cls.instant.astimezone(tz or UTC)

    monkeypatch.setattr("football.product.history_requests.datetime", Clock)
    with psycopg.connect(DATABASE_URL) as connection:
        budget = HistoryRequestBudget(connection, "pitchapi")
        try:
            budget.before_request()
            first_day = Clock.instant.date()
            Clock.instant += timedelta(seconds=2)
            headers = Message()
            headers["Retry-After"] = "7200"
            with pytest.raises(HistoryDeferred):
                budget.record_http_error(
                    HTTPError("https://example.invalid", 429, "limited", headers, None)
                )
            with pytest.raises(HistoryDeferred, match="RETRY_AFTER"):
                budget.before_request()
            assert connection.execute(
                """SELECT window_date, requests_used FROM football.provider_request_budgets
                   WHERE provider_code = 'pitchapi' ORDER BY window_date"""
            ).fetchall() == [(first_day, 1), (Clock.instant.date(), 0)]
        finally:
            connection.rollback()
            connection.execute(
                "DELETE FROM football.provider_request_budgets WHERE provider_code = 'pitchapi'"
            )
            connection.commit()


def test_changing_season_records_new_rows_and_preserves_prior_snapshot(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        sync = OperationalProviderSync(
            connection, tmp_path, provider_code="pitchapi", minimum_interval_seconds=0
        )
        league = "l_Grow02"
        season = str(datetime.now(UTC).year)
        transport = EmptyLeagueTransport()
        client = PitchApiClient("test", transport=transport)
        try:
            enqueue_seasons(sync, league, [season])
            connection.commit()
            assert run_scopes(sync, client, budget=2, competition=league)[0]["fetched"] == 0
            resource = f"league-{league}-{season}"
            original = connection.execute(
                "SELECT id, to_jsonb(s) FROM football.source_snapshots s "
                "WHERE source_identity = %s",
                (resource,),
            ).fetchone()
            transport.matches = [
                {
                    "id": identifier,
                    "league": {"id": league, "name": "Test League"},
                    "home_team": {"id": "t_Home01", "name": "Home"},
                    "away_team": {"id": "t_Away01", "name": "Away"},
                    "time_utc": (datetime.now(UTC) - timedelta(days=days)).isoformat(),
                    "status": "finished",
                    "score_home": 1,
                    "score_away": 0,
                }
                for identifier, days in (("m_Grow01", 2), ("m_Grow02", 1))
            ]
            connection.execute(
                """UPDATE football.product_provider_history_scopes SET next_attempt_at = now()
                   WHERE provider_competition_id = %s""",
                (league,),
            )
            connection.execute(
                """UPDATE football.product_provider_history_discovery
                   SET last_attempt_at = now() - interval '25 hours' WHERE resource_name = %s""",
                (resource,),
            )
            connection.commit()
            result = run_scopes(sync, client, budget=2, competition=league)
            assert len(result) == 1 and result[0]["fetched"] == 2
            assert transport.calls == 2
            assert (
                connection.execute(
                    "SELECT to_jsonb(s) FROM football.source_snapshots s WHERE id = %s",
                    (original[0],),
                ).fetchone()[0]
                == original[1]
            )
            assert connection.execute(
                """SELECT count(DISTINCT provider_match_id)
                   FROM football.product_provider_fixture_observations
                   WHERE provider_competition_id = %s""",
                (league,),
            ).fetchone() == (2,)
            assert connection.execute(
                """SELECT count(*) FROM football.product_eligible_match_history
                   WHERE source_provider_code = 'pitchapi'"""
            ).fetchone() == (0,)
        finally:
            connection.rollback()
            connection.execute(
                "DELETE FROM football.product_provider_history_scopes "
                "WHERE provider_competition_id = %s",
                (league,),
            )
            connection.commit()


def test_fotmob_catalogue_uses_retained_primary_relationships_and_preserves_cooldown(
    tmp_path: Path,
) -> None:
    from football.product.provider_history_scopes import _fotmob_primary_ids, discover_fotmob
    from football.providers.fotmob import FotmobClient, FotmobResponse

    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync = OperationalProviderSync(c, tmp_path, provider_code="fotmob")
        payload = {"leagues": [{"id": 943230, "primaryId": 42, "matches": []}]}
        raw = json.dumps(payload).encode()
        sync._record_response(
            "fixtures-primary-test",
            FotmobResponse(
                "test", datetime.now(UTC), hashlib.sha256(raw).hexdigest(), raw, payload
            ),
        )
        assert _fotmob_primary_ids(sync, ["943230", "42", "47"]) == ["42", "47"]
        c.execute(
            """INSERT INTO football.product_provider_history_discovery (provider_code,
                   provider_competition_id,resource_name,last_attempt_at,next_attempt_at,last_error)
               VALUES ('fotmob','42','league-catalogue-42',now(),
                       now()+interval '1 hour','failed')"""
        )
        # No registered catalogue request may bypass an existing parent cooldown.
        result = discover_fotmob(sync, FotmobClient(), budget=0, refresh=False)
        assert result["requests"] == 0
        other = {"leagues": [{"id": 943230, "primaryId": 99, "matches": []}]}
        raw = json.dumps(other).encode()
        sync._record_response(
            "fixtures-primary-other",
            FotmobResponse("test", datetime.now(UTC), hashlib.sha256(raw).hexdigest(), raw, other),
        )
        with pytest.raises(ValueError, match="conflicting retained"):
            _fotmob_primary_ids(sync, ["943230"])


def test_fotmob_scope_reuses_matching_catalogue_bytes_without_a_request(tmp_path: Path) -> None:
    from football.product.provider_history_scopes import _scope_response
    from football.providers.fotmob import FotmobAccessError, FotmobClient, FotmobResponse

    with psycopg.connect(DATABASE_URL) as c:
        sync = OperationalProviderSync(c, tmp_path, provider_code="fotmob")
        year = str(datetime.now(UTC).year)
        payload = {
            "details": {
                "id": 999999,
                "selectedSeason": year,
                "name": "Test league",
                "country": "ENG",
            },
            "fixtures": {"allMatches": []},
        }
        raw = json.dumps(payload).encode()
        acquired = datetime.now(UTC)
        sync._record_response(
            "league-catalogue-999999",
            FotmobResponse("test", acquired, hashlib.sha256(raw).hexdigest(), raw, payload),
        )
        c.commit()
        enqueue_seasons(sync, "999999", [year])
        c.commit()
        assert claim_scope(sync, "999999", year) == ("999999", year)
        # Disabled network access proves the exact retained catalogue satisfies this scope.
        response, network = _scope_response(sync, FotmobClient(), "999999", year, refresh=False)
        assert not network and response.raw == raw and response.fetched_at == acquired
        count = c.execute("SELECT count(*) FROM football.source_resources").fetchone()
        _, network = _scope_response(sync, FotmobClient(), "999999", year, refresh=False)
        assert not network
        assert c.execute("SELECT count(*) FROM football.source_resources").fetchone() == count
        with pytest.raises(FotmobAccessError, match="disabled"):
            _scope_response(sync, FotmobClient(), "999999", str(int(year) - 1), refresh=False)


def test_cached_response_uses_database_clock_without_relaxing_future_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import football.product.provider_history_scopes as scopes

    class BehindClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return datetime.now(UTC) - timedelta(days=1)

    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        acquired = datetime.now(UTC) - timedelta(hours=1)
        raw = b'{"data":{"matches":[]}}'
        sync = OperationalProviderSync(c, tmp_path, provider_code="pitchapi")
        snapshot = sync._record_response(
            "clock-cache",
            PitchApiResponse(
                "test", acquired, hashlib.sha256(raw).hexdigest(), raw, {"data": {"matches": []}}
            ),
        )
        record_history_check(c, "pitchapi", "clock-cache", snapshot)
        monkeypatch.setattr(scopes, "datetime", BehindClock)
        cached = cached_response(sync, "clock-cache", freshness=timedelta(days=1))
        assert cached is not None and cached.fetched_at == acquired
        c.execute(
            "UPDATE football.product_provider_history_discovery "
            "SET last_attempt_at=clock_timestamp()+interval '1 day' "
            "WHERE provider_code='pitchapi' AND resource_name='clock-cache'"
        )
        with pytest.raises(ValueError, match="in the future"):
            cached_response(sync, "clock-cache")
