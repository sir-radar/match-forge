from __future__ import annotations

import re
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from football.contracts.source import SourceContractError, SourceResource, SourceSnapshot
from football.providers.base import (
    HttpTransport,
    ProviderConfigurationError,
    ProviderFetchError,
)
from football.providers.capabilities import (
    ProviderCapabilityV1,
    ProviderResourceCapabilityV1,
    ProviderScopeV1,
)

_RESOURCE_PATTERN = re.compile(
    r"^data/(competitions\.json|matches/[1-9][0-9]*/[1-9][0-9]*\.json|"
    r"lineups/[1-9][0-9]*\.json|events/[1-9][0-9]*\.json|"
    r"three-sixty/[1-9][0-9]*\.json)$"
)


class UrllibHttpTransport:
    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "football-forecasting/0.1 source-acquisition",
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = cast(bytes, response.read(max_bytes + 1))
        except (HTTPError, URLError, OSError) as error:
            raise ProviderFetchError(f"provider fetch failed for {url}") from error
        if len(payload) > max_bytes:
            raise ProviderFetchError(f"provider resource exceeds {max_bytes} bytes: {url}")
        return payload


class StatsBombOpenDataAdapter:
    provider_code = "statsbomb_open_data"
    repository = "https://github.com/statsbomb/open-data"
    timeout_seconds = 60.0
    max_resource_bytes = 128 * 1024 * 1024
    capability = ProviderCapabilityV1(
        provider_id=provider_code,
        enabled=True,
        terms_status="open_data_non_commercial_research",
        supported_scopes=(
            ProviderScopeV1("2", "27", ("fixtures_results", "lineups", "events")),
            ProviderScopeV1("43", "106", ("fixtures_results", "lineups", "events", "360")),
        ),
        resources=(
            ProviderResourceCapabilityV1("fixtures_results"),
            ProviderResourceCapabilityV1("lineups"),
            ProviderResourceCapabilityV1("events"),
            ProviderResourceCapabilityV1("360"),
        ),
        update_semantics="commit_pinned_snapshot",
        incremental_cursor_support=False,
        webhook_support=False,
        rate_limit_per_minute=None,
        credential_ref=None,
        adapter_version="statsbomb-open-data-v1",
    )

    def __init__(
        self,
        *,
        source_git_sha: str,
        transport: HttpTransport | None = None,
    ) -> None:
        license_url = f"{self.repository}/blob/{source_git_sha}/LICENSE.pdf"
        try:
            self._snapshot = SourceSnapshot(
                provider=self.provider_code,
                repository=self.repository,
                source_git_sha=source_git_sha,
                license="StatsBomb Open Data license",
                license_url=license_url,
                attribution="Data provided by StatsBomb",
            )
        except SourceContractError as error:
            raise ProviderConfigurationError(str(error)) from error
        self._transport = transport or UrllibHttpTransport()

    @property
    def snapshot(self) -> SourceSnapshot:
        return self._snapshot

    def competitions(self) -> SourceResource:
        return SourceResource("data/competitions.json")

    def matches(self, *, competition_id: int, season_id: int) -> SourceResource:
        competition = _positive_identifier(competition_id, "competition_id")
        season = _positive_identifier(season_id, "season_id")
        return SourceResource(f"data/matches/{competition}/{season}.json")

    def lineups(self, *, match_id: int) -> SourceResource:
        match = _positive_identifier(match_id, "match_id")
        return SourceResource(f"data/lineups/{match}.json")

    def events(self, *, match_id: int) -> SourceResource:
        match = _positive_identifier(match_id, "match_id")
        return SourceResource(f"data/events/{match}.json")

    def three_sixty(self, *, match_id: int) -> SourceResource:
        match = _positive_identifier(match_id, "match_id")
        return SourceResource(f"data/three-sixty/{match}.json")

    def fetch(self, resource: SourceResource) -> bytes:
        if resource.media_type != "application/json" or not _RESOURCE_PATTERN.fullmatch(
            resource.path
        ):
            raise ProviderConfigurationError(
                f"unsupported StatsBomb Open Data resource path: {resource.path}"
            )
        url = (
            "https://raw.githubusercontent.com/statsbomb/open-data/"
            f"{self.snapshot.source_git_sha}/{resource.path}"
        )
        return self._transport.get(
            url,
            timeout_seconds=self.timeout_seconds,
            max_bytes=self.max_resource_bytes,
        )


def _positive_identifier(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value
