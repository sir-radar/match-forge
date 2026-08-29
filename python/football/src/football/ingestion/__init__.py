"""Ingestion orchestration boundary."""

from football.ingestion.acquisition import (
    AcquisitionResult,
    SourceAcquirer,
    SourceIntegrityError,
)
from football.ingestion.canonical import (
    CanonicalIngestionResult,
    StatsBombCanonicalIngestor,
)
from football.ingestion.errors import CanonicalIngestionError, RetryableIngestionError

__all__ = [
    "AcquisitionResult",
    "CanonicalIngestionError",
    "CanonicalIngestionResult",
    "RetryableIngestionError",
    "SourceAcquirer",
    "SourceIntegrityError",
    "StatsBombCanonicalIngestor",
]
