"""Real database acceptance for bounded, evidence-qualified Admin resolution."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from football.product.resolution_actions import apply_one, preview
from football.product.resolution_identity import mapping_detail

from tests.integration.test_team_identity_correction import (
    identity,
    isolated_database,
    seed,
)

ACTOR = "owner:0123456789abcdef"


def proposal(correction, action="CORRECT"):
    candidate = {k: str(v) for k, v in asdict(correction).items() if k != "source_mapping_id"}
    return {
        "case_key": f"team:{correction.source_mapping_id}",
        "action": action,
        "reason": "Reviewed exact retained provider IDs and fixture context",
        "candidate": candidate if action == "CORRECT" else {},
    }


def approve(connection, root, request):
    prepared = preview(connection, root, request)
    return {
        **request,
        "evidence_version": prepared["evidence_version"],
        "approved": True,
        "request_id": str(uuid4()),
    }


def test_resolution_preview_apply_retry_and_historical_identity(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        request, _ = seed(c, tmp_path)
        c.commit()
        before = c.execute("SELECT clock_timestamp()").fetchone()[0]
        original = identity(c, request, before)
        detail = mapping_detail(c, tmp_path, "team", request.source_mapping_id)
        assert detail["status"] != "VERIFIED"
        assert any(
            item["mapping_id"] == str(request.target_mapping_id) for item in detail["candidates"]
        )
        assert detail["correction_options"][0]["original_decision_id"] == str(
            request.original_decision_id
        )
        prepared = approve(c, tmp_path, proposal(request))
        c.commit()
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            0,
        )
        first = apply_one(c, tmp_path, prepared, ACTOR)
        assert first["action"] == "CORRECT", first
        c.commit()
        retry = apply_one(c, tmp_path, prepared, ACTOR)
        assert retry == first
        c.commit()
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            1,
        )
        assert identity(c, request, before) == original
        assert identity(c, request, c.execute("SELECT clock_timestamp()").fetchone()[0]) is not None
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("DELETE FROM football.resolution_review_events")


def test_stale_evidence_cannot_write_but_an_independent_decision_can(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, away = seed(c, tmp_path)
        c.commit()
        first = approve(c, tmp_path, proposal(home))
        second = approve(c, tmp_path, proposal(away, "BLOCK"))
        c.execute(
            "UPDATE football.team_provider_mappings SET mapping_confidence=.5 WHERE id=%s",
            (home.source_mapping_id,),
        )
        c.commit()
        with pytest.raises(ValueError, match="preview"), c.transaction():
            apply_one(c, tmp_path, first, ACTOR)
        c.rollback()
        assert apply_one(c, tmp_path, second, ACTOR)["action"] == "BLOCK"
        c.commit()
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            1,
        )


def test_name_candidate_cannot_be_admitted_and_rejection_does_not_withdraw_trust(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, _ = seed(c, tmp_path)
        c.commit()
        request = proposal(home, "APPROVE")
        result = preview(c, tmp_path, request)
        assert not result["allowed"]
        approved = {
            **request,
            "evidence_version": result["evidence_version"],
            "approved": True,
            "request_id": str(uuid4()),
        }
        with pytest.raises(ValueError, match="blocked"), c.transaction():
            apply_one(c, tmp_path, approved, ACTOR)
        c.rollback()
        rejection = approve(
            c,
            tmp_path,
            {
                **proposal(home, "REJECT"),
                "candidate": {"target_mapping_id": str(home.target_mapping_id)},
            },
        )
        c.commit()
        assert apply_one(c, tmp_path, rejection, ACTOR)["action"] == "REJECT"
        c.commit()
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            1,
        )
        assert c.execute(
            "SELECT count(*) FROM football.product_identity_admissions "
            "WHERE mapping_id=%s AND disposition='REVOKED'",
            (home.source_mapping_id,),
        ).fetchone() == (0,)


def test_quarantine_is_prospective_and_idempotency_inputs_are_bound(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, _ = seed(c, tmp_path)
        c.commit()
        correction = approve(c, tmp_path, proposal(home))
        c.commit()
        assert apply_one(c, tmp_path, correction, ACTOR)["action"] == "CORRECT"
        c.commit()
        at = c.execute("SELECT clock_timestamp()").fetchone()[0]
        before = identity(c, home, at)
        withdrawal = approve(c, tmp_path, proposal(home, "QUARANTINE"))
        c.commit()
        result = apply_one(c, tmp_path, withdrawal, ACTOR)
        assert result["action"] == "QUARANTINE", result
        c.commit()
        assert identity(c, home, c.execute("SELECT clock_timestamp()").fetchone()[0]) is None
        assert identity(c, home, at) == before
        changed = {**withdrawal, "reason": "Different input cannot reuse approval identity"}
        with pytest.raises(ValueError, match="different approved inputs"):
            apply_one(c, tmp_path, changed, ACTOR)


def test_concurrent_repeated_clicks_commit_one_event(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    with isolated_database() as url, psycopg.connect(url) as c:
        home, _ = seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal(home, "BLOCK"))
        c.commit()
        barrier = Barrier(2)

        def run():
            with psycopg.connect(url) as worker:
                barrier.wait(timeout=10)
                return apply_one(worker, tmp_path, request, ACTOR)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run) for _ in range(2)]
            events = [future.result(timeout=30) for future in futures]
        assert events[0] == events[1]
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            1,
        )


def test_changed_retained_bytes_block_a_previously_qualified_correction(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, _ = seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal(home))
        c.commit()
        (tmp_path / "raw/api_football.json").write_bytes(b"tampered")
        with pytest.raises(ValueError, match="preview"), c.transaction():
            apply_one(c, tmp_path, request, ACTOR)
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            0,
        )


def test_real_browser_approves_a_qualified_correction(tmp_path, monkeypatch):
    import subprocess

    from tests.integration.test_remediation_browser import running_application

    with isolated_database() as url:
        with psycopg.connect(url) as c:
            home, _ = seed(c, tmp_path)
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path))
        monkeypatch.setenv("MATCHFORGE_ADMIN_CLI_TOKEN", "resolution-disposable-owner")
        with running_application(url, Path.cwd(), tmp_path / "api.log") as (_, env):
            env = {
                **env,
                "MATCHFORGE_RESOLUTION_BACKEND": env["MATCHFORGE_REMEDIATION_BACKEND"],
                "MATCHFORGE_RESOLUTION_SOURCE": str(home.source_mapping_id),
                "MATCHFORGE_RESOLUTION_TARGET": str(home.target_mapping_id),
            }
            run = subprocess.run(
                [
                    "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "resolution-decisions.spec.ts",
                    "--project=desktop",
                    "--workers=1",
                ],
                cwd="web",
                env=env,
                capture_output=True,
                text=True,
                timeout=150,
            )
            assert run.returncode == 0, run.stdout + run.stderr
        with psycopg.connect(url) as c:
            assert c.execute(
                "SELECT count(*) FROM football.resolution_review_events"
            ).fetchone() == (1,)
            assert (
                c.execute("SELECT action,actor FROM football.resolution_review_events").fetchone()[
                    0
                ]
                == "CORRECT"
            )
            assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (1,)
