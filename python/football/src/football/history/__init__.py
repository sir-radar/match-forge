"""Canonical, provider-neutral historical fixture identity."""

from football.history.fixture_identity import (
    RESOLUTION_VERSION,
    CanonicalHistoryAudit,
    CanonicalHistoryRow,
    ProviderFixtureEvidence,
    RealFixtureIdentityV1,
    ResolutionStatus,
    ResolvedHistoricalMatchV1,
    audit_canonical_history,
    load_canonical_history,
    load_persisted_resolved_history,
    load_persisted_resolved_metadata,
    persist_resolutions,
)

__all__ = [
    "RESOLUTION_VERSION",
    "CanonicalHistoryAudit",
    "CanonicalHistoryRow",
    "ProviderFixtureEvidence",
    "RealFixtureIdentityV1",
    "ResolutionStatus",
    "ResolvedHistoricalMatchV1",
    "audit_canonical_history",
    "load_canonical_history",
    "load_persisted_resolved_history",
    "load_persisted_resolved_metadata",
    "persist_resolutions",
]
