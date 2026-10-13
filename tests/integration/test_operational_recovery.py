import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from football.product.operational_provider_sync import SyncCounts
from football.providers.pitchapi import PitchApiResponse, normalize_pitchapi_matches
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier

from tests.integration.test_operational_provider_sync import seed_reviewed_operational_fixture
from tests.integration.test_product_identity_upgrade import _migrate


@pytest.fixture
def recovery_connection() -> Iterator[psycopg.Connection[object]]:
    name = "football_recovery_" + uuid4().hex
    url = make_conninfo(os.environ["TEST_DATABASE_URL"], dbname=name)
    with psycopg.connect(make_conninfo(url, dbname="postgres"), autocommit=True) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
        try:
            _migrate(url, "up")
            with psycopg.connect(url) as connection:
                yield connection
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(name)))


def test_old_fixture_recovers_only_from_retained_source_without_guessed_regulation(
    recovery_connection: psycopg.Connection[object],
    tmp_path: Path,
) -> None:
    connection = recovery_connection
    sync, target, _provisional, _snapshot, live, kickoff, _acquired = (
        seed_reviewed_operational_fixture(connection, tmp_path)
    )
    connection.commit()
    requested = kickoff.date() + timedelta(days=3)
    original = connection.execute(
        "SELECT to_jsonb(f) FROM football.product_fixtures f WHERE fixture_id=%s", (target,)
    ).fetchone()
    calls = []
    matches: list[dict[str, object]] = []

    def fetch(day: object) -> PitchApiResponse:
        calls.append(day)
        raw = json.dumps({"matches": matches}).encode()
        return PitchApiResponse(
            path=f"/v1/date/{day}",
            fetched_at=datetime.now(UTC),
            sha256=hashlib.sha256(raw).hexdigest(),
            raw=raw,
            data=json.loads(raw),
        )

    first = SyncCounts()
    assert (
        sync._recover_unresolved(requested, fetch, normalize_pitchapi_matches, 1, first, None) == []
    )
    assert calls == [kickoff.date()]
    assert first.failure_reasons == {"UNRESOLVED_FIXTURE_NOT_IN_PROVIDER_RESPONSE": 1}
    assert (
        connection.execute(
            "SELECT to_jsonb(f) FROM football.product_fixtures f WHERE fixture_id=%s", (target,)
        ).fetchone()
        == original
    )
    assert sync._lifecycle_diagnostics(requested)["recoverable_for_provider"] == 1
    skipped = SyncCounts()
    assert (
        sync._recover_unresolved(requested, fetch, normalize_pitchapi_matches, 1, skipped, None)
        == []
    )
    assert skipped.attempted_requests == 0 and len(calls) == 1
    connection.execute(
        """UPDATE football.product_provider_refresh_state
           SET next_attempt_at=clock_timestamp()-interval '1 second'
           WHERE provider_code='pitchapi'"""
    )
    connection.commit()
    matches.append(
        {
            "id": live.provider_match_id,
            "league": {"id": live.provider_competition_id, "name": live.provider_competition_name},
            "home_team": {"id": live.provider_home_team_id, "name": live.home_team_name},
            "away_team": {"id": live.provider_away_team_id, "name": live.away_team_name},
            "time_utc": kickoff.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "status": "finished",
            "score_home": 2,
            "score_away": 1,
        }
    )
    completed = SyncCounts()
    recovered = sync._recover_unresolved(
        requested, fetch, normalize_pitchapi_matches, 1, completed, None
    )
    assert [fixture_id for _row, fixture_id in recovered] == [target]
    assert completed.failed == 0 and completed.updated == 1
    assert connection.execute(
        """SELECT status,home_score,away_score,result_score_basis
           FROM football.product_fixtures WHERE fixture_id=%s""",
        (target,),
    ).fetchone() == ("FINISHED", 2, 1, "UNKNOWN")
    assert sync._lifecycle_diagnostics(requested)["unresolved_outside_window"] == 0
    assert connection.execute(
        """SELECT min(observed_at) > %s FROM football.product_provider_fixture_observations
           WHERE canonical_fixture_id=%s AND canonical_status='FINISHED'""",
        (kickoff, target),
    ).fetchone() == (True,)
