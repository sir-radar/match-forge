from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from psycopg import Connection, Cursor

from football.contracts.source import (
    SHA256_PATTERN,
    SourceContractError,
    canonical_json_bytes,
    validate_relative_posix_path,
)
from football.forecasting.contracts import ModelFamily, PointInTimeScopeV1
from football.forecasting.evaluation import MatchResultMetricsV1
from football.storage.raw import ImmutableFileStore

if TYPE_CHECKING:
    from football.forecasting.baseline_policy import Sprint2BaselineGateDecisionV1

EvaluationStatus = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]
PromotionDesignation = Literal["BASELINE_APPROVED", "CALIBRATION_APPROVED", "RETIRED"]
GovernancePublicationStatus = Literal["published", "verified_existing"]

_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_/-]*$")
_CALIBRATION_FAMILIES = {
    "CALIBRATION_PLATT",
    "CALIBRATION_ISOTONIC",
    "CALIBRATION_MULTICLASS",
}
_MODEL_FAMILIES = {
    "TEAM_ELO",
    "DIXON_COLES_GOALS",
    "CORNER_POISSON",
    "CORNER_NEGATIVE_BINOMIAL",
    *_CALIBRATION_FAMILIES,
}


class GovernanceContractError(ValueError):
    """Evaluation report or promotion event violates governance policy."""


class GovernancePublicationError(RuntimeError):
    """Evaluation or promotion registry state conflicts with an immutable retry."""


