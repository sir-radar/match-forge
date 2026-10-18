"""Scheduling identity is metadata; input hashes bind exact immutable work inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from football.contracts.source import SHA256_PATTERN


class WorkContractError(ValueError):
    """Work identity, scheduling or retry inputs violate the shared contract."""


class WorkType(StrEnum):
    PROVIDER_ACQUISITION = "PROVIDER_ACQUISITION"
    HISTORICAL_ACQUISITION = "HISTORICAL_ACQUISITION"
    NORMALIZATION = "NORMALIZATION"
    IDENTITY_REMEDIATION = "IDENTITY_REMEDIATION"
    CANONICAL_RECONCILIATION = "CANONICAL_RECONCILIATION"
    COVERAGE_REBUILD = "COVERAGE_REBUILD"
    READ_MODEL_PROJECTION = "READ_MODEL_PROJECTION"
    FEATURE_BUILD = "FEATURE_BUILD"
    FORECAST_REFRESH = "FORECAST_REFRESH"
    SIMULATION = "SIMULATION"
    POST_MATCH_EVALUATION = "POST_MATCH_EVALUATION"
    EXPERIMENT_EXECUTION = "EXPERIMENT_EXECUTION"


class WorkState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class RetryClassification(StrEnum):
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    base_delay: timedelta
    max_delay: timedelta
    multiplier: float

    def __post_init__(self) -> None:
        if not isinstance(self.base_delay, timedelta) or not isinstance(self.max_delay, timedelta):
            raise WorkContractError("retry delays must be timedeltas")
        if self.base_delay < timedelta() or self.max_delay < self.base_delay:
            raise WorkContractError("retry delays must be nonnegative with a compatible cap")
        if (
            isinstance(self.multiplier, bool)
            or not isinstance(self.multiplier, (int, float))
            or not math.isfinite(self.multiplier)
            or self.multiplier < 1
        ):
            raise WorkContractError("retry multiplier must be finite and at least one")


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkRequest:
    work_type: WorkType
    semantic_key: str
    input_hash: str
    priority: int
    available_at: datetime
    max_attempts: int
    retry_policy: RetryPolicy
    dependencies: tuple[UUID, ...] = ()
    parent_work_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.work_type, WorkType):
            raise WorkContractError("work type must use the shared WorkType contract")
        if not isinstance(self.semantic_key, str) or not self.semantic_key.strip():
            raise WorkContractError("work semantic key is required")
        if not isinstance(self.input_hash, str) or not SHA256_PATTERN.fullmatch(self.input_hash):
            raise WorkContractError("work input hash must be lowercase SHA256")
        if not isinstance(self.available_at, datetime) or self.available_at.utcoffset() is None:
            raise WorkContractError("work availability requires a timezone")
        object.__setattr__(self, "available_at", self.available_at.astimezone(UTC))
        _pg_integer(self.priority, minimum=-(2**31))
        _pg_integer(self.max_attempts, minimum=1)
        if not isinstance(self.retry_policy, RetryPolicy):
            raise WorkContractError("an explicit retry policy is required")
        object.__setattr__(self, "dependencies", _dependencies(self.dependencies))
        if self.parent_work_id is not None and not isinstance(self.parent_work_id, UUID):
            raise WorkContractError("parent work identity must be a UUID")
        if self.work_id in self.dependencies or self.parent_work_id == self.work_id:
            raise WorkContractError("work cannot depend on or parent itself")

    @property
    def work_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"matchforge:work:{self.work_type}:{self.semantic_key}")


def _pg_integer(value: int, *, minimum: int) -> None:
    if type(value) is not int or not minimum <= value < 2**31:
        raise WorkContractError(
            "work priority/attempt count is outside its PostgreSQL integer range"
        )


def _dependencies(value: object) -> tuple[UUID, ...]:
    if not isinstance(value, (tuple, list)) or any(not isinstance(item, UUID) for item in value):
        raise WorkContractError("work dependencies must be explicit work UUIDs")
    if len(set(value)) != len(value):
        raise WorkContractError("work dependencies must be unique")
    return tuple(sorted(value))


@dataclass(frozen=True, slots=True)
class WorkClaim:
    work_id: UUID
    work_type: WorkType
    semantic_key: str
    input_hash: str
    lease_owner: str
    lease_token: UUID
    generation: int
    lease_until: datetime
    attempt_count: int
