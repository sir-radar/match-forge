from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

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


class ProviderSyncPolicyRegistryError(ValueError):
    """Configured provider synchronization policy resolution is invalid."""


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


@dataclass(frozen=True, slots=True)
class ProviderSyncPolicyRegistration:
    policy_version: str
    policy: ProviderSyncPolicyV1

    def __post_init__(self) -> None:
        if not self.policy_version:
            raise ProviderSyncPolicyRegistryError("policy version must not be empty")


@dataclass(frozen=True, slots=True)
class ProviderSyncPolicyScopeBinding:
    provider_id: str
    resource_key: str
    scope_key: str
    policy_version: str

    def __post_init__(self) -> None:
        if not PROVIDER_PATTERN.fullmatch(self.provider_id):
            raise ProviderSyncPolicyRegistryError(
                "binding provider_id must use lowercase snake_case"
            )
        if not self.resource_key or not self.scope_key or not self.policy_version:
            raise ProviderSyncPolicyRegistryError("policy scope binding values must not be empty")


class ProviderSyncPolicyRegistryV1:
    """Immutable configured mapping from operational scope to sync policy."""

    def __init__(
        self,
        registrations: tuple[ProviderSyncPolicyRegistration, ...],
        bindings: tuple[ProviderSyncPolicyScopeBinding, ...],
    ) -> None:
        policies: dict[tuple[str, str], ProviderSyncPolicyRegistration] = {}
        for registration in registrations:
            key = (registration.policy.provider_id, registration.policy_version)
            previous = policies.get(key)
            if previous is not None:
                if previous.policy.sha256 != registration.policy.sha256:
                    raise ProviderSyncPolicyRegistryError(
                        "policy version resolves to different policy SHA-256 values"
                    )
                raise ProviderSyncPolicyRegistryError("policy registrations must be unique")
            policies[key] = registration

        scoped: dict[tuple[str, str, str], ProviderSyncPolicyRegistration] = {}
        for binding in bindings:
            binding_registration = policies.get((binding.provider_id, binding.policy_version))
            if binding_registration is None:
                raise ProviderSyncPolicyRegistryError(
                    "scope binding refers to an unknown policy version"
                )
            if binding.resource_key not in binding_registration.policy.enabled_resources:
                raise ProviderSyncPolicyRegistryError(
                    "scope binding resource is not enabled by policy"
                )
            if not _scope_is_enabled(binding_registration.policy, binding):
                raise ProviderSyncPolicyRegistryError("scope binding is not allowed by policy")
            binding_key = (binding.provider_id, binding.resource_key, binding.scope_key)
            if binding_key in scoped:
                raise ProviderSyncPolicyRegistryError("policy scope bindings must be unique")
            scoped[binding_key] = binding_registration

        self._policies = MappingProxyType(policies)
        self._scoped = MappingProxyType(scoped)

    @classmethod
    def from_path(cls, path: Path) -> ProviderSyncPolicyRegistryV1:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProviderSyncPolicyRegistryError(
                "provider sync policy configuration is unreadable"
            ) from error
        if not isinstance(payload, Mapping):
            raise ProviderSyncPolicyRegistryError(
                "provider sync policy configuration must be an object"
            )
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ProviderSyncPolicyRegistryV1:
        if payload.get("contract") != "ProviderSyncPolicyRegistryV1":
            raise ProviderSyncPolicyRegistryError(
                "unsupported provider sync policy registry contract"
            )
        registrations = tuple(
            _registration(value) for value in _object_list(payload, "registrations")
        )
        bindings = tuple(_binding(value) for value in _object_list(payload, "bindings"))
        return cls(registrations, bindings)

    def resolve(
        self, provider_id: str, resource_key: str, scope_key: str
    ) -> ProviderSyncPolicyRegistration:
        try:
            return self._scoped[(provider_id, resource_key, scope_key)]
        except KeyError as error:
            raise ProviderSyncPolicyRegistryError(
                "provider sync policy is unresolved for provider/resource/scope"
            ) from error

    def resolve_version(
        self, provider_id: str, policy_version: str
    ) -> ProviderSyncPolicyRegistration:
        try:
            return self._policies[(provider_id, policy_version)]
        except KeyError as error:
            raise ProviderSyncPolicyRegistryError(
                "provider sync policy version is unresolved"
            ) from error


