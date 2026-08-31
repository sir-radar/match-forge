from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq

from football.contracts.source import SHA1_PATTERN, SHA256_PATTERN, canonical_json_bytes
from football.forecasting.calibration_analysis import (
    CalibrationPredictionV1,
    Sprint2CalibrationAnalysisV1,
)
from football.forecasting.dataset import (
    EvaluationMatchOutcomeV1,
    PublishedWalkForwardTargetPlanV1,
)
from football.forecasting.execution import PersistedSprint2BatchV1, Sprint2RawForecastV1
from football.forecasting.scoring import Sprint2ComparisonRowV1, Sprint2RawMetricsV1
from football.forecasting.uncertainty import Sprint2BootstrapResultV1
from football.storage.raw import ImmutableFileStore, ImmutableWrite

EvidencePublicationStatus = Literal["published", "verified_existing"]


class EvidencePublicationError(RuntimeError):
    """Evaluation evidence is incomplete or conflicts with immutable bytes."""


@dataclass(frozen=True, slots=True)
class Sprint2EvidenceProvenanceV1:
    code_commit_sha: str
    dependency_lock_sha256: str

    def __post_init__(self) -> None:
        if not SHA1_PATTERN.fullmatch(self.code_commit_sha):
            raise EvidencePublicationError("evidence code commit must be a Git SHA")
        if not SHA256_PATTERN.fullmatch(self.dependency_lock_sha256):
            raise EvidencePublicationError("evidence dependency lock must be a SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {
            "code_commit_sha": self.code_commit_sha,
            "dependency_lock_sha256": self.dependency_lock_sha256,
        }


@dataclass(frozen=True, slots=True)
class EvaluationEvidenceFileV1:
    name: str
    relative_path: str
    media_type: str
    physical_sha256: str
    size_bytes: int
    row_count: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "relative_path": self.relative_path,
            "media_type": self.media_type,
            "physical_sha256": self.physical_sha256,
            "size_bytes": self.size_bytes,
            "row_count": self.row_count,
        }


@dataclass(frozen=True, slots=True)
class Sprint2EvaluationEvidenceManifestV1:
    evaluation_run_id: UUID
    target_set_sha256: str
    target_plan_path: str
    target_plan_sha256: str
    provenance: Sprint2EvidenceProvenanceV1
    bootstrap_policy: dict[str, object]
    calibration_policy: dict[str, object]
    files: tuple[EvaluationEvidenceFileV1, ...]
    contract: str = "Sprint2EvaluationEvidenceManifestV1"

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "evaluation_run_id": str(self.evaluation_run_id),
            "target_set_sha256": self.target_set_sha256,
            "target_plan_path": self.target_plan_path,
            "target_plan_sha256": self.target_plan_sha256,
            "provenance": self.provenance.to_dict(),
            "bootstrap_policy": self.bootstrap_policy,
            "calibration_policy": self.calibration_policy,
            "files": [item.to_dict() for item in self.files],
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"


@dataclass(frozen=True, slots=True)
class PublishedSprint2EvaluationEvidenceV1:
    manifest: Sprint2EvaluationEvidenceManifestV1
    manifest_relative_path: str
    manifest_sha256: str
    status: EvidencePublicationStatus


