from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from football.forecasting.baseline_policy import (
    Sprint2BaselineGateActualsV1,
    Sprint2BaselineGatePolicyV1,
    Sprint2CalibrationGateActualsV1,
    Sprint2CoverageGateActualsV1,
    Sprint2PredictiveGateActualsV1,
    Sprint2RegressionGateActualsV1,
    Sprint2ReproducibilityGateActualsV1,
    compare_equivalent_clean_runs,
)
from football.forecasting.evidence import (
    EvaluationEvidenceFileV1,
    Sprint2EvaluationEvidenceManifestV1,
    Sprint2EvidenceProvenanceV1,
)


def test_locked_policy_records_expected_predictive_failures() -> None:
    decision = Sprint2BaselineGatePolicyV1().evaluate(_review_actuals())

    assert decision.status == "FAIL"
    assert {dimension.name: dimension.status for dimension in decision.dimensions} == {
        "predictive": "FAIL",
        "calibration": "PASS",
        "coverage": "PASS",
        "reproducibility": "PASS",
        "regression": "PASS",
    }
    predictive = decision.dimensions[0]
    assert {
        check.key for check in predictive.checks if check.blocking and check.status == "FAIL"
    } == {
        "goals.point_improvement",
        "corners.nll_upper_bound",
        "corners.crps_upper_bound",
        "corners.point_improvement",
    }
    corner_nll = next(
        check for check in predictive.checks if check.key == "corners.nll_upper_bound"
    )
    assert corner_nll.actual == 0.1334293494138387
    assert corner_nll.threshold == 0.03
    assert corner_nll.operator == "<="
    assert decision.findings == (
        "Dixon-Coles goals did not improve joint-score NLL or total-goal CRPS point estimates",
        "corner Poisson materially exceeded NLL and CRPS non-inferiority limits "
        "and improved neither point estimate",
    )


def test_locked_policy_passes_boundary_values_and_keeps_warnings_non_blocking() -> None:
    actuals = _review_actuals()
    predictive = replace(
        actuals.predictive,
        goal_joint_nll_point_delta=-0.001,
        corner_nll_upper_bound=0.03,
        corner_crps_upper_bound=0.05,
        corner_nll_point_delta=-0.001,
    )
    calibration = replace(
        actuals.calibration,
        slope=1.31,
        intercept=0.26,
    )

    decision = Sprint2BaselineGatePolicyV1().evaluate(
        replace(actuals, predictive=predictive, calibration=calibration)
    )

    assert decision.status == "PASS_WITH_WARNINGS"
    calibration_result = decision.dimensions[1]
    warning_failures = {
        check.key
        for check in calibration_result.checks
        if not check.blocking and check.status == "FAIL"
    }
    assert warning_failures == {"calibration.intercept_warning", "calibration.slope_warning"}


def test_reproducibility_requires_equivalent_clean_runs_and_exact_outputs() -> None:
    primary = _manifest(UUID(int=1), clean=True)
    reproduction = _manifest(UUID(int=2), clean=True)

    actuals = compare_equivalent_clean_runs(primary, reproduction)

    assert actuals.equivalent_clean_run_count == 2
    assert actuals.target_set_reproduced is True
    assert actuals.model_state_reproduced is True
    assert actuals.max_forecast_probability_delta == 0.0
    assert actuals.max_metric_delta == 0.0
    assert actuals.bootstrap_reproduced is True
    assert actuals.lineage_coverage == 1.0
    assert actuals.authoritative_worktree_clean is True

    changed = replace(
        reproduction,
        files=(
            replace(reproduction.files[0], physical_sha256="e" * 64),
            *reproduction.files[1:],
        ),
    )
    changed_actuals = compare_equivalent_clean_runs(primary, changed)
    assert changed_actuals.model_state_reproduced is False
    assert changed_actuals.max_forecast_probability_delta is None


