from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.storage_reclamation import duplicate_manifest, file_observation


def test_duplicate_bytes_do_not_authorize_cleanup(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    one.write_bytes(b"historical original")
    two.write_bytes(one.read_bytes())
    digest = hashlib.sha256(one.read_bytes()).hexdigest()
    (tmp_path / "exact-duplicates.tsv").write_text(
        f"sha256\tpaths\test_recoverable_physical_bytes\n{digest}\t{one} | {two}\t4096\n"
    )
    records = duplicate_manifest(tmp_path, tmp_path)
    assert records[0]["byte_redundancy_verified"] is True
    assert records[0]["approval"] == "NOT_REQUESTED"
    assert records[0]["expected_physical_reclaimed_bytes"] is None
    two.write_bytes(b"unique correction")
    assert duplicate_manifest(tmp_path, tmp_path)[0]["byte_redundancy_verified"] is False


def test_missing_or_symlink_evidence_is_blocked(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.write_bytes(b"evidence")
    link = tmp_path / "link"
    link.symlink_to(original)
    assert file_observation(link)["blockers"]
    assert file_observation(tmp_path / "missing")["blockers"]