@dataclass(frozen=True, slots=True)
class EvaluationCorpusV1:
    provider_code: str = "statsbomb_open_data"
    provider_competition_id: int = 2
    provider_season_id: int = 27
    minimum_team_history: int = 10
    minimum_competition_history: int = 100
    minimum_scored_targets: int = 250

    def __post_init__(self) -> None:
        if not _VERSION_PATTERN.fullmatch(self.provider_code):
            raise GovernanceContractError("provider_code is invalid")
        for field_name, value in (
            ("provider_competition_id", self.provider_competition_id),
            ("provider_season_id", self.provider_season_id),
            ("minimum_team_history", self.minimum_team_history),
            ("minimum_competition_history", self.minimum_competition_history),
            ("minimum_scored_targets", self.minimum_scored_targets),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GovernanceContractError(f"{field_name} must be a positive integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_code": self.provider_code,
            "provider_competition_id": self.provider_competition_id,
            "provider_season_id": self.provider_season_id,
            "minimum_team_history": self.minimum_team_history,
            "minimum_competition_history": self.minimum_competition_history,
            "minimum_scored_targets": self.minimum_scored_targets,
        }


@dataclass(frozen=True, slots=True)
class EvaluationCoverageV1:
    registered_matches: int = 0
    completed_matches: int = 0
    scored_targets: int = 0
    corner_labelled_targets: int = 0

    def __post_init__(self) -> None:
        values = (
            self.registered_matches,
            self.completed_matches,
            self.scored_targets,
            self.corner_labelled_targets,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values
        ):
            raise GovernanceContractError(
                "evaluation coverage counts must be non-negative integers"
            )
        if self.completed_matches > self.registered_matches:
            raise GovernanceContractError("completed match coverage exceeds registered matches")
        if self.scored_targets > self.completed_matches:
            raise GovernanceContractError("scored target coverage exceeds completed matches")
        if self.corner_labelled_targets > self.scored_targets:
            raise GovernanceContractError("corner coverage exceeds scored targets")

    def to_dict(self) -> dict[str, int]:
        return {
            "registered_matches": self.registered_matches,
            "completed_matches": self.completed_matches,
            "scored_targets": self.scored_targets,
            "corner_labelled_targets": self.corner_labelled_targets,
        }


@dataclass(frozen=True, slots=True)
class Sprint2EvaluationReportV1:
    evaluation_run_id: UUID
    policy_version: str
    scope: PointInTimeScopeV1 | None
    status: EvaluationStatus
    completed_at: datetime
    raw_match_result_metrics: MatchResultMetricsV1 | None
    corpus: EvaluationCorpusV1 = field(default_factory=EvaluationCorpusV1)
    coverage: EvaluationCoverageV1 = field(default_factory=EvaluationCoverageV1)
    stage: str = "complete"
    calibrated_match_result_metrics: MatchResultMetricsV1 | None = None
    calibration_accepted: bool | None = None
    baseline_gate_decision: Sprint2BaselineGateDecisionV1 | None = None
    evidence_manifest_path: str | None = None
    evidence_manifest_sha256: str | None = None
    evaluation_football_cutoff_start: datetime | None = None
    evaluation_football_cutoff_end: datetime | None = None
    findings: tuple[str, ...] = ()
    contract: str = "Sprint2EvaluationReportV1"

    def __post_init__(self) -> None:
        if self.contract != "Sprint2EvaluationReportV1":
            raise GovernanceContractError("unsupported evaluation report contract")
        if not _VERSION_PATTERN.fullmatch(self.policy_version):
            raise GovernanceContractError("policy_version is invalid")
        _aware(self.completed_at, "completed_at")
        self._validate_status_contract()
        self._validate_evaluation_cutoffs()
        if any(not finding.strip() for finding in self.findings):
            raise GovernanceContractError("evaluation findings must not be empty")
        if len(self.findings) != len(set(self.findings)):
            raise GovernanceContractError("evaluation findings must be unique")
        self._validate_evidence_manifest()
        self._validate_baseline_gate_decision()

    def _validate_baseline_gate_decision(self) -> None:
        decision = self.baseline_gate_decision
        if decision is None:
            return
        if decision.status != self.status or decision.policy_version != self.policy_version:
            raise GovernanceContractError("baseline gate decision conflicts with report")
        if self.stage != "complete" or self.evidence_manifest_path is None:
            raise GovernanceContractError(
                "baseline gate decision requires complete retained evidence"
            )

    def _validate_evaluation_cutoffs(self) -> None:
        start = self.evaluation_football_cutoff_start
        end = self.evaluation_football_cutoff_end
        if (start is None) != (end is None):
            raise GovernanceContractError(
                "evaluation football cutoff start and end must appear together"
            )
        if start is None or end is None:
            return
        _aware(start, "evaluation_football_cutoff_start")
        _aware(end, "evaluation_football_cutoff_end")
        if start > end:
            raise GovernanceContractError("evaluation football cutoff range is invalid")
        if self.scope is None or self.scope.football_cutoff != end:
            raise GovernanceContractError(
                "evaluation scope must represent the final football cutoff"
            )

    def _validate_evidence_manifest(self) -> None:
        if (self.evidence_manifest_path is None) != (self.evidence_manifest_sha256 is None):
            raise GovernanceContractError(
                "evidence manifest path and checksum must appear together"
            )
        if self.evidence_manifest_path is None:
            return
        try:
            validate_relative_posix_path(self.evidence_manifest_path)
        except SourceContractError as error:
            raise GovernanceContractError("evidence manifest path is invalid") from error
        if not SHA256_PATTERN.fullmatch(self.evidence_manifest_sha256 or ""):
            raise GovernanceContractError("evidence manifest checksum is invalid")

    def _validate_status_contract(self) -> None:
        if self.status not in ("PASS", "PASS_WITH_WARNINGS", "FAIL"):
            raise GovernanceContractError("unsupported evaluation status")
        if not _VERSION_PATTERN.fullmatch(self.stage):
            raise GovernanceContractError("evaluation stage is invalid")
        if self.status in ("PASS", "PASS_WITH_WARNINGS") and (
            self.scope is None or self.raw_match_result_metrics is None
        ):
            raise GovernanceContractError("PASS requires a point-in-time scope and raw metrics")
        if (self.calibrated_match_result_metrics is None) != (self.calibration_accepted is None):
            raise GovernanceContractError(
                "calibrated metrics and calibration decision must appear together"
            )
        if self.status == "PASS" and self.findings:
            raise GovernanceContractError("PASS evaluation cannot contain findings")
        if self.status != "PASS" and not self.findings:
            raise GovernanceContractError("non-PASS evaluation requires findings")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "evaluation_run_id": str(self.evaluation_run_id),
            "policy_version": self.policy_version,
            "corpus": self.corpus.to_dict(),
            "coverage": self.coverage.to_dict(),
            "stage": self.stage,
            "scope": self.scope.to_dict() if self.scope else None,
            "status": self.status,
            "completed_at": _utc(self.completed_at),
            "raw_match_result_metrics": (
                self.raw_match_result_metrics.to_dict() if self.raw_match_result_metrics else None
            ),
            "calibrated_match_result_metrics": (
                self.calibrated_match_result_metrics.to_dict()
                if self.calibrated_match_result_metrics
                else None
            ),
            "calibration_accepted": self.calibration_accepted,
            "baseline_gate_decision": (
                self.baseline_gate_decision.to_dict()
                if self.baseline_gate_decision is not None
                else None
            ),
            "evidence_manifest_path": self.evidence_manifest_path,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "evaluation_football_cutoff_start": (
                _utc(self.evaluation_football_cutoff_start)
                if self.evaluation_football_cutoff_start
                else None
            ),
            "evaluation_football_cutoff_end": (
                _utc(self.evaluation_football_cutoff_end)
                if self.evaluation_football_cutoff_end
                else None
            ),
            "findings": list(self.findings),
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"


@dataclass(frozen=True, slots=True)
class PublishedEvaluationReportV1:
    report: Sprint2EvaluationReportV1
    relative_path: str
    markdown_relative_path: str
    report_sha256: str
    markdown_sha256: str
    size_bytes: int
    status: GovernancePublicationStatus


class ImmutableEvaluationReportStore:
    def __init__(self, data_root: Path) -> None:
        self._files = ImmutableFileStore(data_root)

    def publish(self, report: Sprint2EvaluationReportV1) -> PublishedEvaluationReportV1:
        base = f"run={report.evaluation_run_id}/Sprint2EvaluationReportV1"
        relative_path = f"{base}.json"
        markdown_relative_path = f"{base}.md"
        write = self._files.publish(relative_path, report.to_bytes())
        markdown_write = self._files.publish(
            markdown_relative_path, _evaluation_markdown(report).encode("utf-8")
        )
        return PublishedEvaluationReportV1(
            report=report,
            relative_path=write.relative_path,
            markdown_relative_path=markdown_write.relative_path,
            report_sha256=write.sha256,
            markdown_sha256=markdown_write.sha256,
            size_bytes=write.size_bytes,
            status=(
                "published"
                if write.status == "acquired" or markdown_write.status == "acquired"
                else "verified_existing"
            ),
        )


class PostgresEvaluationRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def register(self, publication: PublishedEvaluationReportV1) -> GovernancePublicationStatus:
        report = publication.report
        if report.scope is None:
            raise GovernancePublicationError("unresolved evaluation scope cannot be registered")
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"sprint2-evaluation:{report.evaluation_run_id}",),
            )
            inserted = cursor.execute(
                """
                INSERT INTO football.sprint2_evaluation_runs
                    (id, policy_version, dataset_version_id, source_snapshot_id,
                     target_set_sha256, report_path, report_sha256, status, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    report.evaluation_run_id,
                    report.policy_version,
                    report.scope.dataset_version_id,
                    report.scope.source_snapshot_id,
                    report.scope.target_set_sha256,
                    publication.relative_path,
                    publication.report_sha256,
                    report.status,
                    report.completed_at,
                ),
            ).rowcount
            row = cursor.execute(
                """
                SELECT id, policy_version, dataset_version_id, source_snapshot_id,
                       target_set_sha256, report_path, report_sha256, status, completed_at
                FROM football.sprint2_evaluation_runs WHERE id = %s
                """,
                (report.evaluation_run_id,),
            ).fetchone()
            expected = (
                report.evaluation_run_id,
                report.policy_version,
                report.scope.dataset_version_id,
                report.scope.source_snapshot_id,
                report.scope.target_set_sha256,
                publication.relative_path,
                publication.report_sha256,
                report.status,
                report.completed_at,
            )
            if row != expected:
                raise GovernancePublicationError(
                    f"evaluation report conflicts with registry: {report.evaluation_run_id}"
                )
        return "published" if inserted else "verified_existing"


class EvaluationReportPublisher:
    def __init__(self, connection: Connection[Any], data_root: Path) -> None:
        self._store = ImmutableEvaluationReportStore(data_root)
        self._registry = PostgresEvaluationRegistry(connection)

    def publish(self, report: Sprint2EvaluationReportV1) -> PublishedEvaluationReportV1:
        publication = self._store.publish(report)
        registry_status = self._registry.register(publication)
        if publication.status == "published" or registry_status == "published":
            return PublishedEvaluationReportV1(
                report=publication.report,
                relative_path=publication.relative_path,
                markdown_relative_path=publication.markdown_relative_path,
                report_sha256=publication.report_sha256,
                markdown_sha256=publication.markdown_sha256,
                size_bytes=publication.size_bytes,
                status="published",
            )
        return publication


@dataclass(frozen=True, slots=True)
class ModelPromotionEventV1:
    promotion_event_id: UUID
    model_artifact_id: UUID
    evaluation_run_id: UUID
    role: str
    designation: PromotionDesignation
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not _ROLE_PATTERN.fullmatch(self.role):
            raise GovernanceContractError("promotion role is invalid")
        if self.designation not in (
            "BASELINE_APPROVED",
            "CALIBRATION_APPROVED",
            "RETIRED",
        ):
            raise GovernanceContractError("unsupported promotion designation")
        _aware(self.recorded_at, "recorded_at")


@dataclass(frozen=True, slots=True)
class PublishedPromotionEventV1:
    event: ModelPromotionEventV1
    status: GovernancePublicationStatus


class PostgresModelPromotionRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def record(self, event: ModelPromotionEventV1) -> PublishedPromotionEventV1:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"model-promotion:{event.role}",),
            )
            evaluation_status = _evaluation_status(cursor, event.evaluation_run_id)
            model_family = _model_family(cursor, event.model_artifact_id)
            _validate_promotion(event, evaluation_status, model_family)
            inserted = cursor.execute(
                """
                INSERT INTO football.model_promotion_events
                    (id, model_artifact_id, evaluation_run_id, role, designation, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    event.promotion_event_id,
                    event.model_artifact_id,
                    event.evaluation_run_id,
                    event.role,
                    event.designation,
                    event.recorded_at,
                ),
            ).rowcount
            row = cursor.execute(
                """
                SELECT id, model_artifact_id, evaluation_run_id, role, designation, recorded_at
                FROM football.model_promotion_events WHERE id = %s
                """,
                (event.promotion_event_id,),
            ).fetchone()
            expected = (
                event.promotion_event_id,
                event.model_artifact_id,
                event.evaluation_run_id,
                event.role,
                event.designation,
                event.recorded_at,
            )
            if row != expected:
                raise GovernancePublicationError(
                    f"promotion event conflicts with registry: {event.promotion_event_id}"
                )
        return PublishedPromotionEventV1(
            event=event,
            status="published" if inserted else "verified_existing",
        )


