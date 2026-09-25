from __future__ import annotations

import io
import json
import urllib.error
from collections.abc import Mapping
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from football.validation.pitchapi import PitchApiSeasonScope

from scripts.run_pitchapi_snapshot_v1_acquisition import (
    Client,
    SnapshotStop,
    Store,
    _register_fixture_mappings,
    _target_plan,
)
from scripts.run_pitchapi_validation_pilot import select_pilot_manifest


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _Response:
    status = 200

    def __init__(self, payload: Mapping[str, object], *, content_type: str = "application/json"):
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self._stream = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self._stream.read(size)


def _manifest(rounds: int = 11) -> dict[str, object]:
    matches: list[dict[str, object]] = []
    for round_index in range(rounds):
        for fixture_index in range(2):
            match_index = round_index * 2 + fixture_index
            matches.append(
                {
                    "id": f"m_{match_index}",
                    "date": f"2023-08-{round_index + 1:02d}",
                    "time_utc": f"2023-08-{round_index + 1:02d}T18:00:00Z",
                    "status": "finished",
                    "home_team": {"id": f"t_{fixture_index * 2}"},
                    "away_team": {"id": f"t_{fixture_index * 2 + 1}"},
                    "score_home": 1,
                    "score_away": 0,
                }
            )
    return {
        "data": {
            "league": {"id": "l_test", "name": "Test", "season": "2023/2024"},
            "matches": matches,
        }
    }


def test_client_streams_paces_and_does_not_persist_secret(tmp_path: Path) -> None:
    clock = _Clock()
    seen_headers: list[dict[str, str]] = []

    def opener(request: Any, *, timeout: int) -> _Response:
        assert timeout == 30
        seen_headers.append(dict(request.header_items()))
        return _Response({"data": {"ok": True}})

    store = Store(tmp_path / "snapshot")
    client = Client(
        "secret-value",
        store,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        opener=opener,
    )

    first = client.get("/v1/test/one", cap=1024)
    second = client.get("/v1/test/two", cap=1024)

    assert first[0] == {"data": {"ok": True}}
    assert second[0] == first[0]
    assert client.starts == [0.0, 1.0]
    assert seen_headers[0]["X-api-key"] == "secret-value"
    assert "secret-value" not in (store.staging / "attempt-ledger.jsonl").read_text()


def test_client_rejects_wrong_content_type_without_retry(tmp_path: Path) -> None:
    store = Store(tmp_path / "snapshot")
    client = Client(
        "secret-value",
        store,
        opener=lambda *_args, **_kwargs: _Response({}, content_type="text/html"),
    )

    with pytest.raises(SnapshotStop, match="CONTENT_TYPE_MISMATCH"):
        client.get("/v1/test", cap=1024)

    assert client.state.attempts == 1


def test_client_retries_one_503_and_counts_attempt(tmp_path: Path) -> None:
    clock = _Clock()
    calls = 0

    def opener(*_args: object, **_kwargs: object) -> _Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(
                "https://api.pitchapi.dev/v1/test",
                503,
                "unavailable",
                Message(),
                io.BytesIO(),
            )
        return _Response({"data": {}})

    store = Store(tmp_path / "snapshot")
    client = Client(
        "secret-value",
        store,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        opener=opener,
    )

    client.get("/v1/test", cap=1024)

    assert client.state.attempts == 2
    assert client.state.retries == 1
    assert len(client.records) == 2


def test_target_plan_freezes_same_kickoff_batch_before_history_update() -> None:
    scope = PitchApiSeasonScope("test", "l_test", "2023/2024", 22)
    selection = select_pilot_manifest(_manifest(), scope, full_expected_match_count=22)
    mappings: dict[tuple[str, str], str] = {}
    _register_fixture_mappings(mappings, selection)

    plan = _target_plan(selection, mappings)

    match_ids = plan["match_ids"]
    target_ids = plan["target_ids"]
    assert isinstance(match_ids, list)
    assert isinstance(target_ids, list)
    assert len(match_ids) == 22
    assert len(target_ids) == 2
    assert plan["exclusions"] == {"TEAM_PRIOR_APPEARANCES_LT_10": 20}
    assert plan["same_kickoff_batch_count"] == 11


def test_store_verifies_backup_and_rejects_existing_root(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    store = Store(root)
    relative, digest, size = store.publish_bytes("normalized", b'{"ok":true}')

    backup_digest, total = store.seal_backup()

    assert relative.endswith(f"{digest}.json")
    assert size == 11
    assert total == 22
    assert len(backup_digest) == 64
    with pytest.raises(SnapshotStop, match="SNAPSHOT_OUTPUT_ALREADY_EXISTS"):
        Store(root)
