"""Approved recovery freezes inputs, publishes fenced checkpoints and resumes fairly."""

from datetime import datetime, timedelta
from importlib import import_module
from uuid import uuid4

import psycopg
import pytest
from football.product import resolution_recovery as recovery
from football.product.resolution_actions import apply_one
from football.product.resolution_cases import case_detail
from football.work.contracts import WorkType
from football.work.storage import WorkLeaseLost, WorkRegistry
from psycopg.types.json import Jsonb

from tests.integration.test_resolution_decisions import ACTOR, approve, proposal
from tests.integration.test_team_identity_correction import identity, isolated_database, seed


def approved_job(c, root, extra_fixtures=0):
    home, _ = seed(c, root)
    original = c.execute(
        "SELECT fixture_id,kickoff_at FROM football.product_fixtures LIMIT 1"
    ).fetchone()
    for n in range(extra_fixtures):
        identifier = uuid4()
        c.execute(
            "INSERT INTO football.matches(id,competition_id,season_id) "
            "SELECT %s,competition_id,season_id FROM football.matches WHERE id=%s",
            (identifier, original[0]),
        )
        c.execute(
            "INSERT INTO football.product_fixtures SELECT (jsonb_populate_record("
            "NULL::football.product_fixtures,to_jsonb(f)||%s)).* "
            "FROM football.product_fixtures f WHERE fixture_id=%s",
            (
                Jsonb(
                    {
                        "fixture_id": str(identifier),
                        "kickoff_at": (original[1] + timedelta(days=n + 1)).isoformat(),
                        "forecast_availability": "NOT_ENOUGH_HISTORY",
                    }
                ),
                original[0],
            ),
        )
    c.commit()
    request = approve(c, root, proposal(home))
    c.commit()
    event = apply_one(c, root, request, ACTOR)
    c.commit()
    assert event["detail"]["result"]["downstream_status"].startswith("QUEUED")
    work = c.execute(
        "SELECT work_id FROM football.resolution_recovery_work WHERE request_id=%s",
        (request["request_id"],),
    ).fetchone()[0]
    c.commit()
    return home, request, work


@pytest.mark.parametrize("kind", ["recovery", "files", "parity"])
def test_immediate_recovery_work_uses_the_database_clock(tmp_path, monkeypatch, kind):
    from tests.integration.test_resolution_files import missing_resource
    from tests.integration.test_resolution_files import proposal as file_proposal

    class AheadClock:
        @staticmethod
        def now(tz):
            return datetime.now(tz) + timedelta(minutes=5)

    module = import_module("football.product.resolution_" + kind)
    monkeypatch.setattr(module, "datetime", AheadClock, raising=False)
    with isolated_database() as url, psycopg.connect(url) as c:
        if kind == "recovery":
            _, _, work = approved_job(c, tmp_path)
        else:
            key, path, _ = missing_resource(c, tmp_path)
            candidate = {"target_path": path, "recovery_path": "recovery/original.json"}
            request = approve(
                c,
                tmp_path,
                file_proposal(key, "RECOVER", **candidate)
                if kind == "files"
                else file_proposal(key, "VERIFY"),
            )
            apply_one(c, tmp_path, request, ACTOR)
            table = "resolution_file_recovery_work" if kind == "files" else "resolution_parity_work"
            work = c.execute(
                "SELECT work_id FROM football." + table + " WHERE request_id=%s",
                (request["request_id"],),
            ).fetchone()[0]
        row = c.execute(
            "SELECT work_type,available_at<=clock_timestamp() "
            "FROM football.work_items WHERE work_id=%s",
            (work,),
        ).fetchone()
        c.commit()
        assert row[1], "Immediate work must not wait for an ahead host clock"
        claim = WorkRegistry(c).claim(
            "database-clock-test", timedelta(seconds=30), (WorkType(row[0]),), work_ids=(work,)
        )
        assert claim is not None


