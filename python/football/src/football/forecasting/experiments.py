"""Frozen experiment definitions and immutable development forecast runs.

Policy and authorization references are evidence, not grants to fit, calibrate,
open protected outcomes, evaluate or promote. Those retain their domain gates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from football.contracts.decisions import DecisionRecordV1
from football.contracts.source import SHA1_PATTERN, SHA256_PATTERN, canonical_json_bytes
from football.forecasting.features import FEATURE_CONTRACT_VERSION, FixtureFeatureSnapshotV1
from football.forecasting.model_contracts import ModelRunResult, ModelStatus
from football.forecasting.model_runner import ModelRegistry, ModelRunner
from football.storage.raw import ImmutableFileStore


@dataclass(frozen=True, slots=True)
class ExperimentArtifact:
    uri: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.uri, str) or not self.uri.strip():
            raise ValueError("experiment artifact URI is required")
        if not isinstance(self.sha256, str) or not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("experiment artifact SHA-256 is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentProtocolV1:
    protocol_id: str
    hypothesis: str
    development_corpus: tuple[UUID, ...]
    validation_corpus: tuple[UUID, ...]
    evaluation_corpus: tuple[UUID, ...]
    forbidden_target_manifest: tuple[UUID, ...]
    feature_contract: str
    candidate_models: tuple[str, ...]
    fit_policy: ExperimentArtifact
    calibration_policy: ExperimentArtifact
    evaluation_policy: ExperimentArtifact
    promotion_policy: ExperimentArtifact
    authorization_refs: tuple[ExperimentArtifact, ...]

    def __post_init__(self) -> None:
        for name in (
            "development_corpus",
            "validation_corpus",
            "evaluation_corpus",
            "forbidden_target_manifest",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, UUID) for value in values
            ):
                raise ValueError("experiment corpus IDs must be immutable UUID tuples")
        if not isinstance(self.candidate_models, tuple) or not isinstance(
            self.authorization_refs, tuple
        ):
            raise ValueError("experiment candidates and references must be immutable tuples")
        if any(
            not isinstance(getattr(self, name), ExperimentArtifact)
            for name in (
                "fit_policy",
                "calibration_policy",
                "evaluation_policy",
                "promotion_policy",
            )
        ) or any(not isinstance(item, ExperimentArtifact) for item in self.authorization_refs):
            raise ValueError("experiment references must be immutable artifacts")
        try:
            Draft202012Validator(
                experiment_protocol_schema(), format_checker=FormatChecker()
            ).validate(self.to_dict())
        except ValidationError as error:
            raise ValueError(error.message) from error
        partitions = (self.development_corpus, self.validation_corpus, self.evaluation_corpus)
        if any(
            set(a) & set(b) for index, a in enumerate(partitions) for b in partitions[index + 1 :]
        ):
            raise ValueError("experiment corpus partitions overlap")
        if set(self.development_corpus + self.validation_corpus) & set(
            self.forbidden_target_manifest
        ):
            raise ValueError("experiment development/validation overlaps forbidden targets")

    def to_dict(self) -> dict[str, Any]:
        return {"contract": "ExperimentProtocolV1", **_wire(asdict(self))}

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, payload: bytes) -> ExperimentProtocolV1:
        value = json.loads(payload, object_pairs_hook=_unique_object)
        try:
            Draft202012Validator(
                experiment_protocol_schema(), format_checker=FormatChecker()
            ).validate(value)
        except ValidationError as error:
            raise ValueError(error.message) from error
        value.pop("contract")
        for name in (
            "development_corpus",
            "validation_corpus",
            "evaluation_corpus",
            "forbidden_target_manifest",
        ):
            value[name] = tuple(UUID(item) for item in value[name])
        for name in ("fit_policy", "calibration_policy", "evaluation_policy", "promotion_policy"):
            value[name] = ExperimentArtifact(**value[name])
        value["authorization_refs"] = tuple(
            ExperimentArtifact(**item) for item in value["authorization_refs"]
        )
        value["candidate_models"] = tuple(value["candidate_models"])
        return cls(**value)


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    run_id: UUID
    protocol_sha256: str
    started_at: datetime
    code_git_sha: str
    dependency_lock_sha256: str
    status: str
    result_artifact: ExperimentArtifact

    @property
    def result_sha256(self) -> str:
        return self.result_artifact.sha256

    def to_dict(self) -> dict[str, object]:
        return {"contract": "ExperimentRun", **_wire(asdict(self))}


@dataclass(frozen=True, slots=True)
class ExperimentDecision:
    run_id: UUID
    decision: DecisionRecordV1
    artifact: ExperimentArtifact


def run_experiment(
    *,
    protocol: ExperimentProtocolV1,
    registry: ModelRegistry,
    features: tuple[FixtureFeatureSnapshotV1, ...],
    files: ImmutableFileStore,
    started_at: datetime,
    code_git_sha: str,
    dependency_lock_sha256: str,
) -> ExperimentRun:
    """Forecast the exact development corpus with already-fitted candidates.

    No corpus loader or outcome reader is exposed. Validation/evaluation IDs and
    forbidden IDs also cannot occur in supplied development history. Fit and
    policy execution remain with existing explicitly authorized domain runners.
    """
    ordered = _preflight(protocol, registry, features)
    if started_at.utcoffset() is None:
        raise ValueError("experiment start time must include a timezone")
    if not SHA1_PATTERN.fullmatch(code_git_sha) or not SHA256_PATTERN.fullmatch(
        dependency_lock_sha256
    ):
        raise ValueError("experiment code/dependency identity is invalid")
    if any(feature.model_input.knowledge_cutoff > started_at for feature in ordered):
        raise ValueError("experiment start precedes input knowledge cutoff")
    started_at = started_at.astimezone(UTC)
    inputs = {
        "protocol_sha256": protocol.sha256,
        "feature_hashes": [item.sha256 for item in ordered],
        "models": [
            {
                "model_id": item.adapter.model_id,
                "model_family": item.adapter.model_family,
                "model_version": item.adapter.model_version,
                "artifact_sha256": item.artifact.artifact_sha256 if item.artifact else None,
                "minimum_team_history": item.minimum_team_history,
                "requires_xg": item.adapter.requires_xg,
                "supports_unseen_teams": item.adapter.supports_unseen_teams,
                "role": item.adapter.role.value,
            }
            for item in registry.models
        ],
        "started_at": started_at.isoformat(),
        "code_git_sha": code_git_sha,
        "dependency_lock_sha256": dependency_lock_sha256,
    }
    run_id = uuid5(
        NAMESPACE_URL,
        f"matchforge:experiment:{hashlib.sha256(canonical_json_bytes(inputs)).hexdigest()}",
    )
    root = f"experiments/{run_id}"
    files.publish(f"{root}/protocol.json", protocol.to_bytes())
    files.publish(
        f"{root}/features.json", canonical_json_bytes([item.to_dict() for item in ordered])
    )
    rows, success = _forecast_development(registry, ordered, started_at)
    result = files.publish(
        f"{root}/results.json", canonical_json_bytes({"inputs": inputs, "results": rows})
    )
    run = ExperimentRun(
        run_id,
        protocol.sha256,
        started_at,
        code_git_sha,
        dependency_lock_sha256,
        "SUCCEEDED" if success else "FAILED",
        ExperimentArtifact(result.relative_path, result.sha256),
    )
    files.publish(f"{root}/run.json", canonical_json_bytes(run.to_dict()) + b"\n")
    return run


def _preflight(
    protocol: ExperimentProtocolV1,
    registry: ModelRegistry,
    features: tuple[FixtureFeatureSnapshotV1, ...],
) -> tuple[FixtureFeatureSnapshotV1, ...]:
    if protocol.feature_contract != FEATURE_CONTRACT_VERSION:
        raise ValueError("experiment feature contract is unsupported")
    identifiers = tuple(item.adapter.model_id for item in registry.models)
    if identifiers != protocol.candidate_models:
        raise ValueError("experiment candidate models must match the frozen protocol")
    if not all(item.enabled for item in registry.models):
        raise ValueError("experiment candidates must be explicitly enabled")
    for item in registry.models:
        if item.artifact is not None and (
            item.artifact.model_id != item.adapter.model_id
            or not SHA256_PATTERN.fullmatch(item.artifact.artifact_sha256)
        ):
            raise ValueError("experiment fitted artifact identity does not match candidate")
    by_id = {item.model_input.fixture_id: item for item in features}
    if len(by_id) != len(features) or set(by_id) != set(protocol.development_corpus):
        raise ValueError("experiment inputs must equal the exact development corpus")
    protected = set(
        protocol.validation_corpus + protocol.evaluation_corpus + protocol.forbidden_target_manifest
    )
    for feature in features:
        if any(
            item.artifact is not None
            and item.artifact.training_cutoff > feature.model_input.football_cutoff
            for item in registry.models
        ):
            raise ValueError("experiment artifact training follows prediction cutoff")
        if protected & {item.fixture_id for item in feature.model_input.qualified_history}:
            raise ValueError("experiment development input contains protected history")
    return tuple(by_id[key] for key in protocol.development_corpus)


def _forecast_development(
    registry: ModelRegistry, features: tuple[FixtureFeatureSnapshotV1, ...], started_at: datetime
) -> tuple[list[dict[str, object]], bool]:
    runner = ModelRunner(registry)
    rows: list[dict[str, object]] = []
    success = True
    for feature in features:
        result = runner.run(feature)
        _validate_results(registry, feature, result)
        success = success and all(
            item.status is ModelStatus.SUCCESS for item in result.availability
        )
        rows.append(
            {
                "feature_sha256": feature.sha256,
                "forecasts": [
                    _wire(asdict(replace(item, created_at=started_at))) for item in result.forecasts
                ],
                "availability": [_wire(asdict(item)) for item in result.availability],
            }
        )
    return rows, success


def _validate_results(
    registry: ModelRegistry, feature: FixtureFeatureSnapshotV1, result: ModelRunResult
) -> None:
    expected = {item.adapter.model_id: item.artifact for item in registry.models}
    availability = {item.model_id: item.status for item in result.availability}
    if len(availability) != len(result.availability) or set(availability) != set(expected):
        raise ValueError("experiment model availability does not match candidates")
    successful = {key for key, status in availability.items() if status is ModelStatus.SUCCESS}
    forecasts = {item.model_id: item for item in result.forecasts}
    if len(forecasts) != len(result.forecasts) or set(forecasts) != successful:
        raise ValueError("experiment forecasts do not match successful candidates")
    source = feature.model_input
    for model_id, forecast in forecasts.items():
        artifact = expected[model_id]
        if (
            artifact is None
            or forecast.status is not ModelStatus.SUCCESS
            or (
                forecast.fixture_id,
                forecast.model_artifact_sha256,
                forecast.input_snapshot_sha256,
                forecast.football_cutoff,
                forecast.knowledge_cutoff,
            )
            != (
                source.fixture_id,
                artifact.artifact_sha256,
                source.sha256,
                source.football_cutoff,
                source.knowledge_cutoff,
            )
        ):
            raise ValueError("experiment forecast identity does not match its frozen inputs")


def record_experiment_decision(
    run: ExperimentRun, decision: DecisionRecordV1, files: ImmutableFileStore
) -> ExperimentDecision:
    if (decision.decision_type, decision.subject_type, decision.subject_id) != (
        "experiment",
        "experiment_run",
        str(run.run_id),
    ) or decision.decided_at < run.started_at:
        raise ValueError("experiment decision does not identify this run or has an earlier clock")
    if decision.evidence.get("result_sha256") != run.result_sha256:
        raise ValueError("experiment decision must bind the exact result checksum")
    registered = files.path_for(f"experiments/{run.run_id}/run.json").read_bytes()
    if registered != canonical_json_bytes(run.to_dict()) + b"\n":
        raise ValueError("experiment run does not match its published record")
    result = files.path_for(run.result_artifact.uri)
    if hashlib.sha256(result.read_bytes()).hexdigest() != run.result_sha256:
        raise ValueError("experiment result checksum mismatch")
    artifact = files.publish(
        f"experiments/{run.run_id}/decisions/{decision.sha256}.json", decision.to_bytes()
    )
    return ExperimentDecision(
        run.run_id, decision, ExperimentArtifact(artifact.relative_path, artifact.sha256)
    )


def _wire(value: Mapping[str, object]) -> dict[str, Any]:
    def encode(item: object) -> str:
        if isinstance(item, (UUID, datetime)):
            return str(item) if isinstance(item, UUID) else item.isoformat()
        raise TypeError(f"unsupported experiment JSON value: {type(item).__name__}")

    return cast(dict[str, Any], json.loads(json.dumps(value, default=encode, allow_nan=False)))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate experiment protocol field")
        value[key] = item
    return value


def experiment_protocol_schema() -> dict[str, Any]:
    text = {"type": "string", "pattern": r"\S"}
    artifact = {
        "type": "object",
        "properties": {
            "uri": text,
            "sha256": {"type": "string", "pattern": SHA256_PATTERN.pattern},
        },
        "required": ["uri", "sha256"],
        "additionalProperties": False,
    }
    corpus = {"type": "array", "items": {"type": "string", "format": "uuid"}, "uniqueItems": True}
    properties = {
        "contract": {"const": "ExperimentProtocolV1"},
        "protocol_id": text,
        "hypothesis": text,
        "development_corpus": {**corpus, "minItems": 1},
        "validation_corpus": corpus,
        "evaluation_corpus": corpus,
        "forbidden_target_manifest": corpus,
        "feature_contract": text,
        "candidate_models": {"type": "array", "items": text, "minItems": 1, "uniqueItems": True},
        "fit_policy": artifact,
        "calibration_policy": artifact,
        "evaluation_policy": artifact,
        "promotion_policy": artifact,
        "authorization_refs": {
            "type": "array",
            "items": artifact,
            "minItems": 1,
            "uniqueItems": True,
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ExperimentProtocolV1",
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
