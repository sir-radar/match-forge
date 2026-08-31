from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from football.forecasting.calibration_analysis import (
    Sprint2CalibrationAnalysisV1,
    Sprint2CalibrationAnalyzerV1,
    Sprint2CalibrationPolicyV1,
)
from football.forecasting.dataset import (
    PublishedWalkForwardTargetPlanV1,
    WalkForwardTargetPlanV1,
)
from football.forecasting.evidence import (
    PublishedSprint2EvaluationEvidenceV1,
    Sprint2EvaluationEvidenceStore,
    Sprint2EvidenceProvenanceV1,
)
from football.forecasting.execution import Sprint2ExecutionResultV1
from football.forecasting.scoring import Sprint2ComparisonRowV1, Sprint2Scorer
from football.forecasting.uncertainty import (
    BootstrapPolicyV1,
    Sprint2BootstrapResultV1,
    paired_moving_block_bootstrap,
)


class Sprint2ExecutorPort(Protocol):
    def execute(self, plan: WalkForwardTargetPlanV1) -> Sprint2ExecutionResultV1: ...


@dataclass(frozen=True, slots=True)
class Sprint2EvaluationRunResultV1:
    execution: Sprint2ExecutionResultV1
    comparison_rows: tuple[Sprint2ComparisonRowV1, ...]
    bootstrap: Sprint2BootstrapResultV1
    calibration: Sprint2CalibrationAnalysisV1
    evidence: PublishedSprint2EvaluationEvidenceV1


class Sprint2EvaluationRunner:
    def __init__(
        self,
        *,
        executor: Sprint2ExecutorPort,
        evidence_store: Sprint2EvaluationEvidenceStore,
        bootstrap_policy: BootstrapPolicyV1 | None = None,
        calibration_policy: Sprint2CalibrationPolicyV1 | None = None,
    ) -> None:
        self._executor = executor
        self._evidence_store = evidence_store
        self._bootstrap_policy = bootstrap_policy or BootstrapPolicyV1()
        self._calibration_analyzer = Sprint2CalibrationAnalyzerV1(calibration_policy)

    def run(
        self,
        *,
        evaluation_run_id: UUID,
        target_plan: PublishedWalkForwardTargetPlanV1,
        provenance: Sprint2EvidenceProvenanceV1,
    ) -> Sprint2EvaluationRunResultV1:
        execution = self._executor.execute(target_plan.plan)
        scorer = Sprint2Scorer()
        comparison_rows = scorer.comparison_rows(execution.forecasts, execution.outcomes)
        bootstrap = paired_moving_block_bootstrap(
            scorer.paired_metric_series(comparison_rows), self._bootstrap_policy
        )
        calibration = self._calibration_analyzer.analyze(execution.forecasts, execution.outcomes)
        evidence = self._evidence_store.publish(
            evaluation_run_id=evaluation_run_id,
            target_plan=target_plan,
            forecasts=execution.forecasts,
            outcomes=execution.outcomes,
            raw_metrics=execution.metrics,
            comparison_rows=comparison_rows,
            bootstrap=bootstrap,
            calibration=calibration,
            provenance=provenance,
        )
        return Sprint2EvaluationRunResultV1(
            execution=execution,
            comparison_rows=comparison_rows,
            bootstrap=bootstrap,
            calibration=calibration,
            evidence=evidence,
        )
