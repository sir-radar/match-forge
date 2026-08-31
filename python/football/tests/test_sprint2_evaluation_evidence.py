from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pyarrow.parquet as parquet
from football.forecasting.calibration_analysis import Sprint2CalibrationAnalyzerV1
from football.forecasting.contracts import (
    CornerForecastPayloadV1,
    GoalForecastPayloadV1,
    MatchResultProbabilitiesV1,
)
from football.forecasting.dataset import (
    EligibleForecastTargetV1,
    EvaluationMatchOutcomeV1,
    ForecastMatchContextV1,
    ImmutableWalkForwardTargetPlanStore,
    WalkForwardDatasetSpecV1,
    WalkForwardTargetBatchV1,
    WalkForwardTargetPlanV1,
)
from football.forecasting.evaluation_run import Sprint2EvaluationRunner
from football.forecasting.evidence import (
    Sprint2EvaluationEvidenceStore,
    Sprint2EvidenceProvenanceV1,
)
from football.forecasting.execution import Sprint2ExecutionResultV1, Sprint2RawForecastV1
from football.forecasting.scoring import Sprint2Scorer
from football.forecasting.uncertainty import (
    BootstrapPolicyV1,
    paired_moving_block_bootstrap,
)


def test_evaluation_evidence_is_immutable_complete_and_machine_readable(
    tmp_path: Path,
) -> None:
    run_id = UUID(int=900)
    forecast, outcome, plan = _evidence_inputs()
    plan_publication = ImmutableWalkForwardTargetPlanStore(tmp_path).publish(plan)
    scorer = Sprint2Scorer()
    metrics = scorer.evaluate((forecast,), (outcome,))
    comparisons = scorer.comparison_rows((forecast,), (outcome,))
    bootstrap = paired_moving_block_bootstrap(
        scorer.paired_metric_series(comparisons),
        BootstrapPolicyV1(replicates=10, block_size=1, seed=5),
    )
    calibration = Sprint2CalibrationAnalyzerV1().analyze((forecast,), (outcome,))
    store = Sprint2EvaluationEvidenceStore(tmp_path)

    first = store.publish(
        evaluation_run_id=run_id,
        target_plan=plan_publication,
        forecasts=(forecast,),
        outcomes=(outcome,),
        raw_metrics=metrics,
        comparison_rows=comparisons,
        bootstrap=bootstrap,
        calibration=calibration,
        provenance=Sprint2EvidenceProvenanceV1("a" * 40, "b" * 64),
    )
    retry = store.publish(
        evaluation_run_id=run_id,
        target_plan=plan_publication,
        forecasts=(forecast,),
        outcomes=(outcome,),
        raw_metrics=metrics,
        comparison_rows=comparisons,
        bootstrap=bootstrap,
        calibration=calibration,
        provenance=Sprint2EvidenceProvenanceV1("a" * 40, "b" * 64),
    )

    assert first.status == "published"
    assert retry.status == "verified_existing"
    assert retry.manifest == first.manifest
    names = {item.name for item in first.manifest.files}
    assert names == {
        "predictions",
        "outcomes",
        "comparison_rows",
        "raw_metrics",
        "paired_bootstrap",
        "calibration_predictions",
        "calibration_bins",
        "calibration_metrics",
        "calibration_reliability_plot",
        "calibration_histogram_plot",
    }
    prediction_file = next(item for item in first.manifest.files if item.name == "predictions")
    table = parquet.read_table(tmp_path / prediction_file.relative_path)
    assert table.num_rows == 1
    payload = json.loads((tmp_path / first.manifest_relative_path).read_text(encoding="utf-8"))
    assert payload["target_set_sha256"] == plan.target_set_sha256
    assert payload["bootstrap_policy"]["seed"] == 5


def test_evaluation_runner_executes_and_retains_analysis(tmp_path: Path) -> None:
    forecast, outcome, plan = _evidence_inputs()
    metrics = Sprint2Scorer().evaluate((forecast,), (outcome,))
    executor = _Executor(Sprint2ExecutionResultV1(1, 1, 4, (forecast,), (outcome,), metrics))
    target_plan = ImmutableWalkForwardTargetPlanStore(tmp_path).publish(plan)
    runner = Sprint2EvaluationRunner(
        executor=executor,
        evidence_store=Sprint2EvaluationEvidenceStore(tmp_path),
        bootstrap_policy=BootstrapPolicyV1(replicates=10, block_size=1, seed=9),
    )

    result = runner.run(
        evaluation_run_id=UUID(int=901),
        target_plan=target_plan,
        provenance=Sprint2EvidenceProvenanceV1("a" * 40, "b" * 64),
    )

    assert executor.plan == plan
    assert result.execution.target_count == 1
    assert result.bootstrap.policy.seed == 9
    assert result.evidence.status == "published"


class _Executor:
    def __init__(self, result: Sprint2ExecutionResultV1) -> None:
        self.result = result
        self.plan: WalkForwardTargetPlanV1 | None = None

    def execute(self, plan: WalkForwardTargetPlanV1) -> Sprint2ExecutionResultV1:
        self.plan = plan
        return self.result


def _evidence_inputs() -> tuple[
    Sprint2RawForecastV1, EvaluationMatchOutcomeV1, WalkForwardTargetPlanV1
]:
    kickoff = datetime(2016, 1, 1, 15, 0, tzinfo=UTC)
    context = ForecastMatchContextV1(
        UUID(int=1), UUID(int=2), UUID(int=3), kickoff, UUID(int=4), UUID(int=5)
    )
    result = MatchResultProbabilitiesV1(0.5, 0.3, 0.2)
    goal = GoalForecastPayloadV1(
        lambda_home=1.5,
        lambda_away=1.0,
        score_labels=("0", "1", "2+"),
        score_probabilities=((0.1, 0.1, 0.1), (0.1, 0.2, 0.1), (0.1, 0.1, 0.1)),
        over_0_5=0.9,
        over_1_5=0.7,
        over_2_5=0.5,
        over_3_5=0.3,
        over_4_5=0.1,
        btts_yes=0.45,
        home_clean_sheet=0.35,
        away_clean_sheet=0.2,
    )
    corners = CornerForecastPayloadV1("poisson", 5.0, 4.0, 5.0, 4.0, None)
    forecast = Sprint2RawForecastV1(
        context=context,
        elo_result=result,
        dixon_coles_result=result,
        goal=goal,
        corner_poisson=corners,
        corner_negative_binomial=CornerForecastPayloadV1(
            "negative_binomial", 5.0, 4.0, 7.5, 5.6, 0.1
        ),
        result_reference=MatchResultProbabilitiesV1(0.4, 0.3, 0.3),
        goal_reference=goal,
        corner_reference=corners,
    )
    outcome = EvaluationMatchOutcomeV1(
        context.match_id, kickoff, 2, 1, 6, 4, kickoff + timedelta(hours=2)
    )
    spec = WalkForwardDatasetSpecV1(
        dataset_version_id=UUID(int=6),
        source_snapshot_id=UUID(int=7),
        feature_set_version="sprint2-team-counts-v1",
        knowledge_cutoff=kickoff + timedelta(days=1),
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256="c" * 64,
        minimum_team_history=10,
        minimum_competition_history=100,
    )
    batch = WalkForwardTargetBatchV1(kickoff, (EligibleForecastTargetV1(context, 10, 10, 100),))
    plan = WalkForwardTargetPlanV1(
        spec, context.competition_id, context.season_id, (batch,), 101, 100
    )
    return forecast, outcome, plan
