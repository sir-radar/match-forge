"""Provider-to-canonical normalization boundary."""

from football.normalization.football_data_uk import (
    FootballDataUkNormalizationError,
    FootballDataUkNormalizedMatchV1,
    normalize_football_data_uk_record,
)

__all__ = [
    "FootballDataUkNormalizationError",
    "FootballDataUkNormalizedMatchV1",
    "normalize_football_data_uk_record",
]
