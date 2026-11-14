"""Pre-P03 result recovery acceptance on a disposable PostgreSQL database.

Provider responses are simulated; identity, canonical, history and scheduling rules
run against the real schema.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.product.api_football import ApiFootballClient, ApiFootballError, ApiResponse
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.result_recovery import (
    RecoveryRequest,
    recover_api_football_results,
    recover_provider_results,
    summarize_recovery,
)
from football.product.sync import ProductSync
from football.providers.pitchapi import PitchApiResponse, normalize_pitchapi_matches

from tests.integration.test_operational_provider_sync import seed_reviewed_operational_fixture
from tests.integration.test_operational_recovery import (
    recovery_connection as recovery_connection,
)


class ApiFootballWorld:
    """Simulated API-Football dates over real identity, canonical and history rules."""

    def __init__(
        self,
        connection: psycopg.Connection[Any],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fixtures: dict[int, tuple[datetime, str]],
    ) -> None:
        self.connection = connection
        self.client = ApiFootballClient("test")
        self.sync = ProductSync(connection, self.client, tmp_path, tmp_path / "unused")
        self.refresh = OperationalProviderSync(
            connection, tmp_path, provider_code="api_football", minimum_interval_seconds=0
        )
        self.calls: list[date] = []
        self.failures: list[Exception] = []
        self.rows: dict[int, dict[str, Any]] = {}
        for number, (kickoff, short) in fixtures.items():
            self.rows[number] = {
                "fixture": {
                    "id": number,
                    "date": kickoff.isoformat(),
                    "status": {"short": short},
                    "venue": {},
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": number * 10, "name": f"Home {number}"},
                    "away": {"id": number * 10 + 1, "name": f"Away {number}"},
                },
                "goals": {"home": None, "away": None},
            }
        for day in sorted({self._day(row) for row in self.rows.values()}):
            acquired = min(
                datetime.fromisoformat(row["fixture"]["date"]) for row in self.rows.values()
            ) - timedelta(hours=1)
            first = self._response(day, acquired)
            snapshot = self.sync._record_response(f"fixtures-{day}", first)
            self.sync._store_fixtures(first.rows, snapshot, acquired)
        with connection.transaction():
            # Native ID, kickoff, season and orientation matching run for real; entity
            # admission has its own tests and is stubbed here.
            connection.execute(
                """CREATE OR REPLACE FUNCTION football.product_mapping_trusted(
                       kind text, mapping_key uuid, canonical_key uuid)
                   RETURNS boolean LANGUAGE sql STABLE AS 'SELECT true'"""
            )
            connection.execute("UPDATE football.product_fixtures SET identity_status='VERIFIED'")
        connection.commit()
        monkeypatch.setattr(self.client, "fixtures_for_date", self.fetch)

    @staticmethod
    def _day(row: dict[str, Any]) -> date:
        return datetime.fromisoformat(row["fixture"]["date"]).astimezone(UTC).date()

    def _response(self, day: date, fetched_at: datetime) -> ApiResponse:
        rows = tuple(json.loads(json.dumps(r)) for r in self.rows.values() if self._day(r) == day)
        return ApiResponse(
            "/fixtures", fetched_at, json.dumps({"response": rows}).encode(), rows, None
        )

    def fetch(self, day: date) -> ApiResponse:
        self.calls.append(day)
        if self.failures:
            raise self.failures.pop(0)
        return self._response(day, datetime.now(UTC))

    def finish(self, number: int, home: int, away: int, short: str = "FT") -> None:
        self.rows[number]["fixture"]["status"] = {"short": short}
        self.rows[number]["goals"] = {"home": home, "away": away}

    def fixture(self, number: int) -> UUID:
        row = self.connection.execute(
            """SELECT m.match_id FROM football.match_provider_mappings m
               JOIN football.providers p ON p.id=m.provider_id AND p.code='api_football'
               WHERE m.provider_match_id=%s AND m.valid_to IS NULL""",
            (str(number),),
        ).fetchone()
        self.connection.commit()
        assert row is not None
        return row[0]

    def run(self, **request: Any) -> dict[str, object]:
        return recover_api_football_results(
            self.sync,
            self.refresh,
            limit=request.get("limit", 4),
            day=request.get("day"),
            fixture_id=request.get("fixture_id"),
        )

    def state(self, number: int) -> tuple[Any, ...]:
        row = self.connection.execute(
            """SELECT outcome,purpose,attempts,last_checked_at,
                      CASE WHEN next_check_at='infinity' THEN NULL ELSE next_check_at END,
                      next_check_at='infinity'
               FROM football.product_result_recovery_state
               WHERE fixture_id=%s AND provider_code='api_football'""",
            (self.fixture(number),),
        ).fetchone()
        self.connection.commit()
        assert row is not None
        return tuple(row)

    def due_now(self, number: int) -> None:
        self.connection.execute(
            """UPDATE football.product_result_recovery_state SET next_check_at=now()
               WHERE fixture_id=%s""",
            (self.fixture(number),),
        )
        self.connection.commit()


OLD = datetime(2026, 10, 9, 23, 50, tzinfo=UTC)


def test_manual_requests_bypass_internal_schedule_and_report_outcomes(
    recovery_connection: psycopg.Connection[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = ApiFootballWorld(recovery_connection, tmp_path, monkeypatch, {802: (OLD, "NS")})
    fixture = world.fixture(802)

    first = world.run()
    assert first["outcomes"] == {"NOT_YET_PUBLISHED": 1} and first["recovered"] == 0
    assert first["successful_requests"] == 1 and world.calls == [OLD.date()]
    outcome, _purpose, _attempts, _checked, following, _never = world.state(802)
    assert outcome == "NOT_YET_PUBLISHED" and following > datetime.now(UTC)
    # Ordinary schedule: an immediate automatic run selects nothing.
    assert world.run()["selected_dates"] == 0 and len(world.calls) == 1

    # An operator's date request is not blocked by the background check.
    by_date = world.run(day=OLD.date())
    assert by_date["outcomes"] == {"NOT_YET_PUBLISHED": 1} and len(world.calls) == 2
    assert world.state(802)[2] == 2  # same outcome, second attempt
    summary = summarize_recovery(
        recovery_connection, RecoveryRequest(4, OLD.date()), {"api_football": by_date}, {}
    )
    assert summary["status"] == "COMPLETED" and summary["recovered"] == 0

    unresolved = world.run(fixture_id=fixture)
    assert unresolved["fixtures"] == {str(fixture): "NOT_YET_PUBLISHED"}
    summary = summarize_recovery(
        recovery_connection,
        RecoveryRequest(4, None, fixture),
        {"api_football": unresolved},
        {},
    )
    # A successful request without a recovered result is not reported as success.
    assert summary["status"] == "COMPLETED_UNRESOLVED"
    assert summary["request_outcome"] == "NOT_YET_PUBLISHED"

    world.finish(802, 2, 0)
    recovered = world.run(fixture_id=fixture)
    assert recovered["fixtures"] == {str(fixture): "RECOVERED"} and len(world.calls) == 4
    assert recovered["recovered"] == 1 and recovered["history_inserted"] == 1
    summary = summarize_recovery(
        recovery_connection, RecoveryRequest(4, None, fixture), {"api_football": recovered}, {}
    )
    assert (summary["status"], summary["request_outcome"]) == ("COMPLETED", "RECOVERED")
    # Older than the last correction check: no further automatic downloads.
    state = world.state(802)
    assert state[1] == "CORRECTION" and state[5] is True
    assert world.run()["selected_dates"] == 0 and len(world.calls) == 4

    missing = uuid4()
    summary = summarize_recovery(
        recovery_connection,
        RecoveryRequest(4, None, missing),
        {"api_football": world.run(fixture_id=missing)},
        {},
    )
    assert (summary["status"], summary["request_outcome"]) == (
        "COMPLETED_UNRESOLVED",
        "FIXTURE_NOT_FOUND",
    )
    assert len(world.calls) == 4


def test_newly_eligible_fixture_is_not_suppressed_by_checked_date_or_midnight(
    recovery_connection: psycopg.Connection[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    late = OLD - timedelta(hours=2)
    after_midnight = OLD + timedelta(minutes=20)  # next UTC date
    world = ApiFootballWorld(
        recovery_connection,
        tmp_path,
        monkeypatch,
        {802: (OLD, "NS"), 803: (late, "CANC"), 804: (after_midnight, "NS")},
    )
    first = world.run()
    # One shared request per UTC date; the cancelled fixture is not a candidate.
    assert sorted(world.calls) == [OLD.date(), after_midnight.date()]
    assert first["outcomes"] == {"NOT_YET_PUBLISHED": 2}
    checked = world.state(802)

    # The cancelled fixture is reinstated and now has a published result.
    recovery_connection.execute(
        "UPDATE football.product_fixtures SET status='SCHEDULED' WHERE fixture_id=%s",
        (world.fixture(803),),
    )
    recovery_connection.commit()
    world.finish(803, 1, 1)
    second = world.run()
    assert world.calls[2:] == [OLD.date()]
    assert second["outcomes"] == {"RECOVERED": 1}
    assert recovery_connection.execute(
        "SELECT status,home_score,away_score FROM football.product_fixtures WHERE fixture_id=%s",
        (world.fixture(803),),
    ).fetchone() == ("FINISHED", 1, 1)
    # The earlier check on that date was neither repeated nor rewritten.
    assert world.state(802) == checked


def test_provider_outage_does_not_block_later_dates_and_recovers(
    recovery_connection: psycopg.Connection[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = OLD - timedelta(days=3)
    world = ApiFootballWorld(
        recovery_connection, tmp_path, monkeypatch, {802: (OLD, "NS"), 805: (other, "NS")}
    )
    world.finish(805, 0, 1)
    world.failures.append(ApiFootballError("upstream 503"))
    result = world.run()
    assert len(world.calls) == 2
    assert result["outcomes"] == {"PROVIDER_UNAVAILABLE": 1, "RECOVERED": 1}
    assert result["failure_reasons"] == {"PROVIDER_REQUEST_FAILED": 1}
    outcome, _purpose, attempts, checked, following, _never = world.state(802)
    assert (outcome, attempts) == ("PROVIDER_UNAVAILABLE", 1)
    assert following - checked == timedelta(minutes=5)
    world.due_now(802)
    world.finish(802, 3, 2)
    assert world.run()["outcomes"] == {"RECOVERED": 1}


def test_autonomous_correction_discovery_is_bounded_and_keeps_history(
    recovery_connection: psycopg.Connection[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kickoff = (datetime.now(UTC) - timedelta(days=3)).replace(second=0, microsecond=0)
    world = ApiFootballWorld(recovery_connection, tmp_path, monkeypatch, {802: (kickoff, "NS")})
    fixture = world.fixture(802)
    world.finish(802, 2, 0)
    assert world.run()["outcomes"] == {"RECOVERED": 1}
    state = world.state(802)
    assert state[1] == "CORRECTION" and state[4] == kickoff + timedelta(days=7)
    assert world.run()["selected_dates"] == 0 and len(world.calls) == 1

    # The scheduled verification finds a provider correction without an operator.
    cutoff = recovery_connection.execute("SELECT clock_timestamp()").fetchone()[0]
    recovery_connection.commit()
    world.due_now(802)
    world.finish(802, 2, 2)
    corrected = world.run()
    assert corrected["outcomes"] == {"CORRECTED": 1} and corrected["corrected"] == 1
    assert recovery_connection.execute(
        """SELECT home_goals,away_goals,decided_at<=%s
           FROM football.product_match_history_decisions
           WHERE fixture_id=%s ORDER BY decided_at,decision_id""",
        (cutoff, fixture),
    ).fetchall() == [(2, 0, True), (2, 2, False)]
    assert world.state(802)[4] == kickoff + timedelta(days=7)

    world.due_now(802)
    assert world.run()["outcomes"] == {"VERIFIED_UNCHANGED": 1}
    assert len(world.calls) == 3


def test_retained_evidence_recovers_without_a_provider_request(
    recovery_connection: psycopg.Connection[Any], tmp_path: Path
) -> None:
    connection = recovery_connection
    sync, fixture, _provisional, snapshot, live, kickoff, acquired = (
        seed_reviewed_operational_fixture(connection, tmp_path)
    )
    final = replace(
        live,
        status="FINISHED",
        provider_status="finished",
        home_score=0,
        away_score=0,
        minute=None,
        period=None,
        source_updated_at=kickoff + timedelta(hours=2),
        observed_at=kickoff + timedelta(hours=2, minutes=1),
        result_score_basis="REGULATION_90",
    )
    # Evidence captured before the identity was trusted, never reconciled.
    with connection.transaction():
        assert sync._store_observation(final, snapshot, None)
    connection.commit()

    def fetch(day: object) -> PitchApiResponse:
        raise AssertionError("retained evidence must not trigger a provider request")

    result = recover_provider_results(sync, fetch, normalize_pitchapi_matches, limit=2)
    assert result["attempted_requests"] == 0
    assert result["outcomes"] == {"RECOVERED": 1}
    assert result["stored_observations_reconciled"] == 1
    assert connection.execute(
        """SELECT status,home_score,away_score,result_score_basis
           FROM football.product_fixtures WHERE fixture_id=%s""",
        (fixture,),
    ).fetchone() == ("FINISHED", 0, 0, "REGULATION_90")
    original = connection.execute(
        """SELECT o.observed_at,s.acquired_at FROM football.product_provider_fixture_observations o
           JOIN football.source_snapshots s ON s.id=o.source_snapshot_id
           WHERE o.provider_code='pitchapi' AND o.canonical_status='FINISHED'"""
    ).fetchall()
    # Reconciliation may attach a copy, but never rewrites acquisition or revision time.
    assert set(original) == {(final.observed_at, acquired)}
    connection.commit()

    # Idempotent: replaying the same evidence again changes nothing.
    before = connection.execute(
        "SELECT count(*) FROM football.product_provider_fixture_observations"
    ).fetchone()
    from football.product.operational_support import SyncCounts
    from football.product.result_recovery import _replay_retained

    _replay_retained(sync, [live.provider_match_id], SyncCounts())
    assert (
        connection.execute(
            "SELECT count(*) FROM football.product_provider_fixture_observations"
        ).fetchone()
        == before
    )


def test_lease_coordinates_duplicate_requests_and_expires_after_restart(
    recovery_connection: psycopg.Connection[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = ApiFootballWorld(recovery_connection, tmp_path, monkeypatch, {802: (OLD, "NS")})
    fixture = world.fixture(802)
    world.finish(802, 1, 0)
    # A concurrent worker (or one that crashed) holds the date lease.
    recovery_connection.execute(
        """INSERT INTO football.product_provider_refresh_state
           (provider_code,resource_name,last_attempt_at,next_attempt_at)
           VALUES ('api_football',%s,now(),now()+interval '15 minutes')""",
        (f"result-recovery-{OLD.date()}",),
    )
    recovery_connection.commit()
    held = world.run(fixture_id=fixture)
    assert held["fixtures"] == {str(fixture): "IN_PROGRESS"} and held["coordinated"] == 1
    assert world.calls == []
    # The lease expires; the next request completes the work exactly once.
    recovery_connection.execute(
        "UPDATE football.product_provider_refresh_state SET next_attempt_at=now()"
    )
    recovery_connection.commit()
    assert world.run(fixture_id=fixture)["fixtures"] == {str(fixture): "RECOVERED"}
    assert world.run(fixture_id=fixture)["fixtures"] == {str(fixture): "VERIFIED_UNCHANGED"}
    assert len(world.calls) == 2
    assert recovery_connection.execute(
        "SELECT count(*) FROM football.product_team_match_history WHERE fixture_id=%s",
        (fixture,),
    ).fetchone() == (1,)


def test_api_football_retained_response_recovers_without_a_request(
    recovery_connection: psycopg.Connection[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = ApiFootballWorld(recovery_connection, tmp_path, monkeypatch, {802: (OLD, "NS")})
    fixture = world.fixture(802)
    # A later dated response was retained but never reached the result owners.
    world.finish(802, 1, 2)
    acquired = OLD + timedelta(hours=3)
    world.sync._record_response(f"fixtures-{OLD.date()}", world._response(OLD.date(), acquired))
    recovery_connection.commit()
    world.failures.append(AssertionError("retained evidence must not trigger a request"))

    result = world.run()
    assert result["attempted_requests"] == 0 and world.calls == []
    assert result["outcomes"] == {"RECOVERED": 1} and result["history_inserted"] == 1
    assert recovery_connection.execute(
        """SELECT f.status,f.home_score,f.away_score,h.source_snapshot_id IS NOT NULL,
                  s.acquired_at
           FROM football.product_fixtures f
           JOIN football.product_team_match_history h ON h.fixture_id=f.fixture_id
           JOIN football.source_snapshots s ON s.id=h.source_snapshot_id
           WHERE f.fixture_id=%s""",
        (fixture,),
    ).fetchone() == ("FINISHED", 1, 2, True, acquired)
    # Replaying the same retained response again changes nothing.
    world.due_now(802)
    world.failures.clear()
    again = world.run(fixture_id=fixture)
    assert again["fixtures"] == {str(fixture): "VERIFIED_UNCHANGED"}
    assert recovery_connection.execute(
        "SELECT count(*) FROM football.product_match_history_decisions WHERE fixture_id=%s",
        (fixture,),
    ).fetchone() == (1,)
