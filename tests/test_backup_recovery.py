from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.backup_recovery import require_restore_storage


def test_restore_rejects_operating_and_original_storage_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operating = tmp_path / "operating"
    original = tmp_path / "original"
    monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(operating))
    report = {"data_root": str(original)}
    for target, message in ((operating, "operating"), (original, "source")):
        with pytest.raises(ValueError, match=message):
            require_restore_storage(report, tmp_path, target / "restore")
    assert not operating.exists()
    assert not original.exists()


def test_restore_requires_capacity_before_creating_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(tmp_path / "operating"))
    (tmp_path / "database.dump").write_bytes(b"dump")
    report = {"files": {"logical_bytes": 20}, "database_size_bytes": 100}
    destination = tmp_path / "new-parent" / "restore"
    monkeypatch.setattr(
        "scripts.backup_recovery.shutil.disk_usage", lambda _: SimpleNamespace(free=119)
    )
    with pytest.raises(ValueError, match="insufficient storage"):
        require_restore_storage(report, tmp_path, destination)
    assert not destination.parent.exists()
    monkeypatch.setattr(
        "scripts.backup_recovery.shutil.disk_usage", lambda _: SimpleNamespace(free=120)
    )
    require_restore_storage(report, tmp_path, destination)
