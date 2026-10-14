"""Exercise the Go diagnostics query against the disposable migration state."""

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


def test_history_diagnostics_use_real_queries_and_authenticated_local_reads(tmp_path: Path) -> None:
    binary = Path(".local/bin/football-api").resolve()
    assert binary.is_file(), "make build must precede API integration"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = {
        **os.environ,
        "DATABASE_URL": os.environ["TEST_DATABASE_URL"],
        "API_ADDR": f"127.0.0.1:{port}",
        "WEB_ORIGIN": "http://127.0.0.1:3000",
        "MATCHFORGE_OPERATIONAL_SYNC_INTERVAL": "0",
        "MATCHFORGE_HISTORY_SYNC_ENABLED": "false",
        "MATCHFORGE_FOTMOB_ENABLED": "false",
        "MATCHFORGE_PITCHAPI_ENABLED": "false",
    }
    with (tmp_path / "api.log").open("wb") as log:
        process = subprocess.Popen([str(binary)], env=environment, stdout=log, stderr=log)
        try:
            root = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urlopen(root + "/healthz", timeout=1) as response:
                        assert response.status == 200
                    break
                except (URLError, OSError):
                    assert process.poll() is None, (tmp_path / "api.log").read_text()
                    assert time.monotonic() < deadline, "API startup timed out"
                    time.sleep(0.05)
            with pytest.raises(HTTPError) as denied:
                urlopen(root + "/v1/admin/sync-runs", timeout=5)
            assert denied.value.code == 403
            denied.value.close()
            request = Request(
                root + "/v1/admin/sync-runs", headers={"Origin": "http://127.0.0.1:3000"}
            )
            with urlopen(request, timeout=5) as response:
                value = json.load(response)
            assert value["provider_configuration"]["history_sync_enabled"] is False
            progress = value["coverage"]["provider_history"]
            assert [item["provider"] for item in progress] == ["fotmob", "pitchapi"]
            for item in progress:
                assert item["remaining_requests"] is None
                assert item["completions_per_hour"] is None
                assert item["estimated_drain_hours"] is None
                assert item["pending"] >= 0 and item["completed"] >= 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
