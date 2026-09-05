from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection

from football.contracts.integrity import IntegrityCheckStatusV1, IntegrityVerificationReportV1
from football.contracts.source import (
    SHA256_PATTERN,
    canonical_json_bytes,
    validate_relative_posix_path,
)
from football.normalization.statsbomb_events import logical_sha256
from football.storage.parquet import ImmutableEventParquetStore, ParquetPublicationError

IntegrityArtifactKind = Literal["RAW_RESOURCE", "DATASET", "MODEL_ARTIFACT"]
IntegrityItemStatus = Literal[
    "PASS",
    "NOT_FOUND",
    "MISSING",
    "UNREADABLE",
    "CHECKSUM_MISMATCH",
    "INVALID_REGISTRATION",
]


@dataclass(frozen=True, slots=True)
class IntegrityFileVerification:
    path: str
    expected_sha256: str | None
    actual_sha256: str | None
    status: IntegrityItemStatus
    failure_reason: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "path": self.path,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "status": self.status,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True, slots=True)
class IntegrityVerificationResult:
    artifact_kind: IntegrityArtifactKind
    artifact_id: UUID
    path: str | None
    expected_sha256: str | None
    actual_sha256: str | None
    status: IntegrityItemStatus
    failure_reason: str | None
    files: tuple[IntegrityFileVerification, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_kind": self.artifact_kind,
            "artifact_id": str(self.artifact_id),
            "path": self.path,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "files": [item.to_dict() for item in self.files],
        }


