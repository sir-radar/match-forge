"""Batch isolation, conflicts and durable per-case outcomes over real identities."""

from pathlib import Path

import psycopg
import pytest
from football.product.resolution_batches import apply_batch, validate_batch
from football.product.resolution_cases import case_page
from football.product.resolution_center import execute

from tests.integration.test_resolution_decisions import ACTOR, approve, proposal
from tests.integration.test_team_identity_correction import isolated_database, seed


def test_batch_bounds_and_duplicate_cases_are_rejected():
    for requests in ([], [{"case_key": str(n)} for n in range(21)], [{"case_key": "same"}] * 2):
        with pytest.raises(ValueError):
            validate_batch(requests)


def test_read_only_batch_gathers_proof_and_exposes_overlapping_effects(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, away = seed(c, tmp_path)
        c.commit()
        result = execute(
            c,
            Path.cwd(),
            tmp_path,
            {"operation": "batch_preview", "requests": [proposal(home), proposal(away)]},
        )
        assert c.execute("SHOW transaction_read_only").fetchone() == ("on",)
        assert result["items"][0]["preview"]["allowed"] is True
        assert result["items"][1]["status"] == "BLOCKED"
        assert "overlapping" in result["items"][1]["error"]
        assert result["source_bytes_verified"] > 0
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            0,
        )


def test_stale_case_does_not_rollback_independent_success_and_retry_converges(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, away = seed(c, tmp_path)
        c.commit()
        requests = [approve(c, tmp_path, proposal(item, "BLOCK")) for item in (home, away)]
        c.execute(
            "UPDATE football.team_provider_mappings SET mapping_confidence=.5 WHERE id=%s",
            (home.source_mapping_id,),
        )
        c.commit()
        result = apply_batch(c, tmp_path, requests, ACTOR)
        assert result["succeeded"] == result["blocked"] == 1
        assert result["items"][0]["status"] == "BLOCKED"
        assert "preview" in result["items"][0]["error"]
        assert apply_batch(c, tmp_path, requests, ACTOR) == result
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            1,
        )


def test_shared_fixture_changes_cannot_be_bulk_applied(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        home, away = seed(c, tmp_path)
        c.commit()
        requests = [approve(c, tmp_path, proposal(item)) for item in (home, away)]
        c.commit()
        result = apply_batch(c, tmp_path, requests, ACTOR)
        assert result["succeeded"] == result["blocked"] == 1
        assert "overlapping" in result["items"][1]["error"]
        assert c.execute("SELECT count(*) FROM football.resolution_review_events").fetchone() == (
            1,
        )


def test_identity_groups_preserve_case_counts_and_known_competition_seasons(tmp_path):
    with isolated_database() as url, psycopg.connect(url) as c:
        seed(c, tmp_path)
        c.commit()
        page = case_page(c, "identity", {"provider": "football_data_org", "kind": "team"})
        assert page["total"] == sum(page["counts"].values()) == 2
        assert page["groups"] and all(
            "competition_id" in group and "season_id" in group for group in page["groups"]
        )
        assert any(group["competition_id"] and group["season_id"] for group in page["groups"])


def test_real_browser_batch_records_independent_reviews(tmp_path, monkeypatch):
    import subprocess

    from tests.integration.test_remediation_browser import running_application

    with isolated_database() as url:
        with psycopg.connect(url) as c:
            home, away = seed(c, tmp_path)
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path))
        monkeypatch.setenv("MATCHFORGE_ADMIN_CLI_TOKEN", "resolution-disposable-owner")
        with running_application(url, Path.cwd(), tmp_path / "api.log") as (_, env):
            env = {
                **env,
                "MATCHFORGE_RESOLUTION_BACKEND": env["MATCHFORGE_REMEDIATION_BACKEND"],
                "MATCHFORGE_RESOLUTION_BATCH_KEYS": (
                    f"team:{home.source_mapping_id},team:{away.source_mapping_id}"
                ),
            }
            run = subprocess.run(
                [
                    "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "resolution-batches.spec.ts",
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
                "SELECT count(*) FROM football.resolution_review_events WHERE action='BLOCK'"
            ).fetchone() == (2,)
            assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (1,)
