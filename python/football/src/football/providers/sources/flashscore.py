"""Acquire a public league results page, retaining its embedded fixture feeds."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

from football.providers.base import HttpResponseTransport, ProviderFetchError, UrllibHttpTransport
from football.providers.sources.contracts import ProviderPayload


class FlashscoreSource:
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

    def league(self, country_slug: str, competition_slug: str) -> ProviderPayload:
        if any(
            re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", part) is None
            for part in (country_slug, competition_slug)
        ):
            raise ValueError("Flashscore league requires native country/competition URL slugs")
        key = f"football/{country_slug}/{competition_slug}/results"
        if self._guard is not None:
            self._guard()
        response = self._transport.get_response(
            "https://www.flashscore.com/" + key + "/", timeout_seconds=30, max_bytes=8 * 1024 * 1024
        )
        if not 200 <= response.status < 300:
            raise ProviderFetchError(f"Flashscore returned HTTP {response.status}")
        return ProviderPayload(
            provider="flashscore",
            resource_key=key,
            acquired_at=datetime.now(UTC),
            raw=response.payload,
            media_type=response.content_type,
        )
