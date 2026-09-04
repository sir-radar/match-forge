from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from football.providers import (
    FootballDataUkAcquirerV1,
    FootballDataUkAdapter,
    FootballDataUkRawStoreV1,
    HttpResponseV1,
)


@dataclass
class RecordingTransport:
    responses: dict[str, HttpResponseV1]
    urls: list[str] = field(default_factory=list)

    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        return self.get_response(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes).payload

    def get_response(self, url: str, *, timeout_seconds: float, max_bytes: int) -> HttpResponseV1:
        self.urls.append(url)
        assert timeout_seconds == 60
        assert max_bytes == 32 * 1024 * 1024
        return self.responses[url]


def test_acquirer_captures_frozen_resources_and_publishes_raw_bytes(tmp_path: Path) -> None:
    base_url = "https://www.football-data.co.uk"
    transport = RecordingTransport(
        {
            f"{base_url}/notes.txt": _response(b"notes", "text/plain"),
            f"{base_url}/mmz4281/2526/E0.csv": _response(b"current", "text/csv"),
            f"{base_url}/mmz4281/1516/E0.csv": _response(b"overlap", "text/csv"),
        }
    )
    clock_values = iter(
        (
            datetime(2026, 9, 4, 13, 45, tzinfo=UTC),
            datetime(2026, 9, 4, 13, 46, tzinfo=UTC),
            datetime(2026, 9, 4, 13, 47, tzinfo=UTC),
            datetime(2026, 9, 4, 13, 48, tzinfo=UTC),
            datetime(2026, 9, 4, 13, 49, tzinfo=UTC),
            datetime(2026, 9, 4, 13, 50, tzinfo=UTC),
        )
    )

    result = FootballDataUkAcquirerV1(
        FootballDataUkAdapter(transport=transport),
        FootballDataUkRawStoreV1(tmp_path),
        clock=lambda: next(clock_values),
    ).acquire()

    assert transport.urls == [
        f"{base_url}/notes.txt",
        f"{base_url}/mmz4281/2526/E0.csv",
        f"{base_url}/mmz4281/1516/E0.csv",
    ]
    assert [item.receipt.source_path for item in result.resources] == [
        "notes.txt",
        "mmz4281/2526/E0.csv",
        "mmz4281/1516/E0.csv",
    ]
    assert result.resources[0].receipt.request_started_at == datetime(
        2026, 9, 4, 13, 45, tzinfo=UTC
    )
    assert result.resources[0].receipt.observed_by_matchforge_at == datetime(
        2026, 9, 4, 13, 46, tzinfo=UTC
    )
    assert [item.raw_write.status for item in result.resources] == ["acquired"] * 3
    assert result.resources[2].raw_write.path.read_bytes() == b"overlap"


def _response(payload: bytes, content_type: str) -> HttpResponseV1:
    return HttpResponseV1(
        payload=payload,
        status=200,
        content_type=content_type,
        etag='"revision"',
        last_modified="Thu, 04 Sep 2026 13:00:00 GMT",
    )
