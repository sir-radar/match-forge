"""Public Understat AJAX resources using its ordinary anonymous session flow."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.request import Request

from football.ingestion.registration import MAX_SOURCE_RESOURCE_BYTES
from football.providers.base import HttpResponseV1, ProviderFetchError, open_bounded, read_bounded
from football.providers.sources.contracts import ProviderPayload, numeric_identifier

Transport = Callable[[str, Mapping[str, str]], HttpResponseV1]
_BASE_URL = "https://understat.com/"


class UnderstatSource:
    def __init__(
        self, *, transport: Transport | None = None, request_guard: Callable[[], None] | None = None
    ) -> None:
        self._transport = transport or _http_get
        self._request_guard = request_guard
        self._cookies = SimpleCookie()
        self._initialized = False

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        if re.fullmatch(r"[A-Za-z_]+", provider_competition_id) is None:
            raise ValueError("Understat league must be a native URL slug")
        year = numeric_identifier(season)
        suffix = f"{provider_competition_id}/{year}"
        return self._resource("getLeagueData/" + suffix, "league/" + suffix)

    def shots(self, provider_match_id: str) -> ProviderPayload:
        match = numeric_identifier(provider_match_id)
        return self._resource(f"getMatchData/{match}", f"match/{match}")

    def _resource(self, path: str, page: str) -> ProviderPayload:
        if not self._initialized:
            self._request(page, ajax=False)
            self._initialized = True
        response = self._request(path, ajax=True)
        return ProviderPayload(
            provider="understat",
            resource_key=path,
            acquired_at=datetime.now(UTC),
            raw=response.payload,
            media_type=response.content_type,
        )

    def _request(self, path: str, *, ajax: bool) -> HttpResponseV1:
        headers = {"Accept": "application/json" if ajax else "text/html"}
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
        if self._cookies:
            headers["Cookie"] = "; ".join(
                f"{key}={value.value}" for key, value in self._cookies.items()
            )
        if self._request_guard is not None:
            self._request_guard()
        response = self._transport(_BASE_URL + path, headers)
        if not 200 <= response.status < 300:
            raise ProviderFetchError(f"Understat returned HTTP {response.status}")
        for key, value in response.headers.items():
            if key.casefold() == "set-cookie":
                self._cookies.load(value)
        return response


def _http_get(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
    request = Request(
        url, headers={**headers, "User-Agent": "football-forecasting/0.1 source-acquisition"}
    )
    try:
        with open_bounded(request, timeout=30) as response:
            payload = read_bounded(
                response, max_bytes=MAX_SOURCE_RESOURCE_BYTES, timeout_seconds=30
            )
            return HttpResponseV1(
                payload,
                response.status,
                response.headers.get_content_type(),
                response.headers.get("ETag"),
                response.headers.get("Last-Modified"),
                headers={"set-cookie": "\n".join(response.headers.get_all("Set-Cookie", []))},
            )
    except HTTPError as error:
        error.close()
        raise ProviderFetchError(f"Understat returned HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise ProviderFetchError("Understat resource request failed") from error
