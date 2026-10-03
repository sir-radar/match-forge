#!/usr/bin/env python3
"""Verify and optionally restore the qualified H2H pre-training snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from football.contracts.source import canonical_json_bytes

DEFAULT_ROOT = Path(".local/pitchapi-firewall-safe-h2h-history-extension-v1")
DEFAULT_EVIDENCE = Path(
    "docs/evidence/matchforge-firewall-safe-h2h-history-extension-v1-result-2026-09-28.json"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def verify_snapshot(root: Path, evidence_path: Path = DEFAULT_EVIDENCE) -> dict[str, object]:
    result = cast(Mapping[str, Any], json.loads((root / "RESULT.json").read_text()))
    evidence = cast(Mapping[str, Any], json.loads(evidence_path.read_text()))
    primary = root / "primary"
    backup = root / "backup"
    primary_inventory = _inventory(primary)
    backup_inventory = _inventory(backup)
    inventory_sha256 = hashlib.sha256(canonical_json_bytes(primary_inventory)).hexdigest()

    failures: list[str] = []
    if primary_inventory != backup_inventory:
        failures.append("PRIMARY_BACKUP_INVENTORY_MISMATCH")
    expected_inventory = str(cast(Mapping[str, Any], evidence["backup"])["inventory_sha256"])
    if inventory_sha256 != expected_inventory:
        failures.append("INVENTORY_SHA256_MISMATCH")

    expected_snapshot = cast(Mapping[str, Any], evidence["snapshot"])
    for key in ("snapshot_id", "snapshot_sha256"):
        if result.get(key) != expected_snapshot.get(key):
            failures.append(f"{key.upper()}_MISMATCH")

    package = cast(Mapping[str, Any], result.get("future_research_package", {}))
    expected_package = cast(Mapping[str, Any], evidence["research_package"])
    if package.get("sha256") != expected_package.get("sha256"):
        failures.append("RESEARCH_PACKAGE_SHA256_MISMATCH")

    expected_digests = {
        *cast(Mapping[str, str], evidence["manifests"]).values(),
        str(expected_snapshot["document_sha256"]),
        str(expected_package["sha256"]),
    }
    stored_digests = {str(item["sha256"]) for item in primary_inventory}
    missing = sorted(expected_digests - stored_digests)
    if missing:
        failures.append("MISSING_CONTENT_ADDRESSED_ARTIFACTS")

    return {
        "contract": "PretrainingSnapshotVerificationV1",
        "status": "FAIL" if failures else "PASS",
        "file_count": len(primary_inventory),
        "inventory_sha256": inventory_sha256,
        "snapshot_id": result.get("snapshot_id"),
        "snapshot_sha256": result.get("snapshot_sha256"),
        "research_package_sha256": package.get("sha256"),
        "missing_sha256": missing,
        "failures": failures,
    }


def restore_backup(root: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"restore destination already exists: {destination}")
    shutil.copytree(root / "backup", destination, copy_function=shutil.copy2)
    if _inventory(destination) != _inventory(root / "primary"):
        raise RuntimeError("restored inventory does not match primary")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--restore-to", type=Path)
    args = parser.parse_args(argv)
    report = verify_snapshot(args.root, args.evidence)
    if report["status"] == "PASS" and args.restore_to is not None:
        restore_backup(args.root, args.restore_to)
        report["restored_to"] = str(args.restore_to)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
