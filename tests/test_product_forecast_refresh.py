import argparse
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from football.forecasting.pitchapi_v3 import TransferableParametersV1
from football.product import cli as product_cli
from football.product.domain import (
    MODEL_ARTIFACT_PATH,
    FinishedMatch,
    forecast_from_history,
    forecast_history_window,
    forecast_input_sha,
    stable_id,
)
from football.product.sync import ProductSync


def test_preloaded_artifact_preserves_forecast() -> None:
    home = stable_id("test-preloaded", "home")
    away = stable_id("test-preloaded", "away")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    history = [
        FinishedMatch(
            stable_id("test-preloaded", team, index),
            start + timedelta(days=index),
            team,
            stable_id("test-preloaded", "opponent", team, index),
            1 + index % 3,
            index % 2,
        )
        for team in (home, away)
        for index in range(10)
    ]
    expected = forecast_from_history(
        artifact_path=MODEL_ARTIFACT_PATH,
        target_kickoff=start + timedelta(days=12),
        home_team_id=home,
        away_team_id=away,
        history=history,
    )
    parameters = TransferableParametersV1(
        **json.loads(MODEL_ARTIFACT_PATH.read_bytes())["parameters"]
    )
    with patch.object(Path, "read_text", side_effect=AssertionError("artifact reloaded")):
        actual = forecast_from_history(
            artifact_path=MODEL_ARTIFACT_PATH,
            target_kickoff=start + timedelta(days=12),
            home_team_id=home,
            away_team_id=away,
            history=history,
            parameters=parameters,
        )
    assert actual == expected


def test_batched_history_excludes_same_kickoff_and_date_only_same_day() -> None:
    home = stable_id("test-batch", "home")
    away = stable_id("test-batch", "away")
    other = stable_id("test-batch", "other")
    kickoff = datetime(2026, 10, 17, 14, tzinfo=UTC)
    earlier = FinishedMatch(
        stable_id("test-batch", 1), kickoff - timedelta(days=1), home, other, 2, 0
    )
    same = FinishedMatch(stable_id("test-batch", 2), kickoff, away, other, 1, 1)
    date_only = FinishedMatch(
        stable_id("test-batch", 3), kickoff - timedelta(hours=2), other, away, 0, 1
    )
    unrelated = FinishedMatch(
        stable_id("test-batch", 4),
        kickoff - timedelta(days=1),
        other,
        stable_id("test-batch", "other2"),
        1,
        2,
    )
    by_team = {
        home: [(earlier, "EXACT")],
        away: [(same, "EXACT"), (date_only, "DATE_ONLY")],
        other: [(unrelated, "EXACT")],
    }
    assert ProductSync._target_history(by_team, home, away, kickoff) == [earlier]


def test_discarded_older_match_does_not_change_rolling_input_identity() -> None:
    home = stable_id("test-window", "home")
    away = stable_id("test-window", "away")
    fixture = stable_id("test-window", "target")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    kickoff = start + timedelta(days=12)
    history = [
        FinishedMatch(
            stable_id("test-window", team, index),
            start + timedelta(days=index),
            team,
            stable_id("test-window", "opponent", team, index),
            2,
            1,
        )
        for team in (home, away)
        for index in range(11)
    ]
    corrected = [replace(history[0], home_goals=9), *history[1:]]
    first = forecast_history_window(history, kickoff, home, away)
    second = forecast_history_window(corrected, kickoff, home, away)
    assert first is not None and first == second
    assert len(first) == 20
    assert forecast_input_sha(fixture, kickoff, home, away, first) == forecast_input_sha(
        fixture, kickoff, home, away, second
    )
    with pytest.raises(ValueError, match="duplicate fixture IDs"):
        forecast_history_window([*history, history[0]], kickoff, home, away)
    assert forecast_from_history(
        artifact_path=MODEL_ARTIFACT_PATH,
        target_kickoff=kickoff,
        home_team_id=home,
        away_team_id=away,
        history=history,
    ) == forecast_from_history(
        artifact_path=MODEL_ARTIFACT_PATH,
        target_kickoff=kickoff,
        home_team_id=home,
        away_team_id=away,
        history=corrected,
    )


def test_full_sync_refreshes_after_operational_history(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setenv("MATCHFORGE_PITCHAPI_ENABLED", "true")
    monkeypatch.setenv("MATCHFORGE_FOTMOB_ENABLED", "true")
    monkeypatch.setattr(
        product_cli,
        "_run_sync_step",
        lambda _connection, name, _operation, _errors: calls.append(name),
    )
    monkeypatch.setattr(product_cli, "_run_external_predictions", lambda _args: 0)
    args = argparse.Namespace(
        database_url="unused",
        data_root=Path("unused"),
        date=date(2026, 10, 13),
        from_date=None,
        history_concurrency=1,
    )
    product_cli._sync_all(MagicMock(), args)
    assert calls.index("forecasts") > calls.index("pitchapi")
    assert calls.index("forecasts") > calls.index("fotmob")
