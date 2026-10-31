"""Read-only Admin views use existing tables and the real Python/Go bridge."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest
from football.product.resolution_cases import case_detail, case_page
from football.product.resolution_center import execute
from football.product.resolution_data import data_detail

from tests.integration.test_team_identity_correction import isolated_database, retained, seed


@pytest.mark.parametrize("view", ["identity", "fixtures", "history", "parity", "cutover"])
def test_read_only_views_preserve_domain_state(tmp_path: Path, view: str) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        seed(connection, tmp_path)
        connection.commit()
        before = retained(connection)
        connection.commit()
        result = execute(
            connection,
            Path.cwd(),
            tmp_path,
            {"operation": "read", "view": view, "query": {"page_size": 20}},
        )
        assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)
        assert 1 <= len(result["items"]) <= 20
        assert result["total"] >= 1
        assert sum(result["counts"].values()) == result["total"]
        assert retained(connection) == before


def test_filtered_counts_and_history_pagination_remain_accurate(tmp_path: Path) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        seed(connection, tmp_path)
        connection.commit()
        query = {"provider": "football_data_org", "kind": "team", "page_size": 1}
        first = case_page(connection, "identity", query)
        second = case_page(connection, "identity", {**query, "page": 2})
        assert first["total"] == second["total"] == 2
        assert first["items"][0]["case_key"] != second["items"][0]["case_key"]
        assert case_page(connection, "identity", {**query, "q": "no such team"})["total"] == 0
        assert case_page(connection, "identity", {**query, "q": "Brentford"})["total"] == 1
        history = case_page(connection, "history", {"page_size": 1})
        past_end = case_page(connection, "history", {"page_size": 1, "page": 1000})
        assert past_end["items"] == [] and past_end["total"] == history["total"]


def test_provisional_fixture_and_native_case_details_are_visible(tmp_path: Path) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        seed(connection, tmp_path)
        connection.execute("UPDATE football.product_fixtures SET identity_status='PROVISIONAL'")
        connection.commit()
        page = case_page(connection, "fixtures", {})
        assert page["total"] == 2
        fixture = next(
            item for item in page["items"] if item["case_key"].startswith("fixture_record:")
        )
        detail = case_detail(connection, tmp_path, fixture["case_key"])
        assert detail["source_mappings"] and detail["published_forecasts"] == 1
        native = next(item for item in page["items"] if item["case_key"].startswith("fixture:"))
        assert (
            case_detail(connection, tmp_path, native["case_key"])["decision"]["disposition"]
            == "CONTRADICTORY"
        )


def test_missing_source_case_is_actual_and_does_not_recover_or_exclude(tmp_path: Path) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        seed(connection, tmp_path)
        connection.commit()
        (tmp_path / "raw/football_data_org.json").unlink()
        result = execute(
            connection, Path.cwd(), tmp_path, {"operation": "read", "view": "missing", "query": {}}
        )
        assert result["total"] == 1
        detail = data_detail(connection, tmp_path, result["items"][0]["case_key"])
        assert detail["status"] == "BLOCKED"
        assert detail["registration"]["sha256"]
        assert not (tmp_path / "raw/football_data_org.json").exists()


def test_python_bridge_rejects_mutation_requests(tmp_path: Path) -> None:
    with (
        isolated_database("202610310300") as url,
        psycopg.connect(url) as connection,
        pytest.raises(ValueError, match="read-only"),
    ):
        execute(connection, Path.cwd(), tmp_path, {"operation": "apply", "view": "identity"})


def test_go_resolution_read_only_database_bridge() -> None:
    with isolated_database("202610310300") as url:
        result = subprocess.run(
            ["go", "test", "./internal/app", "-run", "^TestResolutionDatabase", "-count=1"],
            cwd="go/api",
            env={**os.environ, "TEST_DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "[no tests to run]" not in result.stdout


def test_file_inventory_verification_keeps_full_dataset_checks_separate(tmp_path: Path) -> None:
    from football.integrity import PostgresIntegrityVerifier

    from tests.integration.test_integrity_verification import _registered_artifacts

    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        _, dataset, _, paths = _registered_artifacts(connection, tmp_path)
        verifier = PostgresIntegrityVerifier(connection, tmp_path)
        assert all(check.status == "PASS" for check in verifier.dataset_file_checks(dataset))
        assert verifier.verify_dataset(dataset).status == "PASS"
        (tmp_path / paths["dataset"]).unlink()
        assert any(check.status == "MISSING" for check in verifier.dataset_file_checks(dataset))
        assert verifier.verify_dataset(dataset).status == "MISSING"


def test_resolution_center_real_browser_is_read_only(tmp_path: Path, monkeypatch) -> None:
    from tests.integration.test_remediation_browser import running_application

    with isolated_database("202610310300") as url:
        with psycopg.connect(url) as connection:
            seed(connection, tmp_path)
        (tmp_path / "raw/api_football.json").unlink()
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path))
        with running_application(url, Path.cwd(), tmp_path / "api.log") as (_, env):
            env = {**env, "MATCHFORGE_RESOLUTION_BACKEND": env["MATCHFORGE_REMEDIATION_BACKEND"]}
            result = subprocess.run(
                [
                    "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "resolution.spec.ts",
                    "--grep",
                    "retained backend",
                    "--project=desktop",
                    "--workers=1",
                ],
                cwd="web",
                env=env,
                capture_output=True,
                text=True,
                timeout=150,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        with psycopg.connect(url) as connection:
            assert connection.execute(
                "SELECT to_regclass('football.resolution_review_events')"
            ).fetchone() == (None,)
            assert connection.execute(
                "SELECT count(*) FROM football.product_forecasts"
            ).fetchone() == (1,)
