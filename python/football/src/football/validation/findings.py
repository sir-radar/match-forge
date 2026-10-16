"""Structured findings shared by resource normalization and dataset validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

Severity = Literal["FATAL", "QUARANTINE", "WARNING", "INFO"]


@dataclass(frozen=True)
class ValidationFinding:
    rule_code: str
    severity: Severity
    action: str
    scope_type: str
    message: str
    evidence: dict[str, Any]
    dataset_file_id: UUID | None = None
    source_resource_id: UUID | None = None
    provider_entity_id: str | None = None
    field_path: str | None = None