class Sprint2EvaluationEvidenceStore:
    def __init__(self, root: Path) -> None:
        self._files = ImmutableFileStore(root)

    def publish(
        self,
        *,
        evaluation_run_id: UUID,
        target_plan: PublishedWalkForwardTargetPlanV1,
        persisted_batches: tuple[PersistedSprint2BatchV1, ...],
        forecasts: tuple[Sprint2RawForecastV1, ...],
        outcomes: tuple[EvaluationMatchOutcomeV1, ...],
        raw_metrics: Sprint2RawMetricsV1,
        comparison_rows: tuple[Sprint2ComparisonRowV1, ...],
        bootstrap: Sprint2BootstrapResultV1,
        calibration: Sprint2CalibrationAnalysisV1,
        provenance: Sprint2EvidenceProvenanceV1,
    ) -> PublishedSprint2EvaluationEvidenceV1:
        _validate_population(target_plan, persisted_batches, forecasts, outcomes, comparison_rows)
        base = f"run={evaluation_run_id}"
        writes = (
            self._table(
                base,
                "predictions",
                _prediction_rows(forecasts, persisted_batches),
                _PREDICTION_SCHEMA,
            ),
            self._table(base, "outcomes", _outcome_rows(outcomes), _OUTCOME_SCHEMA),
            self._table(
                base,
                "comparison_rows",
                tuple(row.to_dict() for row in comparison_rows),
                _COMPARISON_SCHEMA,
            ),
            self._json(
                base,
                "raw_metrics",
                {
                    "contract": "Sprint2EvaluationMetricsV1",
                    "raw_metrics": raw_metrics.to_dict(),
                    "bootstrap": bootstrap.to_dict(),
                    "calibration": calibration.to_dict(),
                },
            ),
            self._table(
                base,
                "paired_bootstrap",
                _bootstrap_rows(bootstrap),
                _BOOTSTRAP_SCHEMA,
            ),
            self._table(
                base,
                "calibration_predictions",
                tuple(row.to_dict() for row in calibration.predictions),
                _CALIBRATION_PREDICTION_SCHEMA,
            ),
            self._table(
                base,
                "calibration_bins",
                tuple(row.to_dict() for row in calibration.bins),
                _CALIBRATION_BIN_SCHEMA,
            ),
            self._table(
                base,
                "calibration_metrics",
                tuple(row.to_dict() for row in calibration.metrics),
                _CALIBRATION_METRIC_SCHEMA,
            ),
            self._svg(
                base,
                "calibration_reliability_plot",
                "calibration-reliability-v1.svg",
                _reliability_svg(calibration),
            ),
            self._svg(
                base,
                "calibration_histogram_plot",
                "calibration-histogram-v1.svg",
                _histogram_svg(calibration),
            ),
        )
        manifest = Sprint2EvaluationEvidenceManifestV1(
            evaluation_run_id=evaluation_run_id,
            target_set_sha256=target_plan.plan.target_set_sha256,
            target_plan_path=target_plan.relative_path,
            target_plan_sha256=target_plan.physical_sha256,
            provenance=provenance,
            bootstrap_policy=bootstrap.policy.to_dict(),
            calibration_policy=calibration.policy.to_dict(),
            files=tuple(item[0] for item in writes),
        )
        manifest_path = f"{base}/Sprint2EvaluationEvidenceManifestV1.json"
        manifest_write = self._files.publish(manifest_path, manifest.to_bytes())
        statuses = tuple(item[1].status for item in writes) + (manifest_write.status,)
        return PublishedSprint2EvaluationEvidenceV1(
            manifest=manifest,
            manifest_relative_path=manifest_path,
            manifest_sha256=manifest_write.sha256,
            status="published" if "acquired" in statuses else "verified_existing",
        )

    def _table(
        self,
        base: str,
        name: str,
        rows: tuple[dict[str, object], ...],
        schema: pa.Schema,
    ) -> tuple[EvaluationEvidenceFileV1, ImmutableWrite]:
        relative_path = f"{base}/{name}.parquet"
        write = self._files.publish(relative_path, _parquet(rows, schema))
        return _evidence_file(name, write, "application/vnd.apache.parquet", len(rows)), write

    def _json(
        self, base: str, name: str, payload: dict[str, object]
    ) -> tuple[EvaluationEvidenceFileV1, ImmutableWrite]:
        relative_path = f"{base}/{name.replace('_', '-')}-v1.json"
        write = self._files.publish(relative_path, canonical_json_bytes(payload) + b"\n")
        return _evidence_file(name, write, "application/json", None), write

    def _svg(
        self, base: str, name: str, filename: str, payload: str
    ) -> tuple[EvaluationEvidenceFileV1, ImmutableWrite]:
        write = self._files.publish(f"{base}/{filename}", payload.encode("utf-8"))
        return _evidence_file(name, write, "image/svg+xml", None), write


