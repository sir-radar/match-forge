"""Public league HTML only; detailed match access has a separate recorded blocker."""

from __future__ import annotations

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
        key = f"Regions/{region}/Tournaments/{tournament}"
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
