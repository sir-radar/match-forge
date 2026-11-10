import hashlib
from pathlib import Path

import pytest

from scripts.recovery_files import FileReference, capture_files, restore_files, verify_files


def reference(payload: bytes, path: str = "raw/original.json") -> FileReference:
    return FileReference("data", path, hashlib.sha256(payload).hexdigest(), len(payload))


def test_recovery_preserves_exact_files_and_mtime_without_original_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "raw").mkdir(parents=True)
    payload = b'{"original":true}\n'
    (source / "raw/original.json").write_bytes(payload)
    archive = tmp_path / "archive"
    report = capture_files([reference(payload)], {"data": source}, archive)
    assert report["status"] == "COMPLETE"
    source.rename(tmp_path / "unavailable-original")
    target = tmp_path / "restored"
    restore_files(archive, {"data": target})
    assert (target / "raw/original.json").read_bytes() == payload
    assert (target / "raw/original.json").stat().st_mtime_ns == (
        tmp_path / "unavailable-original/raw/original.json"
    ).stat().st_mtime_ns
    assert verify_files(archive) == []
    (archive / "files/data/raw/original.json").write_bytes(b"corrupt")
    assert verify_files(archive)
    with pytest.raises(ValueError, match="verification"):
        restore_files(archive, {"data": tmp_path / "other"})


@pytest.mark.parametrize("path", ["../escape", "/absolute", "raw/../../escape"])
def test_recovery_rejects_path_escape(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError):
        reference(b"payload", path)


def test_missing_wrong_and_symlink_dependencies_never_complete(tmp_path: Path) -> None:
    (tmp_path / "wrong").write_bytes(b"wrong")
    (tmp_path / "link").symlink_to(tmp_path / "wrong")
    report = capture_files(
        [reference(b"original", path) for path in ("missing", "wrong", "link")],
        {"data": tmp_path},
        tmp_path / "archive",
    )
    assert report["status"] == "INCOMPLETE"
    assert len(report["failures"]) == 3
    with pytest.raises(ValueError, match="incomplete"):
        restore_files(tmp_path / "archive", {"data": tmp_path / "restored"})


def test_conflicting_registrations_and_nonempty_restore_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="conflicting"):
        capture_files([reference(b"one"), reference(b"two")], {"data": tmp_path}, tmp_path / "a")
    (tmp_path / "file").write_bytes(b"one")
    capture_files([reference(b"one", "file")], {"data": tmp_path}, tmp_path / "b")
    with pytest.raises(ValueError, match="empty"):
        restore_files(tmp_path / "b", {"data": tmp_path})
