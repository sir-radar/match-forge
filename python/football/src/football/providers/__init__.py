"""Provider adapter boundary."""

from football.providers.base import (
    FootballDataProvider,
    ProviderConfigurationError,
    ProviderFetchError,
)
from football.providers.statsbomb import StatsBombOpenDataAdapter

__all__ = [
    "FootballDataProvider",
    "ProviderConfigurationError",
    "ProviderFetchError",
    "StatsBombOpenDataAdapter",
]