def _validate_population(
    target_plan: PublishedWalkForwardTargetPlanV1,
    persisted_batches: tuple[PersistedSprint2BatchV1, ...],
    forecasts: tuple[Sprint2RawForecastV1, ...],
    outcomes: tuple[EvaluationMatchOutcomeV1, ...],
    comparisons: tuple[Sprint2ComparisonRowV1, ...],
) -> None:
    target_ids = tuple(
        target.context.match_id for batch in target_plan.plan.batches for target in batch.targets
    )
    if not target_ids or len(target_ids) != len(set(target_ids)):
        raise EvidencePublicationError("evaluation evidence target plan is empty or duplicated")
    populations = (
        tuple(item.context.match_id for item in forecasts),
        tuple(item.match_id for item in outcomes),
        tuple(item.match_id for item in comparisons),
    )
    if any(
        len(values) != len(target_ids) or set(values) != set(target_ids) for values in populations
    ):
        raise EvidencePublicationError("evaluation evidence populations do not match target plan")
    persisted_ids = tuple(
        match_id for batch in persisted_batches for match_id in batch.target_match_ids
    )
    if len(persisted_batches) != len(target_plan.plan.batches) or persisted_ids != target_ids:
        raise EvidencePublicationError("persisted forecast lineage does not match target plan")
    for planned, persisted in zip(target_plan.plan.batches, persisted_batches, strict=True):
        if persisted.cutoff != planned.kickoff_at or persisted.target_match_ids != tuple(
            target.context.match_id for target in planned.targets
        ):
            raise EvidencePublicationError("persisted forecast lineage conflicts with target batch")


def _prediction_rows(
    forecasts: tuple[Sprint2RawForecastV1, ...],
    persisted_batches: tuple[PersistedSprint2BatchV1, ...],
) -> tuple[dict[str, object], ...]:
    lineage = _forecast_lineage(persisted_batches)
    return tuple(
        {
            "match_id": str(item.context.match_id),
            "kickoff_at": item.context.to_dict()["kickoff_at"],
            "forecast_context_sha256": item.context.sha256,
            "elo_model_artifact_id": str(lineage[item.context.match_id][0][0]),
            "dixon_coles_model_artifact_id": str(lineage[item.context.match_id][0][1]),
            "corner_poisson_model_artifact_id": str(lineage[item.context.match_id][0][2]),
            "corner_negative_binomial_model_artifact_id": str(lineage[item.context.match_id][0][3]),
            "elo_forecast_id": str(lineage[item.context.match_id][1][0]),
            "dixon_coles_forecast_id": str(lineage[item.context.match_id][1][1]),
            "corner_poisson_forecast_id": str(lineage[item.context.match_id][1][2]),
            "corner_negative_binomial_forecast_id": str(lineage[item.context.match_id][1][3]),
            "elo_home": item.elo_result.home,
            "elo_draw": item.elo_result.draw,
            "elo_away": item.elo_result.away,
            "dixon_coles_home": item.dixon_coles_result.home,
            "dixon_coles_draw": item.dixon_coles_result.draw,
            "dixon_coles_away": item.dixon_coles_result.away,
            "result_reference_home": item.result_reference.home,
            "result_reference_draw": item.result_reference.draw,
            "result_reference_away": item.result_reference.away,
            "goal_payload_json": _json_text(item.goal.to_dict()),
            "goal_reference_payload_json": _json_text(item.goal_reference.to_dict()),
            "corner_poisson_payload_json": _json_text(item.corner_poisson.to_dict()),
            "corner_negative_binomial_payload_json": _json_text(
                item.corner_negative_binomial.to_dict()
            ),
            "corner_reference_payload_json": _json_text(item.corner_reference.to_dict()),
        }
        for item in forecasts
    )


def _forecast_lineage(
    persisted_batches: tuple[PersistedSprint2BatchV1, ...],
) -> dict[UUID, tuple[tuple[UUID, UUID, UUID, UUID], tuple[UUID, UUID, UUID, UUID]]]:
    lineage: dict[UUID, tuple[tuple[UUID, UUID, UUID, UUID], tuple[UUID, UUID, UUID, UUID]]] = {}
    for batch in persisted_batches:
        for index, match_id in enumerate(batch.target_match_ids):
            offset = index * 4
            forecast_ids = batch.forecast_ids[offset : offset + 4]
            if len(forecast_ids) != 4:
                raise EvidencePublicationError("persisted target forecast lineage is incomplete")
            lineage[match_id] = (batch.model_artifact_ids, forecast_ids)
    return lineage


def _outcome_rows(
    outcomes: tuple[EvaluationMatchOutcomeV1, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(item.to_dict() for item in outcomes)


def _bootstrap_rows(result: Sprint2BootstrapResultV1) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "comparison": interval.comparison,
            "metric": interval.metric,
            "replicate": index,
            "replicate_delta": delta,
            "point_delta": interval.point_delta,
            "lower_bound": interval.lower_bound,
            "upper_bound": interval.upper_bound,
        }
        for interval in result.intervals
        for index, delta in enumerate(interval.replicate_deltas)
    )


