"""Ingestion orchestration boundary."""

from football.ingestion.acquisition import (
    AcquisitionResult,
    SourceAcquirer,
    SourceIntegrityError,
)
from football.ingestion.automatic import (
    ACQUISITION_STAGES_V1,
    AcquisitionStageV1,
    AcquisitionStepV1,
    AutomaticAcquisitionError,
    AutomaticAcquisitionFlowV1,
    AutomaticAcquisitionResultV1,
)
from football.ingestion.canonical import (
    CanonicalIngestionResult,
    StatsBombCanonicalIngestor,
)
from football.ingestion.errors import CanonicalIngestionError, RetryableIngestionError
from football.ingestion.match_resolution import (
    MatchResolutionContextV1,
    MatchResolutionError,
    MatchResolutionResultV1,
    MatchResolutionStatusV1,
    resolve_match_candidates,
)
from football.ingestion.resolution import (
    ResolutionDecisionError,
    ResolutionDecisionV1,
    ResolutionStatusV1,
)

__all__ = [
    "AcquisitionResult",
    "ACQUISITION_STAGES_V1",
    "AcquisitionStageV1",
    "AcquisitionStepV1",
    "AutomaticAcquisitionError",
    "AutomaticAcquisitionFlowV1",
    "AutomaticAcquisitionResultV1",
    "CanonicalIngestionError",
    "CanonicalIngestionResult",
    "RetryableIngestionError",
    "ResolutionDecisionError",
    "ResolutionDecisionV1",
    "ResolutionStatusV1",
    "MatchResolutionContextV1",
    "MatchResolutionError",
    "MatchResolutionResultV1",
    "MatchResolutionStatusV1",
    "resolve_match_candidates",
    "SourceAcquirer",
    "SourceIntegrityError",
    "StatsBombCanonicalIngestor",
]
