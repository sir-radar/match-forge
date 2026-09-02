from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import SHA256_PATTERN, canonical_json_bytes

IntegrityCheckStatusV1 = Literal["PASS", "FAIL", "NOT_RUN"]
_STATUSES = frozenset(("PASS", "FAIL", "NOT_RUN"))


class IntegrityContractError(ValueError):
    """An integrity or recovery evidence report violates its contract."""


@dataclass(frozen=True, slots=True)
class IntegrityVerificationReportV1:
    """Evidence for backup/restore and authoritative artifact verification."""

    report_id: str
    policy_version: str
    created_at: datetime
    postgres_backup: IntegrityCheckStatusV1
    postgres_restore: IntegrityCheckStatusV1
    raw_object_integrity: IntegrityCheckStatusV1
    dataset_manifest_integrity: IntegrityCheckStatusV1
    model_artifact_integrity: IntegrityCheckStatusV1
    forecast_evaluation_integrity: IntegrityCheckStatusV1
    code_git_sha: str
    dependency_lock_sha256: str
    contract: str = "IntegrityVerificationReportV1"

    def __post_init__(self) -> None:
        if self.contract != "IntegrityVerificationReportV1":
            raise IntegrityContractError("unsupported integrity report contract")
        if not self.report_id or not self.policy_version:
            raise IntegrityContractError("integrity report identity and policy are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise IntegrityContractError("integrity report timestamp must include a timezone")
        for name in _CHECK_FIELDS:
            if getattr(self, name) not in _STATUSES:
                raise IntegrityContractError(f"{name} status is unsupported")
        if len(self.code_git_sha) != 40 or any(
            character not in "0123456789abcdef" for character in self.code_git_sha
        ):
            raise IntegrityContractError("code_git_sha must be a 40-character lowercase Git SHA")
        if not SHA256_PATTERN.fullmatch(self.dependency_lock_sha256):
            raise IntegrityContractError("dependency lock must be a SHA-256")

    @property
    def status(self) -> IntegrityCheckStatusV1:
        statuses = [getattr(self, name) for name in _CHECK_FIELDS]
        if "FAIL" in statuses:
            return "FAIL"
        if all(status == "PASS" for status in statuses):
            return "PASS"
        return "NOT_RUN"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "report_id": self.report_id,
            "policy_version": self.policy_version,
            "created_at": self.created_at.isoformat(),
            "postgres_backup": self.postgres_backup,
            "postgres_restore": self.postgres_restore,
            "raw_object_integrity": self.raw_object_integrity,
            "dataset_manifest_integrity": self.dataset_manifest_integrity,
            "model_artifact_integrity": self.model_artifact_integrity,
            "forecast_evaluation_integrity": self.forecast_evaluation_integrity,
            "code_git_sha": self.code_git_sha,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "status": self.status,
        }


_CHECK_FIELDS = (
    "postgres_backup",
    "postgres_restore",
    "raw_object_integrity",
    "dataset_manifest_integrity",
    "model_artifact_integrity",
    "forecast_evaluation_integrity",
)
