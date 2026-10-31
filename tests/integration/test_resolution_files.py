"""Approved missing-data actions preserve original evidence, retries and parity blockers."""

import hashlib
from uuid import uuid4

import psycopg
import pytest
from football.product import resolution_files as files
from football.product.resolution_actions import apply_one, preview
from football.product.resolution_cases import case_detail
from football.product.resolution_data import data_detail, missing_page
from football.product.resolution_recovery import run_pending_recovery
from football.storage.raw import ImmutableFileStore
from football.work.contracts import WorkType
from football.work.storage import WorkRegistry

from tests.integration.test_integrity_verification import _registered_artifacts
from tests.integration.test_resolution_decisions import ACTOR, approve
from tests.integration.test_team_identity_correction import isolated_database, seed


def proposal(key, action, **candidate):
    return {
        "case_key": key,
        "action": action,
        "candidate": candidate,
        "reason": "Owner reviewed original checksum, dependent scopes and retained bytes",
    }


def missing_resource(c, root):
    seed(c, root)
    row = c.execute(
        "SELECT r.id FROM football.source_resources r "
        "JOIN football.source_snapshots s ON s.id=r.source_snapshot_id "
        "JOIN football.providers p ON p.id=s.provider_id WHERE p.code='football_data_org'"
    ).fetchone()
    target = next(
        item["path"]
        for item in data_detail(c, root, f"resource:{row[0]}")["registered_files"]
        if item["kind"] == "SOURCE_RESOURCE"
    )
    original = root / target
    payload = original.read_bytes()
    ImmutableFileStore(root).publish("recovery/original.json", payload)
    original.unlink()
    c.commit()
    return f"resource:{row[0]}", target, payload


def test_exact_original_recovery_is_approved_durable_and_idempotent(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, path, payload = missing_resource(c, tmp_path)
        before = data_detail(c, tmp_path, key)["registration"]
        request = approve(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=path, recovery_path="recovery/original.json"),
        )
        assert not (tmp_path / path).exists()
        c.commit()
        event = apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        assert not (tmp_path / path).exists()  # Approval queues work; it does not publish bytes.
        assert case_detail(c, tmp_path, key)["file_recovery_work"][0]["state"] == "PENDING"
        c.commit()
        outcome = run_pending_recovery(c, tmp_path)
        assert outcome["status"] == "PROCESSED", outcome
        assert outcome["outcome"]["case_status"] == "PASS"
        assert outcome["outcome"]["parity_status"].startswith("RECHECK_REQUIRED")
        assert (tmp_path / path).read_bytes() == payload
        assert data_detail(c, tmp_path, key)["registration"] == before
        assert not any(item["case_key"] == key for item in missing_page(c, tmp_path, {})["items"])
        c.commit()
        assert apply_one(c, tmp_path, request, ACTOR) == event
        c.commit()
        assert run_pending_recovery(c, tmp_path)["status"] == "PROCESSED"  # Scoped followup.
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            1,
        )


@pytest.mark.parametrize("action", ["EXCLUDE", "DEFER", "BLOCK", "REQUEST_EVIDENCE", "VERIFY"])
def test_dispositions_preserve_missing_counts_and_history(tmp_path, action):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, path, _ = missing_resource(c, tmp_path)
        candidate = {"exclusion_scope": key} if action == "EXCLUDE" else {}
        request = approve(c, tmp_path, proposal(key, action, **candidate))
        event = apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        page = missing_page(c, tmp_path, {})
        assert page["total"] == 1 and page["items"][0]["disposition"] == action
        assert event["detail"]["result"]["case_status"] == "BLOCKED"
        assert "FULL_DATA_PARITY" in event["detail"]["result"]["parity_status"]
        assert not (tmp_path / path).exists()
        c.commit()
        assert run_pending_recovery(c, tmp_path)["status"] == "IDLE"


