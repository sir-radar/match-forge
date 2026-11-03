"""Launcher boundaries: preserve installations and keep MCP stdout parseable."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

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
