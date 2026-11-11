import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.backup_destination import BackupError, Restic
from scripts.capture_architecture_v2_baseline import file_sha256


def test_encrypted_incremental_repository_independent_restore_and_corruption(
    tmp_path: Path,
) -> None:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("RESTIC_")}
    environment.update(RESTIC_PASSWORD="disposable-fixture-password-only", GOMAXPROCS="2")
    repository = tmp_path / "repository"
    repository.mkdir()
    restic = Restic(repository, environment)
    restic.run("init", "--repository-version", "2")
    assert len(restic.identity()) == 64
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "random.bin").write_bytes(hashlib.shake_256(b"fixture").digest(1024 * 1024))
    (payload / "source.json").write_bytes(b'{"original":42}\n' * 100000)
    expected = {path.name: file_sha256(path) for path in payload.iterdir()}
    summaries = []
    for _ in range(2):
        events = restic.run("backup", "--json", "--read-concurrency", "2", str(payload))
        summaries.extend(
            json.loads(line)
            for line in events.splitlines()
            if json.loads(line).get("message_type") == "summary"
        )
    assert summaries[0]["data_added_packed"] < summaries[0]["total_bytes_processed"]
    assert summaries[1]["data_blobs"] == 0
    assert summaries[1]["files_unmodified"] == 2
    payload.rename(tmp_path / "original-unavailable")
    restic.run("check", "--read-data")
    restic.run(
        "restore",
        summaries[-1]["snapshot_id"] + ":" + str(payload),
        "--target",
        str(tmp_path / "restored"),
        "--verify",
    )
    assert {path.name: file_sha256(path) for path in (tmp_path / "restored").iterdir()} == expected
    wrong = Restic(repository, {**environment, "RESTIC_PASSWORD": "incorrect-key"})
    with pytest.raises(BackupError):
        wrong.run("snapshots", "--json")
    pack = next((repository / "data").glob("*/*"))
    content = pack.read_bytes()
    pack.chmod(0o600)
    pack.write_bytes(b"corrupt" + content[7:])
    with pytest.raises(BackupError):
        restic.run("check", "--read-data")


def test_repository_operations_pin_directory_before_path_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    environment = {**os.environ, "RESTIC_PASSWORD": "disposable-fixture-password-only"}
    restic = Restic(repository, environment)
    restic.run("init", "--repository-version", "2")
    expected = restic.identity()
    original_run = subprocess.run

    def substitute(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        repository.rename(tmp_path / "original-volume")
        repository.mkdir()
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", substitute)
    actual = json.loads(restic.run("cat", "config"))
    assert actual["id"] == expected
    assert list(repository.iterdir()) == []