def _parquet(rows: tuple[dict[str, object], ...], schema: pa.Schema) -> bytes:
    table = pa.Table.from_pylist(list(rows), schema=schema)
    buffer = BytesIO()
    pq.write_table(
        table,
        buffer,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
    )
    return buffer.getvalue()


def _evidence_file(
    name: str, write: ImmutableWrite, media_type: str, row_count: int | None
) -> EvaluationEvidenceFileV1:
    return EvaluationEvidenceFileV1(
        name=name,
        relative_path=write.relative_path,
        media_type=media_type,
        physical_sha256=write.sha256,
        size_bytes=write.size_bytes,
        row_count=row_count,
    )


def _json_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _reliability_svg(calibration: Sprint2CalibrationAnalysisV1) -> str:
    points = tuple(
        item
        for item in calibration.bins
        if item.variant == "MODEL_CALIBRATED"
        and item.mean_probability is not None
        and item.observed_frequency is not None
    )
    circles = "".join(
        _reliability_circle(item.mean_probability, item.observed_frequency) for item in points
    )
    note = (
        ""
        if points
        else '<text x="200" y="205" text-anchor="middle">No eligible calibration bins</text>'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" '
        'viewBox="0 0 400 400">'
        '<rect width="400" height="400" fill="white"/>'
        '<path d="M50 350 L350 50" stroke="#94a3b8" stroke-width="1"/>'
        '<path d="M50 50 V350 H350" fill="none" stroke="#0f172a" stroke-width="2"/>'
        f"{circles}{note}"
        '<text x="200" y="390" text-anchor="middle">Mean predicted probability</text>'
        '<text x="15" y="200" transform="rotate(-90 15 200)" text-anchor="middle">'
        "Observed frequency</text>"
        "</svg>\n"
    )


def _histogram_svg(calibration: Sprint2CalibrationAnalysisV1) -> str:
    probabilities = tuple(
        value
        for item in calibration.predictions
        if item.status == "AVAILABLE"
        for value in _raw_probabilities(item)
    )
    counts = [0] * 10
    for probability in probabilities:
        counts[min(int(probability * 10), 9)] += 1
    maximum = max(counts, default=0)
    bars = "".join(
        f'<rect x="{55 + index * 30}" y="{350 - (count / maximum * 280 if maximum else 0):.3f}" '
        f'width="22" height="{(count / maximum * 280 if maximum else 0):.3f}" fill="#075985"/>'
        for index, count in enumerate(counts)
    )
    note = (
        ""
        if probabilities
        else '<text x="200" y="205" text-anchor="middle">No eligible calibrated predictions</text>'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" '
        'viewBox="0 0 400 400">'
        '<rect width="400" height="400" fill="white"/>'
        '<path d="M50 50 V350 H355" fill="none" stroke="#0f172a" stroke-width="2"/>'
        f"{bars}{note}"
        '<text x="200" y="390" text-anchor="middle">Raw probability decile</text>'
        "</svg>\n"
    )


def _reliability_circle(mean_probability: float | None, observed: float | None) -> str:
    if mean_probability is None or observed is None:
        return ""
    return (
        f'<circle cx="{50 + mean_probability * 300:.3f}" '
        f'cy="{350 - observed * 300:.3f}" r="3" fill="#075985"/>'
    )


def _raw_probabilities(item: CalibrationPredictionV1) -> tuple[float, ...]:
    if item.product == "1x2":
        return tuple(
            float(value)
            for value in (item.raw_home, item.raw_draw, item.raw_away)
            if value is not None
        )
    return (float(item.raw_probability),) if item.raw_probability is not None else ()


_PREDICTION_SCHEMA = pa.schema(
    [
        ("match_id", pa.string()),
        ("kickoff_at", pa.string()),
        ("forecast_context_sha256", pa.string()),
        ("elo_model_artifact_id", pa.string()),
        ("dixon_coles_model_artifact_id", pa.string()),
        ("corner_poisson_model_artifact_id", pa.string()),
        ("corner_negative_binomial_model_artifact_id", pa.string()),
        ("elo_forecast_id", pa.string()),
        ("dixon_coles_forecast_id", pa.string()),
        ("corner_poisson_forecast_id", pa.string()),
        ("corner_negative_binomial_forecast_id", pa.string()),
        ("elo_home", pa.float64()),
        ("elo_draw", pa.float64()),
        ("elo_away", pa.float64()),
        ("dixon_coles_home", pa.float64()),
        ("dixon_coles_draw", pa.float64()),
        ("dixon_coles_away", pa.float64()),
        ("result_reference_home", pa.float64()),
        ("result_reference_draw", pa.float64()),
        ("result_reference_away", pa.float64()),
        ("goal_payload_json", pa.string()),
        ("goal_reference_payload_json", pa.string()),
        ("corner_poisson_payload_json", pa.string()),
        ("corner_negative_binomial_payload_json", pa.string()),
        ("corner_reference_payload_json", pa.string()),
    ]
)

