"""Target outcomes stay outside the production feature-history query."""

from pathlib import Path

import psycopg
from football.product.api_football import ApiFootballClient
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.sync import ProductSync

from tests.integration.test_concurrency_stress import _history
from tests.integration.test_team_identity_correction import isolated_database


def test_production_feature_history_excludes_target_identity_before_loading_results(
    tmp_path: Path,
) -> None:
    with isolated_database() as url, psycopg.connect(url) as connection:
        history, home, away = _history(connection, tmp_path)
        now, revised_kickoff = connection.execute(
            "SELECT clock_timestamp(),clock_timestamp()+interval '2 days'"
        ).fetchone()
        target = history[0]
        product = ProductSync(
            connection, ApiFootballClient("offline"), tmp_path, MODEL_ARTIFACT_PATH
        )
        rows = product._batch_history([(target, home, away, revised_kickoff)], now)
        loaded = {row.fixture_id for row, _ in rows[home]}
        assert target not in loaded
        assert loaded == set(history) - {target}
