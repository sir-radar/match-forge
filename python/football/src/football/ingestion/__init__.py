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
    "SourceAcquirer",
    "SourceIntegrityError",
    "StatsBombCanonicalIngestor",
]
