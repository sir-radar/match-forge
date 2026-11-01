from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.coverage.resources import CanonicalCoverage, CanonicalCoverageScope
from football.forecasting.market_catalogue import INPUTS, market_catalogue
from football.forecasting.runtime_models import ModelRegistration
from football.product.market_capabilities import (
    MarketQualification,
    MarketSource,
    SourceCompatibility,
    assess_market,
    market_input_key,
)
from football.providers.capability_registry import RegisteredCapability
from football.providers.resource_capabilities import ResourceCapability, ResourceScope

NOW = datetime(2026, 11, 1, tzinfo=UTC)
COMPETITION, SEASON, FIXTURE = UUID(int=1), UUID(int=2), UUID(int=3)
CATALOGUE = {item.market_id: item for item in market_catalogue()}


def qualified(market_id="RESULT_1X2"):
    market = CATALOGUE[market_id]
    parameters = tuple(
        (name, "HOME_WIN" if name == "selection" else "test:explicit-parameter")
        for name in market.parameters
    )
    history = tuple(
        CanonicalCoverage(
            scope=CanonicalCoverageScope(
                competition_id=COMPETITION,
                season_id=SEASON,
                resource_type=market_input_key(market, requirement, parameters),
            ),
            knowledge_cutoff=NOW,
            expected_units=(FIXTURE,),
            qualified_support=((FIXTURE, "fotmob"), (FIXTURE, "pitchapi")),
            evidence_refs=("test:qualified-eligible-fixture",),
        )
        for requirement in market.requirements
    )
    entry = ModelRegistration.from_bytes(Path("config/models/current-champion.json").read_bytes())
    return MarketQualification(
        competition_id=COMPETITION,
        season_id=SEASON,
        knowledge_cutoff=NOW,
        history=history,
        parameters=parameters,
        compatibility=SourceCompatibility.EXACT_OR_VERIFIED_EQUIVALENT,
        semantic_version=market.semantic_version,
        semantic_refs=("test:source-target-proof",),
        history_sufficient=True,
        history_policy_ref="test:frozen-policy",
        model=entry,
        evaluation_status="PASS",
        evaluation_ref="test:scoped-evaluation",
        publication_status="PUBLISHED",
        publication_ref="test:existing-publication",
    )


def test_catalogue_covers_requested_groups_and_named_targets_without_probabilities():
    rows = market_catalogue()
    assert len(rows) == len(CATALOGUE)
    assert {row.group for row in rows} == {
        "GOALS",
        "PERIODS",
        "CORNERS",
        "CARDS",
        "TEAM_STATISTICS",
        "PLAYERS",
        "JOINT",
    }
    assert {
        "DRAW_NO_BET",
        "ASIAN_GOAL_HANDICAP",
        "EUROPEAN_GOAL_HANDICAP",
        "HT_FT",
        "CARD_POINTS",
        "ANYTIME_SCORER",
        "FIRST_SCORER",
        "LAST_SCORER",
        "GOALKEEPER_SAVES",
        "SHOTS_SHOTS_ON_TARGET",
    } <= set(CATALOGUE)
    for row in rows:
        assert row.requirements and set(row.requirements) <= set(INPUTS)
        contract = row.to_dict()["semantic_contract"]
        assert contract["extra_time"] == contract["shootout"] == "EXCLUDED"
        assert "UNSCORABLE" in contract["incomplete_or_void"]
        assert contract["sportsbook_equivalence"].startswith("UNVERIFIED")
        assert len(row.sha256) == 64
        assert "probabilities" not in row.to_dict()


