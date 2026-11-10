import os
from pathlib import Path

import pytest

from scripts.backup_destination import (
    BackupConfig,
    BackupError,
    Restic,
    credential_environment,
    require_capacity,
    validate_volume,
)


def config(tmp_path: Path) -> BackupConfig:
    return BackupConfig(tmp_path, "enrolled-uuid", "repository-id", "", "")


def test_disconnected_internal_substituted_readonly_and_unknown_volumes(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    good = {
        "MountPoint": str(tmp_path),
        "Internal": False,
        "VolumeUUID": cfg.volume_uuid,
        "WritableVolume": True,
        "FilesystemType": "apfs",
    }
    validate_volume(good, cfg, True)
    for changes, mounted, code in [
        ({}, False, "DISCONNECTED"),
        ({"Internal": True}, True, "WRONG_DRIVE"),
        ({"VolumeUUID": "substituted"}, True, "WRONG_DRIVE"),
        ({"WritableVolume": False}, True, "READ_ONLY"),
        ({"FilesystemType": ""}, True, "FILESYSTEM_UNKNOWN"),
    ]:
        with pytest.raises(BackupError) as error:
            validate_volume({**good, **changes}, cfg, mounted)
        assert error.value.code == code
    assert list(tmp_path.iterdir()) == []


def test_credentials_require_owner_only_file_and_ignore_restic_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    password = tmp_path / "password"
    password.write_text("independent-recovery-password")
    cfg = BackupConfig(tmp_path, "uuid", "repo", str(password), "")
    password.chmod(0o644)
    with pytest.raises(BackupError, match="owner-only"):
        credential_environment(cfg)
    password.chmod(0o600)
    monkeypatch.setenv("RESTIC_REPOSITORY", "wrong-destination")
    monkeypatch.setenv("RESTIC_PASSWORD_COMMAND", "unsafe-command")
    env = credential_environment(cfg)
    assert env["RESTIC_PASSWORD_FILE"] == str(password)
    assert env["GOMAXPROCS"] == "2"
    assert "RESTIC_REPOSITORY" not in env
    assert "RESTIC_PASSWORD_COMMAND" not in env
    password.unlink()
    password.symlink_to(tmp_path / "missing")
    with pytest.raises(BackupError):
        credential_environment(cfg)


def test_disabled_activation_and_capacity_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATCHFORGE_BACKUP_ENABLED", raising=False)
    with pytest.raises(BackupError) as error:
        BackupConfig.load()
    assert error.value.code == "DISABLED"
    assert require_capacity(300, 100, 1000) is False
    assert require_capacity(299, 100, 1000) is True
    with pytest.raises(BackupError, match="1 more bytes"):
        require_capacity(99, 100, 1000)
    assert os.environ.get("MATCHFORGE_BACKUP_ENABLED") is None


def test_changed_filesystem_cannot_receive_repository_writes(tmp_path: Path) -> None:
    with pytest.raises(BackupError) as error:
        Restic(tmp_path, {}, device_id=-1).run("init")
    assert error.value.code == "WRONG_DRIVE"
    assert list(tmp_path.iterdir()) == []