@pytest.mark.parametrize(
    "candidate",
    [
        {"target_path": "raw/football_data_org.json", "recovery_path": "../outside"},
        {"target_path": "unregistered.json", "recovery_path": "recovery/original.json"},
        {"target_path": "raw/football_data_org.json", "recovery_path": "recovery/wrong.json"},
        {"target_path": "raw/football_data_org.json", "recovery_path": "recovery/symlink.json"},
    ],
)
def test_recovery_rejects_unsafe_paths_and_unrelated_bytes(tmp_path, candidate):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, _, _ = missing_resource(c, tmp_path)
        (tmp_path / "recovery/wrong.json").write_bytes(b"different")
        (tmp_path / "recovery/symlink.json").symlink_to(tmp_path / "recovery/original.json")
        prepared = preview(c, tmp_path, proposal(key, "RECOVER", **candidate))
        assert not prepared["allowed"]
        assert prepared["qualification"]["status"] == "BLOCKED"


def test_recovery_does_not_overwrite_different_registered_bytes(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, path, _ = missing_resource(c, tmp_path)
        (tmp_path / path).write_bytes(b"corrupt registered path")
        prepared = preview(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=path, recovery_path="recovery/original.json"),
        )
        assert not prepared["allowed"]
        assert "overwrite" in prepared["qualification"]["reason"]
        assert (tmp_path / path).read_bytes() == b"corrupt registered path"


def test_retry_after_publication_reconciles_target_without_temporary_copy(tmp_path, monkeypatch):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, path, payload = missing_resource(c, tmp_path)
        request = approve(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=path, recovery_path="recovery/original.json"),
        )
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        original = files.registered_plan
        checks = []

        def interrupted(*args):
            checks.append(1)
            if len(checks) == 2:
                raise psycopg.OperationalError("injected interruption after immutable publication")
            return original(*args)

        monkeypatch.setattr(files, "registered_plan", interrupted)
        assert run_pending_recovery(c, tmp_path)["status"] == "RETRY_WAIT"
        assert (tmp_path / path).read_bytes() == payload
        (tmp_path / "recovery/original.json").unlink()
        monkeypatch.setattr(files, "registered_plan", original)
        result = run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED", result
        assert result["outcome"]["publication"] == "verified_existing"
        assert case_detail(c, tmp_path, key)["file_recovery_work"][0]["attempt_count"] == 2


@pytest.mark.parametrize("kind", ["raw", "dataset", "dataset_manifest"])
def test_native_and_dataset_recovery_match_registered_storage_layouts(tmp_path, kind):
    with isolated_database() as url, psycopg.connect(url) as c:
        raw, dataset, _, paths = _registered_artifacts(c, tmp_path)
        target = paths[kind]
        payload = (tmp_path / target).read_bytes()
        ImmutableFileStore(tmp_path).publish("recovery/exact", payload)
        (tmp_path / target).unlink()
        c.commit()
        key = f"resource:{raw}" if kind == "raw" else f"dataset:{dataset}"
        detail = data_detail(c, tmp_path, key)
        assert any(item["path"] == target for item in detail["registered_files"])
        request = approve(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=target, recovery_path="recovery/exact"),
        )
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        result = run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED", result
        assert (
            hashlib.sha256((tmp_path / target).read_bytes()).hexdigest()
            == result["outcome"]["sha256"]
        )
        assert data_detail(c, tmp_path, key)["status"] == "PASS"


def test_only_one_worker_claims_approved_file_and_inputs_remain_immutable(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, path, _ = missing_resource(c, tmp_path)
        request = approve(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=path, recovery_path="recovery/original.json"),
        )
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_file_recovery_work").fetchone()[0]
        c.commit()
        from football.product.sync import HISTORY_JOB_LEASE

        claim = WorkRegistry(c).claim(
            "first", HISTORY_JOB_LEASE, (WorkType.PROVIDER_ACQUISITION,), work_ids=(work,)
        )
        assert claim
        with psycopg.connect(url) as other:
            assert run_pending_recovery(other, tmp_path)["status"] == "BUSY"
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("UPDATE football.resolution_file_recovery_work SET plan='{}'")
        c.commit()
        assert files.publish_file(c, tmp_path, claim)["status"] == "PROCESSED"
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("DELETE FROM football.resolution_file_recovery_work")


