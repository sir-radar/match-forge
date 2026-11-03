import argparse
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest
from football.product import cli
from football.product.api_football import ApiFootballError
from football.product.history_requests import HistoryDeferred


@pytest.mark.parametrize("failed_provider", ["pitchapi", "fotmob"])
def test_history_backfill_continues_after_one_provider_fails(
    monkeypatch: pytest.MonkeyPatch, failed_provider: str
) -> None:
    calls: list[str] = []

    class Connection:
        rollbacks = 0

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            self.rollbacks += 1

    def operational(
        _connection: Any, _args: argparse.Namespace, provider: str, _errors: dict[str, str]
    ) -> dict[str, object]:
        calls.append(provider)
        if provider == failed_provider:
            raise ValueError("provider catalogue is invalid")
        return {"stored": None, "acquired": []}

    def archive(_connection: Any, args: argparse.Namespace) -> dict[str, int]:
        calls.append(args.command)
        return {"matches_inserted": 2}

    monkeypatch.setattr(cli, "_operational_history", operational)
    monkeypatch.setattr(cli, "_openfootball", archive)
    monkeypatch.setattr(cli, "_football_data_uk", archive)
    args = cli.build_parser().parse_args(["backfill-history"])
    connection = Connection()

    result = cli._history_backfill(cast(Any, connection), args)

    assert len(calls) == 4
    assert calls[:2] == ["pitchapi", "fotmob"]
    assert result["status"] == "COMPLETED_WITH_ERRORS"
    assert result["errors"] == {failed_provider: "provider catalogue is invalid"}
    assert result[failed_provider] is None
    assert result["openfootball"] == result["football_data_uk"] == {"matches_inserted": 2}
    assert connection.rollbacks == 1