def test_provider_support_does_not_create_history_semantics_or_player_identity():
    source = MarketSource(
        ResourceScope(
            provider="fotmob", resource_type="statistics", competition="native", season="2026"
        ),
        RegisteredCapability(
            UUID(int=10),
            NOW,
            ResourceCapability(
                availability="SUPPORTED", adapter_version="test", normalizer_version="test"
            ),
        ),
    )
    evidence = MarketQualification(
        competition_id=COMPETITION, season_id=SEASON, knowledge_cutoff=NOW
    )
    goals = assess_market(CATALOGUE["RESULT_1X2"], evidence, (source,))
    player = assess_market(CATALOGUE["PLAYER_SHOTS"], evidence, (source,))
    assert goals["diagnostic_status"] == "DATA_COLLECTION_REQUIRED"
    assert player["diagnostic_status"] == "INSUFFICIENT_PLAYER_DATA"
    assert goals["qualified_historical_coverage"]["regulation_score"] is None
    assert not goals["publication"]["grants_new_publication"]
    assert goals["provider_sources"][0]["field_coverage"] is None


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({}, "SUPPORTED"),
        ({"publication_status": "SHADOW"}, "SHADOW"),
        ({"publication_status": "NOT_PUBLISHED"}, "ENGINEERING_READY"),
        ({"evaluation_status": "UNASSESSED"}, "RESEARCH_REQUIRED"),
        ({"history": ()}, "DATA_COLLECTION_REQUIRED"),
        ({"history_sufficient": False}, "INSUFFICIENT_HISTORY"),
        ({"compatibility": SourceCompatibility.INCOMPATIBLE}, "SEMANTIC_MISMATCH"),
        ({"blocker": "existing-owner-blocker"}, "BLOCKED"),
    ],
)
def test_readiness_preserves_current_publication_and_never_grants_new_activation(changes, status):
    evidence = replace(qualified(), **changes)
    result = assess_market(CATALOGUE["RESULT_1X2"], evidence)
    assert result["diagnostic_status"] == status
    assert result["publication"]["current_status"] == evidence.publication_status
    assert not result["publication"]["grants_new_publication"]
    assert result["authoritative"] is False
    assert (
        result["qualified_historical_coverage"].get("regulation_score", {}) is not None
        or status == "DATA_COLLECTION_REQUIRED"
    )


def test_research_registration_cannot_support_declared_public_publication():
    evidence = qualified()
    evidence = replace(evidence, model=replace(evidence.model, lifecycle_state="RESEARCH"))
    result = assess_market(CATALOGUE["RESULT_1X2"], evidence)
    assert result["diagnostic_status"] == "RESEARCH_REQUIRED"
    assert not result["publication"]["eligible_under_declared_evidence"]


def test_joint_inputs_require_common_eligible_fixtures_not_independent_counts():
    evidence = qualified("GOALS_CORNERS")
    other = replace(
        evidence.history[1],
        expected_units=(UUID(int=4),),
        qualified_support=((UUID(int=4), "fotmob"),),
    )
    evidence = replace(evidence, history=(evidence.history[0], other))
    result = assess_market(CATALOGUE["GOALS_CORNERS"], evidence)
    assert result["diagnostic_status"] == "INSUFFICIENT_HISTORY"
    assert result["diagnostic_blocker"] == "NO_COMMON_ELIGIBLE_FIXTURES"


@pytest.mark.parametrize("change", ["competition", "knowledge", "input", "duplicate"])
def test_coverage_cannot_cross_canonical_scope_knowledge_target_or_input(change):
    evidence = qualified()
    report = evidence.history[0]
    if change == "competition":
        report = replace(report, scope=replace(report.scope, competition_id=UUID(int=9)))
    if change == "knowledge":
        report = replace(report, knowledge_cutoff=NOW + timedelta(seconds=1))
    if change == "input":
        report = replace(
            report, scope=replace(report.scope, resource_type="TeamStatisticObservation")
        )
    history = (report, report) if change == "duplicate" else (report,)
    with pytest.raises(ValueError, match="scope|cutoff|target/input"):
        assess_market(CATALOGUE["RESULT_1X2"], replace(evidence, history=history))


