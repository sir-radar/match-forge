"""Launcher boundaries: preserve installations and keep MCP stdout parseable."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.verify_code_intelligence import Client, wait_coverage, wait_symbol

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "code-intelligence.sh"


@pytest.fixture
def launcher(tmp_path: Path) -> tuple[Path, Path]:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    script = tmp_path / "scripts" / LAUNCHER.name
    script.parent.mkdir()
    shutil.copyfile(LAUNCHER, script)
    binary = tmp_path / ".tools/code-intelligence/0.12.1/codebase-memory-mcp"
    binary.parent.mkdir(parents=True)
    return script, binary


def test_missing_installation_fails_with_recovery(launcher: tuple[Path, Path]) -> None:
    script, _ = launcher
    result = subprocess.run(["sh", str(script), "serve"], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "sh scripts/code-intelligence.sh install" in result.stderr


@pytest.mark.parametrize("index_exit", [0, 1])
def test_startup_reconciliation_precedes_mcp(launcher: tuple[Path, Path], index_exit: int) -> None:
    script, binary = launcher
    binary.write_text(
        '#!/bin/sh\ncase "$1" in\n'
        'config) echo "config:$*"; exit 0;;\n'
        f'cli) echo "index:$*"; exit {index_exit};;\n'
        '*) echo "MCP_READY";;\nesac\n'
    )
    binary.chmod(0o755)
    result = subprocess.run(["sh", str(script), "serve"], capture_output=True, text=True)
    assert result.returncode == index_exit
    assert result.stdout == ("MCP_READY\n" if index_exit == 0 else "")
    assert "--mode full --doc-candidates false" in result.stderr
    assert "config set auto_watch true" in result.stderr


def test_bad_download_preserves_installed_binary(launcher: tuple[Path, Path]) -> None:
    script, binary = launcher
    binary.write_text("existing installation")
    stubs = script.parent / "stubs"
    stubs.mkdir()
    (stubs / "uname").write_text(
        '#!/bin/sh\nif [ "$1" = -s ]; then echo Darwin; else echo arm64; fi\n'
    )
    (stubs / "curl").write_text(
        '#!/bin/sh\nwhile [ "$1" != --output ]; do shift; done\nshift\nprintf corrupted > "$1"\n'
    )
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    result = subprocess.run(
        ["sh", str(script), "install"],
        env=os.environ | {"PATH": f"{stubs}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "checksum mismatch" in result.stderr
    assert binary.read_text() == "existing installation"
    assert not list(binary.parent.glob("download.*"))


def test_coverage_waits_for_every_saved_path(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            {"paths": [{"freshness": "metadata_match"}]},
            {"paths": [{"freshness": "metadata_match"}, {"freshness": "changed"}]},
            {"paths": [{"freshness": "metadata_match"}, {"freshness": "metadata_match"}]},
        ]
    )
    monkeypatch.setattr(Client, "call", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr("scripts.verify_code_intelligence.time.sleep", lambda _seconds: None)
    result = wait_coverage(object.__new__(Client), Path("/fixture"), ["a.sql", "b.schema.json"])
    assert len(result["coverage"]["paths"]) == 2
    with pytest.raises(StopIteration):
        next(responses)


def test_stale_coverage_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0, 0, 61])
    monkeypatch.setattr("scripts.verify_code_intelligence.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("scripts.verify_code_intelligence.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(Client, "call", lambda *_args, **_kwargs: {"paths": []})
    with pytest.raises(AssertionError, match="Automatic metadata synchronization failed"):
        wait_coverage(object.__new__(Client), Path("/fixture"), ["a.sql"])


def test_rename_waits_for_obsolete_path_removal(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            {
                "groups": [
                    {"file": "old.py", "name": "mf_probe"},
                    {"file": "new.py", "name": "mf_probe"},
                ]
            },
            {"groups": [{"file": "new.py", "name": "mf_probe"}]},
        ]
    )
    monkeypatch.setattr(Client, "call", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr("scripts.verify_code_intelligence.time.sleep", lambda _seconds: None)
    wait_symbol(object.__new__(Client), Path("/fixture"), "mf_probe", expected_path="new.py")
    with pytest.raises(StopIteration):
        next(responses)
