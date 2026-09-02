from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes
from football.providers.capabilities import ProviderScopeV1

CursorStrategyV1 = Literal[
    "none",
    "updated_since",
    "etag",
    "last_modified",
    "provider_sequence",
    "webhook_plus_reconcile",
]

_CURSOR_STRATEGIES = frozenset(
    (
        "none",
        "updated_since",
        "etag",
        "last_modified",
        "provider_sequence",
        "webhook_plus_reconcile",
    )
)


class ProviderSyncPolicyError(ValueError):
    """A provider synchronization policy violates its versioned contract."""


@dataclass(frozen=True, slots=True)
class ProviderSyncPolicyV1:
    provider_id: str
    enabled_resources: tuple[str, ...]
    scopes: tuple[ProviderScopeV1, ...]
    discovery_cadence_seconds: int
    fixture_lookahead_seconds: int | None
    result_backfill_seconds: int
    historical_backfill: Literal["disabled", "bounded", "full"]
    cursor_strategy: CursorStrategyV1
    request_timeout_seconds: float
    max_attempts: int
    backoff_initial_seconds: float
    backoff_max_seconds: float
    steady_rate_limit_per_minute: int | None
    burst_limit: int | None
    freshness_target_seconds: int
    adapter_version: str
    contract: str = "ProviderSyncPolicyV1"

    def __post_init__(self) -> None:
        _validate_identity(self)
        _validate_scopes(self)
        _validate_schedule(self)
        _validate_retry(self)
        _validate_limits(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "enabled_resources": list(self.enabled_resources),
            "scopes": [scope.to_dict() for scope in self.scopes],
            "discovery_cadence_seconds": self.discovery_cadence_seconds,
            "fixture_lookahead_seconds": self.fixture_lookahead_seconds,
            "result_backfill_seconds": self.result_backfill_seconds,
            "historical_backfill": self.historical_backfill,
            "cursor_strategy": self.cursor_strategy,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_attempts": self.max_attempts,
            "backoff_initial_seconds": self.backoff_initial_seconds,
            "backoff_max_seconds": self.backoff_max_seconds,
            "steady_rate_limit_per_minute": self.steady_rate_limit_per_minute,
            "burst_limit": self.burst_limit,
            "freshness_target_seconds": self.freshness_target_seconds,
            "adapter_version": self.adapter_version,
        }


def _validate_identity(policy: ProviderSyncPolicyV1) -> None:
    if policy.contract != "ProviderSyncPolicyV1":
        raise ProviderSyncPolicyError("unsupported provider sync policy contract")
    if not PROVIDER_PATTERN.fullmatch(policy.provider_id):
        raise ProviderSyncPolicyError("provider_id must use lowercase snake_case")
    if not policy.enabled_resources or any(not resource for resource in policy.enabled_resources):
        raise ProviderSyncPolicyError("enabled resources must not be empty")
    if len(policy.enabled_resources) != len(set(policy.enabled_resources)):
        raise ProviderSyncPolicyError("enabled resources must be unique")
    if not policy.adapter_version:
        raise ProviderSyncPolicyError("adapter_version must not be empty")


def _validate_scopes(policy: ProviderSyncPolicyV1) -> None:
    if not policy.scopes:
        raise ProviderSyncPolicyError("sync policy requires scopes")
    enabled = set(policy.enabled_resources)
    if any(resource not in enabled for scope in policy.scopes for resource in scope.resources):
        raise ProviderSyncPolicyError("sync scope references disabled resource")


def _validate_schedule(policy: ProviderSyncPolicyV1) -> None:
    if policy.discovery_cadence_seconds <= 0:
        raise ProviderSyncPolicyError("discovery cadence must be positive")
    if policy.fixture_lookahead_seconds is not None and policy.fixture_lookahead_seconds < 0:
        raise ProviderSyncPolicyError("fixture lookahead must not be negative")
    if policy.result_backfill_seconds < 0 or policy.freshness_target_seconds <= 0:
        raise ProviderSyncPolicyError("backfill and freshness values are invalid")
    if policy.historical_backfill not in {"disabled", "bounded", "full"}:
        raise ProviderSyncPolicyError("historical backfill mode is unsupported")
    if policy.cursor_strategy not in _CURSOR_STRATEGIES:
        raise ProviderSyncPolicyError("cursor strategy is unsupported")


def _validate_retry(policy: ProviderSyncPolicyV1) -> None:
    if not _finite_positive(policy.request_timeout_seconds):
        raise ProviderSyncPolicyError("request timeout must be finite and positive")
    if policy.max_attempts <= 0:
        raise ProviderSyncPolicyError("max attempts must be positive")
    if not _finite_positive(policy.backoff_initial_seconds):
        raise ProviderSyncPolicyError("backoff initial delay must be finite and positive")
    if not _finite_positive(policy.backoff_max_seconds):
        raise ProviderSyncPolicyError("backoff maximum delay must be finite and positive")
    if policy.backoff_max_seconds < policy.backoff_initial_seconds:
        raise ProviderSyncPolicyError("backoff maximum delay must not precede initial delay")


def _validate_limits(policy: ProviderSyncPolicyV1) -> None:
    if policy.steady_rate_limit_per_minute is not None and policy.steady_rate_limit_per_minute <= 0:
        raise ProviderSyncPolicyError("steady rate limit must be positive")
    if policy.burst_limit is not None and policy.burst_limit <= 0:
        raise ProviderSyncPolicyError("burst limit must be positive")


def _finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0
