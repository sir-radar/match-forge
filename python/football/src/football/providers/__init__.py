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
from football.providers.credentials import (
    CredentialTypeV1,
    ProviderConfigV1,
    ProviderCredentialError,
    ProviderCredentialRefV1,
)
from football.providers.runtime_policy import (
    JitterModeV1,
    ProviderRuntimePolicyError,
    ProviderRuntimePolicyV1,
)
from football.providers.schema_contract import (
    ProviderResourceContractV1,
    ProviderSchemaContractError,
    SchemaCompatibilityResultV1,
)
from football.providers.statsbomb import StatsBombOpenDataAdapter
from football.providers.sync_policy import (
    CursorStrategyV1,
    ProviderSyncPolicyError,
    ProviderSyncPolicyV1,
)

__all__ = [
    "FootballDataProvider",
    "ProviderConfigurationError",
    "ProviderCapabilityError",
    "ProviderCapabilityRegistryV1",
    "ProviderCapabilityV1",
    "ProviderConfigV1",
    "ProviderCredentialError",
    "ProviderCredentialRefV1",
    "ProviderFetchError",
    "ProviderResourceCapabilityV1",
    "ProviderRoleV1",
    "ProviderScopeV1",
    "CredentialTypeV1",
    "ProviderSyncPolicyError",
    "ProviderSyncPolicyV1",
    "ProviderRuntimePolicyError",
    "ProviderRuntimePolicyV1",
    "ProviderResourceContractV1",
    "ProviderSchemaContractError",
    "SchemaCompatibilityResultV1",
    "StatsBombOpenDataAdapter",
    "CursorStrategyV1",
    "JitterModeV1",
]
