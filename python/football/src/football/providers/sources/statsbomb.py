"""Narrow resources from the existing commit-pinned StatsBomb adapter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from football.contracts.source import SourceResource
from football.providers.sources.contracts import ProviderPayload, numeric_identifier
from football.providers.statsbomb import StatsBombOpenDataAdapter


class StatsBombSource:
    def __init__(
        self,
        adapter: StatsBombOpenDataAdapter,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.adapter = adapter
        self.clock = clock or (lambda: datetime.now(UTC))

    def competitions(self) -> ProviderPayload:
        return self._fetch(self.adapter.competitions())

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        return self._fetch(
            self.adapter.matches(
                competition_id=numeric_identifier(provider_competition_id),
                season_id=numeric_identifier(season),
            )
        )

    def lineups(self, provider_match_id: str) -> ProviderPayload:
        return self._fetch(self.adapter.lineups(match_id=numeric_identifier(provider_match_id)))

    def events(self, provider_match_id: str) -> ProviderPayload:
        return self._fetch(self.adapter.events(match_id=numeric_identifier(provider_match_id)))

    def _fetch(self, resource: SourceResource) -> ProviderPayload:
        raw = self.adapter.fetch(resource)
        return ProviderPayload(
            provider="statsbomb_open_data",
            resource_key=resource.path,
            acquired_at=self.clock(),
            raw=raw,
            media_type=resource.media_type,
            source_revision=self.adapter.snapshot.source_git_sha,
        )
