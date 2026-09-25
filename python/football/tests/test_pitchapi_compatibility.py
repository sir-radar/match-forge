from __future__ import annotations

from dataclasses import replace

from football.validation.pitchapi_compatibility import (
    PitchApiXgCompatibilityPolicyV1,
    PitchApiXgDistributionComparisonV1,
    PitchApiXgScopeDiagnosticsV1,
    evaluate_pitchapi_xg_compatibility,
)


def _policy() -> PitchApiXgCompatibilityPolicyV1:
    return PitchApiXgCompatibilityPolicyV1(
        maximum_missing_rate=0.0,
        minimum_penalty_shots=20,
        minimum_penalty_xg=0.65,
        maximum_penalty_xg=0.9,
        maximum_penalty_iqr=0.05,
        maximum_penalty_median_difference=0.05,
        minimum_calibration_shots=800,
        maximum_absolute_calibration_intercept=0.25,
        minimum_calibration_slope=0.8,
        maximum_calibration_slope=1.2,
        minimum_situation_shots=100,
        maximum_distribution_discontinuity=0.1,
        warning_absolute_calibration_intercept=0.2,
        warning_minimum_calibration_slope=0.85,
        warning_maximum_calibration_slope=1.15,
        warning_distribution_discontinuity=0.08,
        warning_penalty_iqr=0.04,
        warning_penalty_median_difference=0.04,
    )


def _scope(key: str) -> PitchApiXgScopeDiagnosticsV1:
    return PitchApiXgScopeDiagnosticsV1(
        scope_key=key,
        shot_count=1000,
        missing_xg_count=0,
        invalid_xg_count=0,
        schema_consistent=True,
        penalty_semantics_consistent=True,
        shot_situation_semantics_consistent=True,
        period_semantics_consistent=True,
        xg_mean=0.11,
        xg_standard_deviation=0.14,
        xg_quantiles=(0.02, 0.06, 0.27),
        penalty_shot_count=30,
        penalty_xg_minimum=0.76,
        penalty_xg_maximum=0.76,
        penalty_xg_median=0.76,
        penalty_xg_iqr=0.0,
        calibration_shot_count=970,
        calibration_intercept=0.02,
        calibration_slope=0.98,
        situation_shot_counts=(("OPEN_PLAY", 700), ("SET_PIECE", 270)),
    )


def _comparison(
    statistic: float,
    *,
    situation: str = "ALL_SHOTS",
    p_value: float = 0.5,
) -> PitchApiXgDistributionComparisonV1:
    return PitchApiXgDistributionComparisonV1(
        "bundesliga",
        "ligue1",
        statistic,
        p_value,
        700,
        700,
        shot_situation=situation,
    )


def _complete_comparisons(
    all_shots: float = 0.04,
) -> tuple[PitchApiXgDistributionComparisonV1, ...]:
    return (
        _comparison(all_shots),
        _comparison(0.04, situation="OPEN_PLAY"),
        _comparison(0.04, situation="SET_PIECE"),
    )


def test_compatibility_gate_covers_structure_calibration_and_distributions() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (_scope("bundesliga"), _scope("ligue1")),
        _complete_comparisons(),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "PASS"
    assert report.policy_sha256 == _policy().sha256
    assert report.findings == ()
    assert report.warnings == ()
    assert report.observational_compatibility_only is True


def test_compatibility_gate_fails_material_or_semantic_differences() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (_scope("bundesliga"), replace(_scope("ligue1"), period_semantics_consistent=False)),
        _complete_comparisons(0.2),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "FAIL"
    assert "PERIOD_SEMANTICS_INCONSISTENT:ligue1" in report.findings
    assert "MATERIAL_DISTRIBUTION_DISCONTINUITY:bundesliga:ligue1:ALL_SHOTS" in report.findings


def test_compatibility_gate_checks_shot_situation_distributions_separately() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (_scope("bundesliga"), _scope("ligue1")),
        (
            _comparison(0.04),
            _comparison(0.2, situation="OPEN_PLAY"),
            _comparison(0.04, situation="SET_PIECE"),
        ),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "FAIL"
    assert "MATERIAL_DISTRIBUTION_DISCONTINUITY:bundesliga:ligue1:OPEN_PLAY" in report.findings


def test_compatibility_gate_is_unproved_without_calibration_or_all_pairs() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (
            replace(_scope("bundesliga"), calibration_intercept=None, calibration_slope=None),
            _scope("ligue1"),
        ),
        (),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "UNPROVED"
    assert "CALIBRATION_UNPROVED:bundesliga" in report.findings
    assert "DISTRIBUTION_COMPARISONS_UNPROVED" in report.findings


def test_compatibility_gate_warns_before_hard_calibration_and_shift_limits() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (
            replace(_scope("bundesliga"), calibration_intercept=0.21),
            _scope("ligue1"),
        ),
        _complete_comparisons(0.09),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "PASS"
    assert "CALIBRATION_INTERCEPT_NEAR_LIMIT:bundesliga" in report.warnings
    assert "DISTRIBUTION_DISCONTINUITY_NEAR_LIMIT:bundesliga:ligue1:ALL_SHOTS" in report.warnings


def test_compatibility_gate_warns_on_holm_adjusted_significance_without_effect_failure() -> None:
    comparisons = list(_complete_comparisons())
    comparisons[0] = _comparison(0.04, p_value=0.01)

    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (_scope("bundesliga"), _scope("ligue1")),
        tuple(comparisons),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "PASS"
    assert (
        "STATISTICALLY_DETECTABLE_DISTRIBUTION_DIFFERENCE:"
        "bundesliga:ligue1:ALL_SHOTS" in report.warnings
    )


def test_compatibility_gate_fails_penalty_behavior_and_insufficient_samples() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (
            replace(
                _scope("bundesliga"),
                penalty_xg_maximum=0.95,
                calibration_shot_count=799,
            ),
            replace(
                _scope("ligue1"),
                penalty_xg_maximum=0.82,
                penalty_xg_median=0.82,
            ),
        ),
        _complete_comparisons(),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "FAIL"
    assert "PENALTY_XG_RANGE_OUTSIDE_LIMIT:bundesliga" in report.findings
    assert "CALIBRATION_SAMPLE_UNPROVED:bundesliga" in report.findings
    assert "PENALTY_MEDIAN_DIFFERENCE_OUTSIDE_LIMIT:bundesliga:ligue1" in report.findings
