from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

SchemaCompatibilityStatusV1 = Literal["accepted", "accepted_with_warnings", "quarantine"]


class ProviderSchemaContractError(ValueError):
    """A provider schema contract violates its versioned declaration."""


@dataclass(frozen=True, slots=True)
class SchemaCompatibilityResultV1:
    status: SchemaCompatibilityStatusV1
    missing_required_fields: tuple[str, ...] = ()
    unknown_additive_fields: tuple[str, ...] = ()
    unknown_enum_fields: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderResourceContractV1:
    provider_id: str
    resource: str
    schema_version: str
    adapter_version: str
    parser_version: str
    normalizer_version: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    enum_fields: Mapping[str, tuple[str, ...]]
    contract: str = "ProviderResourceContractV1"

    def __post_init__(self) -> None:
        if self.contract != "ProviderResourceContractV1":
            raise ProviderSchemaContractError("unsupported provider resource contract")
        if not PROVIDER_PATTERN.fullmatch(self.provider_id):
            raise ProviderSchemaContractError("provider_id must use lowercase snake_case")
        if not self.resource or not self.schema_version:
            raise ProviderSchemaContractError("resource and schema version are required")
        if not self.adapter_version or not self.parser_version or not self.normalizer_version:
            raise ProviderSchemaContractError(
                "adapter, parser, and normalizer versions are required"
            )
        _validate_fields(self.required_fields, "required fields")
        _validate_fields(self.optional_fields, "optional fields")
        if set(self.required_fields) & set(self.optional_fields):
            raise ProviderSchemaContractError("required and optional fields must be disjoint")
        normalized_enums = {field: tuple(values) for field, values in self.enum_fields.items()}
        if any(not field or not values for field, values in normalized_enums.items()):
            raise ProviderSchemaContractError("enum fields require names and values")
        if any(len(values) != len(set(values)) for values in normalized_enums.values()):
            raise ProviderSchemaContractError("enum values must be unique")
        object.__setattr__(self, "enum_fields", MappingProxyType(normalized_enums))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "resource": self.resource,
            "schema_version": self.schema_version,
            "adapter_version": self.adapter_version,
            "parser_version": self.parser_version,
            "normalizer_version": self.normalizer_version,
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "enum_fields": {field: list(values) for field, values in self.enum_fields.items()},
        }

    def inspect(self, payload: Mapping[str, object]) -> SchemaCompatibilityResultV1:
        explicit_version = payload.get("schema_version")
        if explicit_version is not None and explicit_version != self.schema_version:
            return SchemaCompatibilityResultV1(
                status="quarantine",
                reason="unsupported explicit provider schema version",
            )
        missing = tuple(field for field in self.required_fields if field not in payload)
        if missing:
            return SchemaCompatibilityResultV1(
                status="quarantine",
                missing_required_fields=missing,
                reason="required provider field is missing",
            )
        known = set(self.required_fields) | set(self.optional_fields) | set(self.enum_fields)
        unknown = tuple(sorted(set(payload) - known - {"schema_version"}))
        unknown_enums = tuple(
            sorted(
                field
                for field, allowed in self.enum_fields.items()
                if field in payload and payload[field] not in allowed
            )
        )
        return SchemaCompatibilityResultV1(
            status="accepted_with_warnings" if unknown_enums else "accepted",
            unknown_additive_fields=unknown,
            unknown_enum_fields=unknown_enums,
            reason="provider enum value is unknown" if unknown_enums else None,
        )

    def inspect_columns(self, columns: tuple[str, ...]) -> SchemaCompatibilityResultV1:
        """Check a tabular header without inventing values or provider versions."""

        invalid_columns = not columns or any(not column for column in columns)
        if invalid_columns or len(columns) != len(set(columns)):
            return SchemaCompatibilityResultV1(
                status="quarantine",
                reason="CSV header is empty or contains duplicate columns",
            )
        return self.inspect({column: None for column in columns})


def _validate_fields(fields: tuple[str, ...], label: str) -> None:
    if any(not field for field in fields):
        raise ProviderSchemaContractError(f"{label} must not be empty")
    if len(fields) != len(set(fields)):
        raise ProviderSchemaContractError(f"{label} must be unique")
