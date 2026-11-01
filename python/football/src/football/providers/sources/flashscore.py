"""Bounded public league/match pages and source-verified statistics requests."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request

from football.providers.base import (
    HttpResponseTransport,
    HttpResponseV1,
    ProviderFetchError,
    UrllibHttpTransport,
    open_bounded,
    read_bounded,
)
from football.providers.native.flashscore import FlashscoreMatchPage, environment_bytes
from football.providers.native.reader import native_json, native_record
from football.providers.sources.contracts import ProviderPayload

FeedTransport = Callable[[str, Mapping[str, str]], HttpResponseV1]


class FlashscoreSource:
    def __init__(
        self,
        *,
        transport: HttpResponseTransport | None = None,
        request_guard: Callable[[], None] | None = None,
        feed_transport: FeedTransport | None = None,
    ) -> None:
        self._transport = transport or UrllibHttpTransport(
            accept="text/html", request_guard=request_guard
        )
        self._guard = request_guard if transport is not None else None
        self._request_guard = request_guard
        self._feed_transport = feed_transport or _feed_get

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
        return _payload(key, response)

    def match(self, provider_match_id: str) -> ProviderPayload:
        if re.fullmatch(r"[A-Za-z0-9]+", provider_match_id) is None:
            raise ValueError("Flashscore match requires its native ID")
        key = "match/" + provider_match_id
        if self._guard is not None:
            self._guard()
        response = self._transport.get_response(
            "https://www.flashscore.com/" + key + "/", timeout_seconds=30, max_bytes=8 * 1024 * 1024
        )
        return _payload(key, response)

    def statistics(self, match_page: ProviderPayload) -> ProviderPayload:
        scope = re.fullmatch(r"match/([A-Za-z0-9]+)", match_page.resource_key)
        if match_page.provider != "flashscore" or scope is None:
            raise ValueError("Flashscore statistics requires its retained native match page")
        page = native_record(FlashscoreMatchPage, native_json(environment_bytes(match_page.raw)))
        app = page["config"]["app"]
        if (page["event_id_c"], page["sport_id"], app["project_type"]["id"]) != (scope[1], 1, 1):
            raise ValueError("Flashscore match/page or football scope conflicts")
        if (
            app["feed_resolver"]["default_url"] != "https://global.flashscore.ninja"
            or app["project"]["id"] <= 0
        ):
            raise ValueError("Flashscore page has an unverified feed origin/project")
        signature = app["feed_sign"]
        if not signature or any(c in signature for c in "\r\n"):
            raise ValueError("Flashscore page has an invalid public feed header")
        key = "df_st_1_" + scope[1]
        if self._request_guard is not None:
            self._request_guard()
        response = self._feed_transport(
            f"https://global.flashscore.ninja/{app['project']['id']}/x/feed/{key}",
            {"x-fsign": signature, "Accept": "text/plain"},
        )
        return _payload(key, response)


def _payload(key: str, response: HttpResponseV1) -> ProviderPayload:
    if not 200 <= response.status < 300:
        raise ProviderFetchError(f"Flashscore returned HTTP {response.status}")
    return ProviderPayload(
        provider="flashscore",
        resource_key=key,
        acquired_at=datetime.now(UTC),
        raw=response.payload,
        media_type=response.content_type,
    )


def _feed_get(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
    request = Request(
        url, headers={**headers, "User-Agent": "football-forecasting/0.1 source-acquisition"}
    )
    try:
        with open_bounded(request, timeout=30) as response:
            raw = read_bounded(response, max_bytes=8 * 1024 * 1024, timeout_seconds=30)
            return HttpResponseV1(
                raw,
                response.status,
                response.headers.get_content_type(),
                response.headers.get("ETag"),
                response.headers.get("Last-Modified"),
            )
    except HTTPError as error:
        error.close()
        raise ProviderFetchError(f"Flashscore returned HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise ProviderFetchError("Flashscore feed request failed") from error
