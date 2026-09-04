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
from football.ingestion.change_sets import CanonicalChangeSetV1, ChangeSetError
from football.ingestion.conflict_storage import (
    PostgresReconciliationConflictStoreV1,
    ReconciliationConflictRegistrationStatusV1,
    ReconciliationConflictStorageError,
    RegisteredReconciliationConflictV1,
)
from football.ingestion.conflicts import (
    ConflictDispositionV1,
    ConflictRecordError,
    ConflictRecordV1,
    FieldObservationV1,
    FieldReconciliationStatusV1,
    FieldReconciliationV1,
    reconcile_field_observations,
)
from football.ingestion.corrections import BitemporalCorrectionV1, CorrectionRecordError
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
from football.ingestion.partial_failure import (
    AggregateProcessingStatusV1,
    PartialFailureError,
    PartialFailureReportV1,
    ResourceProcessingResultV1,
    ResourceProcessingStatusV1,
)
from football.ingestion.quarantine import (
    QuarantineReasonV1,
    QuarantineRecordError,
    QuarantineRecordV1,
    QuarantineStatusV1,
)
from football.ingestion.quarantine_reprocess import (
    QuarantineReprocessError,
    QuarantineReprocessRequestV1,
    ReprocessTriggerV1,
)
from football.ingestion.resolution import (
    ResolutionDecisionError,
    ResolutionDecisionV1,
    ResolutionStatusV1,
)
from football.ingestion.resolution_policy import (
    DataResolutionPolicyV1,
    EscalationActionV1,
    ResolutionPolicyError,
)
from football.ingestion.resolution_storage import (
    PostgresResolutionDecisionStoreV1,
    RegisteredResolutionDecisionV1,
    ResolutionDecisionRegistrationStatusV1,
    ResolutionDecisionStorageError,
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
    "BitemporalCorrectionV1",
    "CorrectionRecordError",
    "CanonicalChangeSetV1",
    "ChangeSetError",
    "PostgresReconciliationConflictStoreV1",
    "ReconciliationConflictRegistrationStatusV1",
    "ReconciliationConflictStorageError",
    "RegisteredReconciliationConflictV1",
    "EventStreamReconciliationError",
    "EventStreamReconciliationV1",
    "ProviderEventStreamV1",
    "AggregateProcessingStatusV1",
    "PartialFailureError",
    "PartialFailureReportV1",
    "ResourceProcessingResultV1",
    "ResourceProcessingStatusV1",
    "QuarantineReasonV1",
    "QuarantineRecordError",
    "QuarantineRecordV1",
    "QuarantineStatusV1",
    "QuarantineReprocessError",
    "QuarantineReprocessRequestV1",
    "ReprocessTriggerV1",
    "ConflictRecordError",
    "ConflictRecordV1",
    "ConflictDispositionV1",
    "FieldObservationV1",
    "FieldReconciliationStatusV1",
    "FieldReconciliationV1",
    "reconcile_field_observations",
    "RetryableIngestionError",
    "ResolutionDecisionError",
    "ResolutionDecisionV1",
    "ResolutionStatusV1",
    "PostgresResolutionDecisionStoreV1",
    "RegisteredResolutionDecisionV1",
    "ResolutionDecisionRegistrationStatusV1",
    "ResolutionDecisionStorageError",
    "DataResolutionPolicyV1",
    "EscalationActionV1",
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
