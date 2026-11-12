"""Read-only audit of source snapshots whose manifest checksum is the digest of its path.

Before commit 55a7e35d, HistoricalBackfillStore.ensure_snapshot registered
``sha256(manifest_path)`` as the manifest checksum. For Football-Data.co.uk the registered
``manifest_path`` is the raw provider file itself. This audit binds each such snapshot to the
resource checksum and size already registered for that file and hashes the file on disk. It
opens the database with ``default_transaction_read_only=on`` and writes only the evidence JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection, sql

from scripts.recovery_files import regular_file

PROVIDER = "football_data_uk"
FIX_COMMIT = "55a7e35d0d4078092e5665d3a9f2772e65dbd360"
PATH_DIGEST = "encode(sha256(convert_to(s.manifest_path,'UTF8')),'hex')"
RESOURCE_BOUND = "RAW_FILE_PATH_DIGEST_RESOURCE_BOUND"
SIBLING_BOUND = "RAW_FILE_PATH_DIGEST_SIBLING_BOUND"


def _resources(connection: Connection[Any], snapshot_id: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row[0]),
            "provider_path": row[1],
            "sha256": row[2],
            "size_bytes": row[3],
            "media_type": row[4],
            "acquired_raw_path": row[5],
        }
        for row in connection.execute(
            "SELECT r.id,r.provider_path,r.sha256,r.size_bytes,r.media_type,a.raw_path "
            "FROM football.source_resources r "
            "LEFT JOIN football.acquired_resources a ON a.source_resource_id=r.id "
            "WHERE r.source_snapshot_id=%s ORDER BY r.id",
            (snapshot_id,),
        )
    ]


def _file(data_root: Path, relative: str) -> dict[str, Any]:
    try:
        path = regular_file(data_root, relative)
    except (OSError, ValueError) as error:
        return {"present": False, "error": type(error).__name__}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"present": True, "sha256": digest.hexdigest(), "size_bytes": path.stat().st_size}


def _consumers(connection: Connection[Any], table: str, ids: list[str]) -> dict[str, int]:
    """Count rows in every table with a foreign key to ``table`` that reference ``ids``."""
    counts: dict[str, int] = {}
    references = connection.execute(
        "SELECT DISTINCT n.nspname, r.relname, a.attname FROM pg_constraint c "
        "JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace "
        "CROSS JOIN LATERAL unnest(c.conkey, c.confkey) AS k(local_attnum, foreign_attnum) "
        "JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.local_attnum "
        "JOIN pg_attribute f ON f.attrelid=c.confrelid AND f.attnum=k.foreign_attnum "
        "WHERE c.contype='f' AND c.confrelid=%s::regclass AND f.attname='id' ORDER BY 1,2,3",
        ("football." + table,),
    ).fetchall()
    for schema, name, column in references:
        query = sql.SQL("SELECT count(*) FROM {}.{} WHERE {} = ANY(%s::uuid[])").format(
            sql.Identifier(schema), sql.Identifier(name), sql.Identifier(column)
        )
        row = connection.execute(query, (ids,)).fetchone()
        if row and row[0]:
            counts[f"{name}.{column}"] = int(row[0])
    return counts


def audit(connection: Connection[Any], data_root: Path) -> dict[str, Any]:
    if connection.execute("SHOW default_transaction_read_only").fetchone() != ("on",):
        raise RuntimeError("audit requires a read-only session")
    affected = connection.execute(
        "SELECT p.code,count(*) FROM football.source_snapshots s "
        "JOIN football.providers p ON p.id=s.provider_id "
        f"WHERE s.manifest_sha256={PATH_DIGEST} GROUP BY 1 ORDER BY 1"
    ).fetchall()
    provider_totals = connection.execute(
        "SELECT count(*),count(*) FILTER (WHERE s.source_revision LIKE 'manifest-v1:%%'),"
        "min(s.created_at) FILTER (WHERE s.source_revision LIKE 'manifest-v1:%%') "
        "FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id "
        "WHERE p.code=%s",
        (PROVIDER,),
    ).fetchone()
    assert provider_totals is not None
    rows = connection.execute(
        "SELECT s.id,s.source_identity,s.source_revision,s.repository,s.git_sha,s.manifest_path,"
        "s.manifest_sha256,s.status,s.source_kind,s.acquired_at,s.created_at "
        "FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id "
        f"WHERE p.code=%s AND s.manifest_sha256={PATH_DIGEST} ORDER BY s.created_at,s.id",
        (PROVIDER,),
    ).fetchall()
    findings = []
    for row in rows:
        identity, source, revision, repository, git_sha, path, digest = row[:7]
        resources = _resources(connection, identity)
        sibling = None
        if not resources:
            siblings = connection.execute(
                "SELECT s.id,s.source_identity FROM football.source_snapshots s "
                "JOIN football.providers p ON p.id=s.provider_id "
                "WHERE p.code=%s AND s.id<>%s AND s.manifest_path=%s AND s.source_revision=%s "
                "AND EXISTS (SELECT 1 FROM football.source_resources r "
                "WHERE r.source_snapshot_id=s.id) ORDER BY s.id",
                (PROVIDER, identity, path, revision),
            ).fetchall()
            if len(siblings) == 1:
                sibling = {
                    "source_snapshot_id": str(siblings[0][0]),
                    "source_identity": siblings[0][1],
                    "resources": _resources(connection, siblings[0][0]),
                }
        bound = resources if resources else (sibling or {}).get("resources", [])
        on_disk = _file(data_root, path)
        binding = bound[0] if len(bound) == 1 else None
        verified = (
            binding is not None
            and on_disk.get("sha256") == binding["sha256"]
            and on_disk.get("size_bytes") == binding["size_bytes"]
            and revision == binding["sha256"]
            and Path(path).stem == binding["sha256"]
        )
        findings.append(
            {
                "classification": (
                    (RESOURCE_BOUND if resources else SIBLING_BOUND) if verified else "UNVERIFIED"
                ),
                "table": "source_snapshots",
                "keys": {"id": str(identity)},
                "source_identity": source,
                "source_revision": revision,
                "repository": repository,
                "git_sha": git_sha,
                "path": path,
                "registered_sha256": digest,
                "path_digest_verified": hashlib.sha256(path.encode()).hexdigest() == digest,
                "status": row[7],
                "source_kind": row[8],
                "acquired_at": row[9].isoformat(),
                "created_at": row[10].isoformat(),
                "resources": resources,
                "sibling": sibling,
                "bound_resource": binding,
                "file": on_disk,
            }
        )
    ids = [item["keys"]["id"] for item in findings]
    resource_ids = [
        resource["id"] for item in findings for resource in item["resources"]
    ]
    created = [item["created_at"] for item in findings]
    migration = connection.execute("SELECT max(version_id) FROM goose_db_version").fetchone()
    return {
        "observed_at": "2026-11-12",
        "phase": "Stage F recovery remediation, Football-Data.co.uk manifest path digests",
        "scope": "read-only (default_transaction_read_only=on); no registration, file or backup "
        "changed",
        "database_migration_version": migration[0] if migration else None,
        "data_root": "<repo>/.local/football-data",
        "defect": {
            "writer": "HistoricalBackfillStore.ensure_snapshot",
            "registered": "manifest_sha256 = sha256(manifest_path UTF-8 bytes)",
            "fixed_by_commit": FIX_COMMIT,
            "fixed_registration": "source_revision manifest-v1:<revision>:<manifest bytes sha256>",
        },
        "path_digest_snapshots_by_provider": {code: count for code, count in affected},
        "provider_snapshots": int(provider_totals[0]),
        "provider_manifest_v1_snapshots": int(provider_totals[1]),
        "provider_first_manifest_v1_created_at": (
            provider_totals[2].isoformat() if provider_totals[2] else None
        ),
        "registrations": len(findings),
        "created_at_range": [min(created), max(created)] if created else None,
        "classification_counts": dict(
            sorted(Counter(item["classification"] for item in findings).items())
        ),
        "excluded": {
            "openfootball": "1 path-digest snapshot is a never-written catalog with no file to "
            "bind; it is the MANIFEST_NEVER_WRITTEN_PATH_DIGEST correction in "
            "docs/evidence/storage-recovery-gaps-2026-11-12.json"
        },
        "consumers": {
            "source_snapshots": _consumers(connection, "source_snapshots", ids),
            "source_resources": _consumers(connection, "source_resources", resource_ids),
        },
        "backup_dependency": "none: scripts/recovery_files.py source_manifest_reference and "
        "legacy_source_path already resolve every path to the raw file bound by its resource "
        "checksum",
        "registrations_modified": 0,
        "fabricated_values": 0,
        "findings": findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with psycopg.connect(
        os.environ["DATABASE_URL"], options="-c default_transaction_read_only=on"
    ) as connection:
        evidence = audit(connection, args.data_root)
    args.output.write_text(json.dumps(evidence, indent=1, sort_keys=False) + "\n")
    print(
        json.dumps(
            {
                "registrations": evidence["registrations"],
                "classification_counts": evidence["classification_counts"],
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
