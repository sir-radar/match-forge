import json
import sys
from typing import Any

import pytest

from scripts import manual_backup


def test_unexpected_failure_keeps_public_message_and_logs_private_cause(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_args: Any) -> dict[str, Any]:
        raise ValueError("unavailable dependencies changed; inspect a fresh recovery inventory")

    monkeypatch.setattr(manual_backup, "cli_action", fail)
    monkeypatch.setattr(sys, "argv", ["manual_backup", "preview"])
    manual_backup.main()
    output = capsys.readouterr()
    public = json.loads(output.out)
    assert public["state"] == "SNAPSHOT_FAILED"
    assert "unavailable dependencies" not in output.out
    diagnostic = json.loads(output.err)
    assert diagnostic == {
        "status": "RECOVERY_DIAGNOSTIC",
        "private_failure_type": "ValueError",
        "private_failure_detail": (
            "unavailable dependencies changed; inspect a fresh recovery inventory"
        ),
    }
