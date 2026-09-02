from __future__ import annotations

from typing import cast

import pytest
from football.providers import (
    CursorStrategyV1,
    ProviderScopeV1,
    ProviderSyncPolicyError,
    ProviderSyncPolicyV1,
)


def test_sync_policy_is_immutable_and_hashes_canonical_payload() -> None:
    policy = _policy()

    assert policy.to_dict()["contract"] == "ProviderSyncPolicyV1"
    assert policy.to_dict()["cursor_strategy"] == "etag"
    assert len(policy.sha256) == 64
    with pytest.raises(AttributeError):
        policy.provider_id = "other"  # type: ignore[misc]


def test_sync_policy_rejects_duplicate_or_out_of_scope_resources() -> None:
    with pytest.raises(ProviderSyncPolicyError, match="resources must be unique"):
        _policy(enabled_resources=("fixtures", "fixtures"))
    with pytest.raises(ProviderSyncPolicyError, match="disabled resource"):
        _policy(enabled_resources=("fixtures",), scope_resources=("stats",))


def test_sync_policy_rejects_unbounded_or_invalid_runtime_values() -> None:
    with pytest.raises(ProviderSyncPolicyError, match="cadence must be positive"):
        _policy(discovery_cadence_seconds=0)
    with pytest.raises(ProviderSyncPolicyError, match="backoff maximum"):
        _policy(backoff_initial_seconds=10.0, backoff_max_seconds=1.0)
    with pytest.raises(ProviderSyncPolicyError, match="cursor strategy"):
        _policy(cursor_strategy=cast(CursorStrategyV1, "poll_everything"))


def _policy(
    *,
    enabled_resources: tuple[str, ...] = ("fixtures", "stats"),
    discovery_cadence_seconds: int = 900,
    backoff_initial_seconds: float = 1.0,
    backoff_max_seconds: float = 30.0,
    cursor_strategy: CursorStrategyV1 = "etag",
    scope_resources: tuple[str, ...] = ("fixtures",),
) -> ProviderSyncPolicyV1:
    return ProviderSyncPolicyV1(
        provider_id="provider",
        enabled_resources=enabled_resources,
        scopes=(ProviderScopeV1("competition", "season", scope_resources),),
        discovery_cadence_seconds=discovery_cadence_seconds,
        fixture_lookahead_seconds=7 * 24 * 60 * 60,
        result_backfill_seconds=24 * 60 * 60,
        historical_backfill="bounded",
        cursor_strategy=cursor_strategy,
        request_timeout_seconds=30.0,
        max_attempts=3,
        backoff_initial_seconds=backoff_initial_seconds,
        backoff_max_seconds=backoff_max_seconds,
        steady_rate_limit_per_minute=30,
        burst_limit=5,
        freshness_target_seconds=15 * 60,
        adapter_version="provider-v1",
    )
