from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]


def _load(path: str) -> dict[str, Any]:
    value = json.loads((ROOT / path).read_text())
    assert isinstance(value, dict)
    return value


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (ROOT / path).read_text().splitlines()]


def test_historical_context_authorization_is_data_only() -> None:
    decision = _load(
        "docs/evidence/owner-decision-authorize-historical-context-corpus-v1-2026-10-08.json"
    )

    assert decision["decision_id"] == "AUTHORIZE_HISTORICAL_CONTEXT_CORPUS_V1"
    assert decision["scope"] == "DATA_ACQUISITION_AND_QUALIFICATION_ONLY"
    assert decision["model_fitting_authorized"] is False
    assert decision["context_evaluation_authorized"] is False
    assert decision["production_promotion_authorized"] is False
    assert decision["H2H_authorized"] is False


def test_preflight_stopped_before_over_budget_provider_calls() -> None:
    preflight = _load("docs/evaluation/matchforge-historical-context-corpus-v1-preflight.json")
    acquisition = _load(
        "docs/evaluation/matchforge-historical-context-corpus-v1-acquisition-manifest.json"
    )

    assert preflight["request_plan"]["expected_total_calls"] == 8660
    assert preflight["request_plan"]["hard_request_ceiling"] == 80
    assert preflight["decision"] == "STOP_BEFORE_PROVIDER_CALLS"
    assert acquisition["provider_calls_made"] == 0
    assert acquisition["provider_requests_used"] == 0
    assert acquisition["status"] == "STOPPED_BEFORE_NETWORK"


def test_rest_corpus_qualifies_with_zero_forbidden_overlap() -> None:
    manifest = _load("docs/evaluation/matchforge-historical-context-corpus-v1-manifest.json")
    rest = _load("docs/evaluation/matchforge-rest-context-corpus-v1-manifest.json")
    qualification = _load(
        "docs/evidence/matchforge-historical-context-corpus-v1-qualification-2026-10-08.json"
    )

    assert manifest["target_manifest_outcome_blind"] is True
    assert manifest["target_count"] == rest["target_count"] >= 600
    assert rest["competition_count"] >= 3
    assert sum(count >= 150 for count in rest["targets_by_competition"].values()) >= 3
    assert manifest["firewall"]["admitted_target_overlap"] == 0
    assert qualification["global_forbidden_target_overlap"] == 0
    assert qualification["family_results"]["REST"] == "QUALIFIED"
    assert qualification["final_disposition"] == "PARTIAL_CONTEXT_CORPUS_QUALIFIED"


def test_target_manifest_and_phase_a_snapshots_exclude_outcomes_and_labels() -> None:
    manifest = _load("docs/evaluation/matchforge-historical-context-corpus-v1-manifest.json")
    targets = _load_jsonl(manifest["target_manifest"]["path"])
    snapshots = _load_jsonl(manifest["historical_context_snapshots"]["path"])
    forbidden_keys = {"final_score", "home_score", "away_score", "forecast_loss", "winner"}

    assert len(targets) == len(snapshots) == manifest["target_count"]
    for target in targets:
        assert forbidden_keys.isdisjoint(target)
        assert target["rest_context_available"] is True
        assert target["point_in_time_reconstruction_status"] == "POINT_IN_TIME_VERIFIED"
    for snapshot in snapshots:
        assert forbidden_keys.isdisjoint(snapshot)
        assert "confirmed_lineup" not in snapshot


def test_unqualified_families_remain_separate_and_goal_evaluation_was_not_run() -> None:
    lineup = _load("docs/evaluation/matchforge-lineup-prediction-corpus-v1-manifest.json")
    availability = _load("docs/evaluation/matchforge-availability-context-corpus-v1-manifest.json")
    manager = _load("docs/evaluation/matchforge-manager-context-corpus-v1-manifest.json")
    travel = _load("docs/evaluation/matchforge-travel-context-corpus-v1-manifest.json")
    lineup_validation = _load(
        "docs/evidence/matchforge-historical-context-corpus-v1-lineup-validation-2026-10-08.json"
    )
    qualification = _load(
        "docs/evidence/matchforge-historical-context-corpus-v1-qualification-2026-10-08.json"
    )

    assert {lineup["status"], availability["status"], manager["status"], travel["status"]} == {
        "INSUFFICIENT"
    }
    assert availability["tier_a_fixture_count"] == 0
    assert availability["tier_b_fixture_count"] == 0
    assert lineup_validation["cases"] == 0
    assert lineup_validation["goal_model_metrics_calculated"] is False
    assert qualification["context_goal_model_evaluation_executed"] is False
    assert qualification["production_champion_changed"] is False
