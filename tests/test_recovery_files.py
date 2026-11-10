import hashlib
from pathlib import Path

import pytest
from football.providers.football_data_uk_evidence import (
    FootballDataUkAcquisitionEvidenceStoreV1,
    FootballDataUkAcquisitionEvidenceV1,
)

from python.football.tests.test_football_data_uk_evidence import _receipts
from scripts.recovery_files import (
    FileReference,
    RecoveryReferenceError,
    capture_files,
    legacy_source_path,
    restore_files,
    source_manifest_reference,
    verify_files,
)


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


def test_legacy_resource_locator_requires_proven_bytes_or_existing_provider_layout() -> None:
    assert (
        legacy_source_path("legacy", None, "native.json", "source.json", "a" * 64, "a" * 64)
        == "source.json"
    )
    assert (
        legacy_source_path(
            "openfootball", "commit", "native.json", "manifest.json", "a" * 64, "b" * 64
        )
        == "openfootball/commit/native.json"
    )
    with pytest.raises(RecoveryReferenceError, match="verified physical file locator"):
        legacy_source_path("unknown", None, "native.json", "manifest.json", "a" * 64, "b" * 64)


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_references_preserve_every_registered_size_requirement(
    tmp_path: Path, reverse: bool
) -> None:
    payload = b"original"
    (tmp_path / "file").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    refs = [FileReference("data", "file", digest, 999), FileReference("data", "file", digest)]
    if reverse:
        refs.reverse()
    report = capture_files(refs, {"data": tmp_path}, tmp_path / "capture")
    assert report["status"] == "INCOMPLETE"
    assert len(report["failures"]) == 1


def test_legacy_path_identity_is_not_treated_as_a_physical_file_checksum(tmp_path: Path) -> None:
    path = "football_data_uk/2026-2027/original.csv"
    identity = hashlib.sha256(path.encode()).hexdigest()
    ref = source_manifest_reference(tmp_path, "football_data_uk", "old-revision", path, identity)
    assert ref.sha256 is None
    assert legacy_source_path("football_data_uk", None, "E0.csv", path, identity, "a" * 64) == path


def test_acquisition_evidence_preserves_logical_identity_and_physical_bytes(tmp_path: Path) -> None:
    evidence = FootballDataUkAcquisitionEvidenceV1(receipts=_receipts())
    stored = FootballDataUkAcquisitionEvidenceStoreV1(tmp_path).publish(evidence)
    relative = stored.path.relative_to(tmp_path).as_posix()
    ref = source_manifest_reference(
        tmp_path, "football_data_uk", evidence.sha256, relative, evidence.sha256
    )
    assert ref.sha256 == hashlib.sha256(evidence.to_bytes()).hexdigest()
    assert ref.sha256 != evidence.sha256
    assert stored.path.read_bytes() == evidence.to_bytes()
    stored.path.write_bytes(evidence.to_bytes() + b" ")
    with pytest.raises(ValueError):
        source_manifest_reference(
            tmp_path, "football_data_uk", evidence.sha256, relative, evidence.sha256
        )


def test_relocated_original_is_copied_by_checksum_with_registration_trace(tmp_path: Path) -> None:
    retained = tmp_path / "repository"
    retained.mkdir()
    payload = b"retained exact original"
    (retained / "retained.json").write_bytes(payload)
    ref = FileReference(
        "data",
        "missing/report.json",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
        registrations=({"table": "sprint2_evaluation_runs", "keys": {"id": "stable-id"}},),
        source_path="retained.json",
    )
    archive = tmp_path / "capture"
    result = capture_files([ref], {"data": tmp_path / "data", "repository": retained}, archive)
    assert result["status"] == "COMPLETE"
    assert result["files"][0]["registrations"][0]["keys"]["id"] == "stable-id"
    target = tmp_path / "restored"
    restore_files(archive, {"data": target})
    assert (target / "missing/report.json").read_bytes() == payload
    assert (retained / "retained.json").read_bytes() == payload
    with pytest.raises(ValueError):
        FileReference("data", "file", None, source_path="../escape")
