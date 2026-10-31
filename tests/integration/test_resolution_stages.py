"""Real projection rehearsals restore prior state; unqualified stage advances fail closed."""

from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest
from football.product import resolution_stages as stages
from football.product.resolution_actions import apply_one, preview
from football.product.resolution_cases import case_detail
from football.product.resolution_recovery import run_pending_recovery
from football.work.contracts import WorkType
from football.work.storage import WorkRegistry

from tests.integration.test_resolution_decisions import ACTOR, approve
from tests.integration.test_team_identity_correction import isolated_database, retained, seed


def proposal(stage=8, action="REHEARSE_STAGE"):
    return {
        "case_key": f"stage:{stage}",
        "action": action,
        "candidate": {},
        "reason": "Owner approved isolated projection comparison and rollback",
    }


def test_all_thirteen_stage_advances_are_blocked_and_truthful(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        for stage in range(1, 14):
            detail = case_detail(c, tmp_path, f"stage:{stage}")
            assert detail["current_route"] == "LEGACY" and not detail["v2_ready"]
            prepared = preview(c, tmp_path, proposal(stage, "SWITCH_STAGE"))
            assert not prepared["allowed"]
            assert "upstream cutover" in prepared["qualification"]["reason"]
            rehearsal = preview(c, tmp_path, proposal(stage))
            assert rehearsal["allowed"] == (stage == 8)
            if stage != 8:
                assert detail["runtime_binding"] == "NO_QUALIFIED_PRODUCTION_REPLACEMENT"
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            0,
        )


def test_real_projection_rehearsal_restores_route_cache_and_source_history(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        before = retained(c)
        populated = c.execute(
            "SELECT relispopulated FROM pg_class WHERE oid='football.fixture_read_model'::regclass"
        ).fetchone()
        request = approve(c, tmp_path, proposal())
        event = apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        result = run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED", result
        assert result["outcome"]["status"] == "REHEARSAL_PASS_ROLLED_BACK", result
        assert result["outcome"]["legacy"] == result["outcome"]["v2"]
        assert result["outcome"]["legacy"]["rows"] > 0
        assert result["outcome"]["selected_route"] == "V2"
        assert result["outcome"]["restored_route"] == "LEGACY"
        assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("LEGACY",)
        assert (
            c.execute(
                "SELECT relispopulated FROM pg_class "
                "WHERE oid='football.fixture_read_model'::regclass"
            ).fetchone()
            == populated
        )
        assert retained(c) == before
        detail = case_detail(c, tmp_path, "stage:8")
        assert detail["configuration"]["generation"] == 1
        assert detail["approval_execution_history"][0]["result"] == result["outcome"]
        c.commit()
        assert apply_one(c, tmp_path, request, ACTOR) == event
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("DELETE FROM football.resolution_stage_events")


def test_failed_real_projection_refresh_automatically_rolls_back(tmp_path, monkeypatch):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        before = retained(c)
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        digest = stages.projection_digest

        def break_projection(connection, relation):
            if relation == "fixture_read_model":
                connection.execute("DROP MATERIALIZED VIEW football.fixture_read_model")
            return digest(connection, relation)

        monkeypatch.setattr(stages, "projection_digest", break_projection)
        result = run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED", result
        assert result["outcome"]["status"] == "REHEARSAL_FAILED_ROLLED_BACK"
        assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("LEGACY",)
        assert c.execute(
            "SELECT to_regclass('football.fixture_read_model') IS NOT NULL"
        ).fetchone() == (True,)
        assert retained(c) == before


def test_stale_stage_configuration_blocks_queued_rehearsal(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        first = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, first, ACTOR)
        c.commit()
        second = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, second, ACTOR)
        c.commit()
        assert run_pending_recovery(c, tmp_path)["status"] == "PROCESSED"
        assert run_pending_recovery(c, tmp_path)["status"] == "BLOCKED"
        assert c.execute(
            "SELECT generation,route FROM football.resolution_stage_settings WHERE stage=8"
        ).fetchone() == (1, "LEGACY")


