from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from io import BytesIO
from math import isfinite
from ssl import SSLCertVerificationError
from time import monotonic, sleep
from typing import IO, Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from football.contracts.source import SourceResource, SourceSnapshot

_MAX_TRANSPORT_ATTEMPTS = 4
_RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
_RETRYABLE_HTTP_STATUSES = frozenset((408, 429, 500, 502, 503, 504))
_MAX_RETRY_AFTER_SECONDS = 30.0


class ProviderConfigurationError(ValueError):
    """Provider configuration cannot identify a safe immutable source."""


class ProviderFetchError(RuntimeError):
    """A provider resource could not be fetched safely."""


class ProviderIncompleteBodyError(ProviderFetchError):
    """The connection closed before the declared Content-Length arrived."""


class HttpTransport(Protocol):
    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class HttpResponseV1:
    payload: bytes
    status: int
    content_type: str
    etag: str | None
    last_modified: str | None
    cache_control: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)

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
        request_guard: Callable[[], None] | None = None,
        http_error_observer: Callable[[HTTPError], None] | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._accept = accept
        self._request_guard = request_guard
        self._http_error_observer = http_error_observer

    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        return self.get_response(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes).payload

    def get_response(self, url: str, *, timeout_seconds: float, max_bytes: int) -> HttpResponseV1:
        request = Request(
            url,
            headers={"Accept": self._accept, "User-Agent": self._user_agent},
        )
        for attempt in range(1, _MAX_TRANSPORT_ATTEMPTS + 1):
            if self._request_guard is not None:
                self._request_guard()
            failure: HTTPError | URLError | OSError | ProviderIncompleteBodyError
            delay = _RETRY_DELAYS_SECONDS[min(attempt, len(_RETRY_DELAYS_SECONDS)) - 1]
            try:
                with open_bounded(request, timeout=timeout_seconds) as response:
                    payload = read_bounded(
                        response, max_bytes=max_bytes, timeout_seconds=timeout_seconds
                    )
            except HTTPError as error:
                try:
                    if self._http_error_observer is not None:
                        self._http_error_observer(error)
                    requested = retry_after_seconds(
                        error.headers.get("Retry-After") if error.headers is not None else None
                    )
                finally:
                    error.close()
                failure = error
                retryable = error.code in _RETRYABLE_HTTP_STATUSES
                status: int | None = error.code
                if requested is not None:
                    delay = requested
            except (URLError, OSError, ProviderIncompleteBodyError) as error:
                failure = error
                retryable = not isinstance(
                    getattr(error, "reason", error), SSLCertVerificationError
                )
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
                    cache_control=headers.get("Cache-Control"),
                    headers={"content-type": headers.get("Content-Type") or ""},
                )
            if retryable and attempt < _MAX_TRANSPORT_ATTEMPTS:
                sleep(delay)
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


def read_bounded(response: IO[bytes], *, max_bytes: int, timeout_seconds: float) -> bytes:
    """Bound retained bytes and elapsed body reads; retain transport socket timeouts."""
    if max_bytes <= 0 or timeout_seconds <= 0 or not isfinite(timeout_seconds):
        raise ProviderFetchError("positive finite transport limits required")
    declared = _declared_length(getattr(response, "headers", None))
    if declared is not None and declared > max_bytes:
        raise ProviderFetchError(f"provider resource exceeds {max_bytes} bytes")
    deadline = monotonic() + timeout_seconds
    reader = getattr(response, "read1", response.read)
    chunks: list[bytes] = []
    size = 0
    while True:
        if monotonic() >= deadline:
            raise ProviderFetchError("provider response body deadline exceeded")
        chunk = cast(bytes, reader(min(65536, max_bytes - size + 1)))
        if not chunk:
            if declared is not None and size < declared:
                raise ProviderIncompleteBodyError(
                    f"provider response ended after {size} of {declared} declared bytes"
                )
            return b"".join(chunks)
        size += len(chunk)
        if size > max_bytes:
            raise ProviderFetchError(f"provider resource exceeds {max_bytes} bytes")
        chunks.append(chunk)


def _declared_length(headers: Any) -> int | None:
    """Return the body length a non-chunked response promised, if it promised one."""
    if headers is None or headers.get("Transfer-Encoding") is not None:
        return None
    length = headers.get("Content-Length")
    if length is None:
        return None
    if not length.isascii() or not length.isdecimal():
        raise ProviderFetchError("invalid provider Content-Length")
    return int(length)


def retry_after_seconds(value: str | None) -> float | None:
    """Parse a delta-seconds Retry-After header, capped so one response cannot stall a run."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if not isfinite(seconds):
        return None
    return min(max(seconds, 0.0), _MAX_RETRY_AFTER_SECONDS)


class _ClosedRedirectBodyHandler(HTTPRedirectHandler):
    """Retain standard redirect validation/loop limits without draining bodies."""

    def http_error_302(self, req: Any, fp: Any, code: int, msg: str, headers: Any) -> Any:
        fp.close()
        return super().http_error_302(req, BytesIO(), code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        original, destination = urlsplit(req.full_url), urlsplit(newurl)
        if redirected is not None and (original.scheme, original.hostname, original.port) != (
            destination.scheme,
            destination.hostname,
            destination.port,
        ):
            for key in tuple(redirected.headers):
                if key.casefold() in {
                    "authorization",
                    "x-auth-token",
                    "x-apisports-key",
                    "x-api-key",
                    "cookie",
                }:
                    redirected.remove_header(key)
        return redirected


def open_bounded(request: Request, *, timeout: float) -> Any:
    """Use the existing urllib transport with zero retained redirect-body bytes."""
    return build_opener(_ClosedRedirectBodyHandler()).open(request, timeout=timeout)
