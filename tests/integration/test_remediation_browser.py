"""Real Go/Python scheduling and browser reads over disposable synthetic fixtures."""

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import timedelta
from functools import partial
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from football.product.domain import FinishedMatch, forecast_from_history

from tests.integration import test_live_context as live
from tests.integration import test_product_analytics as analytics
from tests.integration import test_public_reports as reports

report_database = reports.report_database


@pytest.fixture(autouse=True)
def api_fixture_identity(monkeypatch):
    # Shared storage fixtures use compact UUID(int=...) values; the real public
    # HTTP boundary correctly requires an RFC-compatible UUID version/variant.
    identity = uuid4()
    for module in (live, analytics, reports):
        monkeypatch.setattr(module, "FIXTURE", identity)
    artifact = Path("docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json")
    forecast = forecast_from_history(
        artifact_path=artifact,
        target_kickoff=live.KICKOFF,
        home_team_id=live.HOME,
        away_team_id=live.AWAY,
        history=[
            FinishedMatch(
                uuid4(), live.KICKOFF - timedelta(days=20 + n), live.HOME, live.AWAY, 2, 1
            )
            for n in range(10)
        ],
    )
    assert forecast is not None
    monkeypatch.setattr(
        reports,
        "_insert_forecast",
        partial(
            live._insert_forecast,
            forecast=forecast,
            artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        ),
    )
    probabilities = {
        "home": forecast.home_probability,
        "draw": forecast.draw_probability,
        "away": forecast.away_probability,
        "total_over_2_5": sum(forecast.total_goal_distribution[3:]),
        "btts_yes": forecast.btts_yes,
    }
    monkeypatch.setattr(
        reports, "_revision", partial(analytics._revision, probabilities=probabilities)
    )


def test_normal_application_scheduler_reaches_real_browser(report_database):
    reports._publish_current_bucket_forecast(report_database)
    root = Path.cwd()
    env = os.environ | {
        "DATABASE_URL": report_database,
        "API_ADDR": "127.0.0.1:58081",
        "WEB_ORIGIN": "http://127.0.0.1:3009",
        "MATCHFORGE_REPO_ROOT": str(root),
        "MATCHFORGE_OPERATIONAL_SYNC_INTERVAL": "0",
        "MATCHFORGE_HISTORY_SYNC_ENABLED": "false",
        "MATCHFORGE_REAL_PROVIDER_E2E": "false",
        "MATCHFORGE_REMEDIATION_BACKEND": "http://127.0.0.1:58081",
    }
    with (root / ".local/remediation-browser-api.log").open("w") as log:
        process = subprocess.Popen(
            [str(root / ".local/bin/football-api")], env=env, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            for _ in range(100):
                assert process.poll() is None, "isolated API stopped; inspect its local log"
                try:
                    with urllib.request.urlopen("http://127.0.0.1:58081/healthz", timeout=1):
                        break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.1)
            result = subprocess.run(
                [
                    "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "remediation-backend.spec.ts",
                    "--project=desktop",
                    "--workers=1",
                ],
                cwd=root / "web",
                env=env,
                capture_output=True,
                text=True,
                timeout=150,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            with psycopg.connect(report_database) as connection:
                assert (
                    connection.execute(
                        "SELECT count(*) FROM football.product_sync_runs "
                        "WHERE sync_type='PUBLIC_REPORTS' AND status='SUCCEEDED'"
                    ).fetchone()[0]
                    >= 1
                )
                assert connection.execute(
                    "SELECT count(DISTINCT report_kind) FROM football.product_read_reports"
                ).fetchone() == (3,)
                rows = connection.execute(
                    "SELECT report_kind,scope_id::text,horizon,record_sha256,source_fingerprint "
                    "FROM football.product_read_reports ORDER BY report_kind,horizon,scope_id"
                ).fetchall()
                (root / ".local/remediation-browser-evidence.json").write_text(
                    json.dumps({"fixture_id": str(reports.FIXTURE), "reports": rows}, indent=2)
                    + "\n"
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
