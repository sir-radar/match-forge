"""Offline xG compatibility gate for the PitchAPI retrospective protocol."""

from __future__ import annotations

import math
from dataclasses import dataclass

from football.validation.pitchapi_contingency import (
    PITCHAPI_RETROSPECTIVE_EVALUATION_V1,
    GateStatus,
)


class PitchApiCompatibilityError(ValueError):
    """PitchAPI compatibility evidence or policy is malformed."""


@dataclass(frozen=True, slots=True)
class PitchApiXgCompatibilityPolicyV1:
    maximum_missing_rate: float
    maximum_absolute_calibration_intercept: float
    minimum_calibration_slope: float
    maximum_calibration_slope: float
    maximum_distribution_discontinuity: float
    calibration_method: str = "logistic-outcome-on-logit-xg"
    distribution_method: str = "two-sample-kolmogorov-smirnov"
    evaluation_protocol_id: str = PITCHAPI_RETROSPECTIVE_EVALUATION_V1
    contract: str = "PitchApiXgCompatibilityPolicyV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiXgCompatibilityPolicyV1":
            raise PitchApiCompatibilityError("unsupported xG compatibility policy")
        if self.evaluation_protocol_id != PITCHAPI_RETROSPECTIVE_EVALUATION_V1:
            raise PitchApiCompatibilityError("xG compatibility policy has the wrong protocol")
        bounded = (self.maximum_missing_rate, self.maximum_distribution_discontinuity)
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in bounded):
            raise PitchApiCompatibilityError("rate and discontinuity limits must be in [0,1]")
        if (
            not math.isfinite(self.maximum_absolute_calibration_intercept)
            or self.maximum_absolute_calibration_intercept < 0
            or not math.isfinite(self.minimum_calibration_slope)
            or not math.isfinite(self.maximum_calibration_slope)
            or self.minimum_calibration_slope > self.maximum_calibration_slope
        ):
            raise PitchApiCompatibilityError("calibration limits are invalid")
        if self.calibration_method != "logistic-outcome-on-logit-xg":
            raise PitchApiCompatibilityError("unsupported calibration method")
        if self.distribution_method != "two-sample-kolmogorov-smirnov":
            raise PitchApiCompatibilityError("unsupported distribution method")


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
    calibration_intercept: float | None
    calibration_slope: float | None
    contract: str = "PitchApiXgScopeDiagnosticsV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiXgScopeDiagnosticsV1" or not self.scope_key:
            raise PitchApiCompatibilityError("unsupported or unnamed xG scope diagnostics")
        counts = (self.shot_count, self.missing_xg_count, self.invalid_xg_count)
        if (
            any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in counts
            )
            or self.shot_count <= 0
        ):
            raise PitchApiCompatibilityError("xG diagnostic counts are invalid")
        if self.missing_xg_count + self.invalid_xg_count > self.shot_count:
            raise PitchApiCompatibilityError("xG diagnostic counts do not reconcile")
        distribution = (self.xg_mean, self.xg_standard_deviation, *self.xg_quantiles)
        if any(not math.isfinite(value) for value in distribution):
            raise PitchApiCompatibilityError("xG distribution values must be finite")
        if not 0 <= self.xg_mean <= 1 or self.xg_standard_deviation < 0:
            raise PitchApiCompatibilityError("xG distribution moments are invalid")
        if tuple(sorted(self.xg_quantiles)) != self.xg_quantiles or any(
            not 0 <= value <= 1 for value in self.xg_quantiles
        ):
            raise PitchApiCompatibilityError("xG quantiles must be ordered in [0,1]")
        for value in (self.calibration_intercept, self.calibration_slope):
            if value is not None and not math.isfinite(value):
                raise PitchApiCompatibilityError("calibration estimates must be finite")


@dataclass(frozen=True, slots=True)
class PitchApiXgDistributionComparisonV1:
    left_scope_key: str
    right_scope_key: str
    statistic: float

    def __post_init__(self) -> None:
        if (
            not self.left_scope_key
            or not self.right_scope_key
            or self.left_scope_key == self.right_scope_key
            or not math.isfinite(self.statistic)
            or not 0 <= self.statistic <= 1
        ):
            raise PitchApiCompatibilityError("xG distribution comparison is invalid")


@dataclass(frozen=True, slots=True)
class PitchApiXgCompatibilityReportV1:
    status: GateStatus
    findings: tuple[str, ...]
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
    if len(diagnostics) != len(observed) or observed != required:
        findings.add("SCOPE_DIAGNOSTICS_UNPROVED")
    for diagnostic in diagnostics:
        findings.update(_scope_findings(policy, diagnostic))
    compared_pairs: set[frozenset[str]] = set()
    for comparison in comparisons:
        pair = frozenset((comparison.left_scope_key, comparison.right_scope_key))
        findings.update(_comparison_findings(policy, comparison, pair, required, compared_pairs))
        compared_pairs.add(pair)
    expected_pairs = len(required) * (len(required) - 1) // 2
    if len(compared_pairs) != expected_pairs:
        findings.add("DISTRIBUTION_COMPARISONS_UNPROVED")
    unproved = {finding for finding in findings if "UNPROVED" in finding}
    status: GateStatus = "FAIL" if findings - unproved else ("UNPROVED" if unproved else "PASS")
    return PitchApiXgCompatibilityReportV1(status=status, findings=tuple(sorted(findings)))


def _scope_findings(
    policy: PitchApiXgCompatibilityPolicyV1,
    diagnostic: PitchApiXgScopeDiagnosticsV1,
) -> set[str]:
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
    if diagnostic.calibration_intercept is None or diagnostic.calibration_slope is None:
        findings.add(f"CALIBRATION_UNPROVED:{prefix}")
        return findings
    if abs(diagnostic.calibration_intercept) > policy.maximum_absolute_calibration_intercept:
        findings.add(f"CALIBRATION_INTERCEPT_OUTSIDE_LIMIT:{prefix}")
    if (
        not policy.minimum_calibration_slope
        <= diagnostic.calibration_slope
        <= (policy.maximum_calibration_slope)
    ):
        findings.add(f"CALIBRATION_SLOPE_OUTSIDE_LIMIT:{prefix}")
    return findings


def _comparison_findings(
    policy: PitchApiXgCompatibilityPolicyV1,
    comparison: PitchApiXgDistributionComparisonV1,
    pair: frozenset[str],
    required: set[str],
    compared_pairs: set[frozenset[str]],
) -> set[str]:
    findings: set[str] = set()
    if not pair <= required:
        findings.add("DISTRIBUTION_COMPARISON_SCOPE_MISMATCH")
    if pair in compared_pairs:
        findings.add("DUPLICATE_DISTRIBUTION_COMPARISON")
    if comparison.statistic > policy.maximum_distribution_discontinuity:
        findings.add(
            f"MATERIAL_DISTRIBUTION_DISCONTINUITY:{comparison.left_scope_key}:"
            f"{comparison.right_scope_key}"
        )
    return findings
