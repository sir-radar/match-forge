from __future__ import annotations

from datetime import UTC, datetime, timedelta

from football.product.context_ingestion import parse_availability, parse_lineups
from football.product.context_sync import (
    ContextResource,
    ContextSyncConfig,
    FixtureContextTarget,
    plan_context_requests,
)

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


def _target(**overrides: object) -> FixtureContextTarget:
    values: dict[str, object] = {
        "provider_fixture_id": "123",
        "kickoff_at": NOW + timedelta(hours=24),
        "injury_capability": "SUPPORTED",
        "lineup_capability": "SUPPORTED",
        "last_injury_fetch_at": None,
        "last_lineup_fetch_at": None,
        "both_lineups_confirmed": False,
    }
    values.update(overrides)
    return FixtureContextTarget(**values)  # type: ignore[arg-type]


def test_context_sync_is_disabled_by_default() -> None:
    config = ContextSyncConfig.from_environ({})

    assert not config.context_enabled
    assert not config.injury_enabled
    assert not config.lineup_enabled
    assert config.request_cap == 100
    assert config.daily_reserve == 20


def test_injury_and_lineup_polling_windows_and_intervals() -> None:
    config = ContextSyncConfig(True, True, True, 100, 20)
    targets = (
        _target(provider_fixture_id="injury", kickoff_at=NOW + timedelta(hours=72)),
        _target(provider_fixture_id="lineup", kickoff_at=NOW + timedelta(minutes=90)),
        _target(
            provider_fixture_id="too-soon",
            kickoff_at=NOW + timedelta(minutes=5),
            last_lineup_fetch_at=NOW - timedelta(minutes=9),
        ),
        _target(provider_fixture_id="started", kickoff_at=NOW),
    )

    requests = plan_context_requests(targets, NOW, 200, config)

    assert ("injury", ContextResource.INJURIES) in {
        (item.provider_fixture_id, item.resource) for item in requests
    }
    assert ("lineup", ContextResource.LINEUPS) in {
        (item.provider_fixture_id, item.resource) for item in requests
    }
    assert ("too-soon", ContextResource.LINEUPS) not in {
        (item.provider_fixture_id, item.resource) for item in requests
    }
    assert all(item.provider_fixture_id != "started" for item in requests)


def test_unsupported_and_confirmed_resources_are_not_polled() -> None:
    config = ContextSyncConfig(True, True, True, 100, 20)
    targets = (
        _target(provider_fixture_id="unsupported", injury_capability="UNSUPPORTED_BY_COMPETITION"),
        _target(
            provider_fixture_id="confirmed",
            kickoff_at=NOW + timedelta(minutes=60),
            both_lineups_confirmed=True,
        ),
    )

    requests = plan_context_requests(targets, NOW, 200, config)

    assert all(
        not (
            item.provider_fixture_id == "unsupported" and item.resource is ContextResource.INJURIES
        )
        for item in requests
    )
    assert all(
        not (item.provider_fixture_id == "confirmed" and item.resource is ContextResource.LINEUPS)
        for item in requests
    )


def test_request_budget_preserves_daily_reserve_and_hard_cap() -> None:
    config = ContextSyncConfig(True, True, True, 2, 20)
    targets = tuple(_target(provider_fixture_id=str(index)) for index in range(5))

    assert len(plan_context_requests(targets, NOW, 22, config)) == 2
    assert plan_context_requests(targets, NOW, 20, config) == ()


def test_provider_context_parsers_keep_suspensions_and_lineup_roles_distinct() -> None:
    availability = parse_availability(
        (
            {
                "team": {"id": 1},
                "player": {"id": 10},
                "type": "Suspension",
                "reason": "Red Card",
            },
        )
    )
    lineups = parse_lineups(
        (
            {
                "team": {"id": 1},
                "coach": {"id": 2},
                "formation": "4-3-3",
                "startXI": [{"player": {"id": 10, "pos": "G", "grid": "1:1"}}],
                "substitutes": [{"player": {"id": 11, "pos": "D", "grid": None}}],
            },
        )
    )

    assert availability[0].availability_state == "UNAVAILABLE_SUSPENSION"
    assert lineups[0].players[0].role == "STARTER"
    assert lineups[0].players[0].normalized_position == "GK"
    assert lineups[0].players[1].role == "BENCH"
