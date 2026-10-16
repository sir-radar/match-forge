import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from football.product.history_requests import HistoryDeferred, HistoryRequestBudget
from football.product.operational_provider_sync import (
    DetailCounts,
    FixtureObservation,
    OperationalProviderSync,
)
from football.providers.pitchapi import PitchApiFixture, PitchApiResponse


def test_twelve_live_fixtures_rotate_across_days_and_preserve_cache_and_failure(
    tmp_path: Path,
) -> None:
    rows = tuple(
        (
            PitchApiFixture(
                provider_match_id=f"m_Fair{index:04}",
                kickoff_at=datetime.now(UTC) - timedelta(days=index % 2),
                provider_competition_id="l_Fair0000",
                provider_home_team_id="t_FairHome",
                provider_away_team_id="t_FairAway",
                home_team_name="Home",
                away_team_name="Away",
                status="LIVE",
                provider_status="LIVE",
                home_score=0,
                away_score=0,
                minute=30,
                added_time=None,
                period=None,
                source_updated_at=None,
                observed_at=datetime.now(UTC),
            ),
            uuid4(),
        )
        for index in range(12)
    )
    names = [f"match-{row.provider_match_id}-details" for row, _ in rows]
    chosen: list[str] = []
    calls: list[tuple[str, str]] = []

    class Client:
        def match(self, match_id: str) -> PitchApiResponse:
            return self.match_resource(match_id, "")

        def match_resource(self, match_id: str, resource: str) -> PitchApiResponse:
            calls.append((match_id, resource))
            if match_id == "m_Fair0000" and resource == "events":
                raise RuntimeError("synthetic detail failure")
            raw = b"{}"
            return PitchApiResponse(
                path=f"/v1/matches/{match_id}/{resource}",
                fetched_at=datetime.now(UTC),
                raw=raw,
                data={},
                sha256=hashlib.sha256(raw).hexdigest(),
            )

    def detail(row: FixtureObservation) -> DetailCounts:
        provider_id = row.provider_match_id
        chosen.append(provider_id)
        assert isinstance(row, PitchApiFixture)
        return replace(
            sync._pitchapi_details(Client(), row),
            fresh_until=datetime.now(UTC) + timedelta(minutes=15),
        )

    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        sync = OperationalProviderSync(
            connection, tmp_path, provider_code="pitchapi", minimum_interval_seconds=0
        )
        try:
            for _cycle in range(3):
                counts, bulk, live = sync._fetch_prioritized_details(
                    rows, detail, bulk_limit=0, live_limit=4
                )
                assert (bulk, live, counts.attempted_requests) == (0, 4, 32)
            assert len(chosen) == len(set(chosen)) == 12
            assert len(calls) == 96
            counts, bulk, live = sync._fetch_prioritized_details(
                rows, detail, bulk_limit=0, live_limit=4
            )
            assert (bulk, live, counts.attempted_requests) == (0, 0, 0)
            failed = connection.execute(
                """SELECT failed_requests,last_error,last_success_at,
                          next_attempt_at < clock_timestamp()+interval '5 minutes'
                   FROM football.product_provider_refresh_state
                   WHERE provider_code='pitchapi' AND resource_name='match-m_Fair0000-details'"""
            ).fetchone()
            assert failed == (1, "DETAIL_REQUEST_FAILED", None, True)
            assert connection.execute(
                """SELECT next_attempt_at > clock_timestamp()+interval '10 minutes'
                   FROM football.product_provider_refresh_state
                   WHERE provider_code='pitchapi' AND resource_name='match-m_Fair0001-details'"""
            ).fetchone() == (True,)
            connection.execute(
                """UPDATE football.product_provider_refresh_state
                   SET next_attempt_at=clock_timestamp()-interval '1 second'
                   WHERE provider_code='pitchapi' AND resource_name='match-m_Fair0000-details'"""
            )
            connection.commit()

            counts, bulk, live = sync._fetch_prioritized_details(
                rows, detail, bulk_limit=1, live_limit=0, recovery_ids=frozenset({"m_Fair0000"})
            )
            assert (bulk, live, counts.attempted_requests) == (1, 0, 8)
        finally:
            connection.rollback()
            connection.execute(
                """DELETE FROM football.product_provider_refresh_state
                   WHERE provider_code='pitchapi' AND resource_name=ANY(%s)""",
                (names,),
            )
            connection.commit()


def test_live_requests_are_counted_while_bulk_work_yields_to_live() -> None:
    run = uuid4()
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        try:
            connection.execute(
                "DELETE FROM football.provider_request_budgets WHERE provider_code='pitchapi'"
            )
            connection.execute(
                """INSERT INTO football.product_sync_runs(run_id,sync_type,status)
                   VALUES (%s,'PITCHAPI_SYNC','QUEUED')""",
                (run,),
            )
            connection.commit()
            bulk = HistoryRequestBudget(
                connection, "pitchapi", historical=False, yield_to_live=True
            )
            with pytest.raises(HistoryDeferred, match="LIVE_SYNC_HAS_PRIORITY"):
                bulk.before_request()
            live = HistoryRequestBudget(connection, "pitchapi", historical=False)
            live.before_request()
            assert connection.execute(
                """SELECT requests_used,historical_requests_used
                   FROM football.provider_request_budgets WHERE provider_code='pitchapi'"""
            ).fetchone() == (1, 0)
        finally:
            connection.rollback()
            connection.execute(
                "DELETE FROM football.provider_request_budgets WHERE provider_code='pitchapi'"
            )
            connection.execute("DELETE FROM football.product_sync_runs WHERE run_id=%s", (run,))
            connection.commit()


def test_calendar_batch_spends_live_details_after_both_dates_are_ingested(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    days: list[object] = []
    detailed: list[str] = []

    class Client:
        def matches_by_date(self, day: object, *, status: str) -> PitchApiResponse:
            days.append(day)
            offset = 6 if day == today else 0
            matches = [
                {
                    "id": f"m_Day{index:03}",
                    "league": {"id": "l_Day001", "name": "Calendar test"},
                    "home_team": {"id": f"t_Ho{index:04}", "name": f"Home {index}"},
                    "away_team": {"id": f"t_Aw{index:04}", "name": f"Away {index}"},
                    "time_utc": f"{day}T00:00:00Z",
                    "status": "live",
                    "score_home": 0,
                    "score_away": 0,
                }
                for index in range(offset, offset + 6)
            ]
            raw = json.dumps(
                {
                    "data": {
                        "matches": matches,
                        "leagues": [{"id": "l_Day001", "country_code": "ENG"}],
                    }
                }
            ).encode()
            return PitchApiResponse(
                path=f"/v1/date/{day}",
                fetched_at=datetime.now(UTC),
                raw=raw,
                data=json.loads(raw)["data"],
                sha256=hashlib.sha256(raw).hexdigest(),
            )

    def detail(_client: object, row: PitchApiFixture) -> DetailCounts:
        detailed.append(row.provider_match_id)
        return DetailCounts(1, 1)

    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        sync = OperationalProviderSync(
            connection, tmp_path, provider_code="pitchapi", minimum_interval_seconds=0
        )
        sync._pitchapi_details = detail
        for _cycle in range(3):
            result = sync.sync_pitchapi(
                Client(), today - timedelta(days=1), today, details_limit=0, live_details_limit=4
            )
            assert result["attempted_requests"] == 6
        assert days == [today, today - timedelta(days=1)] * 3
        assert len(detailed) == len(set(detailed)) == 12
        assert all(int(value[-3:]) >= 6 for value in detailed[:4])
