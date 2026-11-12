"""Read-only, resource-specific review manifest; never a cleanup executor."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


def digest_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def resolve_audit_path(value: str, root: Path) -> Path:
    return Path(value.replace("<repo>", str(root)))


def file_observation(path: Path, expected: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"location": str(path), "present": False}
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            return {**record, "blockers": ["not a regular non-symlink file"]}
        digest = digest_file(path)
        after = path.stat()
        stable = (before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        return {
            **record,
            "present": True,
            "logical_bytes": after.st_size,
            "allocated_file_bytes": after.st_blocks * 512,
            "sha256": digest,
            "device": after.st_dev,
            "inode": after.st_ino,
            "stable": stable,
            "matches_audit": digest == expected if expected else None,
            "blockers": []
            if stable and (expected is None or digest == expected)
            else ["changed since audit or during read"],
        }
    except OSError as error:
        return {**record, "blockers": [type(error).__name__]}


def database_manifest(url: str, audit: Path) -> list[dict[str, Any]]:
    audited = {}
    for line in (audit / "postgres-cluster.txt").read_text().splitlines():
        parts = line.split("|")
        if len(parts) == 5 and parts[0].isdigit() and parts[1].startswith("football_"):
            audited[parts[1]] = {"oid": int(parts[0]), "bytes": int(parts[3])}
    with psycopg.connect(
        url,
        connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
        row_factory=dict_row,
    ) as connection:
        rows = connection.execute("""
            SELECT d.datname, d.oid::bigint AS oid, pg_database_size(d.oid) AS bytes,
                   (SELECT count(*) FROM pg_stat_activity a WHERE a.datid=d.oid) AS connections,
                   (SELECT system_identifier::text FROM pg_control_system()) AS cluster
            FROM pg_database d WHERE NOT d.datistemplate ORDER BY d.datname
        """).fetchall()
        operating = connection.info.dbname
    current = {row["datname"]: row for row in rows}
    names = sorted(set(audited) | {name for name in current if name.startswith("football_")})
    result = []
    for name in names:
        row = current.get(name)
        result.append(
            {
                "kind": "database",
                "location": name,
                "audit": audited.get(name),
                "current": row,
                "operating": name == operating,
                "state": "PROTECTED",
                "approval": "NOT_REQUESTED",
                "expected_physical_reclaimed_bytes": None,
                "potential_database_bytes": row["bytes"] if row else 0,
                "backup_coverage": "UNVERIFIED_POST_REHEARSAL_STATE",
                "blockers": [
                    "unique post-restore changes not covered by source dump",
                    "current independent dump and verified restore required",
                    "dependency and active-owner release required",
                    "explicit owner approval required",
                ],
                "rollback": (
                    "Restore a verified current-state dump into a new isolated database; "
                    "verify all relations, lineage and readers before repointing any consumer."
                ),
            }
        )
    return result


def duplicate_manifest(
    audit: Path, root: Path, scratch: Path | None = None
) -> list[dict[str, Any]]:
    groups = []
    if scratch is not None:
        source_rows = json.loads((scratch / "dedupe.json").read_text())["groups"]
    else:
        with (audit / "exact-duplicates.tsv").open() as source:
            source_rows = list(csv.DictReader(source, delimiter="\t"))
    for row in source_rows:
        paths = row["paths"].split(" | ") if isinstance(row["paths"], str) else row["paths"]
        copies = [file_observation(resolve_audit_path(p, root), row["sha256"]) for p in paths]
        valid = all(p.get("matches_audit") and p.get("stable") for p in copies)
        groups.append(
            {
                "kind": "duplicate_group",
                "sha256": row["sha256"],
                "copies": copies,
                "byte_redundancy_verified": valid,
                "audit_physical_estimate_bytes": int(row["est_recoverable_physical_bytes"]),
                "expected_physical_reclaimed_bytes": None,
                "state": "REVIEW_REQUIRED",
                "approval": "NOT_REQUESTED",
                "blockers": [
                    "path consumers and last-good-copy retention require review",
                    "independent restore coverage and explicit owner approval required",
                ],
                "rollback": (
                    "Restore exact original pathname and SHA-256 bytes from "
                    "an independently verified retained copy; do not rewrite registrations."
                ),
            }
        )
    return groups


def git_output(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True)


def worktree_manifest(root: Path) -> list[dict[str, Any]]:
    result = []
    for block in git_output(root, "worktree", "list", "--porcelain").strip().split("\n\n"):
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        path = Path(fields["worktree"])
        status = git_output(path, "status", "--porcelain", "--untracked-files=all")
        ignored = git_output(
            path, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory"
        )
        ahead = int(git_output(path, "rev-list", "--count", "origin/main..HEAD").strip())
        result.append(
            {
                "kind": "worktree",
                **fields,
                "status": status.splitlines(),
                "ignored_paths": ignored.splitlines(),
                "commits_not_in_main": ahead,
                "state": "PROTECTED",
                "approval": "NOT_REQUESTED",
                "expected_physical_reclaimed_bytes": None,
                "blockers": [
                    "unique ignored files and evidence require retention proof",
                    "active processes and branch dependencies require owner release",
                    "explicit resource-specific approval required",
                ],
                "rollback": (
                    "Recreate the worktree at its recorded commit and "
                    "restore all unique ignored/untracked files from verified retention."
                ),
            }
        )
    return result


def evidence_manifest(audit: Path, root: Path, scratch: Path | None = None) -> list[dict[str, Any]]:
    with (audit / "local-directories.tsv").open() as source:
        directories = [
            {
                "kind": "directory",
                **row,
                "location": str(resolve_audit_path(row["path"], root)),
                "measurement": "DATED_AUDIT_NOT_CURRENT",
                "state": "PROTECTED",
                "expected_physical_reclaimed_bytes": None,
                "approval": "NOT_REQUESTED",
                "blockers": ["directory contains potentially unique evidence; no blanket TTL"],
                "rollback": (
                    "Recover the exact directory tree and "
                    "metadata from a verified retained manifest."
                ),
            }
            for row in csv.DictReader(source, delimiter="\t")
        ]
    with (audit / "top50-files.tsv").open() as source:
        dumps = [
            resolve_audit_path(row["path"], root)
            for row in csv.DictReader(source, delimiter="\t")
            if row["path"].endswith((".dump", ".sql"))
        ]
    backup_root = root / ".local/backups"
    dumps.extend(p for p in backup_root.glob("*") if p.suffix in (".dump", ".sql"))
    if scratch is not None:
        for name in ("walk_repo.json", "walk_tmp.json"):
            data = json.loads((scratch / name).read_text())
            dumps.extend(
                Path(row[-1]) for row in data["big_files"] if row[-1].endswith((".dump", ".sql"))
            )
    return directories + [
        {
            "kind": "dump",
            **file_observation(path),
            "state": "PROTECTED",
            "approval": "NOT_REQUESTED",
            "expected_physical_reclaimed_bytes": None,
            "blockers": [
                "historical point may contain unique originals",
                "per-point verified independent restore required",
            ],
            "rollback": (
                "Retrieve exact dump SHA-256 and companion manifests from "
                "its verified encrypted snapshot; rehearse in an isolated database."
            ),
        }
        for path in sorted(set(dumps))
    ]


def references(root: Path, databases: list[dict[str, Any]]) -> None:
    # One bounded tracked-source traversal, rather than a recursive historical walk per DB.
    names = [r["location"] for r in databases]
    args = ["git", "-C", str(root), "grep", "-n", "-F"]
    for name in names:
        args += ["-e", name]
    found = subprocess.run(
        args + ["--", "docs", "scripts", "tests", "python", "go"],
        text=True,
        capture_output=True,
        check=False,
    )
    if found.returncode not in (0, 1):
        raise RuntimeError("tracked consumer search failed")
    for resource in databases:
        resource["tracked_references"] = [
            line.split(":", 2)[:2]
            for line in found.stdout.splitlines()
            if resource["location"] in line
        ]
        resource["reference_scope"] = (
            "current checkout tracked files; ignored evidence also requires owner review"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--audit-commit", required=True, help="Git revision of the supplied audit")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-scratch", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    databases = database_manifest(os.environ["DATABASE_URL"], args.audit_root)
    references(root, databases)
    manifest: dict[str, Any] = {
        "observed_at": datetime.now(UTC).isoformat(),
        "destructive_cleanup_enabled": False,
        "audit_commit": args.audit_commit,
        "database_resources": databases,
        "worktrees": worktree_manifest(root),
        "evidence_resources": evidence_manifest(args.audit_root, root, args.audit_scratch),
        "duplicate_groups": duplicate_manifest(args.audit_root, root, args.audit_scratch),
        "accounting": (
            "Nested directory/file/database/volume categories overlap. Never sum them. "
            "Allocated bytes do not prove unique APFS extents."
        ),
        "actual_physical_reclaimed_bytes": 0,
    }
    with args.output.open("x") as destination:
        json.dump(manifest, destination, indent=2)
        destination.write("\n")
    print(
        json.dumps(
            {
                "manifest": str(args.output),
                "sha256": digest_file(args.output),
                "databases": len(databases),
                "audited_databases": sum(r["audit"] is not None for r in databases),
                "duplicate_groups": len(manifest["duplicate_groups"]),
                "physical_reclaimed_bytes": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
