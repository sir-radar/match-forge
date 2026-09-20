from __future__ import annotations

from dataclasses import dataclass, field
from email.message import Message
from urllib.error import HTTPError, URLError

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
    monkeypatch.setattr("football.providers.base.sleep", lambda _delay: None)

    with pytest.raises(ProviderFetchError, match="provider fetch failed"):
        UrllibHttpTransport().get("https://example.test/data.json", timeout_seconds=1, max_bytes=4)


def test_default_transport_retries_a_transient_network_failure_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response(b"[]")
    attempts: list[str] = []
    delays: list[float] = []

    def fetch(request: object, **_kwargs: object) -> _Response:
        attempts.append(str(request.full_url))  # type: ignore[attr-defined]
        if len(attempts) == 1:
            raise URLError("connection reset")
        return response

    monkeypatch.setattr("football.providers.base.urlopen", fetch)
    monkeypatch.setattr("football.providers.base.sleep", delays.append)

    payload = UrllibHttpTransport().get(
        "https://example.test/data.json", timeout_seconds=1, max_bytes=4
    )

    assert payload == b"[]"
    assert attempts == ["https://example.test/data.json"] * 2
    assert delays == [1.0]


def test_default_transport_fails_closed_after_bounded_transient_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []
    delays: list[float] = []

    def unavailable(request: object, **_kwargs: object) -> None:
        attempts.append(str(request.full_url))  # type: ignore[attr-defined]
        raise URLError("offline")

    monkeypatch.setattr("football.providers.base.urlopen", unavailable)
    monkeypatch.setattr("football.providers.base.sleep", delays.append)

    with pytest.raises(
        ProviderFetchError,
        match=r"attempt 4/4; exception=URLError; http_status=none",
    ):
        UrllibHttpTransport().get("https://example.test/data.json", timeout_seconds=1, max_bytes=4)

    assert attempts == ["https://example.test/data.json"] * 4
    assert delays == [1.0, 2.0, 4.0]


def test_default_transport_does_not_retry_a_permanent_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []

    def unavailable(*_args: object, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise HTTPError("https://example.test/missing.json", 404, "missing", Message(), None)

    monkeypatch.setattr("football.providers.base.urlopen", unavailable)
    monkeypatch.setattr("football.providers.base.sleep", delays.append)

    with pytest.raises(ProviderFetchError, match="http_status=404"):
        UrllibHttpTransport().get(
            "https://example.test/missing.json", timeout_seconds=1, max_bytes=4
        )

    assert attempts == 1
    assert delays == []


def test_default_transport_retries_a_transient_http_status_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []

    def fetch(*_args: object, **_kwargs: object) -> _Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError("https://example.test/data.json", 503, "unavailable", Message(), None)
        return _response(b"[]")

    monkeypatch.setattr("football.providers.base.urlopen", fetch)
    monkeypatch.setattr("football.providers.base.sleep", delays.append)

    assert (
        UrllibHttpTransport().get("https://example.test/data.json", timeout_seconds=1, max_bytes=4)
        == b"[]"
    )
    assert attempts == 2
    assert delays == [1.0]


def test_statsbomb_adapter_rejects_resources_outside_its_json_contract() -> None:
    adapter = StatsBombOpenDataAdapter(source_git_sha="b0bc9f22dd77c206ddedc1d742893b3bbe64baec")

    with pytest.raises(ProviderConfigurationError, match="unsupported StatsBomb"):
        adapter.fetch(SourceResource("data/competitions.json", "text/plain"))


class _Headers:
    def get_content_type(self) -> str:
        return "application/json"

    def get(self, _name: str) -> None:
        return None


class _Response:
    headers = _Headers()
    status = 200

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return self._payload


def _response(payload: bytes) -> _Response:
    return _Response(payload)
