"""Offline xG compatibility gate for the PitchAPI retrospective protocol."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from football.contracts.source import canonical_json_bytes
from football.validation.pitchapi_contingency import (
    PITCHAPI_RETROSPECTIVE_EVALUATION_V1,
    GateStatus,
)


class PitchApiCompatibilityError(ValueError):
    """PitchAPI compatibility evidence or policy is malformed."""


@dataclass(frozen=True, slots=True)
class PitchApiXgCompatibilityPolicyV1:
    maximum_missing_rate: float
    minimum_penalty_shots: int
    minimum_penalty_xg: float
    maximum_penalty_xg: float
    maximum_penalty_iqr: float
    maximum_penalty_median_difference: float
    minimum_calibration_shots: int
    maximum_absolute_calibration_intercept: float
    minimum_calibration_slope: float
    maximum_calibration_slope: float
    minimum_situation_shots: int
    maximum_distribution_discontinuity: float
    warning_absolute_calibration_intercept: float
    warning_minimum_calibration_slope: float
    warning_maximum_calibration_slope: float
    warning_distribution_discontinuity: float
    warning_penalty_iqr: float
    warning_penalty_median_difference: float
    calibration_method: str = "logistic-outcome-on-logit-xg"
    distribution_method: str = "two-sample-kolmogorov-smirnov"
    multiple_testing_method: str = "holm-bonferroni-descriptive-only"
    sensitivity_analysis_id: str = "PITCHAPI_XG_COMPATIBILITY_SENSITIVITY_V1"
    evaluation_protocol_id: str = PITCHAPI_RETROSPECTIVE_EVALUATION_V1
    contract: str = "PitchApiXgCompatibilityPolicyV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiXgCompatibilityPolicyV1":
            raise PitchApiCompatibilityError("unsupported xG compatibility policy")
        if self.evaluation_protocol_id != PITCHAPI_RETROSPECTIVE_EVALUATION_V1:
            raise PitchApiCompatibilityError("xG compatibility policy has the wrong protocol")
        _validate_policy_numeric_limits(self)
        _validate_policy_methods(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "evaluation_protocol_id": self.evaluation_protocol_id,
            "maximum_missing_rate": self.maximum_missing_rate,
            "minimum_penalty_shots": self.minimum_penalty_shots,
            "minimum_penalty_xg": self.minimum_penalty_xg,
            "maximum_penalty_xg": self.maximum_penalty_xg,
            "maximum_penalty_iqr": self.maximum_penalty_iqr,
            "maximum_penalty_median_difference": self.maximum_penalty_median_difference,
            "minimum_calibration_shots": self.minimum_calibration_shots,
            "maximum_absolute_calibration_intercept": (self.maximum_absolute_calibration_intercept),
            "minimum_calibration_slope": self.minimum_calibration_slope,
            "maximum_calibration_slope": self.maximum_calibration_slope,
            "minimum_situation_shots": self.minimum_situation_shots,
            "maximum_distribution_discontinuity": (self.maximum_distribution_discontinuity),
            "warning_absolute_calibration_intercept": (self.warning_absolute_calibration_intercept),
            "warning_minimum_calibration_slope": self.warning_minimum_calibration_slope,
            "warning_maximum_calibration_slope": self.warning_maximum_calibration_slope,
            "warning_distribution_discontinuity": self.warning_distribution_discontinuity,
            "warning_penalty_iqr": self.warning_penalty_iqr,
            "warning_penalty_median_difference": self.warning_penalty_median_difference,
            "calibration_method": self.calibration_method,
            "distribution_method": self.distribution_method,
            "multiple_testing_method": self.multiple_testing_method,
            "sensitivity_analysis_id": self.sensitivity_analysis_id,
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()


def _validate_policy_numeric_limits(policy: PitchApiXgCompatibilityPolicyV1) -> None:
    bounded = (
        policy.maximum_missing_rate,
        policy.minimum_penalty_xg,
        policy.maximum_penalty_xg,
        policy.maximum_penalty_iqr,
        policy.maximum_penalty_median_difference,
        policy.maximum_distribution_discontinuity,
        policy.warning_distribution_discontinuity,
        policy.warning_penalty_iqr,
        policy.warning_penalty_median_difference,
    )
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in bounded):
        raise PitchApiCompatibilityError("rate and discontinuity limits must be in [0,1]")
    calibration_limits = (
        policy.maximum_absolute_calibration_intercept,
        policy.minimum_calibration_slope,
        policy.maximum_calibration_slope,
    )
    if any(not math.isfinite(value) for value in calibration_limits) or (
        policy.maximum_absolute_calibration_intercept < 0
        or policy.minimum_calibration_slope > policy.maximum_calibration_slope
    ):
        raise PitchApiCompatibilityError("calibration limits are invalid")
    for field_name in (
        "minimum_penalty_shots",
        "minimum_calibration_shots",
        "minimum_situation_shots",
    ):
        value = getattr(policy, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PitchApiCompatibilityError(f"{field_name} must be a positive integer")
    ordered_limits = (
        policy.minimum_penalty_xg <= policy.maximum_penalty_xg,
        policy.warning_absolute_calibration_intercept
        <= policy.maximum_absolute_calibration_intercept,
        policy.minimum_calibration_slope
        <= policy.warning_minimum_calibration_slope
        <= policy.warning_maximum_calibration_slope
        <= policy.maximum_calibration_slope,
        policy.warning_distribution_discontinuity <= policy.maximum_distribution_discontinuity,
        policy.warning_penalty_iqr <= policy.maximum_penalty_iqr,
        policy.warning_penalty_median_difference <= policy.maximum_penalty_median_difference,
    )
    if not all(ordered_limits):
        raise PitchApiCompatibilityError("warning and failure thresholds are misordered")


def _validate_policy_methods(policy: PitchApiXgCompatibilityPolicyV1) -> None:
    if policy.calibration_method != "logistic-outcome-on-logit-xg":
        raise PitchApiCompatibilityError("unsupported calibration method")
    if policy.distribution_method != "two-sample-kolmogorov-smirnov":
        raise PitchApiCompatibilityError("unsupported distribution method")
    if policy.multiple_testing_method != "holm-bonferroni-descriptive-only":
        raise PitchApiCompatibilityError("unsupported multiple-testing method")
    if policy.sensitivity_analysis_id != "PITCHAPI_XG_COMPATIBILITY_SENSITIVITY_V1":
        raise PitchApiCompatibilityError("unsupported sensitivity analysis")


@dataclass(frozen=True, slots=True)
class PitchApiXgScopeDiagnosticsV1:
    scope_key: str
    shot_count: int
    missing_xg_count: int
    invalid_xg_count: int
    schema_consistent: bool
    penalty_semantics_consistent: bool
    shot_situation_semantics_consistent: bool
    period_semantics_consistent: bool
    xg_mean: float
    xg_standard_deviation: float
    xg_quantiles: tuple[float, float, float]
    penalty_shot_count: int
    penalty_xg_minimum: float | None
    penalty_xg_maximum: float | None
    penalty_xg_median: float | None
    penalty_xg_iqr: float | None
    calibration_shot_count: int
    calibration_intercept: float | None
    calibration_slope: float | None
    situation_shot_counts: tuple[tuple[str, int], ...]
    contract: str = "PitchApiXgScopeDiagnosticsV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiXgScopeDiagnosticsV1" or not self.scope_key:
            raise PitchApiCompatibilityError("unsupported or unnamed xG scope diagnostics")
        _validate_diagnostic_counts(self)
        _validate_diagnostic_distribution(self)
        _validate_penalty_diagnostics(self)
        _validate_situation_counts(self)


def _validate_diagnostic_counts(diagnostic: PitchApiXgScopeDiagnosticsV1) -> None:
    counts = (
        diagnostic.shot_count,
        diagnostic.missing_xg_count,
        diagnostic.invalid_xg_count,
        diagnostic.penalty_shot_count,
        diagnostic.calibration_shot_count,
    )
    if (
        any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts)
        or diagnostic.shot_count <= 0
    ):
        raise PitchApiCompatibilityError("xG diagnostic counts are invalid")
    if diagnostic.missing_xg_count + diagnostic.invalid_xg_count > diagnostic.shot_count:
        raise PitchApiCompatibilityError("xG diagnostic counts do not reconcile")
    if (
        diagnostic.penalty_shot_count > diagnostic.shot_count
        or diagnostic.calibration_shot_count > diagnostic.shot_count
    ):
        raise PitchApiCompatibilityError("xG subset counts exceed the shot count")


def _validate_diagnostic_distribution(diagnostic: PitchApiXgScopeDiagnosticsV1) -> None:
    distribution = (
        diagnostic.xg_mean,
        diagnostic.xg_standard_deviation,
        *diagnostic.xg_quantiles,
    )
    if any(not math.isfinite(value) for value in distribution):
        raise PitchApiCompatibilityError("xG distribution values must be finite")
    if not 0 <= diagnostic.xg_mean <= 1 or diagnostic.xg_standard_deviation < 0:
        raise PitchApiCompatibilityError("xG distribution moments are invalid")
    if tuple(sorted(diagnostic.xg_quantiles)) != diagnostic.xg_quantiles or any(
        not 0 <= value <= 1 for value in diagnostic.xg_quantiles
    ):
        raise PitchApiCompatibilityError("xG quantiles must be ordered in [0,1]")
    for value in (diagnostic.calibration_intercept, diagnostic.calibration_slope):
        if value is not None and not math.isfinite(value):
            raise PitchApiCompatibilityError("calibration estimates must be finite")


def _validate_penalty_diagnostics(diagnostic: PitchApiXgScopeDiagnosticsV1) -> None:
    penalty_values = (
        diagnostic.penalty_xg_minimum,
        diagnostic.penalty_xg_maximum,
        diagnostic.penalty_xg_median,
        diagnostic.penalty_xg_iqr,
    )
    if diagnostic.penalty_shot_count == 0 and any(value is not None for value in penalty_values):
        raise PitchApiCompatibilityError("empty penalty diagnostics must not contain values")
    if diagnostic.penalty_shot_count == 0:
        return
    if any(value is None or not math.isfinite(value) for value in penalty_values):
        raise PitchApiCompatibilityError("penalty xG diagnostics are invalid")
    minimum = diagnostic.penalty_xg_minimum
    maximum = diagnostic.penalty_xg_maximum
    median = diagnostic.penalty_xg_median
    iqr = diagnostic.penalty_xg_iqr
    if (
        minimum is None
        or maximum is None
        or median is None
        or iqr is None
        or not 0 <= minimum <= median <= maximum <= 1
        or not 0 <= iqr <= 1
    ):
        raise PitchApiCompatibilityError("penalty xG diagnostics are invalid")


def _validate_situation_counts(diagnostic: PitchApiXgScopeDiagnosticsV1) -> None:
    situation_names = [name for name, _count in diagnostic.situation_shot_counts]
    if (
        not situation_names
        or len(situation_names) != len(set(situation_names))
        or any(not name or count <= 0 for name, count in diagnostic.situation_shot_counts)
        or sum(count for _name, count in diagnostic.situation_shot_counts) > diagnostic.shot_count
    ):
        raise PitchApiCompatibilityError("shot-situation counts are invalid")


@dataclass(frozen=True, slots=True)
class PitchApiXgDistributionComparisonV1:
    left_scope_key: str
    right_scope_key: str
    statistic: float
    p_value: float
    left_shot_count: int
    right_shot_count: int
    shot_situation: str = "ALL_SHOTS"

    def __post_init__(self) -> None:
        if (
            not self.left_scope_key
            or not self.right_scope_key
            or self.left_scope_key == self.right_scope_key
            or not self.shot_situation.strip()
            or not math.isfinite(self.statistic)
            or not 0 <= self.statistic <= 1
            or not math.isfinite(self.p_value)
            or not 0 <= self.p_value <= 1
            or self.left_shot_count <= 0
            or self.right_shot_count <= 0
        ):
            raise PitchApiCompatibilityError("xG distribution comparison is invalid")


@dataclass(frozen=True, slots=True)
class PitchApiXgCompatibilityReportV1:
    status: GateStatus
    policy_sha256: str
    findings: tuple[str, ...]
    warnings: tuple[str, ...]
    observational_compatibility_only: bool = True
    contract: str = "PitchApiXgCompatibilityReportV1"


def evaluate_pitchapi_xg_compatibility(
    policy: PitchApiXgCompatibilityPolicyV1,
    diagnostics: tuple[PitchApiXgScopeDiagnosticsV1, ...],
    comparisons: tuple[PitchApiXgDistributionComparisonV1, ...],
    *,
    required_scope_keys: tuple[str, ...],
) -> PitchApiXgCompatibilityReportV1:
    required = set(required_scope_keys)
    observed = {item.scope_key for item in diagnostics}
    if len(required) < 2 or len(required) != len(required_scope_keys):
        raise PitchApiCompatibilityError("at least two unique required scope keys are required")
    findings: set[str] = set()
    warnings: set[str] = set()
    if len(diagnostics) != len(observed) or observed != required:
        findings.add("SCOPE_DIAGNOSTICS_UNPROVED")
    for diagnostic in diagnostics:
        scope_findings, scope_warnings = _scope_findings(policy, diagnostic)
        findings.update(scope_findings)
        warnings.update(scope_warnings)
    findings.update(_penalty_comparison_findings(policy, diagnostics, warnings))
    adjusted_p_values = _holm_adjusted_p_values(comparisons)
    compared_pairs: set[tuple[frozenset[str], str]] = set()
    for comparison in comparisons:
        pair = frozenset((comparison.left_scope_key, comparison.right_scope_key))
        comparison_key = (pair, comparison.shot_situation)
        comparison_findings, comparison_warnings = _comparison_findings(
            policy,
            comparison,
            adjusted_p_values[comparison_key],
            pair,
            comparison_key,
            required,
            compared_pairs,
        )
        findings.update(comparison_findings)
        warnings.update(comparison_warnings)
        compared_pairs.add(comparison_key)
    required_comparisons = _required_distribution_comparisons(policy, diagnostics)
    if not required_comparisons <= compared_pairs:
        findings.add("DISTRIBUTION_COMPARISONS_UNPROVED")
    unproved = {finding for finding in findings if "UNPROVED" in finding}
    status: GateStatus = "FAIL" if findings - unproved else ("UNPROVED" if unproved else "PASS")
    return PitchApiXgCompatibilityReportV1(
        status=status,
        policy_sha256=policy.sha256,
        findings=tuple(sorted(findings)),
        warnings=tuple(sorted(warnings)),
    )


def _scope_findings(
    policy: PitchApiXgCompatibilityPolicyV1,
    diagnostic: PitchApiXgScopeDiagnosticsV1,
) -> tuple[set[str], set[str]]:
    prefix = diagnostic.scope_key
    checks = (
        (not diagnostic.schema_consistent, f"SCHEMA_INCONSISTENT:{prefix}"),
        (diagnostic.invalid_xg_count > 0, f"INVALID_XG:{prefix}"),
        (
            diagnostic.missing_xg_count / diagnostic.shot_count > policy.maximum_missing_rate,
            f"XG_MISSINGNESS_ABOVE_LIMIT:{prefix}",
        ),
        (
            not diagnostic.penalty_semantics_consistent,
            f"PENALTY_SEMANTICS_INCONSISTENT:{prefix}",
        ),
        (
            not diagnostic.shot_situation_semantics_consistent,
            f"SHOT_SITUATION_SEMANTICS_INCONSISTENT:{prefix}",
        ),
        (not diagnostic.period_semantics_consistent, f"PERIOD_SEMANTICS_INCONSISTENT:{prefix}"),
    )
    findings = {code for failed, code in checks if failed}
    penalty_findings, penalty_warnings = _penalty_scope_findings(policy, diagnostic)
    calibration_findings, calibration_warnings = _calibration_scope_findings(policy, diagnostic)
    findings.update(penalty_findings)
    findings.update(calibration_findings)
    return findings, penalty_warnings | calibration_warnings


def _penalty_scope_findings(
    policy: PitchApiXgCompatibilityPolicyV1,
    diagnostic: PitchApiXgScopeDiagnosticsV1,
) -> tuple[set[str], set[str]]:
    prefix = diagnostic.scope_key
    findings: set[str] = set()
    warnings: set[str] = set()
    if diagnostic.penalty_shot_count < policy.minimum_penalty_shots:
        findings.add(f"PENALTY_SAMPLE_UNPROVED:{prefix}")
    elif (
        diagnostic.penalty_xg_minimum is None
        or diagnostic.penalty_xg_maximum is None
        or diagnostic.penalty_xg_iqr is None
    ):
        findings.add(f"PENALTY_DIAGNOSTICS_UNPROVED:{prefix}")
    else:
        if (
            diagnostic.penalty_xg_minimum < policy.minimum_penalty_xg
            or diagnostic.penalty_xg_maximum > policy.maximum_penalty_xg
        ):
            findings.add(f"PENALTY_XG_RANGE_OUTSIDE_LIMIT:{prefix}")
        if diagnostic.penalty_xg_iqr > policy.maximum_penalty_iqr:
            findings.add(f"PENALTY_XG_IQR_OUTSIDE_LIMIT:{prefix}")
        elif diagnostic.penalty_xg_iqr > policy.warning_penalty_iqr:
            warnings.add(f"PENALTY_XG_IQR_NEAR_LIMIT:{prefix}")
    return findings, warnings


def _calibration_scope_findings(
    policy: PitchApiXgCompatibilityPolicyV1,
    diagnostic: PitchApiXgScopeDiagnosticsV1,
) -> tuple[set[str], set[str]]:
    prefix = diagnostic.scope_key
    findings: set[str] = set()
    warnings: set[str] = set()
    if diagnostic.calibration_shot_count < policy.minimum_calibration_shots:
        findings.add(f"CALIBRATION_SAMPLE_UNPROVED:{prefix}")
    if diagnostic.calibration_intercept is None or diagnostic.calibration_slope is None:
        findings.add(f"CALIBRATION_UNPROVED:{prefix}")
        return findings, warnings
    if abs(diagnostic.calibration_intercept) > policy.maximum_absolute_calibration_intercept:
        findings.add(f"CALIBRATION_INTERCEPT_OUTSIDE_LIMIT:{prefix}")
    elif abs(diagnostic.calibration_intercept) > policy.warning_absolute_calibration_intercept:
        warnings.add(f"CALIBRATION_INTERCEPT_NEAR_LIMIT:{prefix}")
    if (
        not policy.minimum_calibration_slope
        <= diagnostic.calibration_slope
        <= (policy.maximum_calibration_slope)
    ):
        findings.add(f"CALIBRATION_SLOPE_OUTSIDE_LIMIT:{prefix}")
    elif not (
        policy.warning_minimum_calibration_slope
        <= diagnostic.calibration_slope
        <= policy.warning_maximum_calibration_slope
    ):
        warnings.add(f"CALIBRATION_SLOPE_NEAR_LIMIT:{prefix}")
    return findings, warnings


def _comparison_findings(
    policy: PitchApiXgCompatibilityPolicyV1,
    comparison: PitchApiXgDistributionComparisonV1,
    adjusted_p_value: float,
    pair: frozenset[str],
    comparison_key: tuple[frozenset[str], str],
    required: set[str],
    compared_pairs: set[tuple[frozenset[str], str]],
) -> tuple[set[str], set[str]]:
    findings: set[str] = set()
    warnings: set[str] = set()
    if not pair <= required:
        findings.add("DISTRIBUTION_COMPARISON_SCOPE_MISMATCH")
    if comparison_key in compared_pairs:
        findings.add("DUPLICATE_DISTRIBUTION_COMPARISON")
    if comparison.statistic > policy.maximum_distribution_discontinuity:
        findings.add(
            f"MATERIAL_DISTRIBUTION_DISCONTINUITY:{comparison.left_scope_key}:"
            f"{comparison.right_scope_key}:{comparison.shot_situation}"
        )
    elif comparison.statistic > policy.warning_distribution_discontinuity:
        warnings.add(
            f"DISTRIBUTION_DISCONTINUITY_NEAR_LIMIT:{comparison.left_scope_key}:"
            f"{comparison.right_scope_key}:{comparison.shot_situation}"
        )
    elif adjusted_p_value < 0.05:
        warnings.add(
            f"STATISTICALLY_DETECTABLE_DISTRIBUTION_DIFFERENCE:"
            f"{comparison.left_scope_key}:{comparison.right_scope_key}:"
            f"{comparison.shot_situation}"
        )
    if comparison.shot_situation != "ALL_SHOTS" and (
        comparison.left_shot_count < policy.minimum_situation_shots
        or comparison.right_shot_count < policy.minimum_situation_shots
    ):
        findings.add(
            f"SITUATION_COMPARISON_SAMPLE_UNPROVED:{comparison.left_scope_key}:"
            f"{comparison.right_scope_key}:{comparison.shot_situation}"
        )
    return findings, warnings


def _holm_adjusted_p_values(
    comparisons: tuple[PitchApiXgDistributionComparisonV1, ...],
) -> dict[tuple[frozenset[str], str], float]:
    ordered = sorted(comparisons, key=lambda item: item.p_value)
    adjusted: dict[tuple[frozenset[str], str], float] = {}
    running_maximum = 0.0
    family_size = len(ordered)
    for rank, comparison in enumerate(ordered):
        running_maximum = max(
            running_maximum,
            min(1.0, (family_size - rank) * comparison.p_value),
        )
        key = (
            frozenset((comparison.left_scope_key, comparison.right_scope_key)),
            comparison.shot_situation,
        )
        adjusted[key] = running_maximum
    return adjusted


def _required_distribution_comparisons(
    policy: PitchApiXgCompatibilityPolicyV1,
    diagnostics: tuple[PitchApiXgScopeDiagnosticsV1, ...],
) -> set[tuple[frozenset[str], str]]:
    required: set[tuple[frozenset[str], str]] = set()
    for left_index, left in enumerate(diagnostics):
        left_situations = dict(left.situation_shot_counts)
        for right in diagnostics[left_index + 1 :]:
            pair = frozenset((left.scope_key, right.scope_key))
            required.add((pair, "ALL_SHOTS"))
            right_situations = dict(right.situation_shot_counts)
            for situation in left_situations.keys() & right_situations.keys():
                if (
                    left_situations[situation] >= policy.minimum_situation_shots
                    and right_situations[situation] >= policy.minimum_situation_shots
                ):
                    required.add((pair, situation))
    return required


def _penalty_comparison_findings(
    policy: PitchApiXgCompatibilityPolicyV1,
    diagnostics: tuple[PitchApiXgScopeDiagnosticsV1, ...],
    warnings: set[str],
) -> set[str]:
    findings: set[str] = set()
    for left_index, left in enumerate(diagnostics):
        for right in diagnostics[left_index + 1 :]:
            if left.penalty_xg_median is None or right.penalty_xg_median is None:
                continue
            difference = abs(left.penalty_xg_median - right.penalty_xg_median)
            label = f"{left.scope_key}:{right.scope_key}"
            if difference > policy.maximum_penalty_median_difference:
                findings.add(f"PENALTY_MEDIAN_DIFFERENCE_OUTSIDE_LIMIT:{label}")
            elif difference > policy.warning_penalty_median_difference:
                warnings.add(f"PENALTY_MEDIAN_DIFFERENCE_NEAR_LIMIT:{label}")
    return findings
