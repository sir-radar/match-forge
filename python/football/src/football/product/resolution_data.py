"""Read-only registered-file diagnostics; case details retain full integrity checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from jsonschema import ValidationError
from psycopg import Connection

from football.integrity import PostgresIntegrityVerifier, verify_raw_resource_file
from football.product.domain import sha256_json
from football.product.historical_manifest import verify_manifest
from football.product.identity_admission import _retained_payload

RESOURCE_SELECT = """SELECT p.code,s.manifest_path,s.manifest_sha256,s.source_identity,
    s.source_revision,s.git_sha,r.id,r.provider_path,r.sha256,r.size_bytes,r.acquired_at,
    s.id,s.status,r.parse_status,r.validation_status
    FROM football.source_resources r JOIN football.source_snapshots s ON s.id=r.source_snapshot_id
    JOIN football.providers p ON p.id=s.provider_id"""


def resource_check(root: Path, row: tuple[Any, ...]) -> dict[str, Any]:
    raw = verify_raw_resource_file(root, row[6], row[0], row[4], row[7], row[8], row[9])
    if raw.status == "PASS":
        return {"status": "PASS", "path": raw.path, "reason": "EXACT_REGISTERED_BYTES"}
    try:
        payload = _retained_payload(root, row[0], row[1:11])
        if payload is not None:
            return {
                "status": "PASS",
                "path": resource_path(root, row),
                "reason": "EXACT_REGISTERED_BYTES",
            }
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        pass
    return {
        "status": "BLOCKED",
        "path": raw.path,
        "reason": "REGISTERED_BYTES_UNAVAILABLE_OR_CHECKSUM_MISMATCH",
    }


def resource_path(root: Path, row: tuple[Any, ...]) -> str:
    provider, manifest, _, identity, revision, git_sha, _, path = row[:8]
    if revision.startswith("manifest-v1:"):
        version = revision.removeprefix("manifest-v1:").rsplit(":", 1)[0]
        value, digest = verify_manifest(
            root, manifest, provider, identity, version, verify_resources=False
        )
        if digest != row[2]:
            raise ValueError("manifest checksum mismatch")
        entries = [entry for entry in value["resources"] if entry["provider_path"] == path]
        if len(entries) != 1:
            raise ValueError("source path is not unique in manifest")
        return str(entries[0]["raw_path"])
    return f"openfootball/{git_sha}/{path}" if provider == "openfootball" else str(manifest)


def data_detail(connection: Connection[Any], root: Path, case_key: str) -> dict[str, Any]:
    kind, identifier = case_key.split(":", 1)
    key = UUID(identifier)
    result: dict[str, Any]
    if kind == "resource":
        row = connection.execute(RESOURCE_SELECT + " WHERE r.id=%s", (key,)).fetchone()
        if row is None:
            raise ValueError("source resource not found")
        check = resource_check(root, row)
        registered = {
            "provider": row[0],
            "source_snapshot_id": str(row[11]),
            "resource_id": str(key),
            "provider_path": row[7],
            "sha256": row[8],
            "size_bytes": row[9],
            "manifest_path": row[1],
            "manifest_sha256": row[2],
            "source_identity": row[3],
            "source_revision": row[4],
            "acquired_at": row[10].isoformat(),
            "snapshot_status": row[12],
            "parse_status": row[13],
            "validation_status": row[14],
        }
        datasets = connection.execute(
            """SELECT id FROM football.dataset_versions WHERE source_snapshot_id=%s
               UNION SELECT dataset_version_id FROM football.dataset_inputs
               WHERE source_resource_id=%s ORDER BY id""",
            (row[11], key),
        ).fetchall()
        result = {
            "case_key": case_key,
            "registration": registered,
            "verification": check,
            "dependent_datasets": [str(item[0]) for item in datasets],
            "next_action": "Supply exact registered bytes or record an explicit disposition.",
        }
    elif kind == "dataset":
        result = dataset_detail(connection, root, key)
    else:
        raise ValueError("unsupported missing-data case")
    result["status"] = result["verification"]["status"]
    result["evidence_version"] = sha256_json(result)
    return result


def dataset_detail(connection: Connection[Any], root: Path, key: UUID) -> dict[str, Any]:
    row = connection.execute(
        "SELECT to_jsonb(d) FROM football.dataset_versions d WHERE id=%s", (key,)
    ).fetchone()
    if row is None:
        raise ValueError("dataset version not found")
    inputs = connection.execute(
        "SELECT to_jsonb(i) FROM football.dataset_inputs i WHERE dataset_version_id=%s "
        "ORDER BY source_resource_id",
        (key,),
    ).fetchall()
    check = PostgresIntegrityVerifier(connection, root).verify_dataset(key).to_dict()
    return {
        "case_key": f"dataset:{key}",
        "registration": row[0],
        "inputs": [i[0] for i in inputs],
        "verification": {**check, "status": "PASS" if check["status"] == "PASS" else "BLOCKED"},
        "next_action": "Recover original bytes and lineage; rebuilt outputs require a new "
        "immutable version. No automatic rebuild is permitted by this review.",
    }


def missing_page(connection: Connection[Any], root: Path, query: dict[str, Any]) -> dict[str, Any]:
    # Full registered inventory is checked; results are never inferred from an older report.
    items = []
    for row in connection.execute(RESOURCE_SELECT + " ORDER BY r.id").fetchall():
        check = resource_check(root, row)
        if check["status"] != "PASS":
            items.append(
                {
                    "case_key": f"resource:{row[6]}",
                    "kind": "resource",
                    "provider": row[0],
                    "status": "BLOCKED",
                    "reason": check["reason"],
                    "name": row[7],
                    "sha256": row[8],
                    "source_snapshot_id": str(row[11]),
                }
            )
    for (key,) in connection.execute("SELECT id FROM football.dataset_versions ORDER BY id"):
        dataset_check = next(
            (
                item
                for item in PostgresIntegrityVerifier(connection, root).dataset_file_checks(key)
                if item.status != "PASS"
            ),
            None,
        )
        if dataset_check is not None:
            items.append(
                {
                    "case_key": f"dataset:{key}",
                    "kind": "dataset",
                    "provider": "",
                    "name": str(key),
                    "verification_path": dataset_check.path,
                    "expected_sha256": dataset_check.expected_sha256,
                    "recorded_status": dataset_check.status,
                    "status": "BLOCKED",
                    "reason": dataset_check.failure_reason,
                }
            )
    filtered = [item for item in items if matches(item, query)]
    page, size = query.get("page", 1), query.get("page_size", 20)
    return {
        "items": filtered[(page - 1) * size : page * size],
        "page": page,
        "page_size": size,
        "total": len(filtered),
        "counts": {"BLOCKED": len(filtered)},
        "groups": [],
        "scope": "REGISTERED_FILE_BYTES; full logical dataset integrity is checked in case details",
    }


def matches(item: dict[str, Any], query: dict[str, Any]) -> bool:
    return all(
        not query.get(key) or item.get(key) == query[key] for key in ("provider", "status", "kind")
    ) and (str(query.get("q", "")).casefold() in str(item).casefold())
