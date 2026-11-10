"""Snapshot-bound immutable file capture; no recursive .local backup or source repair."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from football.contracts.source import SHA256_PATTERN, validate_relative_posix_path
from psycopg import Connection, sql

from scripts.capture_architecture_v2_baseline import ROOT
from scripts.capture_architecture_v2_baseline import file_sha256 as digest_file


@dataclass(frozen=True)
class FileReference:
    root: str
    path: str
    sha256: str | None
    size: int | None = None

    def __post_init__(self) -> None:
        if self.root not in ("data", "repository"):
            raise ValueError("unknown recovery root")
        validate_relative_posix_path(self.path)
        if self.sha256 is not None and not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("invalid registered checksum")


def regular_file(root: Path, relative: str) -> Path:
    validate_relative_posix_path(relative)
    current = root
    if current.is_symlink():
        raise ValueError("symlink recovery root")
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("symlink recovery dependency")
    current.resolve().relative_to(root.resolve())
    if not stat.S_ISREG(current.stat().st_mode):
        raise ValueError("recovery dependency is not a regular file")
    return current


def unique_references(references: Iterable[FileReference]) -> list[FileReference]:
    result: dict[tuple[str, str], FileReference] = {}
    for ref in references:
        key = ref.root, ref.path
        previous = result.get(key)
        if previous and previous.sha256 and ref.sha256 and previous.sha256 != ref.sha256:
            raise ValueError("conflicting recovery registrations")
        if (
            previous
            and previous.size is not None
            and ref.size is not None
            and previous.size != ref.size
        ):
            raise ValueError("conflicting recovery sizes")
        if previous is None or ref.sha256 is not None:
            result[key] = ref
    return sorted(result.values(), key=lambda ref: (ref.root, ref.path))


def capture_files(
    references: Iterable[FileReference], roots: Mapping[str, Path], archive: Path
) -> dict[str, Any]:
    refs = unique_references(references)
    archive.mkdir(parents=True, exist_ok=True, mode=0o700)
    report: dict[str, Any] = {"status": "INCOMPLETE", "files": [], "failures": []}
    for ref in refs:
        try:
            source = regular_file(roots[ref.root], ref.path)
            target = archive / "files" / ref.root / ref.path
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            before = source.stat()
            with source.open("rb") as src, target.open("xb") as dest:
                shutil.copyfileobj(src, dest, 1024 * 1024)
                dest.flush()
                os.fsync(dest.fileno())
            actual = digest_file(target)
            if ref.sha256 is not None and actual != ref.sha256:
                raise ValueError("registered checksum mismatch")
            if ref.size is not None and target.stat().st_size != ref.size:
                raise ValueError("registered size mismatch")
            after = source.stat()
            if (after.st_size, after.st_mtime_ns, after.st_ino) != (
                before.st_size,
                before.st_mtime_ns,
                before.st_ino,
            ):
                raise ValueError("source changed during capture")
            shutil.copystat(source, target, follow_symlinks=False)
            report["files"].append(
                {
                    **asdict(ref),
                    "sha256": actual,
                    "size": target.stat().st_size,
                    "mtime_ns": before.st_mtime_ns,
                    "registered_checksum": ref.sha256 is not None,
                }
            )
        except (OSError, ValueError) as error:
            report["failures"].append({**asdict(ref), "error": type(error).__name__})
    report["status"] = "INCOMPLETE" if report["failures"] else "COMPLETE"
    report["logical_bytes"] = sum(item["size"] for item in report["files"])
    with (archive / "recovery-files.json").open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return report


def verify_files(archive: Path) -> list[str]:
    report = json.loads(regular_file(archive, "recovery-files.json").read_text())
    if report["status"] != "COMPLETE" or report["failures"]:
        return ["incomplete recovery file closure"]
    failures = []
    for item in report["files"]:
        ref = FileReference(item["root"], item["path"], item["sha256"], item["size"])
        try:
            path = regular_file(archive, f"files/{ref.root}/{ref.path}")
            if path.stat().st_size != ref.size or digest_file(path) != ref.sha256:
                failures.append(ref.path)
        except (OSError, ValueError):
            failures.append(ref.path)
    return failures


def restore_files(archive: Path, roots: Mapping[str, Path]) -> None:
    failures = verify_files(archive)
    if failures:
        raise ValueError("incomplete or failed file verification")
    for root in roots.values():
        if root.is_symlink() or (root.exists() and any(root.iterdir())):
            raise ValueError("restore requires new empty roots")
    report = json.loads((archive / "recovery-files.json").read_text())
    for item in report["files"]:
        target = roots[item["root"]] / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (
            target.open("xb") as dest,
            regular_file(archive, f"files/{item['root']}/{item['path']}").open("rb") as src,
        ):
            shutil.copyfileobj(src, dest, 1024 * 1024)
        os.utime(target, ns=(item["mtime_ns"], item["mtime_ns"]))
        if digest_file(target) != item["sha256"]:
            raise ValueError("restored file verification failed")


# SQL migrations and current readers define these physical dependencies. Inline
# DB payloads, provider-native keys and validation JSON pointers are not files.
FILE_COLUMNS = {
    "source_snapshots": ("manifest_path", "manifest_sha256", None),
    "acquired_resources": ("raw_path", "raw_sha256", "size_bytes"),
    "dataset_versions": ("manifest_path", "manifest_sha256", None),
    "dataset_files": ("relative_path", "physical_sha256", "size_bytes"),
    "model_artifacts": ("manifest_path", "manifest_sha256", None),
    "model_artifact_files": ("relative_path", "physical_sha256", "size_bytes"),
    "baseline_forecasts": ("payload_path", "payload_sha256", None),
    "sprint2_evaluation_runs": ("report_path", "report_sha256", None),
    "resource_observation_artifacts": ("artifact_path", "artifact_sha256", None),
    "canonical_resource_resolutions": ("artifact_path", "artifact_sha256", None),
    "provider_resource_capabilities": ("artifact_path", "artifact_sha256", None),
    "provider_resource_authority": ("artifact_path", "artifact_sha256", None),
    "provider_resource_coverage": ("artifact_path", "artifact_sha256", None),
    "canonical_resource_coverage": ("artifact_path", "artifact_sha256", None),
}


def registered_files(connection: Connection[Any], data_root: Path) -> list[FileReference]:
    known = {(table, columns[0]) for table, columns in FILE_COLUMNS.items()} | {
        ("source_resources", "provider_path"),  # Provider key, resolved from its source manifest.
        ("validation_findings", "field_path"),  # JSON pointer, not a filesystem dependency.
        ("product_history_sync_attempts", "last_resolution_path"),  # Inline decision history.
        ("product_sync_runs", "log_path"),  # Diagnostic stream; authoritative state is in the DB.
        ("product_model_evaluations", "report_uri"),
    }
    actual = set(
        connection.execute(
            "SELECT c.table_name,c.column_name FROM information_schema.columns c "
            "JOIN information_schema.tables t USING(table_catalog,table_schema,table_name) "
            "WHERE c.table_schema='football' AND t.table_type='BASE TABLE' AND "
            "(column_name LIKE %s OR column_name LIKE %s)",
            ("%\\_path", "%\\_uri"),
        ).fetchall()
    )
    if actual - known:
        raise ValueError(f"unclassified database file references: {sorted(actual - known)}")
    references: list[FileReference] = []
    for table, (path, checksum, size) in FILE_COLUMNS.items():
        query = sql.SQL("SELECT {},{},{} FROM football.{}").format(
            sql.Identifier(path),
            sql.Identifier(checksum),
            sql.Identifier(size) if size else sql.SQL("NULL"),
            sql.Identifier(table),
        )
        references.extend(FileReference("data", *row) for row in connection.execute(query))
    references.extend(source_files(connection, data_root))
    for (payload,) in connection.execute(
        "SELECT record_bytes FROM football.runtime_model_registrations"
    ):
        entry = json.loads(bytes(payload))
        references.append(
            FileReference("repository", entry["artifact_uri"], entry["artifact_hash"])
        )
        for path in (*entry["evaluation_refs"], *entry["calibrator_refs"]):
            references.append(FileReference("repository", path, None))
    for (path,) in connection.execute(
        "SELECT report_uri FROM football.product_model_evaluations WHERE report_uri IS NOT NULL"
    ):
        references.append(FileReference("data", path, None))
    for (plan,) in connection.execute(
        "SELECT f.plan FROM football.resolution_file_recovery_work f "
        "JOIN football.work_items w USING(work_id) "
        "WHERE w.state IN ('PENDING','RUNNING','RETRY_WAIT')"
    ):
        references.append(
            FileReference("data", plan["recovery_path"], plan["sha256"], plan["size_bytes"])
        )
    parity = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM football.resolution_parity_work)"
    ).fetchone()
    if parity and parity[0]:
        from football.product.resolution_migration import migration_report
        from football.product.resolution_parity import retained_comparisons

        report = migration_report(ROOT)
        retained = retained_comparisons(ROOT, report)
        references.extend(
            FileReference(
                "repository",
                item["source_ref"],
                item["expected_sha256"],
                item.get("expected_bytes"),
            )
            for item in retained["checks"]
        )
    return unique_references(references)


def source_files(connection: Connection[Any], root: Path) -> list[FileReference]:
    rows = connection.execute(
        """SELECT p.code,s.manifest_path,s.manifest_sha256,s.source_revision,s.git_sha,
                  r.provider_path,r.sha256,r.size_bytes
           FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id
           JOIN football.source_resources r ON r.source_snapshot_id=s.id ORDER BY s.id,r.id"""
    )
    manifests: dict[str, Any] = {}
    refs = []
    for provider, manifest_path, manifest_hash, revision, git_sha, path, digest, size in rows:
        if revision.startswith("manifest-v1:") or provider == "statsbomb_open_data":
            if manifest_path not in manifests:
                raw = regular_file(root, manifest_path).read_bytes()
                if hashlib.sha256(raw).hexdigest() != manifest_hash:
                    raise ValueError("source manifest checksum mismatch")
                manifest = json.loads(raw)
                manifests[manifest_path] = {
                    r.get("provider_path", r.get("path")): r for r in manifest["resources"]
                }
            entry = manifests[manifest_path][path]
            if entry["sha256"] != digest or entry["size_bytes"] != size:
                raise ValueError("source manifest registration mismatch")
            relative = entry["raw_path"]
        else:
            relative = (
                f"openfootball/{git_sha}/{path}" if provider == "openfootball" else manifest_path
            )
        refs.append(FileReference("data", relative, digest, size))
    return refs
