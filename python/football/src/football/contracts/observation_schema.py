"""Deterministic JSON Schema projection of the typed observation contracts."""

from __future__ import annotations

import hashlib
import types
from dataclasses import MISSING, fields, is_dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Any, Literal, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from football.contracts.observations import OBSERVATION_TYPES, Observation
from football.contracts.source import PROVIDER_PATTERN, SHA256_PATTERN, canonical_json_bytes

CONSTRAINTS: dict[str, dict[str, object]] = {
    "nonnegative": {"minimum": 0},
    "positive": {"minimum": 1},
    "probability": {"minimum": 0, "maximum": 1},
    "percentage": {"minimum": 0, "maximum": 100},
    "decimal_odds": {"minimum": 1},
    "sha256": {"pattern": SHA256_PATTERN.pattern},
    "provider": {"pattern": PROVIDER_PATTERN.pattern},
}


def _field_schema(annotation: Any, definitions: dict[str, Any]) -> dict[str, Any]:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return {**_field_schema(args[0], definitions), **CONSTRAINTS[args[1]]}
    if origin in (Union, types.UnionType):
        return {"anyOf": [_field_schema(arg, definitions) for arg in args]}
    if origin is Literal:
        return {"enum": list(args)}
    if origin is tuple:
        return {"type": "array", "items": _field_schema(args[0], definitions)}
    if isinstance(annotation, type) and is_dataclass(annotation):
        if annotation.__name__ not in definitions:
            definitions[annotation.__name__] = _class_schema(annotation, definitions)
        return {"$ref": f"#/$defs/{annotation.__name__}"}
    primitives: dict[Any, dict[str, Any]] = {
        str: {"type": "string", "minLength": 1},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        type(None): {"type": "null"},
        datetime: {"type": "string", "format": "date-time"},
        date: {"type": "string", "format": "date"},
        UUID: {"type": "string", "format": "uuid"},
    }
    return primitives[annotation]


def _class_schema(model: type[Any], definitions: dict[str, Any]) -> dict[str, Any]:
    hints = get_type_hints(model, include_extras=True)
    if issubclass(model, Observation):
        hints["versions"] = model.VERSIONS_TYPE
    properties = {item.name: _field_schema(hints[item.name], definitions) for item in fields(model)}
    required = [
        item.name
        for item in fields(model)
        if item.default is MISSING and item.default_factory is MISSING
    ]
    if issubclass(model, Observation):
        properties["contract"] = {"const": model.CONTRACT}
        required.append("contract")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


@lru_cache(maxsize=3)
def observation_schema(version: str = "1") -> dict[str, Any]:
    models = observation_types(version)
    definitions: dict[str, Any] = {}
    for model in models:
        definitions[model.CONTRACT] = _class_schema(model, definitions)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:matchforge:resource-observations:v{version}",
        "title": f"MatchForge resource observations version {version}",
        "oneOf": [{"$ref": f"#/$defs/{model.CONTRACT}"} for model in models],
        "$defs": definitions,
    }


def observation_schema_sha256(version: str = "1") -> str:
    return hashlib.sha256(canonical_json_bytes(observation_schema(version))).hexdigest()


def observation_types(version: str) -> tuple[type[Observation], ...]:
    if version == "1":
        return OBSERVATION_TYPES
    if version == "2":
        from football.contracts.observations_v2 import OBSERVATION_V2_TYPES

        return OBSERVATION_V2_TYPES
    if version == "3":
        from football.contracts.observations_v3 import OBSERVATION_V3_TYPES

        return OBSERVATION_V3_TYPES
    raise ValueError(f"unsupported resource observation version: {version}")
