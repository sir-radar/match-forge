"""Immutable runtime metadata; fitted artifacts and promotions retain their owners."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from psycopg import Connection
from psycopg.rows import tuple_row

from football.contracts.source import (
    SHA256_PATTERN,
    canonical_json_bytes,
    validate_relative_posix_path,
)
from football.forecasting.model_contracts import FittedModelArtifact
from football.storage.locks import LockClass, LockRequest, acquire_locks

CURRENT_CHAMPION_HASH = "e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4"
CURRENT_CHAMPION_ID = "transferable-rolling-goals-poisson-v1"


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRegistration:
    model_id: str
    family: str
    version: str
    feature_contract: str
    training_manifest: str
    training_start: datetime
    training_cutoff: datetime
    artifact_uri: str
    artifact_hash: str
    implementation_version: str
    dependency_fingerprint: str
    eligible_competitions: tuple[UUID, ...] | None
    eligible_products: tuple[str, ...]
    evaluation_refs: tuple[str, ...]
    calibrator_refs: tuple[str, ...]
    lifecycle_state: Literal["RESEARCH", "CHALLENGER", "CHAMPION", "RETIRED"]

    def __post_init__(self) -> None:
        for name in ("training_start", "training_cutoff"):
            value = getattr(self, name)
            if value.utcoffset() is None:
                raise ValueError("model training clocks require timezones")
            object.__setattr__(self, name, value.astimezone(UTC))
        for name in ("eligible_products", "evaluation_refs", "calibrator_refs"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError("model registry sequences must be immutable tuples")
        if self.eligible_competitions is not None and (
            not isinstance(self.eligible_competitions, tuple)
            or any(not isinstance(value, UUID) for value in self.eligible_competitions)
        ):
            raise ValueError("eligible competitions require immutable MatchForge UUIDs")
        try:
            Draft202012Validator(
                model_registration_schema(), format_checker=FormatChecker()
            ).validate(self.to_dict())
        except ValidationError as error:
            raise ValueError(error.message) from error
        validate_relative_posix_path(self.artifact_uri)
        if self.training_start > self.training_cutoff:
            raise ValueError("model training interval is invalid")
        if self.lifecycle_state == "CHAMPION":
            _validate_current_champion(self)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for name in ("training_start", "training_cutoff"):
            value[name] = getattr(self, name).isoformat()
        if self.eligible_competitions is not None:
            value["eligible_competitions"] = [str(item) for item in self.eligible_competitions]
        for name in ("eligible_products", "evaluation_refs", "calibrator_refs"):
            value[name] = list(getattr(self, name))
        return {"contract": "ModelRegistration", **value}

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, payload: bytes) -> ModelRegistration:
        value = json.loads(payload, object_pairs_hook=_unique_object)
        try:
            Draft202012Validator(
                model_registration_schema(), format_checker=FormatChecker()
            ).validate(value)
        except ValidationError as error:
            raise ValueError(error.message) from error
        value.pop("contract")
        for name in ("training_start", "training_cutoff"):
            value[name] = datetime.fromisoformat(value[name].replace("Z", "+00:00"))
        for name in ("eligible_products", "evaluation_refs", "calibrator_refs"):
            value[name] = tuple(value[name])
        if value["eligible_competitions"] is not None:
            value["eligible_competitions"] = tuple(
                UUID(item) for item in value["eligible_competitions"]
            )
        return cls(**value)


class PostgresModelRegistry:
    """Register/read exact runtime declarations, without fitting or activating models."""

    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def register(self, entry: ModelRegistration) -> Literal["published", "verified_existing"]:
        with self.connection.transaction(), self.connection.cursor(row_factory=tuple_row) as cursor:
            acquire_locks(
                cursor, (LockRequest(LockClass.MODEL, f"runtime-model:{entry.model_id}"),)
            )
            cursor.execute(
                """INSERT INTO football.runtime_model_registrations
                (registration_sha256,model_id,artifact_sha256,lifecycle_state,record_bytes)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(registration_sha256) DO NOTHING""",
                (
                    entry.sha256,
                    entry.model_id,
                    entry.artifact_hash,
                    entry.lifecycle_state,
                    entry.to_bytes(),
                ),
            )
            inserted = cursor.rowcount
            row = cursor.execute(
                "SELECT record_bytes FROM football.runtime_model_registrations "
                "WHERE registration_sha256=%s",
                (entry.sha256,),
            ).fetchone()
            if row is None or bytes(row[0]) != entry.to_bytes():
                raise ValueError("runtime model registration conflict")
        return "published" if inserted else "verified_existing"

    def get(
        self, registration_sha256: str, *, knowledge_cutoff: datetime
    ) -> ModelRegistration | None:
        if (
            not SHA256_PATTERN.fullmatch(registration_sha256)
            or knowledge_cutoff.utcoffset() is None
        ):
            raise ValueError(
                "runtime registry reads require exact identity and aware knowledge cutoff"
            )
        with self.connection.cursor(row_factory=tuple_row) as cursor:
            row = cursor.execute(
                """SELECT record_bytes FROM football.runtime_model_registrations
                WHERE registration_sha256=%s AND registered_at<=%s""",
                (registration_sha256, knowledge_cutoff),
            ).fetchone()
        if row is None:
            return None
        entry = ModelRegistration.from_bytes(bytes(row[0]))
        if entry.sha256 != registration_sha256:
            raise ValueError("runtime model registration checksum mismatch")
        return entry


def _validate_current_champion(entry: ModelRegistration) -> None:
    expected = (
        CURRENT_CHAMPION_ID,
        "MATCHFORGE_TRANSFERABLE_POISSON",
        CURRENT_CHAMPION_ID,
        "MATCHFORGE_TRANSFERABLE_ROLLING_LAST10_V1",
        "be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e",
        "2021-08-13T18:30:00+00:00",
        "2022-05-14T13:35:00+00:00",
        CURRENT_CHAMPION_HASH,
        "transferable-rolling-goals-poisson-v1-analytic-adapter-v2",
        "d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e",
    )
    actual = (
        entry.model_id,
        entry.family,
        entry.version,
        entry.feature_contract,
        entry.training_manifest,
        entry.training_start.isoformat(),
        entry.training_cutoff.isoformat(),
        entry.artifact_hash,
        entry.implementation_version,
        entry.dependency_fingerprint,
    )
    if actual != expected:
        raise ValueError("a different champion requires its existing approved promotion owner")


def load_registered_champion(entry: ModelRegistration, root: Path) -> FittedModelArtifact:
    """Load the original JSON control using frozen training metadata, without fitting."""
    if entry.model_id != CURRENT_CHAMPION_ID or entry.artifact_hash != CURRENT_CHAMPION_HASH:
        raise ValueError("registered model is not the unchanged champion")
    _validate_current_champion(entry)
    path = root / entry.artifact_uri
    path.resolve().relative_to(root.resolve())
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry.artifact_hash:
        raise ValueError("champion artifact checksum mismatch")
    payload = json.loads(raw)
    if (
        payload["algorithm_version"],
        payload["feature_id"],
        payload["development_manifest_sha256"],
        payload["dependency_lock_sha256"],
    ) != (
        entry.version,
        entry.feature_contract,
        entry.training_manifest,
        entry.dependency_fingerprint,
    ):
        raise ValueError("champion registration conflicts with immutable fitted metadata")
    return FittedModelArtifact(
        model_id=entry.model_id,
        model_family=entry.family,
        model_version=entry.version,
        artifact_sha256=entry.artifact_hash,
        training_start=entry.training_start,
        training_cutoff=entry.training_cutoff,
        dataset_sha256=entry.training_manifest,
        configuration=cast(dict[str, object], payload),
        dependency_version=entry.dependency_fingerprint,
        code_commit_sha=str(payload["executor_source_commit"]),
        feature_contract=entry.feature_contract,
        random_seed=None,
        runtime_model=path,
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate model registration field")
        result[key] = value
    return result


def model_registration_schema() -> dict[str, Any]:
    text = {"type": "string", "pattern": r"\S"}
    digest = {"type": "string", "pattern": SHA256_PATTERN.pattern}
    sequence = {"type": "array", "items": text, "uniqueItems": True}
    properties = {
        "contract": {"const": "ModelRegistration"},
        "model_id": text,
        "family": text,
        "version": text,
        "feature_contract": text,
        "training_manifest": digest,
        "training_start": {"type": "string", "format": "date-time"},
        "training_cutoff": {"type": "string", "format": "date-time"},
        "artifact_uri": text,
        "artifact_hash": digest,
        "implementation_version": text,
        "dependency_fingerprint": digest,
        "eligible_competitions": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                    "uniqueItems": True,
                },
            ]
        },
        "eligible_products": sequence,
        "evaluation_refs": sequence,
        "calibrator_refs": sequence,
        "lifecycle_state": {"enum": ["RESEARCH", "CHALLENGER", "CHAMPION", "RETIRED"]},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ModelRegistration",
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
