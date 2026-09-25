from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from football.validation.pitchapi_domain_stratified import (
    CanonicalFixtureKeyV1,
    DomainMetricV1,
    PairedScoreComparisonV1,
    PitchApiDomainPolicyError,
    XgTreatment,
    aggregate_domain_metric,
    select_development_xg_treatment,
    validate_cross_provider_fixture_roles,
    validate_exact_target_plan,
)


def test_development_xg_treatment_requires_both_proper_scores_to_support_transform() -> None:
    log_loss = PairedScoreComparisonV1(-0.0068, -0.0138, -0.0004)
    brier = PairedScoreComparisonV1(0.0018, 0.0008, 0.0029)

    assert select_development_xg_treatment(log_loss=log_loss, brier_score=brier) is XgTreatment.RAW


def test_development_xg_treatment_selects_supported_recalibration() -> None:
    improvement = PairedScoreComparisonV1(-0.01, -0.02, -0.001)

    assert (
        select_development_xg_treatment(log_loss=improvement, brier_score=improvement)
        is XgTreatment.LOGISTIC_RECALIBRATION
    )


def test_domain_aggregation_reports_macro_and_target_weighted_results() -> None:
    aggregate = aggregate_domain_metric(
        {
            "bundesliga_2022_23": DomainMetricV1(1.0, 216),
            "bundesliga_2023_24": DomainMetricV1(2.0, 216),
            "ligue1_2022_23": DomainMetricV1(4.0, 280),
        }
    )

    assert aggregate.macro_average == pytest.approx(7 / 3)
    assert aggregate.target_weighted_average == pytest.approx(1768 / 712)
    assert aggregate.total_targets == 712


def test_domain_aggregation_rejects_changed_target_counts() -> None:
    with pytest.raises(PitchApiDomainPolicyError, match="unexpected target count"):
        aggregate_domain_metric(
            {
                "bundesliga_2022_23": DomainMetricV1(1.0, 215),
                "bundesliga_2023_24": DomainMetricV1(2.0, 216),
                "ligue1_2022_23": DomainMetricV1(4.0, 280),
            }
        )


def test_exact_target_plan_requires_disjoint_frozen_domains() -> None:
    targets = {
        "bundesliga_2022_23": frozenset(f"bl22-{index}" for index in range(216)),
        "bundesliga_2023_24": frozenset(f"bl23-{index}" for index in range(216)),
        "ligue1_2022_23": frozenset(f"l122-{index}" for index in range(280)),
    }

    assert validate_exact_target_plan(targets) == 712


def test_exact_target_plan_rejects_cross_domain_duplicate() -> None:
    shared = "shared"
    targets = {
        "bundesliga_2022_23": frozenset([shared, *(f"bl22-{index}" for index in range(215))]),
        "bundesliga_2023_24": frozenset([shared, *(f"bl23-{index}" for index in range(215))]),
        "ligue1_2022_23": frozenset(f"l122-{index}" for index in range(280)),
    }

    with pytest.raises(PitchApiDomainPolicyError, match="duplicate targets"):
        validate_exact_target_plan(targets)


def test_repository_policy_records_raw_xg_and_domain_safety_gate() -> None:
    root = Path(__file__).resolve().parents[3]
    path = root / "docs/evaluation/pitchapi-domain-stratified-evaluation-v2-policy-proposal.json"
    policy = json.loads(path.read_text(encoding="utf-8"))

    assert policy["status"] == "OWNER_APPROVAL_REQUIRED"
    assert policy["xg_treatment"]["selected"] == "RAW"
    assert policy["groups"]["projected_exact_evaluation_targets"] == 712
    assert policy["acceptance"]["every_domain_joint_log_loss_interval_upper_maximum"] == 0.05
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1"
    )


def test_cross_provider_overlap_uses_resolved_fixture_identity() -> None:
    fixture = CanonicalFixtureKeyV1(
        "bundesliga",
        "2023_24",
        "2023-08-18T18:30:00Z",
        "team-a",
        "team-b",
    )

    with pytest.raises(PitchApiDomainPolicyError, match="development/evaluation"):
        validate_cross_provider_fixture_roles(
            protected=frozenset(),
            development=frozenset({fixture}),
            evaluation=frozenset({fixture}),
            unresolved_fixture_count=0,
        )


def test_cross_provider_overlap_fails_when_aliases_are_unresolved() -> None:
    with pytest.raises(PitchApiDomainPolicyError, match="aliases are unresolved"):
        validate_cross_provider_fixture_roles(
            protected=frozenset(),
            development=frozenset(),
            evaluation=frozenset(),
            unresolved_fixture_count=1,
        )
