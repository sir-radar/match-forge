from __future__ import annotations

from datetime import date

import pytest
from football.providers import (
    ProviderCapabilityError,
    ProviderCapabilityRegistryV1,
    ProviderCapabilityV1,
    ProviderResourceCapabilityV1,
    ProviderScopeV1,
    StatsBombOpenDataAdapter,
)


def test_statsbomb_declares_versioned_capability_contract_without_credentials() -> None:
    capability = StatsBombOpenDataAdapter.capability

    assert capability.provider_id == "statsbomb_open_data"
    assert capability.enabled
    assert capability.credential_ref is None
    assert capability.to_dict()["contract"] == "ProviderCapabilityV1"
    assert len(capability.sha256) == 64
    assert {scope.competition_id for scope in capability.supported_scopes} == {"2", "43"}


def test_capability_registry_is_deterministic_and_filters_enabled_providers() -> None:
    disabled = _capability(provider_id="disabled_provider", enabled=False)
    enabled = _capability(provider_id="enabled_provider", enabled=True)
    registry = ProviderCapabilityRegistryV1((disabled, enabled))

    assert registry.get("enabled_provider") == enabled
    assert registry.all() == (disabled, enabled)
    assert registry.enabled() == (enabled,)
    with pytest.raises(ProviderCapabilityError, match="not registered"):
        registry.get("missing_provider")


def test_capability_contract_rejects_duplicate_resources_scopes_and_invalid_ranges() -> None:
    with pytest.raises(ProviderCapabilityError, match="resources must be unique"):
        ProviderScopeV1("competition", "season", ("events", "events"))
    with pytest.raises(ProviderCapabilityError, match="historical range"):
        ProviderResourceCapabilityV1(
            "events", historical_start=date(2026, 1, 1), historical_end=date(2025, 1, 1)
        )
    with pytest.raises(ProviderCapabilityError, match="provider resources must be unique"):
        _capability_with_duplicate_resources()
    with pytest.raises(ProviderCapabilityError, match="undeclared resource"):
        ProviderCapabilityV1(
            provider_id="provider",
            enabled=True,
            terms_status="research",
            supported_scopes=(ProviderScopeV1("competition", "season", ("lineups",)),),
            resources=(_resource(),),
            update_semantics="snapshot",
            incremental_cursor_support=False,
            webhook_support=False,
            rate_limit_per_minute=None,
            credential_ref=None,
            adapter_version="provider-v1",
        )


def test_registry_rejects_duplicate_provider_ids() -> None:
    capability = _capability()

    with pytest.raises(ProviderCapabilityError, match="provider_ids must be unique"):
        ProviderCapabilityRegistryV1((capability, capability))


def _scope() -> ProviderScopeV1:
    return ProviderScopeV1("competition", "season", ("events",))


def _resource() -> ProviderResourceCapabilityV1:
    return ProviderResourceCapabilityV1("events")


def _capability(*, provider_id: str = "provider", enabled: bool = True) -> ProviderCapabilityV1:
    return ProviderCapabilityV1(
        provider_id=provider_id,
        enabled=enabled,
        terms_status="research",
        supported_scopes=(_scope(),),
        resources=(_resource(),),
        update_semantics="snapshot",
        incremental_cursor_support=False,
        webhook_support=False,
        rate_limit_per_minute=None,
        credential_ref=None,
        adapter_version="provider-v1",
    )


def _capability_with_duplicate_resources() -> ProviderCapabilityV1:
    return ProviderCapabilityV1(
        provider_id="provider",
        enabled=True,
        terms_status="research",
        supported_scopes=(_scope(),),
        resources=(_resource(), _resource()),
        update_semantics="snapshot",
        incremental_cursor_support=False,
        webhook_support=False,
        rate_limit_per_minute=None,
        credential_ref=None,
        adapter_version="provider-v1",
    )
