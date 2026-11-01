"""Public league HTML only; detailed match access has a separate recorded blocker."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

from football.providers.base import HttpResponseTransport, ProviderFetchError, UrllibHttpTransport
from football.providers.sources.contracts import ProviderPayload, numeric_identifier


class WhoScoredSource:
    def __init__(
        self,
        *,
        transport: HttpResponseTransport | None = None,
        request_guard: Callable[[], None] | None = None,
    ) -> None:
        self._transport = transport or UrllibHttpTransport(
            accept="text/html", request_guard=request_guard
        )
        self._guard = request_guard if transport is not None else None

    def league(self, provider_region_id: str, provider_competition_id: str) -> ProviderPayload:
        region, tournament = (
            numeric_identifier(provider_region_id),
            numeric_identifier(provider_competition_id),
        )
        return self._resource(f"Regions/{region}/Tournaments/{tournament}")

    def season(
        self,
        provider_region_id: str,
        provider_competition_id: str,
        provider_season_id: str,
        competition_slug: str,
        *,
        provider_stage_id: str | None = None,
    ) -> ProviderPayload:
        """Fetch a season route discovered in the provider's league selector."""
        region, tournament, season = (
            numeric_identifier(value)
            for value in (provider_region_id, provider_competition_id, provider_season_id)
        )
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", competition_slug) is None:
            raise ValueError("WhoScored season requires its native competition slug")
        key = f"Regions/{region}/Tournaments/{tournament}/Seasons/{season}"
        if provider_stage_id is not None:
            key = f"{key}/stages/{numeric_identifier(provider_stage_id)}/fixtures".lower()
        return self._resource(f"{key}/{competition_slug}")

    def _resource(self, key: str) -> ProviderPayload:
        if self._guard is not None:
            self._guard()
        response = self._transport.get_response(
            "https://www.whoscored.com/" + key, timeout_seconds=30, max_bytes=8 * 1024 * 1024
        )
        if not 200 <= response.status < 300:
            raise ProviderFetchError(f"WhoScored returned HTTP {response.status}")
        return ProviderPayload(
            provider="whoscored",
            resource_key=key,
            acquired_at=datetime.now(UTC),
            raw=response.payload,
            media_type=response.content_type,
        )