def test_exclusion_cannot_broaden_parity_scope(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, _, _ = missing_resource(c, tmp_path)
        assert not preview(c, tmp_path, proposal(key, "EXCLUDE", exclusion_scope="all"))["allowed"]
        request = approve(c, tmp_path, proposal(key, "DEFER"))
        request["approved"] = False
        with pytest.raises(ValueError, match="explicit"):
            apply_one(c, tmp_path, request, ACTOR)
        request["request_id"] = str(uuid4())


def test_manifest_recovery_reveals_original_raw_target_without_guessing(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, _, _ = missing_resource(c, tmp_path)
        manifest = data_detail(c, tmp_path, key)["registration"]["manifest_path"]
        original = (tmp_path / manifest).read_bytes()
        ImmutableFileStore(tmp_path).publish("recovery/manifest", original)
        (tmp_path / manifest).unlink()
        detail = data_detail(c, tmp_path, key)
        assert [item["kind"] for item in detail["registered_files"]] == ["SOURCE_MANIFEST"]
        request = approve(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=manifest, recovery_path="recovery/manifest"),
        )
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        result = run_pending_recovery(c, tmp_path)
        assert result["status"] == "PROCESSED", result
        assert result["outcome"]["case_status"] == "BLOCKED"  # Raw bytes are still missing.
        assert len(data_detail(c, tmp_path, key)["registered_files"]) == 2


def test_input_changed_after_approval_blocks_worker_and_keeps_original_registration(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, path, _ = missing_resource(c, tmp_path)
        request = approve(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=path, recovery_path="recovery/original.json"),
        )
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        (tmp_path / "recovery/original.json").write_bytes(b"unrelated")
        assert run_pending_recovery(c, tmp_path)["status"] == "BLOCKED"
        detail = case_detail(c, tmp_path, key)
        assert detail["file_recovery_work"][0]["state"] == "BLOCKED"
        assert not (tmp_path / path).exists()


def test_lost_lease_after_file_publication_cannot_publish_completion(tmp_path, monkeypatch):
    with isolated_database() as url, psycopg.connect(url) as c:
        key, path, payload = missing_resource(c, tmp_path)
        request = approve(
            c,
            tmp_path,
            proposal(key, "RECOVER", target_path=path, recovery_path="recovery/original.json"),
        )
        apply_one(c, tmp_path, request, ACTOR)
        c.commit()
        work = c.execute("SELECT work_id FROM football.resolution_file_recovery_work").fetchone()[0]
        c.commit()
        original = files.ImmutableFileStore.publish

        def revoke_after_write(store, *args):
            result = original(store, *args)
            with psycopg.connect(url) as other:
                WorkRegistry(other).cancel(work)
            return result

        monkeypatch.setattr(files.ImmutableFileStore, "publish", revoke_after_write)
        assert run_pending_recovery(c, tmp_path)["status"] == "LEASE_LOST"
        assert (tmp_path / path).read_bytes() == payload
        assert c.execute(
            "SELECT outcome FROM football.resolution_file_recovery_work"
        ).fetchone() == (None,)
        assert c.execute("SELECT count(*) FROM football.resolution_recovery_work").fetchone() == (
            0,
        )


def test_real_browser_recovers_registered_original_bytes(tmp_path, monkeypatch):
    import subprocess
    from pathlib import Path

    from tests.integration.test_remediation_browser import running_application

    with isolated_database() as url:
        with psycopg.connect(url) as c:
            key, path, payload = missing_resource(c, tmp_path)
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path))
        monkeypatch.setenv("MATCHFORGE_ADMIN_CLI_TOKEN", "resolution-disposable-owner")
        with running_application(url, Path.cwd(), tmp_path / "api.log") as (_, env):
            run = subprocess.run(
                [
                    "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "resolution-files.spec.ts",
                    "--project=desktop",
                    "--workers=1",
                ],
                cwd="web",
                env={
                    **env,
                    "MATCHFORGE_RESOLUTION_BACKEND": env["MATCHFORGE_REMEDIATION_BACKEND"],
                    "MATCHFORGE_RESOLUTION_FILE_CASE": key,
                    "MATCHFORGE_RESOLUTION_FILE_TARGET": path,
                },
                capture_output=True,
                text=True,
                timeout=150,
            )
            assert run.returncode == 0, run.stdout + run.stderr
        assert (tmp_path / path).read_bytes() == payload
        with psycopg.connect(url) as c:
            assert c.execute("SELECT action FROM football.resolution_review_events").fetchall() == [
                ("RECOVER",)
            ]
            assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (1,)
