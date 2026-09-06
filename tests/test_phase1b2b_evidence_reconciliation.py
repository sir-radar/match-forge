"""Regression checks for the Phase 1B/2B evidence correction record."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORRECTION_PATH = (
    REPOSITORY_ROOT
    / "docs/evidence/phase1b2b-gate-2026-09-06-outcome-scope-checksum-correction.json"
)
REPORT_PATH = "docs/evidence/phase1b2b-gate-2026-09-06-outcome-scope.json"


def _committed_bytes(path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"HEAD:{path}"],
        cwd=REPOSITORY_ROOT,
    )


def test_checksum_correction_matches_committed_gate_report_bytes() -> None:
    correction = json.loads(CORRECTION_PATH.read_text())
    committed_bytes = _committed_bytes(REPORT_PATH)
    committed_blob = subprocess.check_output(
        ["git", "rev-parse", f"HEAD:{REPORT_PATH}"],
        cwd=REPOSITORY_ROOT,
        text=True,
    ).strip()

    assert correction["corrected_artifact"]["path"] == REPORT_PATH
    assert correction["corrected_artifact"]["git_blob_sha"] == committed_blob
    assert correction["corrected_artifact"]["sha256"] == hashlib.sha256(committed_bytes).hexdigest()
    assert (REPOSITORY_ROOT / REPORT_PATH).read_bytes() == committed_bytes
    assert correction["resulting_gate_status"] == "PASS"
