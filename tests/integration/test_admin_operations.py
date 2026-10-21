"""Execute the protected Go control-plane regressions on a disposable migrated database."""

import os
import re
import subprocess
from pathlib import Path

import psycopg
from football.forecasting.runtime_models import ModelRegistration, PostgresModelRegistry

from tests.integration.test_team_identity_correction import isolated_database


def test_go_admin_operations_database_contracts() -> None:
    with isolated_database() as database_url:
        root = Path(__file__).resolve().parents[2]
        registration = ModelRegistration.from_bytes(
            (root / "config/models/current-champion.json").read_bytes()
        )
        with psycopg.connect(database_url) as connection:
            PostgresModelRegistry(connection).register(registration)
        result = subprocess.run(
            ["go", "test", "./internal/app", "-run", "^TestOperationsDatabase", "-count=1", "-v"],
            cwd=Path(__file__).resolve().parents[2] / "go/api",
            env={**os.environ, "TEST_DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    output = re.sub(r"postgres(?:ql)?://\S+", "[REDACTED_DSN]", result.stdout + result.stderr)
    print(output)
    assert result.returncode == 0, output
    assert "SKIP" not in output and "[no tests to run]" not in output
    assert output.count("--- PASS: TestOperationsDatabase") == 9, output