_OUTCOME_SCHEMA = pa.schema(
    [
        ("contract", pa.string()),
        ("match_id", pa.string()),
        ("kickoff_at", pa.string()),
        ("home_score", pa.int64()),
        ("away_score", pa.int64()),
        ("home_corners", pa.int64()),
        ("away_corners", pa.int64()),
        ("outcome_known_at", pa.string()),
    ]
)

_COMPARISON_SCHEMA = pa.schema(
    [("match_id", pa.string()), ("kickoff_at", pa.string())]
    + [
        (name, pa.float64())
        for name in (
            "elo_log_loss",
            "elo_rps",
            "dixon_coles_log_loss",
            "dixon_coles_rps",
            "result_reference_log_loss",
            "result_reference_rps",
            "goal_joint_nll",
            "goal_total_crps",
            "goal_total_absolute_error",
            "goal_reference_joint_nll",
            "goal_reference_total_crps",
            "goal_reference_total_absolute_error",
            "corner_poisson_total_nll",
            "corner_poisson_total_crps",
            "corner_poisson_total_absolute_error",
            "corner_negative_binomial_total_nll",
            "corner_negative_binomial_total_crps",
            "corner_negative_binomial_total_absolute_error",
            "corner_reference_total_nll",
            "corner_reference_total_crps",
            "corner_reference_total_absolute_error",
        )
    ]
)

_BOOTSTRAP_SCHEMA = pa.schema(
    [
        ("comparison", pa.string()),
        ("metric", pa.string()),
        ("replicate", pa.int64()),
        ("replicate_delta", pa.float64()),
        ("point_delta", pa.float64()),
        ("lower_bound", pa.float64()),
        ("upper_bound", pa.float64()),
    ]
)

_CALIBRATION_PREDICTION_SCHEMA = pa.schema(
    [
        ("match_id", pa.string()),
        ("kickoff_at", pa.string()),
        ("outcome_known_at", pa.string()),
        ("base_model", pa.string()),
        ("product", pa.string()),
        ("method", pa.string()),
        ("status", pa.string()),
        ("training_sample_count", pa.int64()),
        ("outcome", pa.string()),
        ("raw_home", pa.float64()),
        ("raw_draw", pa.float64()),
        ("raw_away", pa.float64()),
        ("calibrated_home", pa.float64()),
        ("calibrated_draw", pa.float64()),
        ("calibrated_away", pa.float64()),
        ("raw_probability", pa.float64()),
        ("calibrated_probability", pa.float64()),
    ]
)

_CALIBRATION_BIN_SCHEMA = pa.schema(
    [
        ("base_model", pa.string()),
        ("product", pa.string()),
        ("method", pa.string()),
        ("variant", pa.string()),
        ("outcome_class", pa.string()),
        ("lower_bound", pa.float64()),
        ("upper_bound", pa.float64()),
        ("sample_count", pa.int64()),
        ("event_count", pa.int64()),
        ("mean_probability", pa.float64()),
        ("observed_frequency", pa.float64()),
        ("absolute_gap", pa.float64()),
        ("wilson_lower", pa.float64()),
        ("wilson_upper", pa.float64()),
        ("sparse", pa.bool_()),
    ]
)

_CALIBRATION_METRIC_SCHEMA = pa.schema(
    [
        ("base_model", pa.string()),
        ("product", pa.string()),
        ("method", pa.string()),
        ("sample_count", pa.int64()),
        ("raw_log_loss", pa.float64()),
        ("calibrated_log_loss", pa.float64()),
        ("raw_brier", pa.float64()),
        ("calibrated_brier", pa.float64()),
        ("raw_ece", pa.float64()),
        ("calibrated_ece", pa.float64()),
        ("accepted", pa.bool_()),
    ]
)
