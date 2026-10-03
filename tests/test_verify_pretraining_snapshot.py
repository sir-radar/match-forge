from __future__ import annotations

import hashlib
import json
from pathlib import Path

from football.contracts.source import canonical_json_bytes

from scripts.verify_pretraining_snapshot import _inventory, restore_backup, verify_snapshot


def test_verifies_and_restores_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    primary = root / "primary"
    backup = root / "backup"
    digests: list[str] = []
    for content in (b"snapshot", b"package", b"manifest"):
        digest = hashlib.sha256(content).hexdigest()
        digests.append(digest)
        for tree in (primary, backup):
            path = tree / "manifests" / "sha256" / digest[:2] / f"{digest}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    inventory_sha256 = hashlib.sha256(canonical_json_bytes(_inventory(primary))).hexdigest()
    result = {
        "snapshot_id": "snapshot-id",
        "snapshot_sha256": "snapshot-logical-sha",
        "future_research_package": {"sha256": digests[1]},
    }
    (root / "RESULT.json").write_text(json.dumps(result))
    evidence = {
        "backup": {"inventory_sha256": inventory_sha256},
        "snapshot": {
            "snapshot_id": "snapshot-id",
            "snapshot_sha256": "snapshot-logical-sha",
            "document_sha256": digests[0],
        },
        "research_package": {"sha256": digests[1]},
        "manifests": {"history_sha256": digests[2]},
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence))

    report = verify_snapshot(root, evidence_path)
    restore_to = tmp_path / "restored"
    restore_backup(root, restore_to)

    assert report["status"] == "PASS"
    assert _inventory(restore_to) == _inventory(primary)


def test_snapshot_verification_fails_when_backup_differs(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    (root / "primary").mkdir(parents=True)
    (root / "backup").mkdir(parents=True)
    (root / "primary" / "value").write_text("primary")
    (root / "backup" / "value").write_text("backup")
    (root / "RESULT.json").write_text(
        json.dumps(
            {
                "snapshot_id": "snapshot-id",
                "snapshot_sha256": "snapshot-sha",
                "future_research_package": {"sha256": "package-sha"},
            }
        )
    )
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "backup": {"inventory_sha256": "wrong"},
                "snapshot": {
                    "snapshot_id": "snapshot-id",
                    "snapshot_sha256": "snapshot-sha",
                    "document_sha256": "document-sha",
                },
                "research_package": {"sha256": "package-sha"},
                "manifests": {},
            }
        )
    )

    report = verify_snapshot(root, evidence_path)

    assert report["status"] == "FAIL"
    assert "PRIMARY_BACKUP_INVENTORY_MISMATCH" in report["failures"]