@pytest.mark.parametrize("provider", ["pitchapi", "fotmob"])
def test_operational_history_retains_discovery_summary(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    class Connection:
        def commit(self) -> None:
            pass

    monkeypatch.setenv(f"MATCHFORGE_{provider.upper()}_ENABLED", "true")
    monkeypatch.setenv("PITCH_API_TOKEN", "test-token")
    monkeypatch.setattr(cli, "OperationalProviderSync", lambda *_a, **_kw: object())
    discovery = {"scopes": 3, "requests": 1, "errors": {"native-league": "missing seasons"}}
    monkeypatch.setattr(cli, "_discover_history", lambda *_a: discovery)
    monkeypatch.setattr(cli, "run_scopes", lambda *_a, **_kw: [])
    args = cli.build_parser().parse_args(["backfill-history", "--scheduled"])
    args.data_root = Path("retained")
    errors: dict[str, str] = {}

    result = cli._operational_history(cast(Any, Connection()), args, provider, errors)

    assert result["discovery"] == discovery
    assert result["acquired"] == []
    assert errors == {f"{provider}-discovery": "{'native-league': 'missing seasons'}"}


@pytest.mark.parametrize("provider", ["openfootball", "football_data_uk"])
def test_history_backfill_selects_archive_provider_without_http_work(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    class Connection:
        def commit(self) -> None:
            pass

    def unexpected(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("unselected provider must not run")

    monkeypatch.setattr(cli, "_operational_history", unexpected)
    monkeypatch.setattr(cli, "_openfootball", unexpected)
    monkeypatch.setattr(cli, "_football_data_uk", unexpected)
    monkeypatch.setattr(cli, f"_{provider}", lambda *_a: {"matches_inserted": 7})
    args = cli.build_parser().parse_args(["backfill-history", "--provider-only", provider])

    result = cli._history_backfill(cast(Any, Connection()), args)

    assert result[provider] == {"matches_inserted": 7}
    assert result["status"] == "COMPLETED"


def test_scheduled_history_rejects_archive_selection_before_any_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MATCHFORGE_HISTORY_SYNC_ENABLED", "true")
    args = cli.build_parser().parse_args(
        ["backfill-history", "--scheduled", "--provider-only", "openfootball"]
    )
    with pytest.raises(ValueError, match="scheduled.*provider"):
        cli._history_backfill(cast(Any, object()), args)


@pytest.mark.parametrize("stage", ["stored", "discovery", "acquired"])
def test_history_backfill_propagates_nested_provider_failure(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    class Connection:
        def commit(self) -> None:
            pass

    failed = {"status": "FAILED", "error": "invalid retained resource"}
    summary: dict[str, Any] = {"stored": None, "discovery": None, "acquired": []}
    summary[stage] = [failed] if stage == "acquired" else failed
    monkeypatch.setattr(cli, "_operational_history", lambda *_a: summary)
    args = cli.build_parser().parse_args(["backfill-history", "--provider-only", "fotmob"])

    result = cli._history_backfill(cast(Any, Connection()), args)

    assert result["fotmob"] is summary
    assert result["errors"] == {"fotmob": "invalid retained resource"}
    assert result["status"] == "COMPLETED_WITH_ERRORS"


def test_country_refresh_is_explicit_and_does_not_request_acquisition() -> None:
    args = cli.build_parser().parse_args(
        ["refresh-competition-geography", "--provider", "pitchapi", "--data-root", "retained"]
    )
    assert args.command == "refresh-competition-geography"
    assert args.provider == "pitchapi"
    assert args.data_root == Path("retained")
    assert not hasattr(args, "refresh")


def test_scheduled_history_requires_explicit_enablement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATCHFORGE_HISTORY_SYNC_ENABLED", raising=False)
    args = cli.build_parser().parse_args(["backfill-history", "--scheduled"])
    with pytest.raises(ValueError, match="disabled"):
        cli._history_backfill(cast(Any, object()), args)


def test_scheduled_history_limits_preserve_manual_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["backfill-history", "--scheduled"])
    for provider in ("fotmob", "pitchapi"):
        monkeypatch.delenv(f"MATCHFORGE_{provider.upper()}_HISTORY_SCOPE_LIMIT", raising=False)
        assert cli._history_limits(args, provider) == (2, 1)
    monkeypatch.setenv("MATCHFORGE_FOTMOB_HISTORY_SCOPE_LIMIT", "0")
    assert cli._history_limits(args, "fotmob") == (0, 1)
    monkeypatch.setenv("MATCHFORGE_FOTMOB_HISTORY_SCOPE_LIMIT", "3")
    with pytest.raises(ValueError, match="0–2"):
        cli._history_limits(args, "fotmob")
    manual = cli.build_parser().parse_args(["backfill-history", "--provider-scope-budget", "8"])
    assert cli._history_limits(manual, "fotmob") == (8, 8)


@pytest.mark.parametrize(
    "result",
    [
        {"errors": {"league": "discovery failed"}},
        {"status": "COMPLETED_WITH_ERRORS", "steps": [{"status": "FAILED"}]},
        {"resources": [{"errors": {"detail": "unavailable"}}]},
    ],
)
def test_sync_step_preserves_structured_failures(result: dict[str, object]) -> None:
    class Connection:
        def commit(self) -> None:
            pass

    errors: dict[str, str] = {}
    assert cli._run_sync_step(cast(Any, Connection()), "provider", lambda: result, errors) == result
    assert "provider" in errors


@pytest.mark.parametrize(
    ("reason", "expected", "expected_errors"),
    (
        (
            "LIVE_SYNC_HAS_PRIORITY",
            {
                "status": "DEFERRED",
                "reason": "LIVE_SYNC_HAS_PRIORITY",
                "until": "2026-10-28T00:00:00+00:00",
            },
            {},
        ),
        ("PROVIDER_BUDGET_EXHAUSTED", None, {"fotmob": "PROVIDER_BUDGET_EXHAUSTED"}),
    ),
)
def test_sync_step_records_only_live_priority_as_deferred(
    reason: str,
    expected: object,
    expected_errors: dict[str, str],
) -> None:
    class Connection:
        def __init__(self) -> None:
            self.rollbacks = 0

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            self.rollbacks += 1

    connection = Connection()
    errors: dict[str, str] = {}
    deferred_until = datetime(2026, 10, 28, tzinfo=UTC)

    def defer() -> NoReturn:
        raise HistoryDeferred(reason, deferred_until)

    result = cli._run_sync_step(
        cast(Any, connection),
        "fotmob",
        lambda: cli._with_live_priority_deferral(cast(Any, connection), defer),
        errors,
    )

    assert result == expected
    assert connection.rollbacks == 1
    assert errors == expected_errors


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

        def refresh_forecasts(self, *_args: object, commit_batches: bool = False) -> int:
            assert commit_batches is True
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
        "operational_providers": {},
    }


@pytest.mark.parametrize(
    ("enabled_provider", "disabled_provider"),
    (("fotmob", "pitchapi"), ("pitchapi", "fotmob")),
)
def test_sync_all_enables_operational_providers_independently(
    monkeypatch: pytest.MonkeyPatch,
    enabled_provider: str,
    disabled_provider: str,
) -> None:
    calls: list[str] = []

    class Connection:
        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

    class Sync:
        def run(self, *_args: object, **_kwargs: object) -> dict[str, int]:
            return {"fixtures_from_history": 0}

        def backfill_fixtures_from_history(self, *_args: object) -> int:
            return 0

        def refresh_forecasts(self, *, commit_batches: bool = False) -> int:
            assert commit_batches is True
            return 0

    class OperationalSync:
        def __init__(self, *_args: object, provider_code: str, **_kwargs: object) -> None:
            self.provider_code = provider_code

        def sync_fotmob(self, *_args: object, **_kwargs: object) -> dict[str, str]:
            calls.append(self.provider_code)
            return {"provider": self.provider_code}

        def sync_pitchapi(self, *_args: object, **_kwargs: object) -> dict[str, str]:
            calls.append(self.provider_code)
            return {"provider": self.provider_code}

    monkeypatch.setenv("MATCHFORGE_FOTMOB_ENABLED", str(enabled_provider == "fotmob").lower())
    monkeypatch.setenv("MATCHFORGE_PITCHAPI_ENABLED", str(enabled_provider == "pitchapi").lower())
    monkeypatch.setenv("PITCH_API_TOKEN", "test-token")
    monkeypatch.setattr(cli, "ProductSync", lambda *_args, **_kwargs: Sync())
    monkeypatch.setattr(cli, "run_openfootball_backfill", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cli, "run_football_data_uk_backfill", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cli, "_run_external_predictions", lambda _args: 0)
    monkeypatch.setattr(cli, "OperationalProviderSync", OperationalSync)
    monkeypatch.setattr(cli, "FotmobClient", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "PitchApiClient", lambda *_args, **_kwargs: object())
    args = argparse.Namespace(
        database_url="postgresql://test",
        data_root=Path("data"),
        date=date(2026, 10, 9),
        from_date=None,
        history_concurrency=1,
    )

    result = cli._sync_all(cast(Any, Connection()), args)
    operational = cast(dict[str, object], result["operational_providers"])

    assert calls == [enabled_provider]
    assert disabled_provider not in operational
    assert operational == {enabled_provider: {"provider": enabled_provider}}


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("ENABLED", "NO_PREDICTIONS"), "COMPLETED"),
        (("ENABLED", "PARSER_BROKEN"), "COMPLETED_WITH_ERRORS"),
        (("PARTIAL",), "COMPLETED_WITH_ERRORS"),
        (("PARSER_BROKEN", "TECHNICALLY_UNAVAILABLE"), "FAILED"),
        (("DATE_MISMATCH",), "FAILED"),
        (("NO_DATE_PAGE",), "OUTSIDE_WINDOW"),
    ],
)
def test_source_collection_completion_is_truthful(statuses: tuple[str, ...], expected: str) -> None:
    from football.product.external_prediction_sources import SourceCollection

    results = [
        SourceCollection(f"source_{index}", "https://example.test", state)
        for index, state in enumerate(statuses)
    ]
    results.append(SourceCollection("forebet", "https://example.test", "TECHNICALLY_UNAVAILABLE"))
    assert cli._collection_status(results) == expected


def test_intentionally_disabled_forebet_is_not_a_failed_attempt() -> None:
    from football.product.external_prediction_sources import SourceCollection

    assert (
        cli._collection_status(
            [SourceCollection("forebet", "https://example.test", "TECHNICALLY_UNAVAILABLE")]
        )
        == "DISABLED"
    )
