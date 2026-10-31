import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("sync_exit,collection_exit", [(0, 0), (3, 0), (0, 4), (3, 4)])
def test_daily_stages_are_independent_and_return_truthful_status(
    tmp_path: Path, sync_exit: int, collection_exit: int
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile("scripts/mvp-refresh.sh", scripts / "mvp-refresh.sh")
    binary = tmp_path / "bin"
    binary.mkdir()
    make = binary / "make"
    make.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$1" >> "$CALL_LOG"\n'
        'case "$1" in mvp-sync) exit "$SYNC_EXIT";; *) exit "$COLLECTION_EXIT";; esac\n'
    )
    make.chmod(0o755)
    log = tmp_path / "calls"
    result = subprocess.run(
        ["sh", str(scripts / "mvp-refresh.sh")],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ
        | {
            "PATH": f"{binary}:{os.environ['PATH']}",
            "CALL_LOG": str(log),
            "SYNC_EXIT": str(sync_exit),
            "COLLECTION_EXIT": str(collection_exit),
        },
    )
    assert log.read_text().splitlines() == ["mvp-sync", "external-predictions"]
    assert (result.returncode == 0) == (sync_exit == collection_exit == 0)
    assert f"sync_exit={sync_exit} collection_exit={collection_exit}" in result.stdout
