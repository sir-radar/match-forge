"""Machine-readable report and manifest contract boundary."""

from football.contracts.competition import CompetitionRulesError, CompetitionRulesV1
from football.contracts.dependencies import (
    DependencyContractError,
    DependencyEdgeV1,
    DependencyGraphV1,
    DependencyStateV1,
    DerivedStateRecordV1,
)
from football.contracts.foundation import (
    FoundationEvidenceStatusV1,
    FoundationHardeningReportV1,
    FoundationReportError,
)
from football.contracts.integrity import (
    IntegrityCheckStatusV1,
    IntegrityContractError,
    IntegrityVerificationReportV1,
)
from football.contracts.source import (
    ManifestResource,
    SourceManifest,
    SourceResource,
    SourceSnapshot,
)

__all__ = [
    "DependencyContractError",
    "DependencyEdgeV1",
    "DependencyGraphV1",
    "DependencyStateV1",
    "DerivedStateRecordV1",
    "CompetitionRulesError",
    "CompetitionRulesV1",
    "FoundationEvidenceStatusV1",
    "FoundationHardeningReportV1",
    "FoundationReportError",
    "IntegrityCheckStatusV1",
    "IntegrityContractError",
    "IntegrityVerificationReportV1",
    "ManifestResource",
    "SourceManifest",
    "SourceResource",
    "SourceSnapshot",
]
