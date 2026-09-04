"""Provider adapter boundary."""

from football.providers.base import (
    FootballDataProvider,
    ProviderConfigurationError,
    ProviderFetchError,
    UrllibHttpTransport,
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
from football.providers.football_data_uk import (
    FootballDataUkAdapter,
    FootballDataUkHistoricalLeagueCsvV1,
    FootballDataUkSourceResourceError,
    FootballDataUkSourceResourceV1,
)
from football.providers.football_data_uk_csv import (
    FootballDataUkCoverageReportV1,
    FootballDataUkCsvRecordV1,
    FootballDataUkCsvValidationError,
    FootballDataUkCsvValidationV1,
    FootballDataUkFieldCoverageV1,
    parse_football_data_uk_csv,
)
from football.providers.football_data_uk_storage import FootballDataUkRawStoreV1
from football.providers.observability import (
    CircuitStateV1,
    FreshnessStatusV1,
    ProviderObservabilityError,
    ProviderObservabilitySnapshotV1,
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
from football.providers.worker import ProviderSyncWorkerError, ProviderSyncWorkerV1

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
    "UrllibHttpTransport",
    "ProviderResourceCapabilityV1",
    "ProviderRoleV1",
    "ProviderScopeV1",
    "CredentialTypeV1",
    "ProviderSyncPolicyError",
    "ProviderSyncPolicyV1",
    "ProviderSyncWorkerError",
    "ProviderSyncWorkerV1",
    "ProviderRuntimePolicyError",
    "ProviderRuntimePolicyV1",
    "ProviderResourceContractV1",
    "ProviderSchemaContractError",
    "SchemaCompatibilityResultV1",
    "StatsBombOpenDataAdapter",
    "FootballDataUkAdapter",
    "FootballDataUkHistoricalLeagueCsvV1",
    "FootballDataUkSourceResourceError",
    "FootballDataUkSourceResourceV1",
    "FootballDataUkRawStoreV1",
    "FootballDataUkCoverageReportV1",
    "FootballDataUkCsvRecordV1",
    "FootballDataUkCsvValidationError",
    "FootballDataUkCsvValidationV1",
    "FootballDataUkFieldCoverageV1",
    "parse_football_data_uk_csv",
    "CursorStrategyV1",
    "JitterModeV1",
    "CircuitStateV1",
    "FreshnessStatusV1",
    "ProviderObservabilityError",
    "ProviderObservabilitySnapshotV1",
]
