from __future__ import annotations

from dataclasses import dataclass, field
from urllib.error import URLError

import pytest
from football.contracts.source import SourceResource
from football.providers import (
    ProviderConfigurationError,
    ProviderFetchError,
    StatsBombOpenDataAdapter,
    UrllibHttpTransport,
)


@dataclass
class RecordingTransport:
    payload: bytes = b"[]\n"
    urls: list[str] = field(default_factory=list)

    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        self.urls.append(url)
        assert timeout_seconds == 60
        assert max_bytes == 128 * 1024 * 1024
        return self.payload


def test_statsbomb_adapter_builds_pinned_resource_urls() -> None:
    transport = RecordingTransport()
    adapter = StatsBombOpenDataAdapter(
        source_git_sha="b0bc9f22dd77c206ddedc1d742893b3bbe64baec",
        transport=transport,
    )

    resources = (
        adapter.competitions(),
        adapter.matches(competition_id=43, season_id=106),
        adapter.lineups(match_id=3869685),
        adapter.events(match_id=3869685),
        adapter.three_sixty(match_id=3869685),
    )

    assert [resource.path for resource in resources] == [
        "data/competitions.json",
        "data/matches/43/106.json",
        "data/lineups/3869685.json",
        "data/events/3869685.json",
        "data/three-sixty/3869685.json",
    ]
    assert adapter.fetch(resources[1]) == b"[]\n"
    assert transport.urls == [
        "https://raw.githubusercontent.com/statsbomb/open-data/"
        "b0bc9f22dd77c206ddedc1d742893b3bbe64baec/data/matches/43/106.json"
    ]


@pytest.mark.parametrize("source_git_sha", ["main", "A" * 40, "a" * 39, "a" * 41])
def test_statsbomb_adapter_requires_full_lowercase_git_sha(source_git_sha: str) -> None:
    with pytest.raises(ProviderConfigurationError, match="40-character lowercase Git SHA"):
        StatsBombOpenDataAdapter(source_git_sha=source_git_sha)


@pytest.mark.parametrize("identifier", [True, 0, -1])
def test_statsbomb_adapter_rejects_invalid_provider_identifiers(identifier: int) -> None:
    adapter = StatsBombOpenDataAdapter(source_git_sha="b0bc9f22dd77c206ddedc1d742893b3bbe64baec")

    with pytest.raises(ValueError, match="positive integer"):
        adapter.events(match_id=identifier)


def test_default_transport_enforces_resource_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            assert size == 5
            return b"12345"

    monkeypatch.setattr("football.providers.base.urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(ProviderFetchError, match="exceeds 4 bytes"):
        UrllibHttpTransport().get("https://example.test/data.json", timeout_seconds=1, max_bytes=4)


def test_default_transport_wraps_network_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise URLError("offline")

    monkeypatch.setattr("football.providers.base.urlopen", unavailable)

    with pytest.raises(ProviderFetchError, match="provider fetch failed"):
        UrllibHttpTransport().get("https://example.test/data.json", timeout_seconds=1, max_bytes=4)


def test_statsbomb_adapter_rejects_resources_outside_its_json_contract() -> None:
    adapter = StatsBombOpenDataAdapter(source_git_sha="b0bc9f22dd77c206ddedc1d742893b3bbe64baec")

    with pytest.raises(ProviderConfigurationError, match="unsupported StatsBomb"):
        adapter.fetch(SourceResource("data/competitions.json", "text/plain"))
