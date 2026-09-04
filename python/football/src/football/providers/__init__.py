"""Provider adapter boundary."""

from football.providers.base import (
    FootballDataProvider,
    HttpResponseTransport,
    HttpResponseV1,
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
from football.providers.football_data_uk_acceptance import (
    FootballDataUkAcceptanceCorpusError,
    FootballDataUkAcceptanceCorpusManifestV1,
    FootballDataUkAcceptanceCorpusStoreV1,
)
from football.providers.football_data_uk_acquisition import (
    FootballDataUkAcquiredResourceV1,
    FootballDataUkAcquirerV1,
    FootballDataUkAcquisitionError,
    FootballDataUkAcquisitionResultV1,
)
from football.providers.football_data_uk_csv import (
    FootballDataUkCoverageEvidenceStoreV1,
    FootballDataUkCoverageReportV1,
    FootballDataUkCsvRecordV1,
    FootballDataUkCsvValidationError,
    FootballDataUkCsvValidationV1,
    FootballDataUkFieldCoverageV1,
    parse_football_data_uk_csv,
)
from football.providers.football_data_uk_evidence import (
    FootballDataUkAcquisitionEvidenceError,
    FootballDataUkAcquisitionEvidenceStoreV1,
    FootballDataUkAcquisitionEvidenceV1,
)
from football.providers.football_data_uk_lifecycle import (
    FootballDataUkLifecycleRegistrationError,
    FootballDataUkPostgresLifecycleRegistryV1,
    LifecycleRegistrationStatusV1,
    RegisteredFootballDataUkLifecycleV1,
)
from football.providers.football_data_uk_match_resolution import (
    FootballDataUkCanonicalMatchCandidateV1,
    FootballDataUkMatchResolutionContextV1,
    FootballDataUkMatchResolutionError,
    FootballDataUkMatchResolutionV1,
    resolve_football_data_uk_match,
)
from football.providers.football_data_uk_overlap import (
    FootballDataUkOverlapPrefixSelectionV1,
    FootballDataUkOverlapSelectionError,
    select_football_data_uk_overlap_prefix,
)
from football.providers.football_data_uk_publication import (
    FootballDataUkPostgresTrustedPublicationV1,
    FootballDataUkTrustedP1MatchV1,
    FootballDataUkTrustedPublicationError,
    RegisteredFootballDataUkTrustedPublicationV1,
    TrustedPublicationStatusV1,
)
from football.providers.football_data_uk_registration import (
    FootballDataUkPostgresSourceRegistryV1,
    FootballDataUkSourceRegistrationError,
)
from football.providers.football_data_uk_resolution import (
    FootballDataUkTeamCrosswalkRegistryV1,
    FootballDataUkTeamCrosswalkV1,
    FootballDataUkTeamResolutionError,
    FootballDataUkTeamResolutionV1,
    resolve_football_data_uk_team,
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
    "HttpResponseTransport",
    "HttpResponseV1",
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
    "FootballDataUkAcceptanceCorpusError",
    "FootballDataUkAcceptanceCorpusManifestV1",
    "FootballDataUkAcceptanceCorpusStoreV1",
    "FootballDataUkRawStoreV1",
    "FootballDataUkTeamCrosswalkRegistryV1",
    "FootballDataUkTeamCrosswalkV1",
    "FootballDataUkTeamResolutionError",
    "FootballDataUkTeamResolutionV1",
    "resolve_football_data_uk_team",
    "FootballDataUkPostgresSourceRegistryV1",
    "FootballDataUkSourceRegistrationError",
    "FootballDataUkLifecycleRegistrationError",
    "FootballDataUkPostgresLifecycleRegistryV1",
    "LifecycleRegistrationStatusV1",
    "RegisteredFootballDataUkLifecycleV1",
    "FootballDataUkOverlapPrefixSelectionV1",
    "FootballDataUkOverlapSelectionError",
    "select_football_data_uk_overlap_prefix",
    "FootballDataUkCanonicalMatchCandidateV1",
    "FootballDataUkMatchResolutionContextV1",
    "FootballDataUkMatchResolutionError",
    "FootballDataUkMatchResolutionV1",
    "FootballDataUkPostgresTrustedPublicationV1",
    "FootballDataUkTrustedP1MatchV1",
    "FootballDataUkTrustedPublicationError",
    "RegisteredFootballDataUkTrustedPublicationV1",
    "TrustedPublicationStatusV1",
    "resolve_football_data_uk_match",
    "FootballDataUkAcquiredResourceV1",
    "FootballDataUkAcquirerV1",
    "FootballDataUkAcquisitionError",
    "FootballDataUkAcquisitionResultV1",
    "FootballDataUkCoverageReportV1",
    "FootballDataUkCoverageEvidenceStoreV1",
    "FootballDataUkCsvRecordV1",
    "FootballDataUkCsvValidationError",
    "FootballDataUkCsvValidationV1",
    "FootballDataUkFieldCoverageV1",
    "parse_football_data_uk_csv",
    "FootballDataUkAcquisitionEvidenceError",
    "FootballDataUkAcquisitionEvidenceStoreV1",
    "FootballDataUkAcquisitionEvidenceV1",
    "CursorStrategyV1",
    "JitterModeV1",
    "CircuitStateV1",
    "FreshnessStatusV1",
    "ProviderObservabilityError",
    "ProviderObservabilitySnapshotV1",
]