def test_expired_stage_lease_leaves_no_routing_or_history_change(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_stage_work").fetchone()[0]
        c.commit()
        claim = WorkRegistry(c).claim(
            "expired-stage",
            timedelta(milliseconds=1),
            (WorkType.READ_MODEL_PROJECTION,),
            work_ids=(work,),
        )
        assert claim
        assert stages.publish_stage(c, claim)["status"] == "LEASE_LOST"
        assert c.execute(
            "SELECT generation,route FROM football.resolution_stage_settings WHERE stage=8"
        ).fetchone() == (0, "LEGACY")
        assert c.execute("SELECT count(*) FROM football.resolution_stage_events").fetchone() == (0,)


def test_stage_settings_cannot_enable_an_unleased_or_unsupported_route(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        for stage in range(1, 14):
            with pytest.raises(psycopg.errors.RaiseException), c.transaction():
                c.execute(
                    "UPDATE football.resolution_stage_settings "
                    "SET route='V2',generation=generation+1 WHERE stage=%s",
                    (stage,),
                )
        assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("LEGACY",)
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("TRUNCATE football.resolution_stage_settings")


def test_stage_preview_requires_explicit_owner_approval(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        request = {**proposal(), "approved": False, "request_id": str(uuid4())}
        with pytest.raises(ValueError, match="explicit"):
            apply_one(c, tmp_path, request, ACTOR)


def test_revoked_trial_automatically_returns_to_legacy_and_owner_can_clear_config(tmp_path):
    from football.product.sync import HISTORY_JOB_LEASE

    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_stage_work").fetchone()[0]
        c.commit()
        claim = WorkRegistry(c).claim(
            "interrupted-trial",
            HISTORY_JOB_LEASE,
            (WorkType.READ_MODEL_PROJECTION,),
            work_ids=(work,),
        )
        assert claim
        c.execute(
            "UPDATE football.resolution_stage_settings SET route='V2',generation=generation+1, "
            "trial_work_id=%s,trial_lease_token=%s,trial_generation=%s WHERE stage=8",
            (work, claim.lease_token, claim.generation),
        )
        c.commit()  # Simulated interruption after a trial setting escaped its transaction.
        assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("V2",)
        c.commit()
        WorkRegistry(c).cancel(work)
        assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("LEGACY",)
        c.commit()
        rollback = approve(c, tmp_path, proposal(action="ROLLBACK_STAGE"))
        apply_one(c, tmp_path, rollback, ACTOR)
        c.commit()
        result = run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED", result
        assert result["outcome"]["status"] == "ROLLBACK_VERIFIED"
        assert c.execute(
            "SELECT route,trial_work_id FROM football.resolution_stage_settings WHERE stage=8"
        ).fetchone() == ("LEGACY", None)


def test_real_browser_rehearses_projection_with_preserved_history(tmp_path, monkeypatch):
    import subprocess
    from pathlib import Path

    from tests.integration.test_remediation_browser import running_application

    with isolated_database() as url:
        with psycopg.connect(url) as c:
            seed(c, tmp_path)
            before = retained(c)
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path))
        monkeypatch.setenv("MATCHFORGE_ADMIN_CLI_TOKEN", "resolution-disposable-owner")
        with running_application(url, Path.cwd(), tmp_path / "api.log") as (_, env):
            run = subprocess.run(
                [
                    "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "resolution-stages.spec.ts",
                    "--project=desktop",
                    "--workers=1",
                ],
                cwd="web",
                env={
                    **env,
                    "MATCHFORGE_RESOLUTION_BACKEND": env["MATCHFORGE_REMEDIATION_BACKEND"],
                    "MATCHFORGE_RESOLUTION_STAGES": "1",
                },
                capture_output=True,
                text=True,
                timeout=150,
            )
            assert run.returncode == 0, run.stdout + run.stderr
        with psycopg.connect(url) as c:
            assert retained(c) == before
            assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("LEGACY",)
            assert c.execute(
                "SELECT result->>'status' FROM football.resolution_stage_events"
            ).fetchall() == [("REHEARSAL_PASS_ROLLED_BACK",)]


def test_stage_event_cannot_claim_a_different_approved_stage(tmp_path):
    from psycopg.types.json import Jsonb

    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_stage_work").fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute(
                "INSERT INTO football.resolution_stage_events "
                "(stage,generation,request_id,work_id,result) "
                "VALUES (1,1,%s,%s,%s)",
                (request["request_id"], work, Jsonb({"status": "INVALID"})),
            )


def test_changed_fixture_scope_requires_a_fresh_rehearsal_approval(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        c.execute("UPDATE football.product_fixtures SET venue='changed after preview'")
        c.commit()
        assert run_pending_recovery(c, tmp_path)["status"] == "BLOCKED"
        assert c.execute("SELECT count(*) FROM football.resolution_stage_events").fetchone() == (0,)
        assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("LEGACY",)


def test_real_go_fixture_consumer_uses_v2_and_returns_to_legacy_on_revocation(
    tmp_path, monkeypatch
):
    import json
    from pathlib import Path
    from urllib.request import urlopen

    from football.product.sync import HISTORY_JOB_LEASE

    from tests.integration.test_remediation_browser import running_application

    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        original = retained(c)
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_stage_work").fetchone()[0]
        c.commit()
        claim = WorkRegistry(c).claim(
            "isolated-http-rehearsal",
            HISTORY_JOB_LEASE,
            (WorkType.READ_MODEL_PROJECTION,),
            work_ids=(work,),
        )
        assert claim, c.execute(
            "SELECT state,available_at,clock_timestamp(),last_error_code "
            "FROM football.work_items WHERE work_id=%s",
            (work,),
        ).fetchone()
        c.execute("REFRESH MATERIALIZED VIEW football.fixture_read_model")
        c.execute(
            "UPDATE football.resolution_stage_settings SET route='V2',generation=generation+1, "
            "trial_work_id=%s,trial_lease_token=%s,trial_generation=%s WHERE stage=8",
            (work, claim.lease_token, claim.generation),
        )
        c.commit()
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path))
        endpoint = "http://127.0.0.1:58081/v1/fixtures?date=2026-08-25"
        with running_application(url, Path.cwd(), tmp_path / "api.log"):
            assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("V2",)
            c.commit()
            with urlopen(endpoint, timeout=10) as response:
                v2 = json.load(response)
            assert v2["groups"]
            WorkRegistry(c).cancel(work)
            assert c.execute("SELECT football.resolution_fixture_route()").fetchone() == ("LEGACY",)
            c.commit()
            with urlopen(endpoint, timeout=10) as response:
                legacy = json.load(response)
            assert legacy == v2
        assert retained(c) == original
