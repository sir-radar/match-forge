"""Ingestion orchestration boundary."""

from football.ingestion.acquisition import (
    AcquisitionResult,
    SourceAcquirer,
    SourceIntegrityError,
)

__all__ = ["AcquisitionResult", "SourceAcquirer", "SourceIntegrityError"]
