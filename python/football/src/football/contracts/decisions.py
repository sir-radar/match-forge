"""Common decision semantics; each domain retains its own approval and storage rules."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from types import MappingProxyType
from typing import Any, ClassVar, Literal, NoReturn, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from football.contracts.source import SHA256_PATTERN, canonical_json_bytes


class DecisionRecordError(ValueError):
    """A semantic decision has invalid identity, clocks or evidence."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DecisionRecordV1:
    CONTRACT: ClassVar[str] = "DecisionRecordV1"
    decision_type: str
    subject_type: str
    subject_id: str
    decided_at: datetime
    disposition: str
    reason: str
    evidence: Mapping[str, object]
    effective_at: datetime | None = None
    predecessor: str | None = None
    contract_version: Literal["1"] = "1"
    evidence_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decided_at", _utc(self.decided_at))
        if self.effective_at is not None:
            object.__setattr__(self, "effective_at", _utc(self.effective_at))
        try:
            frozen = _freeze(self.evidence)
        except RecursionError as error:
            raise DecisionRecordError("decision evidence must be acyclic JSON") from error
        if not isinstance(frozen, Mapping):
            raise DecisionRecordError("decision evidence must be a JSON object")
        object.__setattr__(self, "evidence", frozen)
        object.__setattr__(
            self, "evidence_hash", hashlib.sha256(canonical_json_bytes(_thaw(frozen))).hexdigest()
        )
        _validate(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.CONTRACT,
            "contract_version": self.contract_version,
            "decision_type": self.decision_type,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "decided_at": self.decided_at.isoformat(),
            "effective_at": self.effective_at.isoformat()
            if self.effective_at is not None
            else None,
            "disposition": self.disposition,
            "reason": self.reason,
            "evidence": _thaw(self.evidence),
            "evidence_hash": self.evidence_hash,
            "predecessor": self.predecessor,
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @property
    def decision_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"matchforge:decision:{self.CONTRACT}:{self.sha256}")

    @classmethod
    def from_bytes(cls, payload: bytes) -> DecisionRecordV1:
        try:
            value = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            raise DecisionRecordError("decision record is not valid UTF-8 JSON") from error
        data = _validate(value)
        item = cls(
            decision_type=data["decision_type"],
            subject_type=data["subject_type"],
            subject_id=data["subject_id"],
            decided_at=_parse_timestamp(data["decided_at"]),
            effective_at=_parse_timestamp(data["effective_at"])
            if data["effective_at"] is not None
            else None,
            disposition=data["disposition"],
            reason=data["reason"],
            evidence=data["evidence"],
            predecessor=data["predecessor"],
            contract_version=data["contract_version"],
        )
        if item.evidence_hash != data["evidence_hash"]:
            raise DecisionRecordError("decision evidence hash mismatch")
        return item


def decision_schema() -> dict[str, object]:
    text = {"type": "string", "pattern": r"\S"}
    timestamp = {"type": "string", "format": "date-time"}
    properties = {
        "contract": {"const": "DecisionRecordV1"},
        "contract_version": {"const": "1"},
        "decision_type": text,
        "subject_type": text,
        "subject_id": text,
        "decided_at": timestamp,
        "effective_at": {"anyOf": [timestamp, {"type": "null"}]},
        "disposition": text,
        "reason": text,
        "evidence": {"type": "object"},
        "evidence_hash": {"type": "string", "pattern": SHA256_PATTERN.pattern},
        "predecessor": {"anyOf": [text, {"type": "null"}]},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionRecordV1",
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(decision_schema(), format_checker=FormatChecker())


def _validate(value: object) -> dict[str, Any]:
    try:
        _validator().validate(value)
    except ValidationError as error:
        raise DecisionRecordError(error.message) from error
    return cast(dict[str, Any], value)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise DecisionRecordError("decision clocks must include a timezone")
    return value.astimezone(UTC)


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DecisionRecordError("decision timestamp is invalid") from error


def _freeze(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DecisionRecordError("decision evidence numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise DecisionRecordError("decision evidence keys must be text")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    raise DecisionRecordError("decision evidence must contain JSON values")


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DecisionRecordError("decision JSON contains duplicate keys")
        result[key] = value
    return result


def _nonfinite(value: str) -> NoReturn:
    raise DecisionRecordError(f"decision JSON constant {value} is not finite")
