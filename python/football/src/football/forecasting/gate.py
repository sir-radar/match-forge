from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from psycopg import Connection

from football.contracts.source import canonical_json_bytes
from football.forecasting.artifacts import ModelArtifactPublisher, PortableModelArtifactStore
from football.forecasting.baseline_policy import (
    Sprint2BaselineGatePolicyV1,
    collect_sprint2_baseline_gate_actuals,
    compare_equivalent_clean_runs,
    unreproduced_run,
)
from football.forecasting.corner_labels import CORNER_LABEL_VERSION
from football.forecasting.dataset import (
    ImmutableWalkForwardTargetPlanStore,
    PointInTimeMatchDatasetProvider,
    WalkForwardDatasetSpecV1,
)
from football.forecasting.evaluation_run import Sprint2EvaluationRunner
from football.forecasting.evidence import (
    Sprint2EvaluationEvidenceStore,
    Sprint2EvidenceProvenanceV1,
    find_equivalent_clean_manifest,
)
from football.forecasting.execution import (
    Sprint2BatchModeler,
    Sprint2ExecutionPolicyV1,
    Sprint2WalkForwardExecutor,
)
from football.forecasting.execution_publication import (
    Sprint2BatchPublisher,
    Sprint2ExecutionProvenanceV1,
)
from football.forecasting.governance import (
    EvaluationCorpusV1,
    EvaluationCoverageV1,
    EvaluationReportPublisher,
    EvaluationStatus,
    ImmutableEvaluationReportStore,
    Sprint2EvaluationReportV1,
)
from football.forecasting.kickoff import (
    KICKOFF_CLAIM_VERSION,
    KICKOFF_TIMEZONE,
    TZDATA_VERSION,
)
from football.forecasting.lifecycle import LIFECYCLE_CLAIM_VERSION
from football.forecasting.publication import BaselineForecastPublisher

_EVALUATION_NAMESPACE = UUID("4ae2a83b-7efb-4c2c-98bf-70e818c6f6d1")
_MINIMUM_CORNER_LABEL_PERCENT = 95


@dataclass(frozen=True, slots=True)
class Sprint2GateSummary:
    evaluation_run_id: UUID
    status: EvaluationStatus
    stage: str
    json_path: Path
    markdown_path: Path
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedCorpus:
    competition_id: UUID
    season_id: UUID


@dataclass(frozen=True, slots=True)
class _ExecutionLineage:
    dataset_version_id: UUID
    source_snapshot_id: UUID
    quality_policy_sha256: str
    knowledge_cutoff: datetime


