from __future__ import annotations

from typing import cast

import pytest
from football.providers import (
    CursorStrategyV1,
    ProviderScopeV1,
    ProviderSyncPolicyError,
    ProviderSyncPolicyRegistration,
    ProviderSyncPolicyRegistryError,
    ProviderSyncPolicyRegistryV1,
    ProviderSyncPolicyScopeBinding,
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


def test_sync_policy_registry_resolves_a_bound_policy_deterministically() -> None:
    registry = _registry()

    first = registry.resolve("provider", "fixtures", "competition=competition/season=season")
    second = registry.resolve("provider", "fixtures", "competition=competition/season=season")

    assert first == second
    assert first.policy_version == "provider-policy-v1"
    assert first.policy.freshness_target_seconds == 15 * 60
    assert len(first.policy.sha256) == 64


@pytest.mark.parametrize(
    ("provider_id", "resource_key", "scope_key"),
    (
        ("unknown", "fixtures", "competition=competition/season=season"),
        ("provider", "stats", "competition=competition/season=season"),
        ("provider", "fixtures", "global"),
    ),
)
def test_sync_policy_registry_fails_closed_for_unbound_scope(
    provider_id: str, resource_key: str, scope_key: str
) -> None:
    with pytest.raises(ProviderSyncPolicyRegistryError, match="unresolved"):
        _registry().resolve(provider_id, resource_key, scope_key)


def test_sync_policy_registry_fails_closed_for_unknown_policy_version() -> None:
    with pytest.raises(ProviderSyncPolicyRegistryError, match="version is unresolved"):
        _registry().resolve_version("provider", "unknown-policy-v7")


def test_sync_policy_registry_rejects_duplicate_binding_and_invalid_policy_relationships() -> None:
    registration = ProviderSyncPolicyRegistration("provider-policy-v1", _policy())
    binding = ProviderSyncPolicyScopeBinding(
        "provider", "fixtures", "competition=competition/season=season", "provider-policy-v1"
    )
    with pytest.raises(ProviderSyncPolicyRegistryError, match="bindings must be unique"):
        ProviderSyncPolicyRegistryV1((registration,), (binding, binding))
    with pytest.raises(ProviderSyncPolicyRegistryError, match="not enabled"):
        ProviderSyncPolicyRegistryV1(
            (registration,),
            (
                ProviderSyncPolicyScopeBinding(
                    "provider", "missing", binding.scope_key, binding.policy_version
                ),
            ),
        )
    with pytest.raises(ProviderSyncPolicyRegistryError, match="unknown policy version"):
        ProviderSyncPolicyRegistryV1(
            (registration,),
            (
                ProviderSyncPolicyScopeBinding(
                    "other_provider", "fixtures", binding.scope_key, binding.policy_version
                ),
            ),
        )


def test_sync_policy_registry_rejects_a_policy_version_with_different_bytes() -> None:
    with pytest.raises(ProviderSyncPolicyRegistryError, match="different policy SHA"):
        ProviderSyncPolicyRegistryV1(
            (
                ProviderSyncPolicyRegistration("provider-policy-v1", _policy()),
                ProviderSyncPolicyRegistration(
                    "provider-policy-v1", _policy(discovery_cadence_seconds=901)
                ),
            ),
            (),
        )


def test_sync_policy_registry_parses_only_the_existing_policy_contract() -> None:
    policy = _policy().to_dict()
    registry = ProviderSyncPolicyRegistryV1.from_dict(
        {
            "contract": "ProviderSyncPolicyRegistryV1",
            "registrations": [{"policy_version": "provider-policy-v1", "policy": policy}],
            "bindings": [
                {
                    "provider_id": "provider",
                    "resource_key": "fixtures",
                    "scope_key": "competition=competition/season=season",
                    "policy_version": "provider-policy-v1",
                }
            ],
        }
    )

    assert (
        registry.resolve("provider", "fixtures", "competition=competition/season=season").policy
        == _policy()
    )


def _registry() -> ProviderSyncPolicyRegistryV1:
    return ProviderSyncPolicyRegistryV1(
        (ProviderSyncPolicyRegistration("provider-policy-v1", _policy()),),
        (
            ProviderSyncPolicyScopeBinding(
                "provider",
                "fixtures",
                "competition=competition/season=season",
                "provider-policy-v1",
            ),
        ),
    )


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