def test_unknown_sufficiency_and_semantics_cannot_be_inferred_from_coverage_size():
    evidence = qualified()
    result = assess_market(CATALOGUE["RESULT_1X2"], replace(evidence, history_sufficient=None))
    assert result["diagnostic_status"] == "RESEARCH_REQUIRED"
    result = assess_market(
        CATALOGUE["RESULT_1X2"], replace(evidence, compatibility=SourceCompatibility.UNKNOWN)
    )
    assert result["diagnostic_status"] == "DATA_COLLECTION_REQUIRED"
    with pytest.raises(ValueError, match="evidence"):
        replace(evidence, semantic_refs=())
    with pytest.raises(ValueError, match="owner evidence"):
        replace(evidence, history_policy_ref=None)


def test_implementation_inventory_does_not_change_target_semantics_or_coverage_identity():
    market = CATALOGUE["RESULT_1X2"]
    changed = replace(market, implementation="another.implementation")
    assert changed.sha256 == market.sha256
    assert market_input_key(changed, "regulation_score") == market_input_key(
        market, "regulation_score"
    )


def test_target_parameters_are_bound_to_coverage_and_zero_is_not_missing():
    market = CATALOGUE["TOTAL_GOALS"]
    zero = (("line", 0), ("selection", "OVER"))
    another = (("line", 0.5), ("selection", "OVER"))
    assert market_input_key(market, "regulation_score", zero) != market_input_key(
        market, "regulation_score", another
    )
    assert (
        MarketQualification(
            competition_id=COMPETITION, season_id=SEASON, knowledge_cutoff=NOW, parameters=zero
        ).parameters
        == zero
    )
    with pytest.raises(ValueError, match="target/input"):
        evidence = replace(qualified(), parameters=(("selection", "AWAY_WIN"),))
        assess_market(CATALOGUE["RESULT_1X2"], evidence)


@pytest.mark.parametrize("value", [True, None, float("nan"), float("inf"), ""])
def test_invalid_target_parameter_values_are_rejected(value):
    with pytest.raises(ValueError):
        MarketQualification(
            competition_id=COMPETITION,
            season_id=SEASON,
            knowledge_cutoff=NOW,
            parameters=(("line", value),),
        )


def test_provider_evidence_from_future_knowledge_is_rejected():
    source = MarketSource(
        ResourceScope(provider="fotmob", resource_type="results", competition=None, season=None),
        RegisteredCapability(
            UUID(int=10),
            NOW + timedelta(seconds=1),
            ResourceCapability(
                availability="SUPPORTED", adapter_version="test", normalizer_version="test"
            ),
        ),
    )
    with pytest.raises(ValueError, match="knowledge cutoff"):
        assess_market(CATALOGUE["RESULT_1X2"], qualified(), (source,))


def test_coverage_deserialization_checks_unit_evidence_instead_of_trusting_metrics():
    from football.coverage.resources import CoverageError

    report = qualified().history[0]
    assert CanonicalCoverage.from_dict(report.to_dict()) == report
    assert report.metrics.qualified == 1  # Two sources support one canonical fixture.
    changed = report.to_dict()
    changed["metrics"]["qualified_canonical_units"] = 2
    with pytest.raises(CoverageError, match="unit evidence"):
        CanonicalCoverage.from_dict(changed)
    changed = report.to_dict()
    changed["unexpected"] = True
    with pytest.raises(CoverageError, match="unit evidence"):
        CanonicalCoverage.from_dict(changed)


def test_research_only_compatibility_never_becomes_public_support():
    evidence = replace(qualified(), compatibility=SourceCompatibility.RESEARCH_COMPATIBLE_ONLY)
    report = assess_market(CATALOGUE["RESULT_1X2"], evidence)
    assert report["diagnostic_status"] == "RESEARCH_REQUIRED"
    assert not report["publication"]["eligible_under_declared_evidence"]


def test_phase_15_semantic_identities_stay_frozen_as_implementations_expand():
    import json

    baseline = json.loads(Path("docs/evidence/matchforge-v4-phase-15-2026-11-01.json").read_bytes())
    for target in baseline["targets"]:
        assert CATALOGUE[target["market_id"]].sha256 == target["definition_sha256"]
    assert CATALOGUE["RESULT_BTTS"].implementation == "football.forecasting.products.score_products"
