from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

JitterModeV1 = Literal["none", "full", "equal"]
_JITTER_MODES = frozenset(("none", "full", "equal"))


class ProviderRuntimePolicyError(ValueError):
    """A provider runtime policy violates its versioned contract."""


@dataclass(frozen=True, slots=True)
class ProviderRuntimePolicyV1:
    provider_id: str
    request_timeout_seconds: float
    max_concurrency: int
    steady_rate_limit_per_minute: int | None
    burst_limit: int | None
    quota_window_seconds: int | None
    quota_budget: int | None
    retryable_statuses: tuple[int, ...]
    retryable_error_classes: tuple[str, ...]
    max_attempts: int
    backoff_initial_seconds: float
    backoff_max_seconds: float
    jitter_mode: JitterModeV1
    circuit_failure_threshold: int
    circuit_cooldown_seconds: int
    circuit_probe_interval_seconds: int
    stale_data_escalation_seconds: int
    adapter_version: str
    contract: str = "ProviderRuntimePolicyV1"

    def __post_init__(self) -> None:
        _validate_identity(self)
        _validate_limits(self)
        _validate_retry(self)
        _validate_circuit(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_concurrency": self.max_concurrency,
            "steady_rate_limit_per_minute": self.steady_rate_limit_per_minute,
            "burst_limit": self.burst_limit,
            "quota_window_seconds": self.quota_window_seconds,
            "quota_budget": self.quota_budget,
            "retryable_statuses": list(self.retryable_statuses),
            "retryable_error_classes": list(self.retryable_error_classes),
            "max_attempts": self.max_attempts,
            "backoff_initial_seconds": self.backoff_initial_seconds,
            "backoff_max_seconds": self.backoff_max_seconds,
            "jitter_mode": self.jitter_mode,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_cooldown_seconds": self.circuit_cooldown_seconds,
            "circuit_probe_interval_seconds": self.circuit_probe_interval_seconds,
            "stale_data_escalation_seconds": self.stale_data_escalation_seconds,
            "adapter_version": self.adapter_version,
        }


def _validate_identity(policy: ProviderRuntimePolicyV1) -> None:
    if policy.contract != "ProviderRuntimePolicyV1":
        raise ProviderRuntimePolicyError("unsupported provider runtime policy contract")
    if not PROVIDER_PATTERN.fullmatch(policy.provider_id):
        raise ProviderRuntimePolicyError("provider_id must use lowercase snake_case")
    if not policy.adapter_version:
        raise ProviderRuntimePolicyError("adapter_version must not be empty")
    if policy.jitter_mode not in _JITTER_MODES:
        raise ProviderRuntimePolicyError("jitter mode is unsupported")
    if not policy.retryable_statuses and not policy.retryable_error_classes:
        raise ProviderRuntimePolicyError("runtime policy requires retryable failures")
    if len(policy.retryable_statuses) != len(set(policy.retryable_statuses)):
        raise ProviderRuntimePolicyError("retryable statuses must be unique")
    if any(status < 100 or status > 599 for status in policy.retryable_statuses):
        raise ProviderRuntimePolicyError("retryable status must be a valid HTTP status")
    if any(not error_class for error_class in policy.retryable_error_classes):
        raise ProviderRuntimePolicyError("retryable error classes must not be empty")
    if len(policy.retryable_error_classes) != len(set(policy.retryable_error_classes)):
        raise ProviderRuntimePolicyError("retryable error classes must be unique")


def _validate_limits(policy: ProviderRuntimePolicyV1) -> None:
    if policy.max_concurrency <= 0:
        raise ProviderRuntimePolicyError("max concurrency must be positive")
    if policy.steady_rate_limit_per_minute is not None and policy.steady_rate_limit_per_minute <= 0:
        raise ProviderRuntimePolicyError("steady rate limit must be positive")
    if policy.burst_limit is not None and policy.burst_limit <= 0:
        raise ProviderRuntimePolicyError("burst limit must be positive")
    if (policy.quota_window_seconds is None) != (policy.quota_budget is None):
        raise ProviderRuntimePolicyError("quota window and budget must be paired")
    if policy.quota_window_seconds is not None and policy.quota_window_seconds <= 0:
        raise ProviderRuntimePolicyError("quota window must be positive")
    if policy.quota_budget is not None and policy.quota_budget <= 0:
        raise ProviderRuntimePolicyError("quota budget must be positive")


def _validate_retry(policy: ProviderRuntimePolicyV1) -> None:
    if not _finite_positive(policy.request_timeout_seconds):
        raise ProviderRuntimePolicyError("request timeout must be finite and positive")
    if policy.max_attempts <= 0:
        raise ProviderRuntimePolicyError("max attempts must be positive")
    if not _finite_positive(policy.backoff_initial_seconds):
        raise ProviderRuntimePolicyError("backoff initial delay must be finite and positive")
    if not _finite_positive(policy.backoff_max_seconds):
        raise ProviderRuntimePolicyError("backoff maximum delay must be finite and positive")
    if policy.backoff_max_seconds < policy.backoff_initial_seconds:
        raise ProviderRuntimePolicyError("backoff maximum delay must not precede initial delay")


def _validate_circuit(policy: ProviderRuntimePolicyV1) -> None:
    if policy.circuit_failure_threshold <= 0:
        raise ProviderRuntimePolicyError("circuit failure threshold must be positive")
    if policy.circuit_cooldown_seconds <= 0 or policy.circuit_probe_interval_seconds <= 0:
        raise ProviderRuntimePolicyError("circuit timing values must be positive")
    if policy.stale_data_escalation_seconds <= 0:
        raise ProviderRuntimePolicyError("stale-data escalation must be positive")


def _finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0
