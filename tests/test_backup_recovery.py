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


def test_application_restore_keeps_retained_evidence_and_rejects_links(tmp_path: Path) -> None:
    import io
    import tarfile

    from scripts.backup_recovery import restore_application

    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "existing").write_bytes(b"original")
    with tarfile.open(tmp_path / "application.tar", "w") as archive:
        for name, payload in (("existing", b"original"), ("scripts/tool", b"code")):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    restore_application(tmp_path, repository)
    assert (repository / "scripts/tool").read_bytes() == b"code"
    (repository / "existing").write_bytes(b"retained different evidence")
    with pytest.raises(ValueError, match="conflicts"):
        restore_application(tmp_path, repository)
    with tarfile.open(tmp_path / "application.tar", "w") as archive:
        link = tarfile.TarInfo("escape")
        link.type = tarfile.SYMTYPE
        link.linkname = str(tmp_path.parent)
        archive.addfile(link)
    with pytest.raises(ValueError, match="link"):
        restore_application(tmp_path, repository)
    assert not (repository / "escape").exists()


def test_restore_keeps_registered_old_source_beside_current_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tracked file changed after a record registered it must not block restore."""
    import io
    import tarfile

    from scripts import backup_recovery

    path = "python/module.py"
    with tarfile.open(tmp_path / "application.tar", "w") as archive:
        member = tarfile.TarInfo(path)
        member.size = len(b"current")
        archive.addfile(member, io.BytesIO(b"current"))

    def restore_evidence(_archive: Path, roots: dict[str, Path]) -> None:
        target = roots["repository"] / path
        target.parent.mkdir(parents=True)
        target.write_bytes(b"registered")

    class Stop(Exception):
        pass

    def stop(*_args: object, **_kwargs: object) -> None:
        raise Stop

    monkeypatch.setattr(
        backup_recovery, "verify_capture", lambda *_a, **_k: {"files": {"logical_bytes": 0}}
    )
    monkeypatch.setattr(backup_recovery, "require_restore_storage", lambda *_a: None)
    monkeypatch.setattr(backup_recovery, "restore_files", restore_evidence)
    monkeypatch.setattr("psycopg.connect", stop)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    destination = tmp_path / "restored"
    with pytest.raises(Stop):
        backup_recovery.verify_restore(tmp_path, destination)
    assert (destination / "repository" / path).read_bytes() == b"registered"
    assert (destination / "application" / path).read_bytes() == b"current"
