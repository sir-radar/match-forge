from __future__ import annotations

from typing import cast

import pytest
from football.providers import (
    JitterModeV1,
    ProviderRuntimePolicyError,
    ProviderRuntimePolicyV1,
)


def test_runtime_policy_is_canonical_and_immutable() -> None:
    policy = _policy()

    assert policy.to_dict()["contract"] == "ProviderRuntimePolicyV1"
    assert len(policy.sha256) == 64
    with pytest.raises(AttributeError):
        policy.max_concurrency = 2  # type: ignore[misc]


def test_runtime_policy_rejects_unpaired_quota_and_invalid_status() -> None:
    with pytest.raises(ProviderRuntimePolicyError, match="quota window and budget"):
        _policy(quota_budget=None, quota_window_seconds=60)
    with pytest.raises(ProviderRuntimePolicyError, match="valid HTTP status"):
        _policy(retryable_statuses=(429, 700))


def test_runtime_policy_rejects_unbounded_retry_and_circuit_values() -> None:
    with pytest.raises(ProviderRuntimePolicyError, match="backoff maximum"):
        _policy(backoff_initial_seconds=5.0, backoff_max_seconds=1.0)
    with pytest.raises(ProviderRuntimePolicyError, match="circuit failure"):
        _policy(circuit_failure_threshold=0)
    with pytest.raises(ProviderRuntimePolicyError, match="jitter mode"):
        _policy(jitter_mode=cast(JitterModeV1, "random"))


def _policy(
    *,
    quota_budget: int | None = 100,
    quota_window_seconds: int | None = 60,
    retryable_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
    backoff_initial_seconds: float = 1.0,
    backoff_max_seconds: float = 30.0,
    circuit_failure_threshold: int = 5,
    jitter_mode: JitterModeV1 = "full",
) -> ProviderRuntimePolicyV1:
    return ProviderRuntimePolicyV1(
        provider_id="provider",
        request_timeout_seconds=30.0,
        max_concurrency=2,
        steady_rate_limit_per_minute=30,
        burst_limit=5,
        quota_window_seconds=quota_window_seconds,
        quota_budget=quota_budget,
        retryable_statuses=retryable_statuses,
        retryable_error_classes=("timeout", "connection_reset"),
        max_attempts=3,
        backoff_initial_seconds=backoff_initial_seconds,
        backoff_max_seconds=backoff_max_seconds,
        jitter_mode=jitter_mode,
        circuit_failure_threshold=circuit_failure_threshold,
        circuit_cooldown_seconds=300,
        circuit_probe_interval_seconds=60,
        stale_data_escalation_seconds=900,
        adapter_version="provider-v1",
    )