def test_approval_freezes_inventory_and_preserves_source_history(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, request, work = approved_job(c, tmp_path)
        detail = case_detail(c, tmp_path, request["case_key"])
        assert detail["recovery_work"][0]["state"] == "PENDING"
        assert (
            c.execute(
                "SELECT count(*) FROM football.resolution_recovery_targets WHERE request_id=%s",
                (request["request_id"],),
            ).fetchone()[0]
            >= 1
        )
        before = c.execute("SELECT clock_timestamp()").fetchone()[0]
        retained = identity(c, home, before)
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute(
                "INSERT INTO football.resolution_recovery_targets "
                "VALUES (%s,'FIXTURE',uuidv7(),%s)",
                (request["request_id"], "a" * 64),
            )
        c.commit()
        result = recovery.run_pending_recovery(c, tmp_path)
        assert result["status"] in {"PROCESSED", "PROCESSED_WITH_BLOCKERS"}, result
        assert all(
            item["status"] in {"RECONCILED", "CHECKED", "BLOCKED"}
            for item in result["outcome"]["targets"]
        )
        refreshed = case_detail(c, tmp_path, request["case_key"])
        assert refreshed["downstream_work"]["recovery_pending"] == 0
        assert refreshed["downstream_work"]["context_pending"] >= 1
        assert refreshed["downstream_work"]["status"] == "PENDING"
        assert identity(c, home, before) == retained
        assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (1,)
        c.commit()
        parity = recovery.run_pending_recovery(c, tmp_path)
        assert parity["status"] == "PROCESSED" and parity["parity_status"] != "PASS"
        assert recovery.run_pending_recovery(c, tmp_path)["status"] == "IDLE"
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("DELETE FROM football.resolution_recovery_results WHERE work_id=%s", (work,))


def test_worker_fences_expired_target_publication(tmp_path, monkeypatch):
    with isolated_database() as url, psycopg.connect(url) as c:
        _, request, work = approved_job(c, tmp_path)
        registry = WorkRegistry(c)
        claim = registry.claim(
            "expired-test",
            timedelta(milliseconds=200),
            (WorkType.CANONICAL_RECONCILIATION,),
            work_ids=(work,),
        )
        assert claim is not None
        target = c.execute(
            "SELECT target_kind,target_id,source_sha256 "
            "FROM football.resolution_recovery_targets WHERE request_id=%s ORDER BY 1,2 LIMIT 1",
            (request["request_id"],),
        ).fetchone()
        verifier = recovery.RetainedIdentityVerifier(tmp_path)
        blocked = recovery.prepare_targets(c, tmp_path, [target], verifier)
        c.commit()
        process = recovery.process_target

        def delayed(*args):
            result = process(*args)
            c.execute("SELECT pg_sleep(.25)")
            return result

        monkeypatch.setattr(recovery, "process_target", delayed)
        with pytest.raises(WorkLeaseLost):
            recovery.publish_target(
                c, tmp_path, claim, request["request_id"], target, verifier, blocked
            )
        assert c.execute(
            "SELECT count(*) FROM football.resolution_recovery_results"
        ).fetchone() == (0,)


def test_unavailable_proof_is_reported_without_inventing_recovery(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        _, request, _ = approved_job(c, tmp_path)
        (tmp_path / "raw/api_football.json").unlink()
        result = recovery.run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED_WITH_BLOCKERS", result
        assert result["outcome"]["blocked"] >= 1
        assert not (tmp_path / "raw/api_football.json").exists()
        assert c.execute(
            "SELECT count(*) FROM football.resolution_review_events WHERE request_id=%s",
            (request["request_id"],),
        ).fetchone() == (1,)


def test_continuations_checkpoint_more_than_one_page_without_full_reprocessing(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        _, request, _ = approved_job(c, tmp_path, extra_fixtures=64)
        total = c.execute(
            "SELECT count(*) FROM football.resolution_recovery_targets WHERE request_id=%s",
            (request["request_id"],),
        ).fetchone()[0]
        c.commit()
        pages = []
        for _ in range(5):
            result = recovery.run_pending_recovery(c, tmp_path)
            if result["status"] == "IDLE":
                break
            assert result["status"].startswith("PROCESSED"), result
            if "parity_status" in result:
                assert result["parity_status"] != "PASS"
                continue
            assert result["outcome"]["processed"] <= recovery.BATCH_SIZE
            pages.append(result)
        assert len(pages) == (total + recovery.BATCH_SIZE - 1) // recovery.BATCH_SIZE
        assert total > 64
        assert sum(page["outcome"]["processed"] for page in pages) == total
        assert c.execute(
            "SELECT count(*) FROM football.resolution_recovery_results WHERE request_id=%s",
            (request["request_id"],),
        ).fetchone() == (total,)
        assert all(page["outcome"].get("continuation_work_id") for page in pages[:-1])
        assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (1,)


def test_target_checkpoint_survives_transient_failure_and_retry(tmp_path, monkeypatch):
    with isolated_database() as url, psycopg.connect(url) as c:
        _, request, work = approved_job(c, tmp_path, extra_fixtures=2)
        process, calls = recovery.process_target, []

        def interrupted(*args):
            calls.append(args[2][1])
            if len(calls) == 2:
                raise psycopg.OperationalError("injected transient failure")
            return process(*args)

        monkeypatch.setattr(recovery, "process_target", interrupted)
        result = recovery.run_pending_recovery(c, tmp_path)
        assert result["status"] == "RETRY_WAIT", result
        assert c.execute(
            "SELECT count(*) FROM football.resolution_recovery_results"
        ).fetchone() == (1,)
        c.commit()
        monkeypatch.setattr(recovery, "process_target", process)
        result = recovery.run_pending_recovery(c, tmp_path)
        assert result["status"].startswith("PROCESSED"), result
        assert c.execute(
            "SELECT state FROM football.work_items WHERE work_id=%s", (work,)
        ).fetchone() == ("SUCCEEDED",)
        assert (
            c.execute(
                "SELECT count(*) FROM football.resolution_recovery_results WHERE request_id=%s",
                (request["request_id"],),
            ).fetchone()[0]
            == result["outcome"]["processed"]
        )


def test_go_schedule_drains_committed_recovery_after_restart(tmp_path, monkeypatch):
    import time
    from pathlib import Path

    from tests.integration.test_remediation_browser import running_application

    with isolated_database() as url:
        with psycopg.connect(url) as c:
            _, request, work = approved_job(c, tmp_path)
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path))
        with running_application(url, Path.cwd(), tmp_path / "api.log"):
            deadline = time.monotonic() + 20
            with psycopg.connect(url, autocommit=True) as c:
                while time.monotonic() < deadline:
                    state = c.execute(
                        "SELECT state FROM football.work_items WHERE work_id=%s", (work,)
                    ).fetchone()[0]
                    if state == "SUCCEEDED":
                        break
                    time.sleep(0.05)
                else:
                    pytest.fail(
                        f"recovery worker did not finish: {state}; "
                        f"{(tmp_path / 'api.log').read_text()}"
                    )
                assert (
                    c.execute(
                        "SELECT count(*) FROM football.resolution_recovery_results "
                        "WHERE request_id=%s",
                        (request["request_id"],),
                    ).fetchone()[0]
                    > 0
                )
                assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (
                    1,
                )


def test_retained_bytes_are_verified_before_coordination_locks(tmp_path, monkeypatch):
    from football.product import identity_admission

    with isolated_database() as url, psycopg.connect(url) as c:
        approved_job(c, tmp_path)
        payload = identity_admission._retained_payload
        reads = []

        def checked(*args):
            ledger = c.execute("SELECT current_setting('matchforge.lock_order',true)").fetchone()[0]
            assert not ledger, "retained file access occurred under publication/identity locks"
            reads.append(args)
            return payload(*args)

        monkeypatch.setattr(identity_admission, "_retained_payload", checked)
        result = recovery.run_pending_recovery(c, tmp_path)
        assert result["status"].startswith("PROCESSED"), result
        assert reads


def test_work_input_hash_mismatch_blocks_publication(tmp_path):
    from datetime import UTC, datetime

    from football.work.contracts import RetryPolicy, WorkRequest

    with isolated_database() as url, psycopg.connect(url) as c:
        _, request, _ = approved_job(c, tmp_path)
        broken = WorkRequest(
            work_type=WorkType.CANONICAL_RECONCILIATION,
            semantic_key="corrupt-input-binding",
            input_hash="b" * 64,
            priority=1,
            available_at=datetime.now(UTC),
            max_attempts=1,
            retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
        )
        WorkRegistry(c).enqueue(broken)
        c.execute(
            "INSERT INTO football.resolution_recovery_work "
            "(work_id,request_id,inventory_sha256,cursor_kind,cursor_id) VALUES (%s,%s,%s,'',%s)",
            (
                broken.work_id,
                request["request_id"],
                recovery.inventory_digest(c, request["request_id"]),
                recovery.ZERO,
            ),
        )
        c.commit()
        result = recovery.run_pending_recovery(c, tmp_path)
        assert result["status"] == "BLOCKED", result
        assert c.execute(
            "SELECT state FROM football.work_items WHERE work_id=%s", (broken.work_id,)
        ).fetchone() == ("BLOCKED",)
        assert c.execute(
            "SELECT count(*) FROM football.resolution_recovery_results"
        ).fetchone() == (0,)


def unknown_season_context(c, root, ambiguous):
    import hashlib

    from tests.integration.test_operational_provider_sync import seed_reviewed_operational_fixture

    _, fixture, _, _, live, _, _ = seed_reviewed_operational_fixture(c, root)
    competition, season = c.execute(
        "SELECT competition_id,season_id FROM football.matches WHERE id=%s", (fixture,)
    ).fetchone()
    observation = c.execute(
        "SELECT observation_id FROM football.product_provider_fixture_observations "
        "WHERE provider_code='pitchapi' AND provider_match_id=%s LIMIT 1",
        (live.provider_match_id,),
    ).fetchone()[0]
    c.execute(
        "UPDATE football.product_provider_fixture_observations "
        "SET canonical_fixture_id=%s WHERE observation_id=%s",
        (fixture, observation),
    )
    members = []
    for status, label in [("PROVISIONAL", "Unknown")] + (
        [("VERIFIED", "2025/2026")] if ambiguous else []
    ):
        new_competition, new_season, new_fixture = uuid4(), uuid4(), uuid4()
        c.execute("INSERT INTO football.competitions(id) VALUES (%s)", (new_competition,))
        c.execute(
            "INSERT INTO football.product_competitions SELECT (jsonb_populate_record("
            "NULL::football.product_competitions,to_jsonb(p)||%s)).* "
            "FROM football.product_competitions p WHERE competition_id=%s",
            (
                Jsonb(
                    {
                        "competition_id": str(new_competition),
                        "season_label": label,
                        "metadata_status": status,
                    }
                ),
                competition,
            ),
        )
        c.execute(
            "INSERT INTO football.seasons SELECT (jsonb_populate_record("
            "NULL::football.seasons,to_jsonb(s)||%s)).* FROM football.seasons s WHERE id=%s",
            (Jsonb({"id": str(new_season), "competition_id": str(new_competition)}), season),
        )
        c.execute(
            "INSERT INTO football.matches(id,competition_id,season_id) VALUES (%s,%s,%s)",
            (new_fixture, new_competition, new_season),
        )
        c.execute(
            "INSERT INTO football.product_fixtures SELECT (jsonb_populate_record("
            "NULL::football.product_fixtures,to_jsonb(f)||%s)).* "
            "FROM football.product_fixtures f WHERE fixture_id=%s",
            (
                Jsonb(
                    {
                        "fixture_id": str(new_fixture),
                        "competition_id": str(new_competition),
                        "identity_status": status,
                    }
                ),
                fixture,
            ),
        )
        c.execute(
            "INSERT INTO football.product_provider_fixture_observations "
            "SELECT (jsonb_populate_record("
            "NULL::football.product_provider_fixture_observations,to_jsonb(o)||%s)).* "
            "FROM football.product_provider_fixture_observations o WHERE observation_id=%s",
            (
                Jsonb(
                    {
                        "observation_id": str(uuid4()),
                        "canonical_fixture_id": str(new_fixture),
                        "semantic_sha256": hashlib.sha256(new_fixture.bytes).hexdigest(),
                    }
                ),
                observation,
            ),
        )
        members.append(new_fixture)
    c.commit()
    return fixture, members[0]


@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize("ambiguous", [False, True])
def test_unknown_season_scope_keeps_all_competing_candidates(tmp_path, scoped, ambiguous):
    with isolated_database() as url, psycopg.connect(url) as c:
        target, member = unknown_season_context(c, tmp_path, ambiguous)
        if scoped:
            result = c.execute(
                "SELECT football.reconcile_unknown_season_fixtures(%s::uuid[])", ([target],)
            ).fetchone()[0]
        else:
            result = c.execute("SELECT football.reconcile_unknown_season_fixtures()").fetchone()[0]
        assert result == (0 if ambiguous else 1)
        assert c.execute(
            "SELECT count(*) FROM football.fixture_identity_resolutions "
            "WHERE member_fixture_id=%s AND active",
            (member,),
        ).fetchone() == (0 if ambiguous else 1,)


def test_recovery_replays_retained_native_observation_without_changing_source_clocks(tmp_path):
    from tests.integration.test_operational_provider_sync import seed_reviewed_operational_fixture

    with isolated_database() as url, psycopg.connect(url) as c:
        _, target, _, _, live, _, _ = seed_reviewed_operational_fixture(c, tmp_path)
        original = c.execute(
            "SELECT observation_id,observed_at,source_updated_at,source_snapshot_id "
            "FROM football.product_provider_fixture_observations "
            "WHERE provider_code='pitchapi' AND provider_match_id=%s LIMIT 1",
            (live.provider_match_id,),
        ).fetchone()
        c.commit()
        proposal = {
            "case_key": f"fixture:pitchapi:{live.provider_match_id}",
            "action": "REVALIDATE",
            "reason": "Recheck retained native fixture context after reviewed identity",
        }
        request = approve(c, tmp_path, proposal)
        c.commit()
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        result = recovery.run_pending_recovery(c, tmp_path)
        assert result["status"].startswith("PROCESSED"), result
        observation = [
            item for item in result["outcome"]["targets"] if item["kind"] == "OBSERVATION"
        ]
        assert len(observation) == 1 and observation[0]["status"] == "RECONCILED", result
        assert observation[0]["fixture_id"] == str(target)
        assert (
            c.execute(
                "SELECT observation_id,observed_at,source_updated_at,source_snapshot_id "
                "FROM football.product_provider_fixture_observations WHERE observation_id=%s",
                (original[0],),
            ).fetchone()
            == original
        )
        assert (
            c.execute(
                "SELECT fixture_id FROM football.product_forecast_refresh_work WHERE fixture_id=%s",
                (target,),
            ).fetchone()
            is None
        )
