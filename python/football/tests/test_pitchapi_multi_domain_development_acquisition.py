from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from football.validation.pitchapi import PitchApiSeasonScope

import scripts.run_pitchapi_multi_domain_development_acquisition as acquisition
from scripts.run_pitchapi_multi_domain_development_acquisition import (
    CONFIG_PATH,
    GroupSpec,
    _groups,
    _load_config,
    _mapping,
    _package_failures,
    _register_mappings,
    _resolve_scopes,
    _select_valid_manifest,
    _targets,
)
from scripts.run_pitchapi_snapshot_v1_acquisition import SnapshotStop


def _matches(rounds: int = 11) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for round_index in range(rounds):
        kickoff = f"2024-08-{round_index + 1:02d}T18:00:00Z"
        for fixture_index in range(2):
            match_id = f"m_{round_index}_{fixture_index}"
            matches.append(
                {
                    "id": match_id,
                    "time_utc": kickoff,
                    "home_team": {"id": f"t_{fixture_index * 2}"},
                    "away_team": {"id": f"t_{fixture_index * 2 + 1}"},
                    "score_home": 1,
                    "score_away": 0,
                }
            )
    return matches


def test_frozen_configuration_has_exact_authorized_scope_and_budget() -> None:
    config = _load_config(CONFIG_PATH)
    groups = _groups(config)

    assert [(group.competition, group.season) for group in groups] == [
        ("Bundesliga", "2024/2025"),
        ("Bundesliga", "2025/2026"),
        ("Premier League", "2024/2025"),
        ("La Liga", "2024/2025"),
        ("Serie A", "2024/2025"),
    ]
    assert sum(group.expected_matches for group in groups) == 1752
    assert config["expected_requests"] == 1758
    assert config["hard_request_ceiling"] == 1791
    assert config["prior_attempts_used"] == 3
    assert config["task_hard_request_ceiling"] == 1794
    assert config["hard_storage_ceiling_bytes"] == 1024**3


def test_resolve_scopes_requires_exact_catalog_match() -> None:
    group = GroupSpec("scope", "La Liga", "ESP", "2024/2025", 380, 280)
    payload: dict[str, Any] = {
        "data": {
            "leagues": [
                {
                    "id": "l_leagueid",
                    "name": "LaLiga",
                    "country_code": "ESP",
                    "seasons": ["2024/2025"],
                }
            ]
        }
    }

    resolved = _resolve_scopes(payload, (group,))

    assert resolved["scope"].league_id == "l_leagueid"

    payload["data"]["leagues"][0]["country_code"] = "OTHER"
    with pytest.raises(SnapshotStop, match="AUTHORIZED_SCOPE_UNAVAILABLE:scope"):
        _resolve_scopes(payload, (group,))


def test_manifest_quarantines_awarded_fixture_before_existing_validation() -> None:
    matches = _matches()
    for index, match in enumerate(matches):
        match["id"] = f"m_{index}"
        match["date"] = str(match["time_utc"])[:10]
        match["status"] = "finished"
    matches[5]["status"] = "awarded"
    payload = {
        "data": {
            "league": {"id": "l_test", "name": "Test", "season": "2024/2025"},
            "matches": matches,
        }
    }
    scope = PitchApiSeasonScope("scope", "l_test", "2024/2025", 22)

    selection, exclusions, validation_scope = _select_valid_manifest(payload, scope, 22)

    assert len(selection.ordered_matches) == 21
    assert exclusions == {"awarded": 1}
    assert validation_scope.expected_match_count == 21
    assert all(match["status"] == "finished" for match in selection.ordered_matches)


def test_targets_freeze_same_kickoff_before_history_update() -> None:
    matches = _matches()
    mappings: dict[tuple[str, str], str] = {}
    _register_mappings(mappings, matches)
    lineage = {
        str(match["id"]): {
            "resource_ref": f"shots:{match['id']}",
            "raw_sha256": "a" * 64,
            "normalized_sha256": "b" * 64,
        }
        for match in matches
    }
    group = GroupSpec("scope", "Test", "TST", "2024/2025", 22, 2)

    rows, outcomes, teams = _targets(
        group,
        matches,
        lineage,
        mappings,
        UUID("00000000-0000-0000-0000-000000000001"),
    )

    assert len(rows) == 2
    assert outcomes == Counter({"home": 2})
    assert len(teams) == 4
    assert {row["home_prior_appearances"] for row in rows} == {10}
    assert {row["away_prior_appearances"] for row in rows} == {10}
    assert all(row["football_cutoff"] == row["kickoff"] for row in rows)


def test_canonical_mapping_preserves_pitchapi_namespace() -> None:
    mappings: dict[tuple[str, str], str] = {}

    canonical = _mapping(mappings, "match", "m_00R1We")

    assert canonical == "c2bc17d8-470d-5fd0-903a-379496fac6cd"


def test_package_qualification_requires_all_floors_and_firewall() -> None:
    summaries: list[dict[str, object]] = [
        {"scope_key": "scope", "qualification_failures": []},
    ]
    passing_outcomes = Counter({"home": 450, "draw": 300, "away": 450})

    assert _package_failures(summaries, 1200, passing_outcomes, "PASS", {"status": "PASS"}) == []
    failures = _package_failures(
        summaries,
        1199,
        Counter({"home": 450, "draw": 249, "away": 500}),
        "FAIL",
        {"status": "FAIL"},
    )

    assert "TOTAL_TARGET_SHORTFALL:1" in failures
    assert "TOTAL_DRAW_OUTCOMES_LT_250" in failures
    assert "TECHNICAL_STATUS:FAIL" in failures
    assert "FIREWALL" in failures


def test_firewall_rejects_spent_and_protected_identity_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition, "_v5_target_ids", lambda: {"spent"})
    monkeypatch.setattr(
        acquisition,
        "_prior_spent_pitchapi",
        lambda: ({"spent"}, {("bundesliga", "2023/2024")}),
    )
    monkeypatch.setattr(
        acquisition,
        "_v5_evaluation_scopes",
        lambda: {("bundesliga", "2023/2024")},
    )
    monkeypatch.setattr(acquisition, "_statsbomb_protected_ids", lambda: {"protected"})
    targets: list[dict[str, object]] = [
        {"canonical_fixture_id": "spent", "scope_key": "scope"},
        {"canonical_fixture_id": "protected", "scope_key": "scope"},
    ]
    summaries: list[dict[str, object]] = [
        {"scope_key": "scope", "competition": "La Liga", "season": "2024/2025"}
    ]

    report = acquisition._firewall(targets, summaries)

    assert report["status"] == "FAIL"
    assert report["v5_intersection_count"] == 1
    assert report["statsbomb_protected_intersection_count"] == 1


def test_invalid_request_arithmetic_stops_before_acquisition(tmp_path: Path) -> None:
    payload = json.loads(CONFIG_PATH.read_text())
    payload["expected_requests"] = 1
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(SnapshotStop, match="CONFIGURATION_REQUEST_BUDGET_MISMATCH"):
        _load_config(path)