def _review_actuals() -> Sprint2BaselineGateActualsV1:
    return Sprint2BaselineGateActualsV1(
        predictive=Sprint2PredictiveGateActualsV1(
            elo_log_loss_point_delta=-0.031810581946572776,
            elo_log_loss_upper_bound=-0.002278372399708321,
            elo_rps_point_delta=-0.01714477911867331,
            elo_rps_upper_bound=-0.0070044470485929695,
            dixon_coles_log_loss_point_delta=-0.004317129373794899,
            dixon_coles_log_loss_upper_bound=0.001054982093272671,
            dixon_coles_rps_point_delta=-0.001645391694426456,
            dixon_coles_rps_upper_bound=0.00028145622057049587,
            goal_joint_nll_point_delta=0.0,
            goal_joint_nll_upper_bound=0.0,
            goal_total_crps_point_delta=0.0,
            goal_total_crps_upper_bound=0.0,
            goal_total_mae_point_delta=0.0,
            corner_nll_point_delta=0.07474906843946444,
            corner_nll_upper_bound=0.1334293494138387,
            corner_crps_point_delta=0.11220273633078141,
            corner_crps_upper_bound=0.2042466708474623,
            corner_mae_point_delta=0.13830595219167047,
            negative_binomial_evaluated_targets=280,
        ),
        calibration=Sprint2CalibrationGateActualsV1(
            result_model="dixon_coles",
            macro_classwise_ece=0.02504894139011091,
            home_ece=0.014568003243822828,
            draw_ece=0.0230054088413435,
            away_ece=0.0375734120851664,
            over_2_5_ece=0.0644803530351942,
            btts_yes_ece=0.017758972754030822,
            maximum_absolute_bias=0.037573412085166395,
            accepted_challengers=3,
            accepted_challenger_regressions=0,
            intercept=0.0,
            slope=1.0,
        ),
        coverage=Sprint2CoverageGateActualsV1(
            primary_scored_targets=280,
            elo_execution_coverage=1.0,
            dixon_coles_execution_coverage=1.0,
            corner_execution_coverage=1.0,
            corner_label_coverage=1.0,
            common_comparison_coverage=1.0,
            silent_unexplained_skips=0,
            mandatory_model_runtime_failures=0,
        ),
        reproducibility=Sprint2ReproducibilityGateActualsV1(
            equivalent_clean_run_count=2,
            target_set_reproduced=True,
            model_state_reproduced=True,
            max_forecast_probability_delta=0.0,
            max_artifact_reload_probability_delta=0.0,
            max_metric_delta=0.0,
            bootstrap_reproduced=True,
            lineage_coverage=1.0,
            authoritative_worktree_clean=True,
        ),
        regression=Sprint2RegressionGateActualsV1(
            invalid_probability_count=0,
            normalization_failure_count=0,
            future_data_leakage_count=0,
            target_outcome_leakage_count=0,
            same_batch_leakage_count=0,
            mandatory_test_failures=0,
            quality_gate_bypasses=0,
            regression_budget_breaches=0,
        ),
    )


def _manifest(run_id: UUID, *, clean: bool) -> Sprint2EvaluationEvidenceManifestV1:
    return Sprint2EvaluationEvidenceManifestV1(
        evaluation_run_id=run_id,
        target_set_sha256="a" * 64,
        target_plan_path="target-plan.json",
        target_plan_sha256="b" * 64,
        provenance=Sprint2EvidenceProvenanceV1("c" * 40, "d" * 64, clean),
        bootstrap_policy={"seed": 7},
        calibration_policy={"fixed_bin_count": 10},
        artifact_reload_max_probability_delta=0.0,
        files=(
            EvaluationEvidenceFileV1(
                "predictions",
                "predictions.parquet",
                "application/vnd.apache.parquet",
                "1" * 64,
                1,
                280,
            ),
            EvaluationEvidenceFileV1(
                "raw_metrics", "raw-metrics.json", "application/json", "2" * 64, 1, None
            ),
            EvaluationEvidenceFileV1(
                "paired_bootstrap",
                "bootstrap.parquet",
                "application/vnd.apache.parquet",
                "3" * 64,
                1,
                24_000,
            ),
        ),
    )
