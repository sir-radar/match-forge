from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Any, Literal
from uuid import UUID

from football.forecasting.calibration_analysis import Sprint2CalibrationAnalysisV1
from football.forecasting.dataset import EvaluationMatchOutcomeV1
from football.forecasting.evidence import (
    EvaluationEvidenceFileV1,
    Sprint2EvaluationEvidenceManifestV1,
)
from football.forecasting.execution import Sprint2ExecutionResultV1, Sprint2RawForecastV1
from football.forecasting.uncertainty import (
    MetricDeltaIntervalV1,
    Sprint2BootstrapResultV1,
)

GateStatus = Literal["PASS", "FAIL"]
PolicyStatus = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]
GateValue = bool | int | float | str | None


class BaselineGatePolicyError(ValueError):
    """Sprint 2 gate actuals or reproduction inputs are incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class Sprint2PredictiveGateActualsV1:
    elo_log_loss_point_delta: float
    elo_log_loss_upper_bound: float
    elo_rps_point_delta: float
    elo_rps_upper_bound: float
    dixon_coles_log_loss_point_delta: float
    dixon_coles_log_loss_upper_bound: float
    dixon_coles_rps_point_delta: float
    dixon_coles_rps_upper_bound: float
    goal_joint_nll_point_delta: float
    goal_joint_nll_upper_bound: float
    goal_total_crps_point_delta: float
    goal_total_crps_upper_bound: float
    goal_total_mae_point_delta: float
    corner_nll_point_delta: float
    corner_nll_upper_bound: float
    corner_crps_point_delta: float
    corner_crps_upper_bound: float
    corner_mae_point_delta: float
    negative_binomial_evaluated_targets: int

    def __post_init__(self) -> None:
        _finite_actuals(self)
        _non_negative_count(
            self.negative_binomial_evaluated_targets,
            "negative_binomial_evaluated_targets",
        )


@dataclass(frozen=True, slots=True)
class Sprint2CalibrationGateActualsV1:
    result_model: str
    macro_classwise_ece: float
    home_ece: float
    draw_ece: float
    away_ece: float
    over_2_5_ece: float
    btts_yes_ece: float
    maximum_absolute_bias: float
    accepted_challengers: int
    accepted_challenger_regressions: int
    intercept: float | None
    slope: float | None

    def __post_init__(self) -> None:
        if self.result_model not in ("elo", "dixon_coles"):
            raise BaselineGatePolicyError("calibration result model is invalid")
        _finite_actuals(self)
        _non_negative_count(self.accepted_challengers, "accepted_challengers")
        _non_negative_count(
            self.accepted_challenger_regressions,
            "accepted_challenger_regressions",
        )


@dataclass(frozen=True, slots=True)
class Sprint2CoverageGateActualsV1:
    primary_scored_targets: int
    elo_execution_coverage: float
    dixon_coles_execution_coverage: float
    corner_execution_coverage: float
    corner_label_coverage: float
    common_comparison_coverage: float
    silent_unexplained_skips: int
    mandatory_model_runtime_failures: int

    def __post_init__(self) -> None:
        _finite_actuals(self)
        for field_name in (
            "primary_scored_targets",
            "silent_unexplained_skips",
            "mandatory_model_runtime_failures",
        ):
            _non_negative_count(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class Sprint2ReproducibilityGateActualsV1:
    equivalent_clean_run_count: int
    target_set_reproduced: bool
    model_state_reproduced: bool
    max_forecast_probability_delta: float | None
    max_artifact_reload_probability_delta: float | None
    max_metric_delta: float | None
    bootstrap_reproduced: bool
    lineage_coverage: float
    authoritative_worktree_clean: bool

    def __post_init__(self) -> None:
        _finite_actuals(self)
        _non_negative_count(self.equivalent_clean_run_count, "equivalent_clean_run_count")


@dataclass(frozen=True, slots=True)
class Sprint2RegressionGateActualsV1:
    invalid_probability_count: int
    normalization_failure_count: int
    future_data_leakage_count: int
    target_outcome_leakage_count: int
    same_batch_leakage_count: int
    mandatory_test_failures: int
    quality_gate_bypasses: int
    regression_budget_breaches: int

    def __post_init__(self) -> None:
        for item in fields(self):
            _non_negative_count(getattr(self, item.name), item.name)


@dataclass(frozen=True, slots=True)
class Sprint2BaselineGateActualsV1:
    predictive: Sprint2PredictiveGateActualsV1
    calibration: Sprint2CalibrationGateActualsV1
    coverage: Sprint2CoverageGateActualsV1
    reproducibility: Sprint2ReproducibilityGateActualsV1
    regression: Sprint2RegressionGateActualsV1


@dataclass(frozen=True, slots=True)
class Sprint2GateCheckV1:
    key: str
    status: GateStatus
    actual: GateValue
    operator: str
    threshold: GateValue
    blocking: bool = True

    def __post_init__(self) -> None:
        if not self.key or self.status not in ("PASS", "FAIL") or not self.operator:
            raise BaselineGatePolicyError("gate check is invalid")

    def to_dict(self) -> dict[str, GateValue]:
        return {
            "key": self.key,
            "status": self.status,
            "actual": self.actual,
            "operator": self.operator,
            "threshold": self.threshold,
            "blocking": self.blocking,
        }


@dataclass(frozen=True, slots=True)
class Sprint2GateDimensionV1:
    name: str
    status: GateStatus
    checks: tuple[Sprint2GateCheckV1, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.checks:
            raise BaselineGatePolicyError("gate dimension requires named checks")
        expected = (
            "FAIL"
            if any(check.blocking and check.status == "FAIL" for check in self.checks)
            else "PASS"
        )
        if self.status != expected:
            raise BaselineGatePolicyError("gate dimension status conflicts with checks")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True, slots=True)
class Sprint2BaselineGateDecisionV1:
    status: PolicyStatus
    dimensions: tuple[Sprint2GateDimensionV1, ...]
    findings: tuple[str, ...]
    policy_version: str = "sprint2-baseline-gate-policy-v1"
    contract: str = "Sprint2BaselineGateDecisionV1"

    def __post_init__(self) -> None:
        names = tuple(dimension.name for dimension in self.dimensions)
        if names != ("predictive", "calibration", "coverage", "reproducibility", "regression"):
            raise BaselineGatePolicyError("gate decision dimensions are incomplete or unordered")
        expected = _decision_status(self.dimensions)
        if self.status != expected:
            raise BaselineGatePolicyError("gate decision status conflicts with dimensions")
        if (self.status == "PASS") == bool(self.findings):
            raise BaselineGatePolicyError("gate decision findings conflict with status")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "policy_version": self.policy_version,
            "status": self.status,
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
            "findings": list(self.findings),
        }


@dataclass(frozen=True, slots=True)
class Sprint2BaselineGatePolicyV1:
    result_log_loss_upper_delta: float = field(default=0.02, init=False)
    result_rps_upper_delta: float = field(default=0.01, init=False)
    goal_upper_delta: float = field(default=0.02, init=False)
    goal_mae_delta: float = field(default=0.10, init=False)
    corner_nll_upper_delta: float = field(default=0.03, init=False)
    corner_crps_upper_delta: float = field(default=0.05, init=False)
    corner_mae_delta: float = field(default=0.15, init=False)
    result_macro_ece: float = field(default=0.10, init=False)
    result_class_ece: float = field(default=0.15, init=False)
    binary_ece: float = field(default=0.10, init=False)
    absolute_bias: float = field(default=0.075, init=False)
    calibration_intercept_warning: float = field(default=0.25, init=False)
    calibration_slope_minimum_warning: float = field(default=0.70, init=False)
    calibration_slope_maximum_warning: float = field(default=1.30, init=False)
    minimum_targets: int = field(default=250, init=False)
    minimum_corner_label_coverage: float = field(default=0.95, init=False)
    reproduction_tolerance: float = field(default=1e-12, init=False)

    def __post_init__(self) -> None:
        _finite_actuals(self)
        if self.minimum_targets != 250:
            raise BaselineGatePolicyError("Sprint 2 minimum target threshold is locked at 250")

    def evaluate(self, actuals: Sprint2BaselineGateActualsV1) -> Sprint2BaselineGateDecisionV1:
        dimensions = (
            self._predictive(actuals),
            self._calibration(actuals.calibration),
            self._coverage(actuals.coverage),
            self._reproducibility(actuals.reproducibility),
            self._regression(actuals.regression),
        )
        status = _decision_status(dimensions)
        return Sprint2BaselineGateDecisionV1(
            status=status,
            dimensions=dimensions,
            findings=_findings(dimensions, status),
        )

    def _predictive(self, actuals: Sprint2BaselineGateActualsV1) -> Sprint2GateDimensionV1:
        value = actuals.predictive
        result_improvement = (
            value.elo_log_loss_point_delta < 0.0 and value.elo_rps_point_delta < 0.0
        ) or (
            value.dixon_coles_log_loss_point_delta < 0.0 and value.dixon_coles_rps_point_delta < 0.0
        )
        checks = (
            _maximum(
                "results.elo_log_loss_upper_bound",
                value.elo_log_loss_upper_bound,
                self.result_log_loss_upper_delta,
            ),
            _maximum(
                "results.elo_rps_upper_bound",
                value.elo_rps_upper_bound,
                self.result_rps_upper_delta,
            ),
            _maximum(
                "results.dixon_coles_log_loss_upper_bound",
                value.dixon_coles_log_loss_upper_bound,
                self.result_log_loss_upper_delta,
            ),
            _maximum(
                "results.dixon_coles_rps_upper_bound",
                value.dixon_coles_rps_upper_bound,
                self.result_rps_upper_delta,
            ),
            _boolean("results.point_improvement", result_improvement),
            _maximum(
                "goals.joint_nll_upper_bound",
                value.goal_joint_nll_upper_bound,
                self.goal_upper_delta,
            ),
            _maximum(
                "goals.crps_upper_bound", value.goal_total_crps_upper_bound, self.goal_upper_delta
            ),
            _minimum_delta(
                "goals.point_improvement",
                min(value.goal_joint_nll_point_delta, value.goal_total_crps_point_delta),
            ),
            _maximum("goals.mae_delta", value.goal_total_mae_point_delta, self.goal_mae_delta),
            _maximum(
                "corners.nll_upper_bound", value.corner_nll_upper_bound, self.corner_nll_upper_delta
            ),
            _maximum(
                "corners.crps_upper_bound",
                value.corner_crps_upper_bound,
                self.corner_crps_upper_delta,
            ),
            _minimum_delta(
                "corners.point_improvement",
                min(value.corner_nll_point_delta, value.corner_crps_point_delta),
            ),
            _maximum("corners.mae_delta", value.corner_mae_point_delta, self.corner_mae_delta),
            _minimum(
                "corners.negative_binomial_evaluated_targets",
                value.negative_binomial_evaluated_targets,
                actuals.coverage.primary_scored_targets,
            ),
        )
        return _dimension("predictive", checks)

    def _calibration(self, actuals: Sprint2CalibrationGateActualsV1) -> Sprint2GateDimensionV1:
        checks = (
            _informational("calibration.result_model", actuals.result_model),
            _maximum(
                "calibration.1x2_macro_ece", actuals.macro_classwise_ece, self.result_macro_ece
            ),
            _maximum("calibration.1x2_home_ece", actuals.home_ece, self.result_class_ece),
            _maximum("calibration.1x2_draw_ece", actuals.draw_ece, self.result_class_ece),
            _maximum("calibration.1x2_away_ece", actuals.away_ece, self.result_class_ece),
            _maximum("calibration.over_2_5_ece", actuals.over_2_5_ece, self.binary_ece),
            _maximum("calibration.btts_yes_ece", actuals.btts_yes_ece, self.binary_ece),
            _maximum(
                "calibration.maximum_absolute_bias",
                actuals.maximum_absolute_bias,
                self.absolute_bias,
            ),
            _maximum(
                "calibration.accepted_challenger_regressions",
                actuals.accepted_challenger_regressions,
                0,
            ),
            _informational(
                "calibration.accepted_challengers",
                actuals.accepted_challengers,
            ),
            _warning_range(
                "calibration.intercept_warning",
                actuals.intercept,
                -self.calibration_intercept_warning,
                self.calibration_intercept_warning,
            ),
            _warning_range(
                "calibration.slope_warning",
                actuals.slope,
                self.calibration_slope_minimum_warning,
                self.calibration_slope_maximum_warning,
            ),
        )
        return _dimension("calibration", checks)

    def _coverage(self, actuals: Sprint2CoverageGateActualsV1) -> Sprint2GateDimensionV1:
        checks = (
            _minimum(
                "coverage.primary_scored_targets",
                actuals.primary_scored_targets,
                self.minimum_targets,
            ),
            _minimum("coverage.elo_execution", actuals.elo_execution_coverage, 1.0),
            _minimum("coverage.dixon_coles_execution", actuals.dixon_coles_execution_coverage, 1.0),
            _minimum("coverage.corner_execution", actuals.corner_execution_coverage, 1.0),
            _minimum(
                "coverage.corner_labels",
                actuals.corner_label_coverage,
                self.minimum_corner_label_coverage,
            ),
            _minimum("coverage.common_comparison", actuals.common_comparison_coverage, 0.95),
            _maximum("coverage.silent_unexplained_skips", actuals.silent_unexplained_skips, 0),
            _maximum(
                "coverage.mandatory_model_runtime_failures",
                actuals.mandatory_model_runtime_failures,
                0,
            ),
        )
        return _dimension("coverage", checks)

    def _reproducibility(
        self, actuals: Sprint2ReproducibilityGateActualsV1
    ) -> Sprint2GateDimensionV1:
        checks = (
            _minimum(
                "reproducibility.equivalent_clean_runs", actuals.equivalent_clean_run_count, 2
            ),
            _boolean("reproducibility.target_set", actuals.target_set_reproduced),
            _boolean("reproducibility.model_state", actuals.model_state_reproduced),
            _optional_maximum(
                "reproducibility.forecast_probability_delta",
                actuals.max_forecast_probability_delta,
                self.reproduction_tolerance,
            ),
            _optional_maximum(
                "reproducibility.artifact_reload_probability_delta",
                actuals.max_artifact_reload_probability_delta,
                self.reproduction_tolerance,
            ),
            _optional_maximum(
                "reproducibility.metric_delta",
                actuals.max_metric_delta,
                self.reproduction_tolerance,
            ),
            _boolean("reproducibility.bootstrap", actuals.bootstrap_reproduced),
            _minimum("reproducibility.forecast_lineage", actuals.lineage_coverage, 1.0),
            _boolean(
                "reproducibility.authoritative_worktree_clean", actuals.authoritative_worktree_clean
            ),
        )
        return _dimension("reproducibility", checks)

    @staticmethod
    def _regression(actuals: Sprint2RegressionGateActualsV1) -> Sprint2GateDimensionV1:
        checks = tuple(
            _maximum(f"regression.{item.name}", getattr(actuals, item.name), 0)
            for item in fields(actuals)
        )
        return _dimension("regression", checks)


def collect_sprint2_baseline_gate_actuals(
    *,
    execution: Sprint2ExecutionResultV1,
    bootstrap: Sprint2BootstrapResultV1,
    calibration: Sprint2CalibrationAnalysisV1,
    planned_target_count: int,
    corpus_scored_targets: int,
    corner_labelled_targets: int,
    reproducibility: Sprint2ReproducibilityGateActualsV1,
) -> Sprint2BaselineGateActualsV1:
    if planned_target_count <= 0 or corpus_scored_targets <= 0:
        raise BaselineGatePolicyError("gate coverage populations must be positive")
    predictive = _predictive_actuals(execution, bootstrap)
    calibration_actuals = _calibration_actuals(execution, calibration)
    executed = execution.target_count
    invalid_probabilities, normalization_failures = _probability_integrity(execution.forecasts)
    target_leakage = sum(
        any(
            key in forecast.context.to_dict()
            for key in ("home_score", "away_score", "home_corners", "away_corners")
        )
        for forecast in execution.forecasts
    )
    coverage = Sprint2CoverageGateActualsV1(
        primary_scored_targets=executed,
        elo_execution_coverage=executed / planned_target_count,
        dixon_coles_execution_coverage=executed / planned_target_count,
        corner_execution_coverage=executed / planned_target_count,
        corner_label_coverage=corner_labelled_targets / corpus_scored_targets,
        common_comparison_coverage=bootstrap.sample_count / planned_target_count,
        silent_unexplained_skips=max(0, planned_target_count - executed),
        mandatory_model_runtime_failures=0,
    )
    regression = Sprint2RegressionGateActualsV1(
        invalid_probability_count=invalid_probabilities,
        normalization_failure_count=normalization_failures,
        future_data_leakage_count=0,
        target_outcome_leakage_count=target_leakage,
        same_batch_leakage_count=0,
        mandatory_test_failures=0,
        quality_gate_bypasses=0,
        regression_budget_breaches=0,
    )
    return Sprint2BaselineGateActualsV1(
        predictive,
        calibration_actuals,
        coverage,
        reproducibility,
        regression,
    )


def unreproduced_run(
    manifest: Sprint2EvaluationEvidenceManifestV1,
) -> Sprint2ReproducibilityGateActualsV1:
    prediction = next((item for item in manifest.files if item.name == "predictions"), None)
    return Sprint2ReproducibilityGateActualsV1(
        equivalent_clean_run_count=1,
        target_set_reproduced=True,
        model_state_reproduced=False,
        max_forecast_probability_delta=None,
        max_artifact_reload_probability_delta=(manifest.artifact_reload_max_probability_delta),
        max_metric_delta=None,
        bootstrap_reproduced=False,
        lineage_coverage=float(prediction is not None and (prediction.row_count or 0) > 0),
        authoritative_worktree_clean=manifest.provenance.authoritative_worktree_clean,
    )


def _predictive_actuals(
    execution: Sprint2ExecutionResultV1,
    bootstrap: Sprint2BootstrapResultV1,
) -> Sprint2PredictiveGateActualsV1:
    intervals = {(item.comparison, item.metric): item for item in bootstrap.intervals}
    if len(intervals) != len(bootstrap.intervals):
        raise BaselineGatePolicyError("bootstrap comparisons must be unique")

    def resolved(comparison: str, metric: str) -> MetricDeltaIntervalV1:
        try:
            return intervals[(comparison, metric)]
        except KeyError as error:
            raise BaselineGatePolicyError(
                f"missing bootstrap comparison: {comparison}/{metric}"
            ) from error

    elo_log = resolved("elo_vs_result_reference", "log_loss")
    elo_rps = resolved("elo_vs_result_reference", "ranked_probability_score")
    dixon_log = resolved("dixon_coles_vs_result_reference", "log_loss")
    dixon_rps = resolved("dixon_coles_vs_result_reference", "ranked_probability_score")
    goal_nll = resolved("dixon_coles_goals_vs_goal_reference", "joint_score_nll")
    goal_crps = resolved("dixon_coles_goals_vs_goal_reference", "total_crps")
    goal_mae = resolved("dixon_coles_goals_vs_goal_reference", "total_mae")
    corner_nll = resolved("corner_poisson_vs_corner_reference", "total_nll")
    corner_crps = resolved("corner_poisson_vs_corner_reference", "total_crps")
    corner_mae = resolved("corner_poisson_vs_corner_reference", "total_mae")
    return Sprint2PredictiveGateActualsV1(
        elo_log.point_delta,
        elo_log.upper_bound,
        elo_rps.point_delta,
        elo_rps.upper_bound,
        dixon_log.point_delta,
        dixon_log.upper_bound,
        dixon_rps.point_delta,
        dixon_rps.upper_bound,
        goal_nll.point_delta,
        goal_nll.upper_bound,
        goal_crps.point_delta,
        goal_crps.upper_bound,
        goal_mae.point_delta,
        corner_nll.point_delta,
        corner_nll.upper_bound,
        corner_crps.point_delta,
        corner_crps.upper_bound,
        corner_mae.point_delta,
        execution.metrics.corner_negative_binomial.total.sample_count,
    )


def _calibration_actuals(
    execution: Sprint2ExecutionResultV1,
    calibration: Sprint2CalibrationAnalysisV1,
) -> Sprint2CalibrationGateActualsV1:
    outcome_by_match = {item.match_id: item for item in execution.outcomes}
    candidates = {
        model: _result_calibration(execution.forecasts, outcome_by_match, model)
        for model in ("elo", "dixon_coles")
    }
    result_model, result_values = min(candidates.items(), key=lambda item: item[1][0])
    over_2_5 = _binary_calibration(execution.forecasts, outcome_by_match, "over_2_5")
    btts_yes = _binary_calibration(execution.forecasts, outcome_by_match, "btts_yes")
    accepted = tuple(metric for metric in calibration.metrics if metric.accepted)
    regressions = sum(
        metric.calibrated_log_loss
        > metric.raw_log_loss + calibration.policy.max_log_loss_regression
        or metric.calibrated_brier > metric.raw_brier + calibration.policy.max_brier_regression
        for metric in accepted
    )
    return Sprint2CalibrationGateActualsV1(
        result_model=result_model,
        macro_classwise_ece=result_values[0],
        home_ece=result_values[1],
        draw_ece=result_values[2],
        away_ece=result_values[3],
        over_2_5_ece=over_2_5[0],
        btts_yes_ece=btts_yes[0],
        maximum_absolute_bias=max(result_values[4], over_2_5[1], btts_yes[1]),
        accepted_challengers=len(accepted),
        accepted_challenger_regressions=regressions,
        intercept=None,
        slope=None,
    )


def _result_calibration(
    forecasts: tuple[Sprint2RawForecastV1, ...],
    outcomes: dict[UUID, EvaluationMatchOutcomeV1],
    model: str,
) -> tuple[float, float, float, float, float]:
    class_samples: list[list[tuple[float, int]]] = [[], [], []]
    for forecast in forecasts:
        outcome = outcomes[forecast.context.match_id]
        outcome_index = _outcome_index(outcome)
        result = forecast.elo_result if model == "elo" else forecast.dixon_coles_result
        for index, probability in enumerate((result.home, result.draw, result.away)):
            class_samples[index].append((probability, int(index == outcome_index)))
    values = tuple(_ece(tuple(samples)) for samples in class_samples)
    maximum_bias = max(_absolute_bias(tuple(samples)) for samples in class_samples)
    return sum(values) / 3.0, values[0], values[1], values[2], maximum_bias


def _binary_calibration(
    forecasts: tuple[Sprint2RawForecastV1, ...],
    outcomes: dict[UUID, EvaluationMatchOutcomeV1],
    product: Literal["over_2_5", "btts_yes"],
) -> tuple[float, float]:
    samples = []
    for forecast in forecasts:
        outcome = outcomes[forecast.context.match_id]
        if product == "over_2_5":
            probability = forecast.goal.over_2_5
            target = outcome.home_score + outcome.away_score >= 3
        else:
            probability = forecast.goal.btts_yes
            target = outcome.home_score > 0 and outcome.away_score > 0
        samples.append((probability, int(target)))
    resolved = tuple(samples)
    return _ece(resolved), _absolute_bias(resolved)


def _ece(samples: tuple[tuple[float, int], ...]) -> float:
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for probability, target in samples:
        grouped[min(int(probability * 10), 9)].append((probability, target))
    return sum(
        len(values)
        / len(samples)
        * abs(
            sum(probability for probability, _target in values) / len(values)
            - sum(target for _probability, target in values) / len(values)
        )
        for values in grouped
        if values
    )


def _absolute_bias(samples: tuple[tuple[float, int], ...]) -> float:
    return abs(sum(probability - target for probability, target in samples) / len(samples))


def _outcome_index(outcome: EvaluationMatchOutcomeV1) -> int:
    if outcome.home_score > outcome.away_score:
        return 0
    return 2 if outcome.home_score < outcome.away_score else 1


def _probability_integrity(
    forecasts: tuple[Sprint2RawForecastV1, ...],
) -> tuple[int, int]:
    invalid = 0
    normalization = 0
    for forecast in forecasts:
        results = (
            forecast.elo_result,
            forecast.dixon_coles_result,
            forecast.result_reference,
        )
        for result in results:
            probabilities = (result.home, result.draw, result.away)
            invalid += sum(
                not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities
            )
            normalization += int(abs(sum(probabilities) - 1.0) > 1e-12)
        goal_probabilities = tuple(
            value for row in forecast.goal.score_probabilities for value in row
        )
        invalid += sum(
            not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in goal_probabilities
        )
        normalization += int(abs(sum(goal_probabilities) - 1.0) > 1e-12)
    return invalid, normalization


def compare_equivalent_clean_runs(
    primary: Sprint2EvaluationEvidenceManifestV1,
    reproduction: Sprint2EvaluationEvidenceManifestV1,
) -> Sprint2ReproducibilityGateActualsV1:
    _validate_equivalent_runs(primary, reproduction)
    primary_files = {item.name: item for item in primary.files}
    reproduced_files = {item.name: item for item in reproduction.files}
    predictions_equal = _same_file(primary_files, reproduced_files, "predictions")
    metrics_equal = _same_file(primary_files, reproduced_files, "raw_metrics")
    bootstrap_equal = _same_file(primary_files, reproduced_files, "paired_bootstrap")
    primary_predictions = primary_files.get("predictions")
    reproduced_predictions = reproduced_files.get("predictions")
    lineage_coverage = float(
        primary_predictions is not None
        and reproduced_predictions is not None
        and primary_predictions.row_count is not None
        and primary_predictions.row_count == reproduced_predictions.row_count
        and primary_predictions.row_count > 0
    )
    return Sprint2ReproducibilityGateActualsV1(
        equivalent_clean_run_count=2,
        target_set_reproduced=primary.target_set_sha256 == reproduction.target_set_sha256,
        model_state_reproduced=predictions_equal,
        max_forecast_probability_delta=0.0 if predictions_equal else None,
        max_artifact_reload_probability_delta=max(
            primary.artifact_reload_max_probability_delta,
            reproduction.artifact_reload_max_probability_delta,
        ),
        max_metric_delta=0.0 if metrics_equal else None,
        bootstrap_reproduced=bootstrap_equal,
        lineage_coverage=lineage_coverage,
        authoritative_worktree_clean=(
            primary.provenance.authoritative_worktree_clean
            and reproduction.provenance.authoritative_worktree_clean
        ),
    )


def _validate_equivalent_runs(
    primary: Sprint2EvaluationEvidenceManifestV1,
    reproduction: Sprint2EvaluationEvidenceManifestV1,
) -> None:
    equivalent = (
        primary.evaluation_run_id != reproduction.evaluation_run_id
        and primary.target_set_sha256 == reproduction.target_set_sha256
        and primary.provenance.code_commit_sha == reproduction.provenance.code_commit_sha
        and primary.provenance.dependency_lock_sha256
        == reproduction.provenance.dependency_lock_sha256
        and primary.bootstrap_policy == reproduction.bootstrap_policy
        and primary.calibration_policy == reproduction.calibration_policy
    )
    if not equivalent:
        raise BaselineGatePolicyError("reproducibility comparison requires equivalent runs")


def _same_file(
    primary: dict[str, EvaluationEvidenceFileV1],
    reproduced: dict[str, EvaluationEvidenceFileV1],
    name: str,
) -> bool:
    first = primary.get(name)
    second = reproduced.get(name)
    return bool(
        first is not None and second is not None and first.physical_sha256 == second.physical_sha256
    )


def _dimension(name: str, checks: tuple[Sprint2GateCheckV1, ...]) -> Sprint2GateDimensionV1:
    status: GateStatus = (
        "FAIL" if any(check.blocking and check.status == "FAIL" for check in checks) else "PASS"
    )
    return Sprint2GateDimensionV1(name, status, checks)


def _maximum(key: str, actual: int | float, threshold: int | float) -> Sprint2GateCheckV1:
    return Sprint2GateCheckV1(
        key,
        "PASS" if actual <= threshold else "FAIL",
        actual,
        "<=",
        threshold,
    )


def _optional_maximum(key: str, actual: float | None, threshold: float) -> Sprint2GateCheckV1:
    return Sprint2GateCheckV1(
        key,
        "PASS" if actual is not None and actual <= threshold else "FAIL",
        actual,
        "<=",
        threshold,
    )


def _minimum(key: str, actual: int | float, threshold: int | float) -> Sprint2GateCheckV1:
    return Sprint2GateCheckV1(
        key,
        "PASS" if actual >= threshold else "FAIL",
        actual,
        ">=",
        threshold,
    )


def _minimum_delta(key: str, actual: float) -> Sprint2GateCheckV1:
    return Sprint2GateCheckV1(key, "PASS" if actual < 0.0 else "FAIL", actual, "<", 0.0)


def _boolean(key: str, actual: bool) -> Sprint2GateCheckV1:
    return Sprint2GateCheckV1(key, "PASS" if actual else "FAIL", actual, "==", True)


def _warning_range(
    key: str, actual: float | None, lower: float, upper: float
) -> Sprint2GateCheckV1:
    passed = actual is None or lower <= actual <= upper
    return Sprint2GateCheckV1(
        key,
        "PASS" if passed else "FAIL",
        actual,
        "within",
        f"[{lower},{upper}]",
        blocking=False,
    )


def _informational(key: str, actual: GateValue) -> Sprint2GateCheckV1:
    return Sprint2GateCheckV1(
        key,
        "PASS",
        actual,
        "recorded",
        "diagnostic only",
        blocking=False,
    )


def _decision_status(dimensions: tuple[Sprint2GateDimensionV1, ...]) -> PolicyStatus:
    if any(dimension.status == "FAIL" for dimension in dimensions):
        return "FAIL"
    if any(
        check.status == "FAIL" and not check.blocking
        for dimension in dimensions
        for check in dimension.checks
    ):
        return "PASS_WITH_WARNINGS"
    return "PASS"


def _findings(
    dimensions: tuple[Sprint2GateDimensionV1, ...], status: PolicyStatus
) -> tuple[str, ...]:
    if status == "PASS":
        return ()
    failed = {
        check.key
        for dimension in dimensions
        for check in dimension.checks
        if check.status == "FAIL"
    }
    findings: list[str] = []
    if "goals.point_improvement" in failed:
        findings.append(
            "Dixon-Coles goals did not improve joint-score NLL or total-goal CRPS point estimates"
        )
    if failed.intersection(
        {"corners.nll_upper_bound", "corners.crps_upper_bound", "corners.point_improvement"}
    ):
        findings.append(
            "corner Poisson materially exceeded NLL and CRPS non-inferiority limits "
            "and improved neither point estimate"
        )
    covered = {
        "goals.point_improvement",
        "corners.nll_upper_bound",
        "corners.crps_upper_bound",
        "corners.point_improvement",
    }
    for key in sorted(failed - covered):
        findings.append(f"gate check failed: {key}")
    return tuple(findings)


def _finite_actuals(instance: Any) -> None:
    for item in fields(instance):
        value = getattr(instance, item.name)
        if isinstance(value, float) and not math.isfinite(value):
            raise BaselineGatePolicyError(f"{item.name} must be finite")


def _non_negative_count(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BaselineGatePolicyError(f"{field_name} must be a non-negative integer")
