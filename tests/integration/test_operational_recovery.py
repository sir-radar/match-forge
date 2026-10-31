import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

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


def test_current_acquisition_remains_visible_when_historical_recovery_is_missing(
    recovery_connection: psycopg.Connection[object], tmp_path: Path
) -> None:
    from football.product.operational_provider_sync import DetailCounts

    connection = recovery_connection
    sync, _target, _provisional, _snapshot, _live, kickoff, _acquired = (
        seed_reviewed_operational_fixture(connection, tmp_path)
    )
    connection.commit()
    requested = kickoff.date() + timedelta(days=3)

    def fetch(day: object) -> PitchApiResponse:
        raw = b'{"matches":[]}'
        return PitchApiResponse(
            path=f"/v1/date/{day}",
            fetched_at=datetime.now(UTC),
            sha256=hashlib.sha256(raw).hexdigest(),
            raw=raw,
            data=json.loads(raw),
        )

    result = sync._sync_dates(
        requested,
        requested,
        fetch=fetch,
        normalize=normalize_pitchapi_matches,
        detail=lambda _row: DetailCounts(),
        details_limit=1,
        live_details_limit=0,
        competition_id=None,
    )
    assert result["status"] == "COMPLETED_WITH_ERRORS"
    assert result["current_acquisition"]["status"] == "COMPLETED"
    assert result["current_acquisition"]["successful_requests"] == 1
    assert result["historical_recovery"]["failed"] == 1
    assert result["failed"] == 1 and result["successful_requests"] == 2
    assert connection.execute(
        "SELECT next_attempt_at > clock_timestamp()+interval '23 hours',last_error "
        "FROM football.product_provider_refresh_state WHERE provider_code='pitchapi'"
    ).fetchone() == (True, "RECOVERY_FIXTURES_MISSING")


def test_killed_worker_reclaims_committed_checkpoint_and_fences_old_owner(
    recovery_connection: psycopg.Connection[object],
) -> None:
    import select
    import subprocess
    import sys
    from dataclasses import asdict

    from football.work.contracts import RetryPolicy, WorkClaim, WorkRequest, WorkType
    from football.work.storage import WorkLeaseLost, WorkRegistry

    connection = recovery_connection
    connection.execute("CREATE TABLE interruption_checkpoint (work_id uuid PRIMARY KEY)")
    connection.execute("CREATE TABLE interruption_result (work_id uuid PRIMARY KEY)")
    connection.commit()
    registry = WorkRegistry(connection)
    identity = registry.enqueue(
        WorkRequest(
            work_type=WorkType.HISTORICAL_ACQUISITION,
            semantic_key=f"interruption:{uuid4()}",
            input_hash="a" * 64,
            priority=0,
            available_at=datetime.now(UTC),
            max_attempts=3,
            retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
        )
    )
    script = """
import json, os, sys
from dataclasses import asdict
from datetime import timedelta
from uuid import UUID
import psycopg
from football.work.contracts import WorkType
from football.work.storage import WorkRegistry
with psycopg.connect(os.environ["INTERRUPTION_DATABASE_URL"]) as c:
    registry = WorkRegistry(c)
    claim = registry.claim("killed-worker", timedelta(seconds=2),
        (WorkType.HISTORICAL_ACQUISITION,), work_ids=(UUID(os.environ["INTERRUPTION_WORK_ID"]),))
    with registry.progress(claim) as publisher:
        publisher.execute("INSERT INTO interruption_checkpoint VALUES (%s)", (claim.work_id,))
    print(json.dumps(asdict(claim), default=str), flush=True)
    sys.stdin.read()
"""
    with subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ
        | {
            "INTERRUPTION_DATABASE_URL": make_conninfo(
                os.environ["TEST_DATABASE_URL"], dbname=connection.info.dbname
            ),
            "INTERRUPTION_WORK_ID": str(identity),
        },
    ) as process:
        assert select.select([process.stdout], [], [], 15)[0], "worker did not checkpoint"
        line = process.stdout.readline()
        assert line, process.stderr.read()
        data = json.loads(line)
        process.kill()
        process.communicate(timeout=10)
    data.update(
        work_id=identity,
        work_type=WorkType(data["work_type"]),
        lease_token=UUID(data["lease_token"]),
        lease_until=datetime.fromisoformat(data["lease_until"]),
    )
    old = WorkClaim(**data)
    connection.execute(
        "SELECT pg_sleep(GREATEST(0,extract(epoch FROM (%s-clock_timestamp())))+0.01)",
        (old.lease_until,),
    )
    connection.commit()
    replacement = registry.claim(
        "restarted-worker",
        timedelta(minutes=1),
        (WorkType.HISTORICAL_ACQUISITION,),
        work_ids=(identity,),
    )
    assert replacement is not None and replacement.generation > old.generation
    assert connection.execute("SELECT work_id FROM interruption_checkpoint").fetchone() == (
        identity,
    )
    connection.commit()
    with pytest.raises(WorkLeaseLost):
        registry.heartbeat(old, timedelta(minutes=1))
    with registry.publication(replacement, result_hash="b" * 64) as publisher:
        publisher.execute("INSERT INTO interruption_result VALUES (%s)", (identity,))
    assert connection.execute("SELECT count(*) FROM interruption_result").fetchone() == (1,)
    assert asdict(replacement)["attempt_count"] == 2


def test_conflicting_native_mapping_cannot_attach_or_serve_resource(
    recovery_connection: psycopg.Connection[object], tmp_path: Path
) -> None:
    from tests.integration.test_live_context import FIXTURE, _seed_fixture

    connection = recovery_connection
    sync, target, _provisional, snapshot, live, _kickoff, _acquired = (
        seed_reviewed_operational_fixture(connection, tmp_path)
    )
    _seed_fixture(connection)
    raw = b'{"events":[]}'
    response = PitchApiResponse(
        path="/synthetic/events",
        fetched_at=datetime.now(UTC),
        sha256=hashlib.sha256(raw).hexdigest(),
        raw=raw,
        data=json.loads(raw),
    )
    sync._store_resource(
        live.provider_match_id,
        FIXTURE,
        "NORMALIZED_EVENTS",
        response.data,
        response,
        snapshot,
        eligibility="ELIGIBLE",
    )
    assert connection.execute(
        "SELECT count(*) FROM football.product_provider_resource_observations "
        "WHERE canonical_fixture_id=%s",
        (FIXTURE,),
    ).fetchone() == (1,)
    assert connection.execute(
        "SELECT count(*) FROM football.product_uncontested_provider_resources "
        "WHERE canonical_fixture_id=%s",
        (FIXTURE,),
    ).fetchone() == (0,)
    import subprocess

    connection.commit()
    result = subprocess.run(
        [
            "go",
            "test",
            "./internal/app",
            "-run",
            "^TestConflictingLiveResourceDatabase$",
            "-count=1",
        ],
        cwd="go/api",
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ
        | {
            "TEST_DATABASE_URL": make_conninfo(
                os.environ["TEST_DATABASE_URL"], dbname=connection.info.dbname
            ),
            "TEST_CONFLICT_FIXTURE_ID": str(FIXTURE),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    connection.execute(
        "UPDATE football.match_provider_mappings SET match_id=%s WHERE match_id=%s "
        "AND provider_match_id=%s",
        (FIXTURE, target, live.provider_match_id),
    )
    assert sync._resolve_fixture(live) is None
