"""Data-quality validation boundary."""

from football.validation.datasets import (
    DatasetValidationError,
    DatasetValidationResult,
    StatsBombDatasetValidator,
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
    "PositionStintValidationContext",
    "QualityPolicy",
    "StatsBombDatasetValidator",
    "ValidationFinding",
    "make_finding",
    "validate_statsbomb_dataset",
]
