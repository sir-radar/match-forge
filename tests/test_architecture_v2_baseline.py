from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest
from football.storage.raw import ImmutableFileConflict

from scripts import capture_architecture_v2_baseline as baseline
from scripts.capture_architecture_v2_baseline import (
    capture_source_resource,
    compare_relations,
    verify_source_archive,
    write_row_hashes,
)


def test_row_manifest_preserves_keys_and_duplicate_rows(tmp_path: Path) -> None:
    rows = [(None, "a" * 64), (None, "a" * 64), ('["fixture-id"]', "b" * 64)]
    first = tmp_path / "first.gz"
    second = tmp_path / "second.gz"
    result = write_row_hashes(iter(rows), first)
    assert result == write_row_hashes(iter(rows), second)
    with gzip.open(first, "rb") as handle:
        payload = handle.read()
    assert [tuple(json.loads(line)) for line in payload.splitlines()] == rows
    assert result == {"rows": 3, "sha256": hashlib.sha256(payload).hexdigest()}
    assert first.read_bytes() == second.read_bytes()


def test_restore_comparison_requires_every_relation_and_exact_contents() -> None:
    before = {"football.matches": {"rows": 1, "sha256": "original"}}
    assert compare_relations(before, before) == []
    assert compare_relations(before, {}) == ["football.matches"]
    assert compare_relations({}, before) == ["football.matches"]
    changed = {"football.matches": {"rows": 1, "sha256": "changed"}}
    assert compare_relations(before, changed) == ["football.matches"]


def source_row(payload: bytes) -> tuple[object, ...]:
    return (
        "retained.json",
        hashlib.sha256(payload).hexdigest(),
        "source",
        "revision",
        None,
        "resource-id",
        "native.json",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
        None,
    )


