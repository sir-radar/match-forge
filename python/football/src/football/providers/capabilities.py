from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ProviderCapabilityError(ValueError):
    """A provider capability declaration violates its versioned contract."""


@dataclass(frozen=True, slots=True)
class ProviderScopeV1:
    competition_id: str
    season_id: str
    resources: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.competition_id or not self.season_id:
            raise ProviderCapabilityError("provider scope identifiers must not be empty")
        if not self.resources or any(not resource for resource in self.resources):
            raise ProviderCapabilityError("provider scope must declare resources")
        if len(self.resources) != len(set(self.resources)):
            raise ProviderCapabilityError("provider scope resources must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "competition_id": self.competition_id,
            "season_id": self.season_id,
            "resources": list(self.resources),
        }


@dataclass(frozen=True, slots=True)
class ProviderResourceCapabilityV1:
    resource: str
    historical_start: date | None = None
    historical_end: date | None = None
    coverage_density: float | None = None

    def __post_init__(self) -> None:
        if not self.resource:
            raise ProviderCapabilityError("provider resource must not be empty")
        if (
            self.historical_start
            and self.historical_end
            and self.historical_end < self.historical_start
        ):
            raise ProviderCapabilityError("provider resource historical range is reversed")
        if self.coverage_density is not None and not 0.0 <= self.coverage_density <= 1.0:
            raise ProviderCapabilityError("provider resource coverage density must be 0..1")

    def to_dict(self) -> dict[str, object]:
        return {
            "resource": self.resource,
            "historical_start": self.historical_start.isoformat()
            if self.historical_start
            else None,
            "historical_end": self.historical_end.isoformat() if self.historical_end else None,
            "coverage_density": self.coverage_density,
        }


@dataclass(frozen=True, slots=True)
class ProviderCapabilityV1:
    provider_id: str
    enabled: bool
    terms_status: str
    supported_scopes: tuple[ProviderScopeV1, ...]
    resources: tuple[ProviderResourceCapabilityV1, ...]
    update_semantics: str
    incremental_cursor_support: bool
    webhook_support: bool
    rate_limit_per_minute: int | None
    credential_ref: str | None
    adapter_version: str
    contract: str = "ProviderCapabilityV1"

    def __post_init__(self) -> None:
        _validate_capability_identity(self)
        _validate_capability_resources(self)
        _validate_capability_runtime(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "enabled": self.enabled,
            "terms_status": self.terms_status,
            "supported_scopes": [scope.to_dict() for scope in self.supported_scopes],
            "resources": [resource.to_dict() for resource in self.resources],
            "update_semantics": self.update_semantics,
            "incremental_cursor_support": self.incremental_cursor_support,
            "webhook_support": self.webhook_support,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "credential_ref": self.credential_ref,
            "adapter_version": self.adapter_version,
        }


class ProviderCapabilityRegistryV1:
    """Immutable provider capability declarations for one process configuration."""

    def __init__(self, capabilities: tuple[ProviderCapabilityV1, ...]) -> None:
        provider_ids = [capability.provider_id for capability in capabilities]
        if len(provider_ids) != len(set(provider_ids)):
            raise ProviderCapabilityError("provider capability provider_ids must be unique")
        self._capabilities = MappingProxyType(
            {capability.provider_id: capability for capability in capabilities}
        )

    def get(self, provider_id: str) -> ProviderCapabilityV1:
        try:
            return self._capabilities[provider_id]
        except KeyError as error:
            raise ProviderCapabilityError(
                f"provider capability is not registered: {provider_id}"
            ) from error

    def enabled(self) -> tuple[ProviderCapabilityV1, ...]:
        return tuple(capability for capability in self._capabilities.values() if capability.enabled)

    def all(self) -> tuple[ProviderCapabilityV1, ...]:
        return tuple(self._capabilities.values())


def _validate_capability_identity(capability: ProviderCapabilityV1) -> None:
    if capability.contract != "ProviderCapabilityV1":
        raise ProviderCapabilityError("unsupported provider capability contract")
    if not PROVIDER_PATTERN.fullmatch(capability.provider_id):
        raise ProviderCapabilityError("provider_id must use lowercase snake_case")
    if not capability.terms_status or not capability.update_semantics:
        raise ProviderCapabilityError("provider terms and update semantics are required")
    if not _VERSION_PATTERN.fullmatch(capability.adapter_version):
        raise ProviderCapabilityError("adapter_version is invalid")


def _validate_capability_resources(capability: ProviderCapabilityV1) -> None:
    if not capability.supported_scopes:
        raise ProviderCapabilityError("provider capability requires supported scopes")
    if not capability.resources:
        raise ProviderCapabilityError("provider capability requires resources")
    resource_ids = [resource.resource for resource in capability.resources]
    if len(resource_ids) != len(set(resource_ids)):
        raise ProviderCapabilityError("provider resources must be unique")
    declared_resources = set(resource_ids)
    scope_ids = [(scope.competition_id, scope.season_id) for scope in capability.supported_scopes]
    if len(scope_ids) != len(set(scope_ids)):
        raise ProviderCapabilityError("provider scopes must be unique")
    if any(
        resource not in declared_resources
        for scope in capability.supported_scopes
        for resource in scope.resources
    ):
        raise ProviderCapabilityError("provider scope references undeclared resource")


def _validate_capability_runtime(capability: ProviderCapabilityV1) -> None:
    if capability.rate_limit_per_minute is not None and capability.rate_limit_per_minute <= 0:
        raise ProviderCapabilityError("provider rate limit must be positive")
    if capability.credential_ref is not None and not capability.credential_ref:
        raise ProviderCapabilityError("provider credential reference must not be empty")
