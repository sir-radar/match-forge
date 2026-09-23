"""Data-quality validation boundary."""

from football.validation.datasets import (
    DatasetValidationError,
    DatasetValidationResult,
    StatsBombDatasetValidator,
)
from football.validation.pitchapi import (
    PitchApiAuditInput,
    PitchApiAuditMetadata,
    PitchApiAuditReport,
    PitchApiQualificationEvidence,
    PitchApiRequestBudget,
    PitchApiRequestRecord,
    PitchApiSeasonAuditInput,
    PitchApiSeasonScope,
    validate_pitchapi_audit,
)
from football.validation.statsbomb import (
    EventFileValidationInput,
    MatchValidationContext,
    PositionStintValidationContext,
    QualityPolicy,
    ValidationFinding,
    make_finding,
    validate_statsbomb_dataset,
)

__all__ = [
    "EventFileValidationInput",
    "DatasetValidationError",
    "DatasetValidationResult",
    "MatchValidationContext",
    "PitchApiAuditInput",
    "PitchApiAuditMetadata",
    "PitchApiAuditReport",
    "PitchApiQualificationEvidence",
    "PitchApiRequestBudget",
    "PitchApiRequestRecord",
    "PitchApiSeasonAuditInput",
    "PitchApiSeasonScope",
    "PositionStintValidationContext",
    "QualityPolicy",
    "StatsBombDatasetValidator",
    "ValidationFinding",
    "make_finding",
    "validate_pitchapi_audit",
    "validate_statsbomb_dataset",
]