def test_source_capture_archives_verified_bytes_and_reports_missing(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    archive = tmp_path / "archive"
    payload = b'{"provider_native_id":42}'
    (root / "retained.json").write_bytes(payload)
    row = source_row(payload)
    verified = capture_source_resource(root, archive, "fotmob", row)
    assert verified["status"] == "BYTE_VERIFIED"
    assert (archive / str(verified["archive_path"])).read_bytes() == payload
    (root / "retained.json").unlink()
    missing = capture_source_resource(root, archive, "fotmob", row)
    assert missing["status"] == "SOURCE_BYTES_MISSING"
    assert "archive_path" not in missing


@pytest.mark.parametrize("actual", [b"tampered", b"{}"])
def test_source_capture_never_archives_wrong_bytes(tmp_path: Path, actual: bytes) -> None:
    (tmp_path / "retained.json").write_bytes(actual)
    archive = tmp_path / "archive"
    result = capture_source_resource(tmp_path, archive, "fotmob", source_row(b"original"))
    assert result["status"] == "REGISTERED_CHECKSUM_NOT_VERIFIED"
    assert not archive.exists()


def test_source_capture_rejects_path_escape_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    secret = tmp_path / "outside.json"
    secret.write_bytes(b"outside")
    row = source_row(b"outside")
    escaped = ("../outside.json", *row[1:])
    assert capture_source_resource(root, tmp_path / "archive", "fotmob", escaped)["status"] == (
        "INVALID_SOURCE_REFERENCE"
    )
    (root / "retained.json").symlink_to(secret)
    assert capture_source_resource(root, tmp_path / "archive", "fotmob", row)["status"] == (
        "INVALID_SOURCE_REFERENCE"
    )


def test_source_capture_does_not_reuse_corrupted_archive(tmp_path: Path) -> None:
    payload = b"original"
    (tmp_path / "retained.json").write_bytes(payload)
    archive = tmp_path / "archive"
    first = capture_source_resource(tmp_path, archive, "fotmob", source_row(payload))
    (archive / first["archive_path"]).write_bytes(b"corrupted")
    with pytest.raises(ImmutableFileConflict):
        capture_source_resource(tmp_path, archive, "fotmob", source_row(payload))


def test_archive_verification_detects_missing_or_changed_bytes(tmp_path: Path) -> None:
    payload = b"original"
    (tmp_path / "retained.json").write_bytes(payload)
    archive = tmp_path / "archive"
    result = capture_source_resource(tmp_path, archive, "fotmob", source_row(payload))
    (archive / "source-resources.json").write_text(json.dumps([result]))
    (archive / "source-manifests.json").write_text("[]")
    assert verify_source_archive(archive) == []
    (archive / result["archive_path"]).write_bytes(b"changed")
    assert verify_source_archive(archive) == [result["archive_path"]]
    (archive / result["archive_path"]).unlink()
    assert verify_source_archive(archive) == [result["archive_path"]]


def test_failed_capture_cannot_leave_a_passing_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_capture(*args: object) -> None:
        raise RuntimeError("snapshot export failed")

    monkeypatch.setattr(baseline, "repository_state", lambda: {})
    monkeypatch.setattr(baseline, "capture_database", fail_capture)
    output = tmp_path / "baseline"
    with pytest.raises(RuntimeError, match="snapshot export failed"):
        baseline.main(["--output", str(output), "--fixture-date", "2026-10-16"])
    assert json.loads((output / "manifest.json").read_text())["status"] == "INCOMPLETE"
    assert output.stat().st_mode & 0o077 == 0


def test_failed_baseline_cannot_be_used_as_restore_evidence(tmp_path: Path) -> None:
    original = tmp_path / "failed"
    original.mkdir()
    (original / "manifest.json").write_text(json.dumps({"status": "FAIL"}))
    with pytest.raises(ValueError, match="incomplete or failed"):
        baseline.main(
            [
                "--output",
                str(tmp_path / "verification"),
                "--verify-restored-baseline",
                str(original),
            ]
        )


@pytest.mark.parametrize("health", ["ok", "degraded"])
def test_capture_rejects_duplicate_api_ids_or_unhealthy_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, health: str
) -> None:
    monkeypatch.setattr(
        baseline,
        "repository_state",
        lambda: {
            "champion_sha256": baseline.CHAMPION_SHA256,
        },
    )
    monkeypatch.setattr(
        baseline,
        "capture_database",
        lambda *args: {
            "duplicates": {"status": "PASS"},
            "source_bytes": {
                "resources": {"BYTE_VERIFIED": 1},
                "manifests": {"BYTE_VERIFIED": 1},
            },
        },
    )
    monkeypatch.setattr(
        baseline,
        "capture_api",
        lambda *args: {
            "responses": [
                {"status": health},
                {"status": "ready"},
                {"duplicate_fixture_ids": 1 if health == "ok" else 0},
            ]
        },
    )
    output = tmp_path / "baseline"
    assert baseline.main(["--output", str(output), "--fixture-date", "2026-10-16"]) == 1
    assert json.loads((output / "manifest.json").read_text())["status"] == "FAIL"


def test_missing_manifest_warns_even_when_resource_bytes_are_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        baseline,
        "repository_state",
        lambda: {
            "champion_sha256": baseline.CHAMPION_SHA256,
        },
    )
    monkeypatch.setattr(
        baseline,
        "capture_database",
        lambda *args: {
            "duplicates": {"status": "PASS"},
            "source_bytes": {
                "resources": {"BYTE_VERIFIED": 1},
                "manifests": {"SOURCE_BYTES_MISSING": 1},
            },
        },
    )
    monkeypatch.setattr(
        baseline,
        "capture_api",
        lambda *args: {
            "responses": [{"status": "ok"}, {"status": "ready"}],
        },
    )
    output = tmp_path / "baseline"
    assert baseline.main(["--output", str(output), "--fixture-date", "2026-10-16"]) == 0
    assert json.loads((output / "manifest.json").read_text())["status"] == "PASS_WITH_WARNINGS"
