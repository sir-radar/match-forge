"""Identity and isolation contracts for evaluation results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from football.contracts.source import SHA256_PATTERN

EvaluationAnalysisKind = Literal["single_evaluation", "cross_evaluation_robustness"]


class EvaluationProtocolError(ValueError):
    """Evaluation result identities cannot be combined safely."""


@dataclass(frozen=True, slots=True)
class EvaluationResultIdentityV1:
    evaluation_protocol_id: str
    provider_source_series_id: str
    snapshot_id: UUID
    snapshot_sha256: str
    corpus_sha256: str
    firewall_sha256: str
    model_build: str
    simulation_build: str
    preregistration_id: str
    evaluation_configuration_sha256: str
    metric_configuration_sha256: str
    simulation_configuration_sha256: str
    evaluation_date: date
    target_count: int
    contract: str = "EvaluationResultIdentityV1"

    def __post_init__(self) -> None:
        if self.contract != "EvaluationResultIdentityV1":
            raise EvaluationProtocolError("unsupported evaluation result identity contract")
        for field_name in (
            "evaluation_protocol_id",
            "provider_source_series_id",
            "model_build",
            "simulation_build",
            "preregistration_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise EvaluationProtocolError(f"{field_name} is required")
        for field_name in (
            "corpus_sha256",
            "firewall_sha256",
            "snapshot_sha256",
            "evaluation_configuration_sha256",
            "metric_configuration_sha256",
            "simulation_configuration_sha256",
        ):
            if not SHA256_PATTERN.fullmatch(getattr(self, field_name)):
                raise EvaluationProtocolError(f"{field_name} must be a SHA-256")
        if isinstance(self.evaluation_date, datetime) or not isinstance(self.evaluation_date, date):
            raise EvaluationProtocolError("evaluation_date must be a calendar date")
        if (
            isinstance(self.target_count, bool)
            or not isinstance(self.target_count, int)
            or self.target_count <= 0
        ):
            raise EvaluationProtocolError("target_count must be a positive integer")


def validate_evaluation_result_set(
    results: tuple[EvaluationResultIdentityV1, ...],
    *,
    analysis_kind: EvaluationAnalysisKind = "single_evaluation",
) -> None:
    if not results:
        raise EvaluationProtocolError("evaluation result set must not be empty")
    if analysis_kind == "cross_evaluation_robustness":
        return
    identities = {
        (
            result.evaluation_protocol_id,
            result.provider_source_series_id,
            result.snapshot_id,
            result.snapshot_sha256,
            result.corpus_sha256,
            result.firewall_sha256,
            result.model_build,
            result.simulation_build,
            result.preregistration_id,
            result.evaluation_configuration_sha256,
            result.metric_configuration_sha256,
            result.simulation_configuration_sha256,
            result.evaluation_date,
            result.target_count,
        )
        for result in results
    }
    if len(identities) != 1:
        raise EvaluationProtocolError(
            "mixed evaluation results require cross_evaluation_robustness analysis"
        )
