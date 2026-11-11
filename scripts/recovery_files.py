"""Snapshot-bound immutable file capture; no recursive .local backup or source repair."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from football.contracts.source import SHA256_PATTERN, validate_relative_posix_path
from football.integrity import _raw_relative_path
from football.providers.football_data_uk_evidence import FootballDataUkAcquisitionEvidenceV1
from psycopg import Connection, sql

from scripts.capture_architecture_v2_baseline import ROOT
from scripts.capture_architecture_v2_baseline import file_sha256 as digest_file


class RecoveryReferenceError(ValueError):
    """The snapshot's registered dependencies cannot describe one complete file set."""


@dataclass(frozen=True)
class FileReference:
    root: str
    path: str
    sha256: str | None
    size: int | None = None
    registrations: tuple[dict[str, Any], ...] = field(default=(), compare=False, hash=False)
    source_path: str | None = field(default=None, compare=False, hash=False)

    def __post_init__(self) -> None:
        if self.root not in ("data", "repository"):
            raise ValueError("unknown recovery root")
        validate_relative_posix_path(self.path)
        if self.source_path is not None:
            validate_relative_posix_path(self.source_path)
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
            raise RecoveryReferenceError(
                f"conflicting recovery registrations: {ref.root}/{ref.path}; "
                f"{previous.sha256} != {ref.sha256}"
            )
        if (
            previous
            and previous.size is not None
            and ref.size is not None
            and previous.size != ref.size
        ):
            raise RecoveryReferenceError("conflicting recovery sizes")
        if previous:
            ref = FileReference(
                ref.root,
                ref.path,
                ref.sha256 or previous.sha256,
                previous.size if ref.size is None else ref.size,
                (*previous.registrations, *ref.registrations),
                ref.source_path or previous.source_path,
            )
        result[key] = ref
    return [
        replace(
            ref,
            registrations=tuple(
                sorted(ref.registrations, key=lambda r: json.dumps(r, sort_keys=True))
            ),
        )
        for ref in sorted(result.values(), key=lambda ref: (ref.root, ref.path))
    ]


def capture_files(
    references: Iterable[FileReference], roots: Mapping[str, Path], archive: Path
) -> dict[str, Any]:
    refs = unique_references(references)
    archive.mkdir(parents=True, exist_ok=True, mode=0o700)
    report: dict[str, Any] = {"status": "INCOMPLETE", "files": [], "failures": []}
    for ref in refs:
        try:
            source = regular_file(
                roots["repository"] if ref.source_path is not None else roots[ref.root],
                ref.source_path if ref.source_path is not None else ref.path,
            )
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
                    "registered_checksum": _physical_checksum_registered(ref),
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


def _physical_checksum_registered(ref: FileReference) -> bool:
    if not ref.registrations:
        return ref.sha256 is not None
    return any(
        entry.get("checksum_kind") == "PHYSICAL" and entry.get("registered_sha256") == ref.sha256
        for entry in ref.registrations
    )


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


def _require_classified_columns(connection: Connection[Any]) -> None:
    known = {(table, columns[0]) for table, columns in FILE_COLUMNS.items()} | {
        ("source_snapshots", "manifest_path"),  # Provider contracts distinguish logical identities.
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
        raise RecoveryReferenceError(
            f"unclassified database file references: {sorted(actual - known)}"
        )


def _unresolved_reference(
    unresolved: list[dict[str, Any]] | None, registration: dict[str, Any], error: Exception
) -> None:
    if unresolved is None:
        raise error
    unresolved.append({**registration, "error": type(error).__name__, "reason": str(error)})


def _column_files(connection: Connection[Any]) -> list[FileReference]:
    references: list[FileReference] = []
    for table, (path, checksum, size) in FILE_COLUMNS.items():
        keys = connection.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
            "ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) "
            "WHERE i.indrelid=%s::regclass AND i.indisprimary ORDER BY a.attnum",
            ("football." + table,),
        ).fetchall()
        key_fields = sql.SQL(",").join(
            part for (name,) in keys for part in (sql.Literal(name), sql.Identifier(name))
        )
        query = sql.SQL("SELECT jsonb_build_object({}),{},{},{} FROM football.{}").format(
            key_fields,
            sql.Identifier(path),
            sql.Identifier(checksum),
            sql.Identifier(size) if size else sql.SQL("NULL"),
            sql.Identifier(table),
        )
        for identity, relative, digest, length in connection.execute(query):
            owner = {
                "table": table,
                "keys": identity,
                "column": path,
                "registered_sha256": digest,
                "checksum_kind": "PHYSICAL",
            }
            references.append(FileReference("data", relative, digest, length, (owner,)))
    return references


def _snapshot_files(
    connection: Connection[Any], data_root: Path, unresolved: list[dict[str, Any]] | None
) -> list[FileReference]:
    references = []
    for identity, provider, revision, path, digest in connection.execute(
        "SELECT s.id,p.code,s.source_revision,s.manifest_path,s.manifest_sha256 "
        "FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id"
    ):
        owner = {
            "table": "source_snapshots",
            "keys": {"id": str(identity)},
            "column": "manifest_path",
            "registered_sha256": digest,
        }
        try:
            ref = source_manifest_reference(data_root, provider, revision, path, digest)
            owner["checksum_kind"] = (
                "PATH_IDENTITY"
                if ref.sha256 is None
                else ("PHYSICAL" if ref.sha256 == digest else "LOGICAL_IDENTITY")
            )
            references.append(replace(ref, registrations=(owner,)))
        except (OSError, ValueError, KeyError, TypeError) as error:
            _unresolved_reference(
                unresolved,
                {"registration": owner, "path": path, "sha256": digest, "size": None},
                error,
            )
    return references


