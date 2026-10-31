"""Parity rechecks are read-only, fail closed and retain verifiable history."""

from pathlib import Path

import psycopg
import pytest
from football.product import resolution_parity as parity
from football.product.domain import sha256_json
from football.product.resolution_actions import apply_one
from football.product.resolution_cases import case_detail
from football.product.resolution_migration import parity_report
from football.product.resolution_recovery import run_pending_recovery
from football.product.sync import HISTORY_JOB_LEASE
from football.work.contracts import WorkType
from football.work.storage import WorkRegistry

from tests.integration.test_resolution_decisions import ACTOR, approve
from tests.integration.test_team_identity_correction import isolated_database, retained, seed

KEY = "parity:identity_and_canonical_state"


def proposal():
    return {
        "case_key": KEY,
        "action": "RECHECK_PARITY",
        "candidate": {},
        "reason": "Owner requested source-backed verification; existing exceptions remain explicit",
    }


def test_real_parity_recheck_preserves_domain_and_known_discrepancies(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        before = retained(c)
        request = approve(c, tmp_path, proposal())
        event = apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        result = run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED", result
        assert result["parity_status"] in {"BLOCKED", "FAIL"}
        report = parity_report(c, Path.cwd())
        assert report["status"] != "PASS"
        assert report["fresh_for_tracked_evidence"] is True
        assert report["exceptions"]["generic_elo_conflicts"] == 59
        assert report["exceptions"]["insufficient_history_targets"] == 327
        assert report["current_diagnostics"]["database_identity"]["name"].startswith(
            "football_correction_"
        )
        assert len(report["items"]) == 11
        assert all(
            item["status"] in {"PASS", "FAIL", "BLOCKED", "NOT_RUN"} for item in report["items"]
        )
        assert all(item["verified_at"] == report["verified_at"] for item in report["items"])
        assert (
            case_detail(c, tmp_path, KEY)["verification_history"][0]["report_sha256"]
            == result["report_sha256"]
        )
        assert retained(c) == before
        c.commit()
        assert apply_one(c, tmp_path, request, ACTOR) == event
        c.commit()
        assert run_pending_recovery(c, tmp_path)["status"] == "IDLE"
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("UPDATE football.resolution_parity_work SET outcome='{}'")
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("TRUNCATE football.resolution_parity_work")


def test_verification_reads_domain_in_repeatable_read_read_only_transaction(tmp_path, monkeypatch):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        verify = parity.verify_parity

        def checked(connection, *args):
            assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)
            assert connection.execute("SHOW transaction_isolation").fetchone() == (
                "repeatable read",
            )
            return verify(connection, *args)

        monkeypatch.setattr(parity, "verify_parity", checked)
        assert run_pending_recovery(c, tmp_path)["status"] == "PROCESSED"


def test_expired_parity_lease_cannot_publish_report(tmp_path):
    from datetime import timedelta

    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_parity_work").fetchone()[0]
        c.commit()
        claim = WorkRegistry(c).claim(
            "expired-parity",
            timedelta(milliseconds=1),
            (WorkType.READ_MODEL_PROJECTION,),
            work_ids=(work,),
        )
        assert claim
        assert parity.publish_parity(c, Path.cwd(), tmp_path, claim)["status"] == "LEASE_LOST"
        assert c.execute("SELECT outcome FROM football.resolution_parity_work").fetchone() == (
            None,
        )


def test_parity_input_identity_is_checked_before_verification(tmp_path):
    from dataclasses import replace

    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_parity_work").fetchone()[0]
        c.commit()
        claim = WorkRegistry(c).claim(
            "changed-inputs", HISTORY_JOB_LEASE, (WorkType.READ_MODEL_PROJECTION,), work_ids=(work,)
        )
        assert claim
        result = parity.publish_parity(
            c, Path.cwd(), tmp_path, replace(claim, input_hash=sha256_json({}))
        )
        assert result["status"] == "BLOCKED"
        assert c.execute("SELECT outcome FROM football.resolution_parity_work").fetchone() == (
            None,
        )


def test_real_browser_rechecks_parity_with_unchanged_domain(tmp_path, monkeypatch):
    import subprocess

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
                    "resolution-parity.spec.ts",
                    "--project=desktop",
                    "--workers=1",
                ],
                cwd="web",
                env={
                    **env,
                    "MATCHFORGE_RESOLUTION_BACKEND": env["MATCHFORGE_REMEDIATION_BACKEND"],
                    "MATCHFORGE_RESOLUTION_PARITY": "1",
                },
                capture_output=True,
                text=True,
                timeout=150,
            )
            assert run.returncode == 0, run.stdout + run.stderr
        with psycopg.connect(url) as c:
            assert retained(c) == before
            report = parity_report(c, Path.cwd())
            assert report["status"] in {"BLOCKED", "FAIL"}
            assert c.execute("SELECT action FROM football.resolution_review_events").fetchall() == [
                ("RECHECK_PARITY",)
            ]


def test_copied_report_cannot_claim_current_database_readiness(tmp_path, monkeypatch):
    from copy import deepcopy

    with isolated_database() as first, psycopg.connect(first) as c:
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        assert run_pending_recovery(c, tmp_path)["status"] == "PROCESSED"
        original = c.execute("SELECT outcome FROM football.resolution_parity_work").fetchone()[0][
            "report"
        ]
    with isolated_database() as second, psycopg.connect(second) as c:
        # Simulate a restored/copied verification result; its database binding must stay visible.
        seed(c, tmp_path)
        c.commit()
        request = approve(c, tmp_path, proposal())
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        monkeypatch.setattr(parity, "verify_parity", lambda *args: deepcopy(original))
        assert run_pending_recovery(c, tmp_path)["status"] == "PROCESSED"
        report = parity_report(c, Path.cwd())
        assert report["fresh_for_tracked_evidence"] is False
        assert report["status"] == "BLOCKED"
