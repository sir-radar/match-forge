from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from football.contracts.source import (
    SHA1_PATTERN,
    SHA256_PATTERN,
    canonical_json_bytes,
    sha256_bytes,
    validate_relative_posix_path,
)

ModelFamily = Literal[
    "TEAM_ELO",
    "DIXON_COLES_GOALS",
    "CORNER_POISSON",
    "CORNER_NEGATIVE_BINOMIAL",
    "CALIBRATION_PLATT",
    "CALIBRATION_ISOTONIC",
    "CALIBRATION_MULTICLASS",
]
ProbabilityVariant = Literal["MODEL_RAW", "MODEL_CALIBRATED"]

_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_MODEL_FAMILIES = {
    "TEAM_ELO",
    "DIXON_COLES_GOALS",
    "CORNER_POISSON",
    "CORNER_NEGATIVE_BINOMIAL",
    "CALIBRATION_PLATT",
    "CALIBRATION_ISOTONIC",
    "CALIBRATION_MULTICLASS",
}
_PROBABILITY_VARIANTS = {"MODEL_RAW", "MODEL_CALIBRATED"}


class ForecastContractError(ValueError):
    """A Sprint 2 forecasting identity or probability contract is invalid."""


@dataclass(frozen=True, slots=True)
class PointInTimeScopeV1:
    dataset_version_id: UUID
    source_snapshot_id: UUID
    feature_set_version: str
    football_cutoff: datetime
    knowledge_cutoff: datetime
    knowledge_mode: str
    quality_policy_sha256: str
    target_set_sha256: str
    contract: str = "PointInTimeScopeV1"

    def __post_init__(self) -> None:
        if self.contract != "PointInTimeScopeV1":
            raise ForecastContractError("unsupported point-in-time scope contract")
        _version(self.feature_set_version, "feature_set_version")
        _aware(self.football_cutoff, "football_cutoff")
        _aware(self.knowledge_cutoff, "knowledge_cutoff")
        _version(self.knowledge_mode, "knowledge_mode")
        _sha256(self.quality_policy_sha256, "quality_policy_sha256")
        _sha256(self.target_set_sha256, "target_set_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "dataset_version_id": str(self.dataset_version_id),
            "source_snapshot_id": str(self.source_snapshot_id),
            "feature_set_version": self.feature_set_version,
            "football_cutoff": _utc(self.football_cutoff),
            "knowledge_cutoff": _utc(self.knowledge_cutoff),
            "knowledge_mode": self.knowledge_mode,
            "quality_policy_sha256": self.quality_policy_sha256,
            "target_set_sha256": self.target_set_sha256,
        }


@dataclass(frozen=True, slots=True)
class ModelFitSpecV1:
    model_family: ModelFamily
    algorithm_version: str
    config_sha256: str
    scope: PointInTimeScopeV1
    code_commit_sha: str
    dependency_lock_sha256: str
    random_seed: int | None = None
    contract: str = "ModelFitSpecV1"

    def __post_init__(self) -> None:
        if self.contract != "ModelFitSpecV1":
            raise ForecastContractError("unsupported model fit specification contract")
        _model_family(self.model_family)
        _version(self.algorithm_version, "algorithm_version")
        _sha256(self.config_sha256, "config_sha256")
        if not SHA1_PATTERN.fullmatch(self.code_commit_sha):
            raise ForecastContractError("code_commit_sha must be a lowercase 40-character Git SHA")
        _sha256(self.dependency_lock_sha256, "dependency_lock_sha256")
        if self.random_seed is not None and (
            isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int)
        ):
            raise ForecastContractError("random_seed must be an integer or null")

    @property
    def sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "model_family": self.model_family,
            "algorithm_version": self.algorithm_version,
            "config_sha256": self.config_sha256,
            "scope": self.scope.to_dict(),
            "code_commit_sha": self.code_commit_sha,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "random_seed": self.random_seed,
        }