def registered_files(
    connection: Connection[Any],
    data_root: Path,
    *,
    unresolved: list[dict[str, Any]] | None = None,
    repository_root: Path = ROOT,
) -> list[FileReference]:
    _require_classified_columns(connection)
    references = _column_files(connection)
    references.extend(_snapshot_files(connection, data_root, unresolved))
    references.extend(source_files(connection, data_root, unresolved=unresolved))
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

        report = migration_report(repository_root)
        retained = retained_comparisons(repository_root, report)
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


def source_files(
    connection: Connection[Any],
    root: Path,
    *,
    unresolved: list[dict[str, Any]] | None = None,
) -> list[FileReference]:
    rows = connection.execute(
        """SELECT p.code,s.manifest_path,s.manifest_sha256,s.source_revision,s.git_sha,
                  r.provider_path,r.sha256,r.size_bytes,a.raw_path,r.id,s.id
           FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id
           JOIN football.source_resources r ON r.source_snapshot_id=s.id
           LEFT JOIN football.acquired_resources a ON a.source_resource_id=r.id
           ORDER BY s.id,r.id"""
    )
    manifests: dict[str, Any] = {}
    refs = []
    for row in rows:
        owner = {
            "table": "source_resources",
            "keys": {"id": str(row[9])},
            "source_snapshot_id": str(row[10]),
            "provider": row[0],
            "provider_path": row[5],
            "registered_sha256": row[6],
            "checksum_kind": "PHYSICAL",
        }
        try:
            ref = _source_reference(root, row[:9], manifests)
            refs.append(replace(ref, registrations=(owner,)))
        except (OSError, ValueError, KeyError, TypeError) as error:
            _unresolved_reference(
                unresolved, {"registration": owner, "sha256": row[6], "size": row[7]}, error
            )
    return refs


def _source_reference(root: Path, row: tuple[Any, ...], manifests: dict[str, Any]) -> FileReference:
    provider, manifest_path, manifest_hash, revision, git_sha, path, digest, size, acquired = row
    if acquired:
        return FileReference("data", acquired, digest, size)
    if revision.startswith("manifest-v1:") or provider == "statsbomb_open_data":
        return _manifest_resource(root, row, manifests)
    try:
        relative = legacy_source_path(provider, git_sha, path, manifest_path, manifest_hash, digest)
    except RecoveryReferenceError:
        raw_relative = _raw_relative_path(provider, revision, path, digest)
        if raw_relative is None:
            raise
        relative = raw_relative
    return FileReference("data", relative, digest, size)


def _manifest_resource(
    root: Path, row: tuple[Any, ...], manifests: dict[str, Any]
) -> FileReference:
    _, manifest_path, manifest_hash, _, _, path, digest, size, _ = row
    if manifest_path not in manifests:
        raw = regular_file(root, manifest_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest_hash:
            raise RecoveryReferenceError("source manifest checksum mismatch")
        manifest = json.loads(raw)
        entries = {r.get("provider_path", r.get("path")): r for r in manifest["resources"]}
        if len(entries) != len(manifest["resources"]):
            raise RecoveryReferenceError("source manifest resource paths are not unique")
        manifests[manifest_path] = entries
    try:
        entry = manifests[manifest_path][path]
    except KeyError as error:
        raise RecoveryReferenceError("source manifest lacks a registered resource") from error
    if entry["sha256"] != digest or entry["size_bytes"] != size:
        raise RecoveryReferenceError("source manifest registration mismatch")
    return FileReference("data", entry["raw_path"], digest, size)


def legacy_source_path(
    provider: str,
    git_sha: str | None,
    path: str,
    manifest_path: str,
    manifest_hash: str,
    resource_hash: str,
) -> str:
    if provider == "openfootball" and git_sha:
        return f"openfootball/{git_sha}/{path}"
    if manifest_hash in (resource_hash, hashlib.sha256(manifest_path.encode()).hexdigest()):
        return manifest_path  # Legacy location; the resource checksum still binds original bytes.
    raise RecoveryReferenceError("legacy source resource lacks a verified physical file locator")


def source_manifest_reference(
    root: Path, provider: str, revision: str, path: str, digest: str
) -> FileReference:
    if (
        not revision.startswith("manifest-v1:")
        and hashlib.sha256(path.encode()).hexdigest() == digest
    ):
        # HistoricalBackfillStore originally registered a pathname identity, not a byte hash.
        # Source resource registrations still bind the original payload hashes and sizes.
        return FileReference("data", path, None)
    receipt_path = (
        f"manifests/provider=football_data_uk/acquisition_sha256={digest}/"
        "acquisition-evidence-v1.json"
    )
    if provider == "football_data_uk" and path == receipt_path:
        raw = regular_file(root, path).read_bytes()
        evidence = FootballDataUkAcquisitionEvidenceV1.from_bytes(raw)
        if evidence.sha256 != digest or revision != digest:
            raise RecoveryReferenceError("acquisition receipt identity differs from registration")
        return FileReference("data", path, hashlib.sha256(raw).hexdigest(), len(raw))
    return FileReference("data", path, digest)
