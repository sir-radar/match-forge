"""Provider adapter boundary."""

from football.providers.base import (
    FootballDataProvider,
    ProviderConfigurationError,
    ProviderFetchError,
)
from football.providers.capabilities import (
    ProviderCapabilityError,
    ProviderCapabilityRegistryV1,
    ProviderCapabilityV1,
    ProviderResourceCapabilityV1,
    ProviderRoleV1,
    ProviderScopeV1,
)
from football.providers.statsbomb import StatsBombOpenDataAdapter

__all__ = [
    "FootballDataProvider",
    "ProviderConfigurationError",
    "ProviderCapabilityError",
    "ProviderCapabilityRegistryV1",
    "ProviderCapabilityV1",
    "ProviderFetchError",
    "ProviderResourceCapabilityV1",
    "ProviderRoleV1",
    "ProviderScopeV1",
    "StatsBombOpenDataAdapter",
]