@dataclass(frozen=True, slots=True)
class ArtifactFileV1:
    relative_path: str
    media_type: str
    size_bytes: int
    physical_sha256: str

    def __post_init__(self) -> None:
        try:
            validate_relative_posix_path(self.relative_path)
        except ValueError as error:
            raise ForecastContractError(str(error)) from error
        if not self.media_type:
            raise ForecastContractError("artifact file media_type must not be empty")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise ForecastContractError("artifact file size_bytes must be an integer")
        if self.size_bytes <= 0:
            raise ForecastContractError("artifact file size_bytes must be positive")
        _sha256(self.physical_sha256, "physical_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "physical_sha256": self.physical_sha256,
        }


@dataclass(frozen=True, slots=True)
class ArtifactCompatibilityV1:
    runtime: str
    runtime_version: str
    loader_version: str
    feature_contract_version: str
    contract: str = "ArtifactCompatibilityV1"

    def __post_init__(self) -> None:
        if self.contract != "ArtifactCompatibilityV1":
            raise ForecastContractError("unsupported artifact compatibility contract")
        _version(self.runtime, "runtime")
        if not self.runtime_version.strip():
            raise ForecastContractError("runtime_version must not be empty")
        _version(self.loader_version, "loader_version")
        _version(self.feature_contract_version, "feature_contract_version")

    def to_dict(self) -> dict[str, str]:
        return {
            "contract": self.contract,
            "runtime": self.runtime,
            "runtime_version": self.runtime_version,
            "loader_version": self.loader_version,
            "feature_contract_version": self.feature_contract_version,
        }


@dataclass(frozen=True, slots=True)
class ModelArtifactManifestV1:
    model_artifact_id: UUID
    model_family: ModelFamily
    fit_spec_sha256: str
    schema_version: str
    algorithm_version: str
    serializer_version: str
    compatibility: ArtifactCompatibilityV1
    logical_model_state_sha256: str
    created_at: datetime
    files: tuple[ArtifactFileV1, ...]
    contract: str = "ModelArtifactManifestV1"

    def __post_init__(self) -> None:
        if self.contract != "ModelArtifactManifestV1":
            raise ForecastContractError("unsupported model artifact manifest contract")
        _model_family(self.model_family)
        _sha256(self.fit_spec_sha256, "fit_spec_sha256")
        _version(self.schema_version, "schema_version")
        _version(self.algorithm_version, "algorithm_version")
        _version(self.serializer_version, "serializer_version")
        _sha256(self.logical_model_state_sha256, "logical_model_state_sha256")
        _aware(self.created_at, "created_at")
        if not self.files:
            raise ForecastContractError("model artifact manifest requires at least one file")
        paths = [file.relative_path for file in self.files]
        if len(paths) != len(set(paths)):
            raise ForecastContractError("model artifact file paths must be unique")

    @property
    def sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "model_artifact_id": str(self.model_artifact_id),
            "model_family": self.model_family,
            "fit_spec_sha256": self.fit_spec_sha256,
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "serializer_version": self.serializer_version,
            "compatibility": self.compatibility.to_dict(),
            "logical_model_state_sha256": self.logical_model_state_sha256,
            "created_at": _utc(self.created_at),
            "files": [file.to_dict() for file in self.files],
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"


@dataclass(frozen=True, slots=True)
class MatchResultProbabilitiesV1:
    home: float
    draw: float
    away: float
    contract: str = "MatchResultProbabilitiesV1"

    def __post_init__(self) -> None:
        if self.contract != "MatchResultProbabilitiesV1":
            raise ForecastContractError("unsupported match-result probability contract")
        for field_name, value in (("home", self.home), ("draw", self.draw), ("away", self.away)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ForecastContractError(f"{field_name} probability must be finite in [0, 1]")
        if not math.isclose(self.home + self.draw + self.away, 1.0, abs_tol=1e-12):
            raise ForecastContractError("match-result probabilities must sum to one")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "home": self.home,
            "draw": self.draw,
            "away": self.away,
        }


