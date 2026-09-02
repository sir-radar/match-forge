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
from football.ingestion.conflicts import (
    ConflictDispositionV1,
    ConflictRecordError,
    ConflictRecordV1,
)
from football.ingestion.errors import CanonicalIngestionError, RetryableIngestionError
from football.ingestion.event_streams import (
    EventStreamReconciliationError,
    EventStreamReconciliationV1,
    ProviderEventStreamV1,
)
from football.ingestion.match_resolution import (
    MatchResolutionContextV1,
    MatchResolutionError,
    MatchResolutionResultV1,
    MatchResolutionStatusV1,
    resolve_match_candidates,
)
from football.ingestion.quarantine import (
    QuarantineReasonV1,
    QuarantineRecordError,
    QuarantineRecordV1,
    QuarantineStatusV1,
)
from football.ingestion.resolution import (
    ResolutionDecisionError,
    ResolutionDecisionV1,
    ResolutionStatusV1,
)
from football.ingestion.resolution_policy import DataResolutionPolicyV1, ResolutionPolicyError

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
    "EventStreamReconciliationError",
    "EventStreamReconciliationV1",
    "ProviderEventStreamV1",
    "QuarantineReasonV1",
    "QuarantineRecordError",
    "QuarantineRecordV1",
    "QuarantineStatusV1",
    "ConflictRecordError",
    "ConflictRecordV1",
    "ConflictDispositionV1",
    "RetryableIngestionError",
    "ResolutionDecisionError",
    "ResolutionDecisionV1",
    "ResolutionStatusV1",
    "DataResolutionPolicyV1",
    "ResolutionPolicyError",
    "MatchResolutionContextV1",
    "MatchResolutionError",
    "MatchResolutionResultV1",
    "MatchResolutionStatusV1",
    "resolve_match_candidates",
    "SourceAcquirer",
    "SourceIntegrityError",
    "StatsBombCanonicalIngestor",
]
