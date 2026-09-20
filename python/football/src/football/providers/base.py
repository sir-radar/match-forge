from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from football.contracts.source import SourceResource, SourceSnapshot

_MAX_TRANSPORT_ATTEMPTS = 4
_RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
_RETRYABLE_HTTP_STATUSES = frozenset((408, 429, 500, 502, 503, 504))


class ProviderConfigurationError(ValueError):
    """Provider configuration cannot identify a safe immutable source."""


class ProviderFetchError(RuntimeError):
    """A provider resource could not be fetched safely."""


class HttpTransport(Protocol):
    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class HttpResponseV1:
    payload: bytes
    status: int
    content_type: str
    etag: str | None
    last_modified: str | None

    def __post_init__(self) -> None:
        if not 100 <= self.status <= 599 or not self.content_type:
            raise ProviderFetchError("HTTP response status and content type are required")


class HttpResponseTransport(HttpTransport, Protocol):
    def get_response(
        self, url: str, *, timeout_seconds: float, max_bytes: int
    ) -> HttpResponseV1: ...


class UrllibHttpTransport:
    """Bounded unauthenticated HTTPS transport for public provider resources."""

    def __init__(
        self,
        user_agent: str = "football-forecasting/0.1 source-acquisition",
        accept: str = "*/*",
    ) -> None:
        self._user_agent = user_agent
        self._accept = accept

    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        return self.get_response(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes).payload

    def get_response(self, url: str, *, timeout_seconds: float, max_bytes: int) -> HttpResponseV1:
        request = Request(
            url,
            headers={"Accept": self._accept, "User-Agent": self._user_agent},
        )
        for attempt in range(1, _MAX_TRANSPORT_ATTEMPTS + 1):
            failure: HTTPError | URLError | OSError
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    payload = cast(bytes, response.read(max_bytes + 1))
            except HTTPError as error:
                failure = error
                retryable = error.code in _RETRYABLE_HTTP_STATUSES
                status: int | None = error.code
            except (URLError, OSError) as error:
                failure = error
                retryable = True
                status = None
            else:
                if len(payload) > max_bytes:
                    raise ProviderFetchError(f"provider resource exceeds {max_bytes} bytes: {url}")
                headers = response.headers
                return HttpResponseV1(
                    payload=payload,
                    status=getattr(response, "status", 200),
                    content_type=headers.get_content_type(),
                    etag=headers.get("ETag"),
                    last_modified=headers.get("Last-Modified"),
                )
            if retryable and attempt < _MAX_TRANSPORT_ATTEMPTS:
                sleep(_RETRY_DELAYS_SECONDS[attempt - 1])
                continue
            status_text = str(status) if status is not None else "none"
            raise ProviderFetchError(
                f"provider fetch failed for {url}: attempt {attempt}/{_MAX_TRANSPORT_ATTEMPTS}; "
                f"exception={type(failure).__name__}; http_status={status_text}; {failure}"
            ) from failure
        raise AssertionError("bounded transport retry loop exited unexpectedly")


class FootballDataProvider(Protocol):
    @property
    def snapshot(self) -> SourceSnapshot: ...

    def competitions(self) -> SourceResource: ...

    def matches(self, *, competition_id: int, season_id: int) -> SourceResource: ...

    def lineups(self, *, match_id: int) -> SourceResource: ...

    def events(self, *, match_id: int) -> SourceResource: ...

    def fetch(self, resource: SourceResource) -> bytes: ...
