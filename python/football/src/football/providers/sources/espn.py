"""Bounded public ESPN scoreboards and single-request match summaries."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime

from football.providers.base import HttpResponseTransport, ProviderFetchError, UrllibHttpTransport
from football.providers.sources.contracts import ProviderPayload, numeric_identifier


class ESPNSource:
    def __init__(
        self,
        *,
        league_slug: str,
        transport: HttpResponseTransport | None = None,
        request_guard: Callable[[], None] | None = None,
    ) -> None:
        if re.fullmatch(r"[a-z][a-z0-9]*\.[a-z0-9]+", league_slug) is None:
            raise ValueError("ESPN league must be a native URL slug")
        self._league = league_slug
        self._transport = transport or UrllibHttpTransport(
            accept="application/json", request_guard=request_guard
        )
        self._guard = request_guard if transport is not None else None

    def fixtures(self, day: date) -> ProviderPayload:
        return self._resource(f"scoreboard?dates={day:%Y%m%d}")

    def summary(self, provider_match_id: str) -> ProviderPayload:
        return self._resource(f"summary?event={numeric_identifier(provider_match_id)}")

    def _resource(self, route: str) -> ProviderPayload:
        key = f"{self._league}/{route}"
        if self._guard is not None:
            self._guard()
        response = self._transport.get_response(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/" + key,
            timeout_seconds=30,
            max_bytes=8 * 1024 * 1024,
        )
        if not 200 <= response.status < 300:
            raise ProviderFetchError(f"ESPN returned HTTP {response.status}")
        return ProviderPayload(
            provider="espn",
            resource_key=key,
            acquired_at=datetime.now(UTC),
            raw=response.payload,
            media_type=response.content_type,
        )