def _evaluation_status(cursor: Cursor[Any], evaluation_run_id: UUID) -> EvaluationStatus:
    row = cursor.execute(
        "SELECT status FROM football.sprint2_evaluation_runs WHERE id = %s",
        (evaluation_run_id,),
    ).fetchone()
    if row is None:
        raise GovernancePublicationError(f"evaluation run is not registered: {evaluation_run_id}")
    status = str(row[0])
    if status not in ("PASS", "PASS_WITH_WARNINGS", "FAIL"):
        raise GovernancePublicationError("registered evaluation has invalid status")
    return cast(EvaluationStatus, status)


def _model_family(cursor: Cursor[Any], model_artifact_id: UUID) -> ModelFamily:
    row = cursor.execute(
        "SELECT model_family FROM football.model_artifacts WHERE id = %s",
        (model_artifact_id,),
    ).fetchone()
    if row is None:
        raise GovernancePublicationError(f"model artifact is not registered: {model_artifact_id}")
    model_family = str(row[0])
    if model_family not in _MODEL_FAMILIES:
        raise GovernancePublicationError("registered artifact has invalid model family")
    return cast(ModelFamily, model_family)


def _validate_promotion(
    event: ModelPromotionEventV1,
    evaluation_status: EvaluationStatus,
    model_family: ModelFamily,
) -> None:
    if event.designation != "RETIRED" and evaluation_status == "FAIL":
        raise GovernancePublicationError("failed evaluation cannot approve a model artifact")
    calibration_family = model_family in _CALIBRATION_FAMILIES
    if event.designation == "CALIBRATION_APPROVED" and not calibration_family:
        raise GovernancePublicationError("calibration approval requires a calibration artifact")
    if event.designation == "BASELINE_APPROVED" and calibration_family:
        raise GovernancePublicationError("baseline approval cannot target a calibration artifact")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GovernanceContractError(f"{field_name} must include a timezone")


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _evaluation_markdown(report: Sprint2EvaluationReportV1) -> str:
    scope = report.scope
    raw = report.raw_match_result_metrics
    calibrated = report.calibrated_match_result_metrics
    lines = [
        "# Sprint 2 evaluation report",
        "",
        f"- Status: **{report.status}**",
        f"- Stage: `{report.stage}`",
        f"- Evaluation run: `{report.evaluation_run_id}`",
        f"- Policy: `{report.policy_version}`",
        f"- Completed at: `{_utc(report.completed_at)}`",
        "",
        "## Corpus",
        "",
        f"- Provider: `{report.corpus.provider_code}`",
        f"- Provider competition ID: `{report.corpus.provider_competition_id}`",
        f"- Provider season ID: `{report.corpus.provider_season_id}`",
        f"- Minimum scored targets: `{report.corpus.minimum_scored_targets}`",
        "",
        "## Coverage",
        "",
        f"- Registered matches: `{report.coverage.registered_matches}`",
        f"- Completed matches: `{report.coverage.completed_matches}`",
        f"- Scored targets: `{report.coverage.scored_targets}`",
        f"- Corner-labelled targets: `{report.coverage.corner_labelled_targets}`",
        "",
        "## Point-in-time scope",
        "",
    ]
    if scope is None:
        lines.append("Not resolved. No historical scoring was performed.")
    else:
        lines.extend(
            (
                f"- Dataset version: `{scope.dataset_version_id}`",
                f"- Source snapshot: `{scope.source_snapshot_id}`",
                f"- Knowledge mode: `{scope.knowledge_mode}`",
                f"- Evaluation football cutoff start: "
                f"`{_utc(report.evaluation_football_cutoff_start)}`"
                if report.evaluation_football_cutoff_start
                else "- Evaluation football cutoff start: `not resolved`",
                f"- Evaluation football cutoff end: `{_utc(report.evaluation_football_cutoff_end)}`"
                if report.evaluation_football_cutoff_end
                else "- Evaluation football cutoff end: `not resolved`",
                f"- Target set SHA-256: `{scope.target_set_sha256}`",
            )
        )
    lines.extend(("", "## Match-result metrics", ""))
    if raw is None:
        lines.append("Not produced. No placeholder or fabricated metric values were emitted.")
    else:
        lines.extend(
            (
                f"- Raw sample count: `{raw.sample_count}`",
                f"- Raw log loss: `{raw.log_loss}`",
                f"- Raw Brier score: `{raw.brier_score}`",
                f"- Raw RPS: `{raw.ranked_probability_score}`",
            )
        )
    if calibrated is not None:
        lines.extend(
            (
                f"- Calibrated log loss: `{calibrated.log_loss}`",
                f"- Calibration accepted: `{report.calibration_accepted}`",
            )
        )
    lines.extend(("", "## Retained evidence", ""))
    if report.evidence_manifest_path is None:
        lines.append("Not produced.")
    else:
        lines.extend(
            (
                f"- Manifest: `{report.evidence_manifest_path}`",
                f"- Manifest SHA-256: `{report.evidence_manifest_sha256}`",
            )
        )
    if report.baseline_gate_decision is not None:
        lines.extend(("", "## Locked baseline policy", ""))
        for dimension in report.baseline_gate_decision.dimensions:
            lines.append(f"### {dimension.name.replace('_', ' ').title()}: {dimension.status}")
            lines.append("")
            lines.extend(
                f"- `{check.key}`: **{check.status}**; actual `{check.actual}` "
                f"{check.operator} threshold `{check.threshold}`"
                for check in dimension.checks
            )
    lines.extend(("", "## Findings", ""))
    lines.extend(f"- {finding}" for finding in report.findings)
    return "\n".join(lines) + "\n"