@dataclass(frozen=True, slots=True)
class BaselineForecastV1:
    forecast_id: UUID
    match_id: UUID
    prediction_cutoff: datetime
    scope: PointInTimeScopeV1
    probability_variant: ProbabilityVariant
    model_artifact_ids: tuple[UUID, ...]
    forecast_context_sha256: str
    payload_sha256: str
    match_result: MatchResultProbabilitiesV1 | None = None
    calibrator_artifact_id: UUID | None = None
    probability_contract_version: str = "match-result-probabilities-v1"
    output_version: str = "baseline-forecast-v1"
    contract: str = "BaselineForecastV1"

    def __post_init__(self) -> None:
        if self.contract != "BaselineForecastV1":
            raise ForecastContractError("unsupported baseline forecast contract")
        _aware(self.prediction_cutoff, "prediction_cutoff")
        if self.prediction_cutoff != self.scope.football_cutoff:
            raise ForecastContractError("prediction_cutoff must equal scope football_cutoff")
        if self.probability_variant not in _PROBABILITY_VARIANTS:
            raise ForecastContractError("unsupported probability_variant")
        if not self.model_artifact_ids:
            raise ForecastContractError("forecast requires at least one model artifact")
        if len(self.model_artifact_ids) != len(set(self.model_artifact_ids)):
            raise ForecastContractError("forecast model artifact IDs must be unique")
        _sha256(self.forecast_context_sha256, "forecast_context_sha256")
        _sha256(self.payload_sha256, "payload_sha256")
        _version(self.probability_contract_version, "probability_contract_version")
        _version(self.output_version, "output_version")
        if self.payload_sha256 != forecast_payload_sha256(self.match_result):
            raise ForecastContractError("payload_sha256 does not match forecast payload")
        if self.probability_variant == "MODEL_RAW" and self.calibrator_artifact_id is not None:
            raise ForecastContractError("raw forecast cannot reference a calibrator artifact")
        if self.probability_variant == "MODEL_CALIBRATED" and self.calibrator_artifact_id is None:
            raise ForecastContractError("calibrated forecast requires a calibrator artifact")
        if self.calibrator_artifact_id in self.model_artifact_ids:
            raise ForecastContractError(
                "calibrator artifact must be distinct from primary artifacts"
            )

    @property
    def semantic_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.semantic_dict()))

    def semantic_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "match_id": str(self.match_id),
            "prediction_cutoff": _utc(self.prediction_cutoff),
            "scope": self.scope.to_dict(),
            "probability_variant": self.probability_variant,
            "probability_contract_version": self.probability_contract_version,
            "output_version": self.output_version,
            "forecast_context_sha256": self.forecast_context_sha256,
            "model_artifact_ids": sorted(str(value) for value in self.model_artifact_ids),
            "calibrator_artifact_id": (
                str(self.calibrator_artifact_id) if self.calibrator_artifact_id else None
            ),
            "payload_sha256": self.payload_sha256,
            "match_result": self.match_result.to_dict() if self.match_result else None,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "forecast_id": str(self.forecast_id),
            "semantic_sha256": self.semantic_sha256,
            **self.semantic_dict(),
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"


def forecast_payload_dict(
    match_result: MatchResultProbabilitiesV1 | None,
) -> dict[str, object]:
    return {
        "contract": "BaselineForecastPayloadV1",
        "match_result": match_result.to_dict() if match_result else None,
    }


def forecast_payload_bytes(match_result: MatchResultProbabilitiesV1 | None) -> bytes:
    return canonical_json_bytes(forecast_payload_dict(match_result))


def forecast_payload_sha256(match_result: MatchResultProbabilitiesV1 | None) -> str:
    return sha256_bytes(forecast_payload_bytes(match_result))


def _model_family(value: str) -> None:
    if value not in _MODEL_FAMILIES:
        raise ForecastContractError("unsupported model_family")


def _version(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _VERSION_PATTERN.fullmatch(value):
        raise ForecastContractError(f"{field_name} must use lowercase letters, digits, ., _, or -")


def _sha256(value: str, field_name: str) -> None:
    if not SHA256_PATTERN.fullmatch(value):
        raise ForecastContractError(f"{field_name} must be a lowercase SHA-256")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ForecastContractError(f"{field_name} must include a timezone")


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
