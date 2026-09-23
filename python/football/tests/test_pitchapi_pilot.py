from __future__ import annotations

import io
import json
import urllib.error
from collections.abc import Mapping
from email.message import Message
from typing import Any

import pytest
from football.validation.pitchapi import PitchApiSeasonScope

from scripts.run_pitchapi_validation_pilot import (
    PilotHttpClient,
    PilotStop,
    _stopped_report,
    select_pilot_manifest,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _Response:
    status = 200

    def __init__(self, payload: Mapping[str, object]) -> None:
        self.headers = Message()
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self._body


def _manifest(count: int = 12) -> dict[str, object]:
    matches = [
        {
            "id": f"m_{index:02d}",
            "date": f"2023-08-{index + 1:02d}",
            "time_utc": f"2023-08-{index + 1:02d}T18:30:00Z",
            "status": "finished",
            "home_team": {"id": f"t_h{index}"},
            "away_team": {"id": f"t_a{index}"},
            "score_home": 1,
            "score_away": 0,
        }
        for index in reversed(range(count))
    ]
    return {
        "data": {
            "league": {"id": "l_test", "name": "Test", "season": "2023/2024"},
            "matches": matches,
        }
    }


def test_manifest_selection_is_complete_deterministic_and_earliest_first() -> None:
    scope = PitchApiSeasonScope("test", "l_test", "2023/2024", 10)

    first = select_pilot_manifest(_manifest(), scope, full_expected_match_count=12)
    second = select_pilot_manifest(_manifest(), scope, full_expected_match_count=12)

    assert first.observed_match_count == 12
    assert first.manifest_identity_sha256 == second.manifest_identity_sha256
    assert first.selection_sha256 == second.selection_sha256
    data = first.payload["data"]
    assert isinstance(data, Mapping)
    matches = data["matches"]
    assert isinstance(matches, list)
    assert [match["id"] for match in matches] == [f"m_{index:02d}" for index in range(10)]


def test_manifest_selection_stops_on_incomplete_or_invalid_manifest() -> None:
    scope = PitchApiSeasonScope("test", "l_test", "2023/2024", 10)

    with pytest.raises(PilotStop, match="FULL_SEASON_MATCH_COUNT_MISMATCH"):
        select_pilot_manifest(_manifest(11), scope, full_expected_match_count=12)

    payload = _manifest()
    data = payload["data"]
    assert isinstance(data, dict)
    matches = data["matches"]
    assert isinstance(matches, list)
    matches[0]["time_utc"] = None
    with pytest.raises(PilotStop, match="INVALID_MANIFEST_FIXTURE"):
        select_pilot_manifest(payload, scope, full_expected_match_count=12)


def test_http_client_paces_requests_and_never_records_credential() -> None:
    clock = _Clock()
    seen_headers: list[dict[str, str]] = []

    def opener(request: Any, *, timeout: int) -> _Response:
        assert timeout == 30
        seen_headers.append(dict(request.header_items()))
        return _Response({"data": {}})

    client = PilotHttpClient(
        "secret-value",
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        opener=opener,
    )

    client.get_json("/v1/test/one")
    client.get_json("/v1/test/two")

    assert client.request_start_times == [0.0, 1.0]
    assert len(client.records) == 2
    assert all("secret-value" not in repr(record) for record in client.records)
    assert seen_headers[0]["X-api-key"] == "secret-value"


def test_second_rate_limit_stops_and_reports_consumed_budget() -> None:
    clock = _Clock()

    def opener(request: Any, *, timeout: int) -> _Response:
        del request, timeout
        headers = Message()
        headers["Retry-After"] = "1"
        raise urllib.error.HTTPError(
            url="https://api.pitchapi.dev/v1/test",
            code=429,
            msg="rate limited",
            hdrs=headers,
            fp=io.BytesIO(b""),
        )

    client = PilotHttpClient(
        "secret-value",
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        opener=opener,
    )

    with pytest.raises(PilotStop, match="REPEATED_RATE_LIMIT") as stopped:
        client.get_json("/v1/test")

    report = _stopped_report(client, stopped.value.code)
    assert report["status"] == "STOPPED"
    assert report["stop_code"] == "REPEATED_RATE_LIMIT"
    assert report["request_budget"] == {
        "pilot_base_attempts": 22,
        "pilot_attempt_ceiling": 34,
        "original_audit_attempt_ceiling": 702,
        "absolute_remaining_ceiling_before_run": 700,
        "prior_attempts_used": 2,
        "attempts_used_this_run": 2,
        "cumulative_attempts_used": 4,
        "retries_used": 1,
        "remaining_total_attempts": 698,
        "remaining_retry_reserve": 11,
    }
