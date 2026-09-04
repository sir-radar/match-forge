from __future__ import annotations

from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from football.contracts.source import SourceResource, SourceSnapshot


class ProviderConfigurationError(ValueError):
    """Provider configuration cannot identify a safe immutable source."""


class ProviderFetchError(RuntimeError):
    """A provider resource could not be fetched safely."""


class HttpTransport(Protocol):
    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes: ...


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
        request = Request(
            url,
            headers={"Accept": self._accept, "User-Agent": self._user_agent},
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = cast(bytes, response.read(max_bytes + 1))
        except (HTTPError, URLError, OSError) as error:
            raise ProviderFetchError(f"provider fetch failed for {url}") from error
        if len(payload) > max_bytes:
            raise ProviderFetchError(f"provider resource exceeds {max_bytes} bytes: {url}")
        return payload


class FootballDataProvider(Protocol):
    @property
    def snapshot(self) -> SourceSnapshot: ...

    def competitions(self) -> SourceResource: ...

    def matches(self, *, competition_id: int, season_id: int) -> SourceResource: ...

    def lineups(self, *, match_id: int) -> SourceResource: ...

    def events(self, *, match_id: int) -> SourceResource: ...

    def fetch(self, resource: SourceResource) -> bytes: ...
