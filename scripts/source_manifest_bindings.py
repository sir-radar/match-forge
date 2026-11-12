"""Record owner-approved raw-file bindings for path-digest source manifests.

Each binding is append-only and evidence-bound. It names the registered source resource whose
checksum and size already prove the bytes at a legacy snapshot's ``manifest_path``. Nothing
here edits a snapshot, writes a file or supplies a checksum: the database rejects a binding
whose path, checksums, size or resource lineage differ from the registrations it names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.errors import CheckViolation, ForeignKeyViolation

from scripts.capture_architecture_v2_baseline import ROOT
from scripts.recovery_dispositions import Approval
from scripts.recovery_files import regular_file

# Immutable read-only export of the 47 Football-Data.co.uk path-digest snapshots.
APPROVED_EVIDENCE = (
    "docs/evidence/fduk-manifest-path-digests-2026-11-12.json",
    "e912287d773cdad3ff2098a3fdd88a68d1184db5395a5cdc6c3ac1085f197da2",
)
BOUND_CLASSIFICATIONS = frozenset(
    {"RAW_FILE_PATH_DIGEST_RESOURCE_BOUND", "RAW_FILE_PATH_DIGEST_SIBLING_BOUND"}
)


class SourceManifestBindingError(ValueError):
    """A binding conflicts with its evidence, its registrations or recorded history."""


@dataclass(frozen=True)
class Binding:
    source_snapshot_id: str
    path: str
    source_resource_id: str
    resource_sha256: str
    resource_size_bytes: int
    evidence_reference: str
    evidence_sha256: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.path.encode()).hexdigest()


def evidence_bindings(raw: bytes, reference: str, expected_sha256: str) -> tuple[Binding, ...]:
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise SourceManifestBindingError("binding evidence checksum differs from approval")
    evidence = json.loads(raw)
    findings = evidence["findings"]
    if (
        evidence["registrations"] != len(findings)
        or evidence["registrations_modified"] != 0
        or evidence["fabricated_values"] != 0
    ):
        raise SourceManifestBindingError("binding evidence is not a read-only export")
    bindings = []
    for finding in findings:
        resource = finding["bound_resource"]
        on_disk = finding["file"]
        if (
            finding["classification"] not in BOUND_CLASSIFICATIONS
            or finding["table"] != "source_snapshots"
            or finding["registered_sha256"] != hashlib.sha256(finding["path"].encode()).hexdigest()
            or resource is None
            or on_disk.get("sha256") != resource["sha256"]
            or on_disk.get("size_bytes") != resource["size_bytes"]
        ):
            raise SourceManifestBindingError(
                "path-digest snapshot has no verified raw-file binding"
            )
        bindings.append(
            Binding(
                str(finding["keys"]["id"]),
                finding["path"],
                resource["id"],
                resource["sha256"],
                int(resource["size_bytes"]),
                reference,
                expected_sha256,
            )
        )
    if len({item.source_snapshot_id for item in bindings}) != len(bindings):
        raise SourceManifestBindingError("binding evidence repeats a snapshot")
    return tuple(bindings)


def approved_bindings() -> tuple[Binding, ...]:
    reference, digest = APPROVED_EVIDENCE
    return evidence_bindings(regular_file(ROOT, reference).read_bytes(), reference, digest)


_INSERT = (
    "INSERT INTO football.source_manifest_raw_file_bindings(source_snapshot_id,binding,"
    "registered_path,registered_sha256,source_resource_id,resource_sha256,resource_size_bytes,"
    "evidence_reference,evidence_sha256,decision_reference,recorded_at,code_commit_sha) "
    "VALUES (%s,'MANIFEST_PATH_IS_RAW_RESOURCE',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON CONFLICT (source_snapshot_id) DO NOTHING"
)
_SELECT = (
    "SELECT registered_path,registered_sha256,source_resource_id,resource_sha256,"
    "resource_size_bytes,evidence_reference,evidence_sha256,decision_reference,code_commit_sha "
    "FROM football.source_manifest_raw_file_bindings WHERE source_snapshot_id=%s"
)


def record_bindings(
    connection: Connection[Any], bindings: tuple[Binding, ...], approval: Approval
) -> dict[str, int]:
    """Insert every binding in one transaction, or verify an identical earlier one."""
    counts = {"inserted": 0, "verified_existing": 0}
    try:
        with connection.transaction(), connection.cursor() as cursor:
            for item in bindings:
                bound = (
                    item.path,
                    item.sha256,
                    item.source_resource_id,
                    item.resource_sha256,
                    item.resource_size_bytes,
                    item.evidence_reference,
                    item.evidence_sha256,
                )
                inserted = cursor.execute(
                    _INSERT,
                    (
                        item.source_snapshot_id,
                        *bound,
                        approval.decision_reference,
                        approval.recorded_at,
                        approval.code_commit_sha,
                    ),
                ).rowcount
                counts["inserted" if inserted == 1 else "verified_existing"] += 1
                row = cursor.execute(_SELECT, (item.source_snapshot_id,)).fetchone()
                expected = (*bound, approval.decision_reference, approval.code_commit_sha)
                if row is None or tuple(map(str, row)) != tuple(map(str, expected)):
                    raise SourceManifestBindingError(
                        "source manifest binding conflicts with immutable history"
                    )
    except (CheckViolation, ForeignKeyViolation) as error:
        raise SourceManifestBindingError(str(error).splitlines()[0]) from error
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-reference", required=True)
    parser.add_argument("--code-commit-sha", required=True)
    parser.add_argument(
        "--apply", action="store_true", help="write to DATABASE_URL; without it only validate"
    )
    args = parser.parse_args()
    bindings = approved_bindings()
    summary: dict[str, Any] = {"bindings": len(bindings), "applied": args.apply}
    if args.apply:
        approval = Approval(args.decision_reference, datetime.now(UTC), args.code_commit_sha)
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            summary |= record_bindings(connection, bindings, approval)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
