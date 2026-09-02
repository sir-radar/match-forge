from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ResourceProcessingStatusV1 = Literal["SUCCEEDED", "RETRYABLE", "QUARANTINED", "FAILED"]
AggregateProcessingStatusV1 = Literal["SUCCEEDED", "PARTIAL", "FAILED"]
_RESOURCE_STATUSES = frozenset(("SUCCEEDED", "RETRYABLE", "QUARANTINED", "FAILED"))


class PartialFailureError(ValueError):
    """A per-resource processing result violates its contract."""


@dataclass(frozen=True, slots=True)
class ResourceProcessingResultV1:
    resource_identity: str
    status: ResourceProcessingStatusV1
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not self.resource_identity:
            raise PartialFailureError("resource identity is required")
        if self.status not in _RESOURCE_STATUSES:
            raise PartialFailureError("resource processing status is unsupported")
        if self.status == "SUCCEEDED" and self.error_code is not None:
            raise PartialFailureError("succeeded resource cannot carry an error")
        if self.status != "SUCCEEDED" and not self.error_code:
            raise PartialFailureError("failed resource requires an error code")


@dataclass(frozen=True, slots=True)
class PartialFailureReportV1:
    resources: tuple[ResourceProcessingResultV1, ...]

    def __post_init__(self) -> None:
        if not self.resources:
            raise PartialFailureError("partial-failure report requires resources")
        identities = [resource.resource_identity for resource in self.resources]
        if len(identities) != len(set(identities)):
            raise PartialFailureError("resource identities must be unique")

    @property
    def status(self) -> AggregateProcessingStatusV1:
        statuses = {resource.status for resource in self.resources}
        if statuses == {"SUCCEEDED"}:
            return "SUCCEEDED"
        if "SUCCEEDED" in statuses:
            return "PARTIAL"
        return "FAILED"
