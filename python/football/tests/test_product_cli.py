import argparse
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from football.product import cli
from football.product.api_football import ApiFootballError


def test_sync_all_continues_after_api_football_quota_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Connection:
        def __init__(self) -> None:
            self.rollbacks = 0

        def rollback(self) -> None:
            self.rollbacks += 1

        def commit(self) -> None:
            pass

    class Sync:
        def run(self, *_args: object, **_kwargs: object) -> dict[str, int]:
            calls.append("mvp")
            raise ApiFootballError("API-Football rejected /leagues: request limit reached")

        def backfill_fixtures_from_history(self, *_args: object) -> int:
            calls.append("fixture_history")
            return 2

        def refresh_forecasts(self, *_args: object) -> int:
            calls.append("forecasts")
            return 3

    def openfootball(*_args: object, **_kwargs: object) -> dict[str, int]:
        calls.append("openfootball")
        return {"matches_inserted": 5}

    def football_data_uk(*_args: object, **_kwargs: object) -> dict[str, int]:
        calls.append("football_data_uk")
        return {"matches_inserted": 7}

    def external_predictions(_args: argparse.Namespace) -> int:
        calls.append("external_predictions")
        return 0

    monkeypatch.setenv("API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(cli, "ProductSync", lambda *_args, **_kwargs: Sync())
    monkeypatch.setattr(cli, "run_openfootball_backfill", openfootball)
    monkeypatch.setattr(cli, "run_football_data_uk_backfill", football_data_uk)
    monkeypatch.setattr(cli, "_run_external_predictions", external_predictions)
    connection = Connection()
    args = argparse.Namespace(
        database_url="postgresql://test",
        data_root=Path("data"),
        date=date(2026, 10, 9),
        from_date=None,
        history_concurrency=1,
    )

    result = cli._sync_all(cast(Any, connection), args)

    assert calls == [
        "mvp",
        "openfootball",
        "football_data_uk",
        "fixture_history",
        "forecasts",
        "external_predictions",
    ]
    assert connection.rollbacks == 1
    assert result == {
        "status": "COMPLETED_WITH_ERRORS",
        "errors": {
            "mvp": "API-Football rejected /leagues: request limit reached",
        },
        "mvp": None,
        "history": {
            "openfootball": {"matches_inserted": 5},
            "football_data_uk": {"matches_inserted": 7},
        },
        "fixtures_from_history": 2,
        "forecasts_created": 3,
        "external_predictions_exit_code": 0,
    }