class Sprint2GateService:
    """Run the authoritative Sprint 2 gate until the first blocking stage."""

    def __init__(
        self,
        connection: Connection[Any],
        report_root: Path,
        *,
        data_root: Path | None = None,
        provenance: Sprint2EvidenceProvenanceV1 | None = None,
    ) -> None:
        self._connection = connection
        self._report_root = report_root.resolve()
        self._data_root = data_root.resolve() if data_root is not None else None
        self._provenance = provenance

    def evaluate(self, corpus: EvaluationCorpusV1 | None = None) -> Sprint2GateSummary:
        requested = corpus or EvaluationCorpusV1()
        completed_at = datetime.now(UTC)
        coverage, stage, findings, resolved = self._inspect_corpus(requested)
        if stage != "walk-forward-execution" or resolved is None:
            return self._publish_preflight(requested, coverage, stage, findings, completed_at)
        if self._data_root is None or self._provenance is None:
            return self._publish_preflight(
                requested,
                coverage,
                "execution-provenance",
                (
                    "walk-forward execution requires the immutable data root, code Git SHA, "
                    "and dependency lock SHA-256",
                ),
                completed_at,
            )
        lineage = self._execution_lineage(resolved.season_id, coverage.scored_targets)
        if lineage is None:
            return self._publish_preflight(
                requested,
                coverage,
                "execution-lineage",
                (
                    "approved corpus does not resolve to one complete validated dataset, "
                    "source snapshot, and quality policy lineage",
                ),
                completed_at,
            )
        policy = Sprint2ExecutionPolicyV1()
        provider = PointInTimeMatchDatasetProvider(self._connection)
        spec = WalkForwardDatasetSpecV1(
            dataset_version_id=lineage.dataset_version_id,
            source_snapshot_id=lineage.source_snapshot_id,
            feature_set_version=policy.feature_set_version,
            knowledge_cutoff=lineage.knowledge_cutoff,
            knowledge_mode="retrospective-fixed-snapshot-v1",
            quality_policy_sha256=lineage.quality_policy_sha256,
            minimum_team_history=requested.minimum_team_history,
            minimum_competition_history=requested.minimum_competition_history,
        )
        plan = provider.walk_forward_plan(spec, resolved.competition_id, resolved.season_id)
        target_plan = ImmutableWalkForwardTargetPlanStore(self._report_root).publish(plan)
        if plan.target_count < requested.minimum_scored_targets:
            return self._publish_preflight(
                requested,
                coverage,
                "target-plan-coverage",
                (
                    f"walk-forward target plan has {plan.target_count} eligible targets; "
                    f"minimum is {requested.minimum_scored_targets}",
                ),
                completed_at,
            )
        findings = ("applying locked Sprint 2 baseline policy to retained evidence",)
        evaluation_run_id = _evaluation_id(
            completed_at, requested, coverage, "baseline-policy-evaluation", findings
        )
        scope = plan.scope_for(plan.batches[-1])
        cutoff_start = plan.batches[0].kickoff_at
        cutoff_end = plan.batches[-1].kickoff_at
        try:
            run = self._runner(provider, policy, completed_at).run(
                evaluation_run_id=evaluation_run_id,
                target_plan=target_plan,
                provenance=self._provenance,
            )
        except (RuntimeError, ValueError) as error:
            return self._publish_report(
                Sprint2EvaluationReportV1(
                    evaluation_run_id=evaluation_run_id,
                    policy_version="sprint2-baseline-gate-v1",
                    corpus=requested,
                    coverage=coverage,
                    stage="walk-forward-execution",
                    scope=scope,
                    status="FAIL",
                    completed_at=completed_at,
                    raw_match_result_metrics=None,
                    evaluation_football_cutoff_start=cutoff_start,
                    evaluation_football_cutoff_end=cutoff_end,
                    findings=(f"walk-forward evaluation failed: {error}",),
                ),
                register=True,
            )
        current_manifest = run.evidence.manifest
        reproduction_manifest = find_equivalent_clean_manifest(self._report_root, current_manifest)
        reproducibility = (
            compare_equivalent_clean_runs(current_manifest, reproduction_manifest)
            if reproduction_manifest is not None
            else unreproduced_run(current_manifest)
        )
        actuals = collect_sprint2_baseline_gate_actuals(
            execution=run.execution,
            bootstrap=run.bootstrap,
            calibration=run.calibration,
            planned_target_count=plan.target_count,
            corpus_scored_targets=coverage.scored_targets,
            corner_labelled_targets=coverage.corner_labelled_targets,
            reproducibility=reproducibility,
        )
        decision = Sprint2BaselineGatePolicyV1().evaluate(actuals)
        report = Sprint2EvaluationReportV1(
            evaluation_run_id=evaluation_run_id,
            policy_version=decision.policy_version,
            corpus=requested,
            coverage=coverage,
            stage="complete",
            scope=scope,
            status=decision.status,
            completed_at=completed_at,
            raw_match_result_metrics=run.execution.metrics.dixon_coles_result,
            baseline_gate_decision=decision,
            evidence_manifest_path=run.evidence.manifest_relative_path,
            evidence_manifest_sha256=run.evidence.manifest_sha256,
            evaluation_football_cutoff_start=cutoff_start,
            evaluation_football_cutoff_end=cutoff_end,
            findings=decision.findings,
        )
        return self._publish_report(report, register=True)

    def _runner(
        self,
        provider: PointInTimeMatchDatasetProvider,
        policy: Sprint2ExecutionPolicyV1,
        completed_at: datetime,
    ) -> Sprint2EvaluationRunner:
        if self._data_root is None or self._provenance is None:
            raise RuntimeError("Sprint 2 execution configuration is missing")
        persistence = Sprint2BatchPublisher(
            artifact_publisher=ModelArtifactPublisher(self._connection, self._data_root),
            artifact_loader=PortableModelArtifactStore(self._data_root),
            forecast_publisher=BaselineForecastPublisher(self._connection, self._data_root),
            policy=policy,
            provenance=Sprint2ExecutionProvenanceV1(
                self._provenance.code_commit_sha,
                self._provenance.dependency_lock_sha256,
                completed_at,
            ),
        )
        executor = Sprint2WalkForwardExecutor(
            provider=provider,
            persistence=persistence,
            modeler=Sprint2BatchModeler(policy),
        )
        return Sprint2EvaluationRunner(
            executor=executor,
            evidence_store=Sprint2EvaluationEvidenceStore(self._report_root),
        )

    def _publish_preflight(
        self,
        corpus: EvaluationCorpusV1,
        coverage: EvaluationCoverageV1,
        stage: str,
        findings: tuple[str, ...],
        completed_at: datetime,
    ) -> Sprint2GateSummary:
        report = Sprint2EvaluationReportV1(
            evaluation_run_id=_evaluation_id(completed_at, corpus, coverage, stage, findings),
            policy_version="sprint2-baseline-gate-v1",
            corpus=corpus,
            coverage=coverage,
            stage=stage,
            scope=None,
            status="FAIL",
            completed_at=completed_at,
            raw_match_result_metrics=None,
            findings=findings,
        )
        return self._publish_report(report, register=False)

    def _publish_report(
        self, report: Sprint2EvaluationReportV1, *, register: bool
    ) -> Sprint2GateSummary:
        publication = (
            EvaluationReportPublisher(self._connection, self._report_root).publish(report)
            if register
            else ImmutableEvaluationReportStore(self._report_root).publish(report)
        )
        return Sprint2GateSummary(
            evaluation_run_id=report.evaluation_run_id,
            status=report.status,
            stage=report.stage,
            json_path=self._report_root / publication.relative_path,
            markdown_path=self._report_root / publication.markdown_relative_path,
            findings=report.findings,
        )

    def _inspect_corpus(
        self, corpus: EvaluationCorpusV1
    ) -> tuple[EvaluationCoverageV1, str, tuple[str, ...], _ResolvedCorpus | None]:
        with self._connection.cursor() as cursor:
            mappings = cursor.execute(
                """
                SELECT season.id, season.competition_id
                FROM football.season_provider_mappings AS mapping
                JOIN football.providers AS provider ON provider.id = mapping.provider_id
                JOIN football.seasons AS season ON season.id = mapping.season_id
                WHERE provider.code = %s
                  AND mapping.provider_competition_id = %s
                  AND mapping.provider_season_id = %s
                  AND mapping.valid_to IS NULL
                ORDER BY season.id
                """,
                (
                    corpus.provider_code,
                    str(corpus.provider_competition_id),
                    str(corpus.provider_season_id),
                ),
            ).fetchall()
        if not mappings:
            return (
                EvaluationCoverageV1(),
                "corpus-resolution",
                (
                    "approved corpus is not ingested: "
                    f"{corpus.provider_code} competition_id={corpus.provider_competition_id} "
                    f"season_id={corpus.provider_season_id}",
                    "chronological walk-forward evaluation did not run",
                ),
                None,
            )
        if len(mappings) != 1:
            return (
                EvaluationCoverageV1(),
                "corpus-resolution",
                (
                    "approved corpus maps to multiple canonical seasons",
                    "chronological walk-forward evaluation did not run",
                ),
                None,
            )
        season_id = UUID(str(mappings[0][0]))
        resolved = _ResolvedCorpus(UUID(str(mappings[0][1])), season_id)
        coverage = self._coverage(season_id)
        if coverage.scored_targets < corpus.minimum_scored_targets:
            return (
                coverage,
                "coverage",
                (
                    f"primary evaluation has {coverage.scored_targets} scored targets; "
                    f"minimum is {corpus.minimum_scored_targets}",
                    "chronological walk-forward evaluation did not run",
                ),
                resolved,
            )
        chronological_targets, chronological_batches = self._chronology(season_id)
        if chronological_targets != coverage.scored_targets:
            return (
                coverage,
                "chronology-resolution",
                (
                    f"primary evaluation has {chronological_targets} timezone-resolved targets; "
                    f"expected {coverage.scored_targets}",
                    "chronological walk-forward evaluation did not run",
                ),
                resolved,
            )
        required_corner_labels = _minimum_corner_labels(coverage.scored_targets)
        if coverage.corner_labelled_targets < required_corner_labels:
            return (
                coverage,
                "corner-label-coverage",
                (
                    f"primary evaluation has {coverage.corner_labelled_targets} "
                    f"corner-labelled targets; minimum is {required_corner_labels} "
                    f"({_MINIMUM_CORNER_LABEL_PERCENT}% of scored targets)",
                    "chronological walk-forward evaluation did not run",
                ),
                resolved,
            )
        return (
            coverage,
            "walk-forward-execution",
            (
                "approved corpus passed count and chronology preflight across "
                f"{chronological_batches} batches but no complete retained walk-forward "
                "evaluation exists",
            ),
            resolved,
        )

    def _execution_lineage(
        self, season_id: UUID, expected_targets: int
    ) -> _ExecutionLineage | None:
        with self._connection.cursor() as cursor:
            rows = cursor.execute(
                """
                SELECT lifecycle.dataset_version_id, lifecycle.source_snapshot_id,
                       validation.policy_sha256,
                       GREATEST(max(lifecycle.known_from), max(kickoff.known_from),
                                COALESCE(max(corner.known_from), max(lifecycle.known_from))),
                       count(DISTINCT lifecycle.match_id)
                FROM football.match_lifecycle_claims AS lifecycle
                JOIN football.matches AS match ON match.id = lifecycle.match_id
                JOIN football.match_kickoff_claims AS kickoff
                  ON kickoff.lifecycle_claim_id = lifecycle.id
                 AND kickoff.claim_version = %s
                 AND kickoff.timezone_name = %s
                 AND kickoff.tzdata_version = %s
                LEFT JOIN football.match_corner_labels AS corner
                  ON corner.lifecycle_claim_id = lifecycle.id
                 AND corner.claim_version = %s
                JOIN football.match_observations AS observation
                  ON observation.id = lifecycle.match_observation_id
                JOIN football.validation_runs AS validation
                  ON validation.id = lifecycle.validation_run_id
                 AND validation.dataset_version_id = lifecycle.dataset_version_id
                 AND validation.source_snapshot_id = lifecycle.source_snapshot_id
                 AND validation.status IN ('passed', 'warnings')
                WHERE match.season_id = %s
                  AND lifecycle.claim_version = %s
                  AND observation.home_score IS NOT NULL
                  AND observation.away_score IS NOT NULL
                GROUP BY lifecycle.dataset_version_id, lifecycle.source_snapshot_id,
                         validation.policy_sha256
                ORDER BY lifecycle.dataset_version_id
                """,
                (
                    KICKOFF_CLAIM_VERSION,
                    KICKOFF_TIMEZONE,
                    TZDATA_VERSION,
                    CORNER_LABEL_VERSION,
                    season_id,
                    LIFECYCLE_CLAIM_VERSION,
                ),
            ).fetchall()
        if len(rows) != 1 or int(rows[0][4]) != expected_targets:
            return None
        return _ExecutionLineage(
            dataset_version_id=UUID(str(rows[0][0])),
            source_snapshot_id=UUID(str(rows[0][1])),
            quality_policy_sha256=str(rows[0][2]),
            knowledge_cutoff=rows[0][3],
        )

    def _chronology(self, season_id: UUID) -> tuple[int, int]:
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT count(DISTINCT kickoff.match_id), count(DISTINCT kickoff.kickoff_at)
                FROM football.match_kickoff_claims AS kickoff
                JOIN football.match_lifecycle_claims AS lifecycle
                  ON lifecycle.id = kickoff.lifecycle_claim_id
                JOIN football.match_observations AS observation
                  ON observation.id = kickoff.match_observation_id
                WHERE kickoff.season_id = %s
                  AND kickoff.claim_version = %s
                  AND kickoff.timezone_name = %s
                  AND kickoff.tzdata_version = %s
                  AND lifecycle.claim_version = %s
                  AND observation.home_score IS NOT NULL
                  AND observation.away_score IS NOT NULL
                """,
                (
                    season_id,
                    KICKOFF_CLAIM_VERSION,
                    KICKOFF_TIMEZONE,
                    TZDATA_VERSION,
                    LIFECYCLE_CLAIM_VERSION,
                ),
            ).fetchone()
        return (int(row[0]), int(row[1])) if row is not None else (0, 0)

    def _coverage(self, season_id: UUID) -> EvaluationCoverageV1:
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT
                    count(DISTINCT match.id),
                    count(DISTINCT match.id) FILTER (
                        WHERE claim.id IS NOT NULL
                    ),
                    count(DISTINCT match.id) FILTER (
                        WHERE claim.id IS NOT NULL
                          AND observation.home_score IS NOT NULL
                          AND observation.away_score IS NOT NULL
                    ),
                    count(DISTINCT match.id) FILTER (
                        WHERE claim.id IS NOT NULL
                          AND observation.home_score IS NOT NULL
                          AND observation.away_score IS NOT NULL
                          AND corner.id IS NOT NULL
                    )
                FROM football.matches AS match
                LEFT JOIN football.match_lifecycle_claims AS claim
                  ON claim.match_id = match.id
                 AND claim.claim_version = %s
                 AND claim.lifecycle = 'completed'
                LEFT JOIN football.match_observations AS observation
                  ON observation.id = claim.match_observation_id
                LEFT JOIN football.match_corner_labels AS corner
                  ON corner.match_id = match.id
                 AND corner.lifecycle_claim_id = claim.id
                 AND corner.claim_version = %s
                WHERE match.season_id = %s
                """,
                (LIFECYCLE_CLAIM_VERSION, CORNER_LABEL_VERSION, season_id),
            ).fetchone()
        if row is None:
            return EvaluationCoverageV1()
        return EvaluationCoverageV1(
            registered_matches=int(row[0]),
            completed_matches=int(row[1]),
            scored_targets=int(row[2]),
            corner_labelled_targets=int(row[3]),
        )


def _evaluation_id(
    completed_at: datetime,
    corpus: EvaluationCorpusV1,
    coverage: EvaluationCoverageV1,
    stage: str,
    findings: tuple[str, ...],
) -> UUID:
    identity = {
        "completed_at": completed_at.isoformat(),
        "corpus": corpus.to_dict(),
        "coverage": coverage.to_dict(),
        "stage": stage,
        "findings": list(findings),
    }
    digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return uuid5(_EVALUATION_NAMESPACE, digest)


def _minimum_corner_labels(scored_targets: int) -> int:
    return (scored_targets * _MINIMUM_CORNER_LABEL_PERCENT + 99) // 100