class PostgresIntegrityVerifier:
    """Read-only verification of registered immutable files."""

    def __init__(self, connection: Connection[Any], data_root: Path) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()

    def verify_raw_resource(self, resource_id: UUID) -> IntegrityVerificationResult:
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT provider.code, snapshot.source_revision, resource.provider_path,
                       resource.sha256, resource.size_bytes
                FROM football.source_resources AS resource
                JOIN football.source_snapshots AS snapshot
                  ON snapshot.id = resource.source_snapshot_id
                JOIN football.providers AS provider ON provider.id = snapshot.provider_id
                WHERE resource.id = %s
                """,
                (resource_id,),
            ).fetchone()
        if row is None:
            return _not_found("RAW_RESOURCE", resource_id)
        provider_code, revision, provider_path, expected, size_bytes = row
        path = _raw_relative_path(
            str(provider_code), str(revision), str(provider_path), str(expected)
        )
        if path is None:
            return _invalid(
                "RAW_RESOURCE", resource_id, None, str(expected), "raw storage layout unsupported"
            )
        result = _verify_file(self._data_root, path, str(expected), int(size_bytes))
        return IntegrityVerificationResult(
            artifact_kind="RAW_RESOURCE",
            artifact_id=resource_id,
            path=path,
            expected_sha256=str(expected),
            actual_sha256=result.actual_sha256,
            status=result.status,
            failure_reason=result.failure_reason,
        )

    def verify_dataset(self, dataset_id: UUID) -> IntegrityVerificationResult:
        with self._connection.cursor() as cursor:
            registration = cursor.execute(
                """
                SELECT dataset_name, schema_version, schema_sha256, normalizer_version,
                       manifest_path, manifest_sha256, build_spec_sha256
                FROM football.dataset_versions
                WHERE id = %s
                """,
                (dataset_id,),
            ).fetchone()
            files = tuple(
                cursor.execute(
                    """
                    SELECT relative_path, physical_sha256, logical_sha256, row_count, size_bytes
                    FROM football.dataset_files
                    WHERE dataset_version_id = %s
                    ORDER BY relative_path
                    """,
                    (dataset_id,),
                )
            )
        if registration is None:
            return _not_found("DATASET", dataset_id)
        (
            dataset_name,
            schema_version,
            schema_sha256,
            normalizer_version,
            manifest_path,
            manifest_sha256,
            build_spec,
        ) = registration
        manifest_check = _verify_file(self._data_root, str(manifest_path), str(manifest_sha256))
        if manifest_check.status != "PASS":
            return _result_from_file("DATASET", dataset_id, manifest_check)
        try:
            manifest = _json_object(self._data_root / str(manifest_path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _invalid(
                "DATASET",
                dataset_id,
                str(manifest_path),
                str(manifest_sha256),
                "dataset manifest is invalid",
            )
        expected_identity = {
            "contract": "DatasetManifestV1",
            "dataset_version_id": str(dataset_id),
            "dataset_name": str(dataset_name),
            "schema_version": str(schema_version),
            "schema_sha256": str(schema_sha256),
            "normalizer_version": str(normalizer_version),
            "build_spec_sha256": str(build_spec) if build_spec is not None else None,
        }
        if any(manifest.get(key) != value for key, value in expected_identity.items()):
            return _invalid(
                "DATASET",
                dataset_id,
                str(manifest_path),
                str(manifest_sha256),
                "dataset manifest conflicts with registration",
            )
        manifest_files = manifest.get("files")
        if not isinstance(manifest_files, list) or len(manifest_files) != len(files):
            return _invalid(
                "DATASET",
                dataset_id,
                str(manifest_path),
                str(manifest_sha256),
                "dataset files conflict with registration",
            )
        file_results = tuple(
            _verify_dataset_file(self._data_root, row, entry)
            for row, entry in zip(files, manifest_files, strict=True)
        )
        failure = _first_failure(file_results)
        if failure is not None:
            return IntegrityVerificationResult(
                "DATASET",
                dataset_id,
                str(manifest_path),
                str(manifest_sha256),
                manifest_check.actual_sha256,
                failure.status,
                failure.failure_reason,
                file_results,
            )
        return IntegrityVerificationResult(
            "DATASET",
            dataset_id,
            str(manifest_path),
            str(manifest_sha256),
            manifest_check.actual_sha256,
            "PASS",
            None,
            file_results,
        )

    def verify_model_artifact(self, artifact_id: UUID) -> IntegrityVerificationResult:
        with self._connection.cursor() as cursor:
            registration = cursor.execute(
                """
                SELECT model_family, fit_spec_sha256, logical_model_state_sha256,
                       schema_version, algorithm_version, serializer_version,
                       manifest_path, manifest_sha256
                FROM football.model_artifacts
                WHERE id = %s
                """,
                (artifact_id,),
            ).fetchone()
            files = tuple(
                cursor.execute(
                    """
                    SELECT relative_path, media_type, physical_sha256, size_bytes
                    FROM football.model_artifact_files
                    WHERE model_artifact_id = %s
                    ORDER BY relative_path
                    """,
                    (artifact_id,),
                )
            )
        if registration is None:
            return _not_found("MODEL_ARTIFACT", artifact_id)
        (
            family,
            fit_spec,
            logical_state,
            schema,
            algorithm,
            serializer,
            manifest_path,
            manifest_sha256,
        ) = registration
        manifest_check = _verify_file(self._data_root, str(manifest_path), str(manifest_sha256))
        if manifest_check.status != "PASS":
            return _result_from_file("MODEL_ARTIFACT", artifact_id, manifest_check)
        try:
            manifest = _json_object(self._data_root / str(manifest_path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _invalid(
                "MODEL_ARTIFACT",
                artifact_id,
                str(manifest_path),
                str(manifest_sha256),
                "model manifest is invalid",
            )
        expected_identity = {
            "contract": "ModelArtifactManifestV1",
            "model_artifact_id": str(artifact_id),
            "model_family": str(family),
            "fit_spec_sha256": str(fit_spec),
            "logical_model_state_sha256": str(logical_state),
            "schema_version": str(schema),
            "algorithm_version": str(algorithm),
            "serializer_version": str(serializer),
        }
        if any(manifest.get(key) != value for key, value in expected_identity.items()):
            return _invalid(
                "MODEL_ARTIFACT",
                artifact_id,
                str(manifest_path),
                str(manifest_sha256),
                "model manifest conflicts with registration",
            )
        manifest_files = manifest.get("files")
        if not isinstance(manifest_files, list) or len(manifest_files) != len(files):
            return _invalid(
                "MODEL_ARTIFACT",
                artifact_id,
                str(manifest_path),
                str(manifest_sha256),
                "model files conflict with registration",
            )
        file_results = tuple(
            _verify_model_file(self._data_root, row, entry)
            for row, entry in zip(files, manifest_files, strict=True)
        )
        failure = _first_failure(file_results)
        if failure is not None:
            return IntegrityVerificationResult(
                "MODEL_ARTIFACT",
                artifact_id,
                str(manifest_path),
                str(manifest_sha256),
                manifest_check.actual_sha256,
                failure.status,
                failure.failure_reason,
                file_results,
            )
        if len(files) == 1:
            state_check = _verify_logical_model_state(
                self._data_root, str(files[0][0]), str(logical_state)
            )
            if state_check is not None:
                return IntegrityVerificationResult(
                    "MODEL_ARTIFACT",
                    artifact_id,
                    str(manifest_path),
                    str(manifest_sha256),
                    manifest_check.actual_sha256,
                    state_check.status,
                    state_check.failure_reason,
                    file_results,
                )
        return IntegrityVerificationResult(
            "MODEL_ARTIFACT",
            artifact_id,
            str(manifest_path),
            str(manifest_sha256),
            manifest_check.actual_sha256,
            "PASS",
            None,
            file_results,
        )

    def build_report(
        self,
        *,
        report_id: str,
        policy_version: str,
        created_at: datetime,
        code_git_sha: str,
        dependency_lock_sha256: str,
        raw_resources: Iterable[IntegrityVerificationResult],
        datasets: Iterable[IntegrityVerificationResult],
        model_artifacts: Iterable[IntegrityVerificationResult],
        postgres_backup: IntegrityCheckStatusV1,
        postgres_restore: IntegrityCheckStatusV1,
        forecast_evaluation_integrity: IntegrityCheckStatusV1,
    ) -> IntegrityVerificationReportV1:
        return IntegrityVerificationReportV1(
            report_id=report_id,
            policy_version=policy_version,
            created_at=created_at,
            postgres_backup=postgres_backup,
            postgres_restore=postgres_restore,
            raw_object_integrity=_aggregate_status(raw_resources),
            dataset_manifest_integrity=_aggregate_status(datasets),
            model_artifact_integrity=_aggregate_status(model_artifacts),
            forecast_evaluation_integrity=forecast_evaluation_integrity,
            code_git_sha=code_git_sha,
            dependency_lock_sha256=dependency_lock_sha256,
        )


def _raw_relative_path(
    provider_code: str, source_revision: str, provider_path: str, sha256: str
) -> str | None:
    if provider_code == "statsbomb_open_data":
        return f"raw/provider={provider_code}/snapshot={source_revision}/{provider_path}"
    if provider_code == "football_data_uk":
        path_sha256 = hashlib.sha256(provider_path.encode("utf-8")).hexdigest()
        filename = provider_path.rsplit("/", maxsplit=1)[-1]
        return (
            f"raw/provider={provider_code}/source_path_sha256={path_sha256}/"
            f"sha256={sha256}/{filename}"
        )
    return None


def _verify_dataset_file(
    root: Path, row: tuple[object, ...], manifest_entry: object
) -> IntegrityFileVerification:
    path, expected_physical, expected_logical, row_count, size_bytes = row
    if not isinstance(manifest_entry, dict) or (
        manifest_entry.get("relative_path"),
        manifest_entry.get("physical_sha256"),
        manifest_entry.get("logical_sha256"),
        manifest_entry.get("row_count"),
        manifest_entry.get("size_bytes"),
    ) != (path, expected_physical, expected_logical, row_count, size_bytes):
        return IntegrityFileVerification(
            str(path),
            str(expected_physical),
            None,
            "INVALID_REGISTRATION",
            "dataset file manifest conflicts with registration",
        )
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
        return IntegrityFileVerification(
            str(path),
            str(expected_physical),
            None,
            "INVALID_REGISTRATION",
            "dataset file size is invalid",
        )
    result = _verify_file(root, str(path), str(expected_physical), size_bytes)
    if result.status != "PASS":
        return result
    try:
        rows = ImmutableEventParquetStore(root).read_rows(str(path))
    except (OSError, ParquetPublicationError):
        return IntegrityFileVerification(
            str(path),
            str(expected_physical),
            result.actual_sha256,
            "UNREADABLE",
            "dataset bytes cannot be read",
        )
    if len(rows) != row_count or logical_sha256(rows) != expected_logical:
        return IntegrityFileVerification(
            str(path),
            str(expected_physical),
            result.actual_sha256,
            "CHECKSUM_MISMATCH",
            "dataset logical checksum does not match bytes",
        )
    return result


def _verify_model_file(
    root: Path, row: tuple[object, ...], manifest_entry: object
) -> IntegrityFileVerification:
    path, media_type, expected, size_bytes = row
    if not isinstance(manifest_entry, dict) or (
        manifest_entry.get("relative_path"),
        manifest_entry.get("media_type"),
        manifest_entry.get("physical_sha256"),
        manifest_entry.get("size_bytes"),
    ) != (path, media_type, expected, size_bytes):
        return IntegrityFileVerification(
            str(path),
            str(expected),
            None,
            "INVALID_REGISTRATION",
            "model file manifest conflicts with registration",
        )
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
        return IntegrityFileVerification(
            str(path), str(expected), None, "INVALID_REGISTRATION", "model file size is invalid"
        )
    return _verify_file(root, str(path), str(expected), size_bytes)


def _verify_logical_model_state(
    root: Path, relative_path: str, expected_sha256: str
) -> IntegrityFileVerification | None:
    path = _storage_path(root, relative_path)
    if path is None:
        return IntegrityFileVerification(
            relative_path,
            expected_sha256,
            None,
            "INVALID_REGISTRATION",
            "registered path is invalid",
        )
    try:
        state = _json_object(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return IntegrityFileVerification(
            relative_path, expected_sha256, None, "UNREADABLE", "model state is invalid"
        )
    actual = hashlib.sha256(canonical_json_bytes(state)).hexdigest()
    if actual != expected_sha256:
        return IntegrityFileVerification(
            relative_path,
            expected_sha256,
            actual,
            "CHECKSUM_MISMATCH",
            "model logical state checksum does not match bytes",
        )
    return None


def _verify_file(
    root: Path, relative_path: str, expected_sha256: str, expected_size: int | None = None
) -> IntegrityFileVerification:
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        return IntegrityFileVerification(
            relative_path,
            expected_sha256,
            None,
            "INVALID_REGISTRATION",
            "registered checksum is invalid",
        )
    path = _storage_path(root, relative_path)
    if path is None:
        return IntegrityFileVerification(
            relative_path,
            expected_sha256,
            None,
            "INVALID_REGISTRATION",
            "registered path is invalid",
        )
    try:
        if not path.is_file() or path.is_symlink():
            return IntegrityFileVerification(
                relative_path, expected_sha256, None, "MISSING", "registered bytes are missing"
            )
        actual_sha256, actual_size = _sha256_path(path)
    except OSError:
        return IntegrityFileVerification(
            relative_path, expected_sha256, None, "UNREADABLE", "registered bytes cannot be read"
        )
    if expected_size is not None and actual_size != expected_size:
        return IntegrityFileVerification(
            relative_path,
            expected_sha256,
            actual_sha256,
            "CHECKSUM_MISMATCH",
            "registered checksum does not match bytes",
        )
    if actual_sha256 != expected_sha256:
        return IntegrityFileVerification(
            relative_path,
            expected_sha256,
            actual_sha256,
            "CHECKSUM_MISMATCH",
            "registered checksum does not match bytes",
        )
    return IntegrityFileVerification(relative_path, expected_sha256, actual_sha256, "PASS", None)


def _storage_path(root: Path, relative_path: str) -> Path | None:
    try:
        validated = validate_relative_posix_path(relative_path)
        candidate = root.joinpath(*validated.split("/"))
        candidate.resolve(strict=False).relative_to(root)
    except ValueError:
        return None
    return candidate


def _sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("expected object", "", 0)
    return payload


def _first_failure(
    results: Iterable[IntegrityFileVerification],
) -> IntegrityFileVerification | None:
    return next((result for result in results if result.status != "PASS"), None)


def _aggregate_status(items: Iterable[IntegrityVerificationResult]) -> IntegrityCheckStatusV1:
    values = tuple(items)
    if not values:
        return "NOT_RUN"
    return "PASS" if all(item.status == "PASS" for item in values) else "FAIL"


def _not_found(kind: IntegrityArtifactKind, artifact_id: UUID) -> IntegrityVerificationResult:
    return IntegrityVerificationResult(
        kind, artifact_id, None, None, None, "NOT_FOUND", "artifact is not registered"
    )


def _invalid(
    kind: IntegrityArtifactKind,
    artifact_id: UUID,
    path: str | None,
    checksum: str | None,
    reason: str,
) -> IntegrityVerificationResult:
    return IntegrityVerificationResult(
        kind, artifact_id, path, checksum, None, "INVALID_REGISTRATION", reason
    )


def _result_from_file(
    kind: IntegrityArtifactKind, artifact_id: UUID, result: IntegrityFileVerification
) -> IntegrityVerificationResult:
    return IntegrityVerificationResult(
        kind,
        artifact_id,
        result.path,
        result.expected_sha256,
        result.actual_sha256,
        result.status,
        result.failure_reason,
    )
