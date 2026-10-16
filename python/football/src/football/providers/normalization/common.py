"""Provenance and strict value readers shared by provider normalization."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from football.contracts.observations import (
    Observation,
    ObservationProvenance,
    ObservationTime,
)
from football.contracts.observations_v2 import EntityReferenceV2, ObservationVersionsV2
from football.ingestion.errors import CanonicalIngestionError
from football.validation.findings import Severity, ValidationFinding


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizationContext:
    provenance: ObservationProvenance
    time: ObservationTime
    resource_key: str
    provider_schema_version: str | None = None
    fixture_native_id: str | None = None
    competition_native_id: str | None = None
    season_label: str | None = None

    def fixture(self) -> EntityReferenceV2:
        if self.fixture_native_id is None:
            raise ValueError("match-specific resource requires an explicit fixture ID")
        return self.reference(self.fixture_native_id, "request:fixture")

    def reference(self, native_id: object, record_key: str) -> EntityReferenceV2:
        if native_id is not None and (
            isinstance(native_id, bool) or not isinstance(native_id, (str, int))
        ):
            raise ValueError("native entity ID must be a string, integer or absent")
        return EntityReferenceV2(
            str(native_id) if native_id is not None else None,
            source_record_key=record_key,
        )


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    observations: tuple[Observation, ...]
    findings: tuple[ValidationFinding, ...]
    records_seen: int


class ObservationCollector:
    def __init__(self, context: NormalizationContext, resource: str) -> None:
        self.context, self.resource = context, resource
        self.observations: list[Observation] = []
        self.findings: list[ValidationFinding] = []
        self.records_seen = 0

    @contextmanager
    def record(self, record_key: str) -> Iterator[None]:
        self.records_seen += 1
        try:
            yield
        except (ValueError, CanonicalIngestionError) as error:
            self.finding("SOURCE_RECORD_INVALID", record_key, str(error))

    def emit(
        self,
        model: Callable[..., Observation],
        record_key: str,
        native_id: object = None,
        observation_time: ObservationTime | None = None,
        **values: Any,
    ) -> Observation | None:
        context = self.context
        try:
            native = context.reference(native_id, record_key).provider_native_id
            observation = model(
                provenance=replace(
                    context.provenance, provider_native_id=native, source_record_key=record_key
                ),
                time=observation_time or context.time,
                versions=ObservationVersionsV2(
                    adapter_version=f"{context.provenance.provider}-resource-adapter-v1",
                    normalizer_version=f"{context.provenance.provider}-{self.resource}-v1",
                    provider_schema_version=context.provider_schema_version,
                ),
                **values,
            )
        except ValueError as error:
            self.finding("OBSERVATION_CONTRACT_INVALID", record_key, str(error))
            return None
        else:
            self.observations.append(observation)
            return observation

    def finding(
        self,
        code: str,
        record_key: str,
        message: str,
        *,
        severity: Severity = "QUARANTINE",
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.findings.append(
            ValidationFinding(
                rule_code=f"MF_NORM_{code}",
                severity=severity,
                action="quarantine_observation" if severity == "QUARANTINE" else "report",
                scope_type="source_resource",
                message=message,
                evidence=evidence or {},
                source_resource_id=self.context.provenance.source_resource_id,
                field_path=record_key,
            )
        )

    def result(self) -> NormalizationResult:
        return NormalizationResult(
            tuple(self.observations), tuple(self.findings), self.records_seen
        )


def object_value(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("source field must be an object")
    return value


def array(value: object) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("source field must be an array or absent")
    return value


def required_text(value: object) -> str:
    result = text(value)
    if result is None:
        raise ValueError("source field requires nonempty text")
    return result


def optional_bool(value: object) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError("source flag must be boolean or absent")
    return value


def text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source field must be nonempty text")
    return value


def number(value: object, *, percent: bool = False) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("source measurement must be numeric")
    cleaned = value.strip().removesuffix("%") if isinstance(value, str) and percent else value
    result = float(cleaned)
    if not math.isfinite(result):
        raise ValueError("source measurement must be finite")
    return result


def count(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("source count must be numeric")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("source count must be numeric") from error
    if not result.is_finite() or result != result.to_integral_value() or result < 0:
        raise ValueError("source count must be a nonnegative integer")
    return int(result)


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("source timestamp must be text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("source timestamp must declare a timezone")
    return result