def _registration(payload: Mapping[str, object]) -> ProviderSyncPolicyRegistration:
    policy_payload = _object(payload.get("policy"), "policy registration policy")
    return ProviderSyncPolicyRegistration(
        policy_version=_string(payload.get("policy_version"), "policy version"),
        policy=_policy(policy_payload),
    )


def _binding(payload: Mapping[str, object]) -> ProviderSyncPolicyScopeBinding:
    return ProviderSyncPolicyScopeBinding(
        provider_id=_string(payload.get("provider_id"), "binding provider_id"),
        resource_key=_string(payload.get("resource_key"), "binding resource_key"),
        scope_key=_string(payload.get("scope_key"), "binding scope_key"),
        policy_version=_string(payload.get("policy_version"), "binding policy_version"),
    )


def _policy(payload: Mapping[str, object]) -> ProviderSyncPolicyV1:
    if payload.get("contract", "ProviderSyncPolicyV1") != "ProviderSyncPolicyV1":
        raise ProviderSyncPolicyRegistryError("unsupported provider sync policy contract")
    return ProviderSyncPolicyV1(
        provider_id=_string(payload.get("provider_id"), "policy provider_id"),
        enabled_resources=_string_tuple(payload.get("enabled_resources"), "enabled_resources"),
        scopes=tuple(_scope(value) for value in _object_list(payload, "scopes")),
        discovery_cadence_seconds=_integer(payload.get("discovery_cadence_seconds"), "cadence"),
        fixture_lookahead_seconds=_optional_integer(
            payload.get("fixture_lookahead_seconds"), "fixture lookahead"
        ),
        result_backfill_seconds=_integer(payload.get("result_backfill_seconds"), "backfill"),
        historical_backfill=cast(
            Literal["disabled", "bounded", "full"],
            _string(payload.get("historical_backfill"), "historical backfill"),
        ),
        cursor_strategy=cast(
            CursorStrategyV1,
            _string(payload.get("cursor_strategy"), "cursor strategy"),
        ),
        request_timeout_seconds=_number(payload.get("request_timeout_seconds"), "request timeout"),
        max_attempts=_integer(payload.get("max_attempts"), "max attempts"),
        backoff_initial_seconds=_number(payload.get("backoff_initial_seconds"), "initial backoff"),
        backoff_max_seconds=_number(payload.get("backoff_max_seconds"), "maximum backoff"),
        steady_rate_limit_per_minute=_optional_integer(
            payload.get("steady_rate_limit_per_minute"), "steady rate limit"
        ),
        burst_limit=_optional_integer(payload.get("burst_limit"), "burst limit"),
        freshness_target_seconds=_integer(
            payload.get("freshness_target_seconds"), "freshness target"
        ),
        adapter_version=_string(payload.get("adapter_version"), "adapter version"),
    )


def _scope(payload: Mapping[str, object]) -> ProviderScopeV1:
    return ProviderScopeV1(
        competition_id=_string(payload.get("competition_id"), "scope competition_id"),
        season_id=_string(payload.get("season_id"), "scope season_id"),
        resources=_string_tuple(payload.get("resources"), "scope resources"),
    )


def _scope_is_enabled(
    policy: ProviderSyncPolicyV1, binding: ProviderSyncPolicyScopeBinding
) -> bool:
    return any(
        binding.resource_key in scope.resources
        and binding.scope_key == f"competition={scope.competition_id}/season={scope.season_id}"
        for scope in policy.scopes
    )


def _object_list(payload: Mapping[str, object], name: str) -> tuple[Mapping[str, object], ...]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise ProviderSyncPolicyRegistryError(f"{name} must be a list")
    return tuple(_object(item, name) for item in value)


def _object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProviderSyncPolicyRegistryError(f"{name} must be an object")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderSyncPolicyRegistryError(f"{name} must be a non-empty string")
    return value


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ProviderSyncPolicyRegistryError(f"{name} must be a list of non-empty strings")
    return tuple(value)


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProviderSyncPolicyRegistryError(f"{name} must be an integer")
    return value


def _optional_integer(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, name)


def _number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProviderSyncPolicyRegistryError(f"{name} must be a number")
    return float(value)


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
