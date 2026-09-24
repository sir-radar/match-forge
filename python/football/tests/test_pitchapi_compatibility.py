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
        maximum_missing_rate=0.01,
        maximum_absolute_calibration_intercept=0.25,
        minimum_calibration_slope=0.8,
        maximum_calibration_slope=1.2,
        maximum_distribution_discontinuity=0.1,
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
        calibration_intercept=0.02,
        calibration_slope=0.98,
    )


def test_compatibility_gate_covers_structure_calibration_and_distributions() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (_scope("bundesliga"), _scope("ligue1")),
        (PitchApiXgDistributionComparisonV1("bundesliga", "ligue1", 0.04),),
        required_scope_keys=("bundesliga", "ligue1"),
    )

    assert report.status == "PASS"
    assert report.policy_sha256 == _policy().sha256
    assert report.findings == ()
    assert report.observational_compatibility_only is True


def test_compatibility_gate_fails_material_or_semantic_differences() -> None:
    report = evaluate_pitchapi_xg_compatibility(
        _policy(),
        (_scope("bundesliga"), replace(_scope("ligue1"), period_semantics_consistent=False)),
        (PitchApiXgDistributionComparisonV1("bundesliga", "ligue1", 0.2),),
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
            PitchApiXgDistributionComparisonV1("bundesliga", "ligue1", 0.04),
            PitchApiXgDistributionComparisonV1(
                "bundesliga", "ligue1", 0.2, shot_situation="OPEN_PLAY"
            ),
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
