from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_h2h_development_history_acquisition import (
    CONFIG_PATH,
    EXCLUDED_COMPETITIONS,
    _classification,
    _groups,
    _load_config,
    _mapping_continuity,
)
from scripts.run_pitchapi_snapshot_v1_acquisition import SnapshotStop


def _coverage(two: int, three: int, per_competition: tuple[int, ...]) -> dict[str, object]:
    names = ("Bundesliga", "Premier League", "Serie A")
    return {
        "coverage": {
            "at_least_2": {"count": two},
            "at_least_3": {"count": three},
        },
        "coverage_by_competition": {
            (names[index] if index < len(names) else f"competition_{index}"): {"at_least_2": count}
            for index, count in enumerate(per_competition)
        },
    }


def test_configuration_freezes_exact_history_scope_and_budget() -> None:
    config = _load_config(CONFIG_PATH)
    groups = _groups(config)

    assert {(group.competition, group.season) for group in groups} == {
        ("Premier League", "2022/2023"),
        ("Premier League", "2023/2024"),
        ("Serie A", "2022/2023"),
        ("Serie A", "2023/2024"),
    }
    assert EXCLUDED_COMPETITIONS == {
        "La Liga 2023/24": "EXCLUDED_FROM_H2H_DEVELOPMENT_HISTORY_V2_PROVIDER_INCOMPLETE"
    }
    assert all(group.projected_targets == 0 for group in groups)
    assert config["expected_requests"] == 382
    assert config["retry_allowance"] == 8
    assert config["match_detail_requests"] == 1
    assert config["shot_requests"] == 380
    assert config["hard_request_ceiling"] == 390
    assert config["hard_storage_ceiling_bytes"] == 512 * 1024**2


def test_invalid_request_budget_stops_before_provider_calls(tmp_path: Path) -> None:
    payload = json.loads(CONFIG_PATH.read_text())
    payload["expected_requests"] = 1
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(SnapshotStop, match="CONFIGURATION_REQUEST_BUDGET_MISMATCH"):
        _load_config(path)


def test_mapping_continuity_reuses_existing_aliases_and_rejects_mismatch() -> None:
    mappings = {("team", "provider-team"): "canonical-team"}

    result = _mapping_continuity(mappings, mappings)

    assert result["status"] == "PASS"
    assert result["existing_team_aliases_reused"] == 1
    with pytest.raises(SnapshotStop, match="CANONICAL_MAPPING_CONTINUITY_FAILURE"):
        _mapping_continuity(mappings, {("team", "provider-team"): "different"})


def test_classification_requires_global_and_three_domain_floors() -> None:
    summaries: tuple[dict[str, object], ...] = ({"qualification_failures": []},)
    firewall: dict[str, object] = {"status": "PASS"}

    assert (
        _classification(summaries, _coverage(600, 300, (150, 150, 150, 149)), firewall)
        == "H2H_DEVELOPMENT_HISTORY_QUALIFIED"
    )
    assert (
        _classification(summaries, _coverage(599, 300, (150, 150, 150)), firewall)
        == "H2H_DEVELOPMENT_HISTORY_INSUFFICIENT"
    )
    assert (
        _classification(summaries, _coverage(600, 300, (150, 150, 149)), firewall)
        == "H2H_DEVELOPMENT_HISTORY_INSUFFICIENT"
    )
    assert (
        _classification(
            ({"qualification_failures": ["SCHEMA"]},),
            _coverage(600, 300, (150, 150, 150)),
            firewall,
        )
        == "ACQUISITION_FAILED"
    )


def test_classification_requires_each_named_competition_floor() -> None:
    summaries: tuple[dict[str, object], ...] = ({"qualification_failures": []},)
    firewall: dict[str, object] = {"status": "PASS"}
    coverage = _coverage(600, 300, ())
    coverage["coverage_by_competition"] = {
        "Bundesliga": {"at_least_2": 150},
        "Premier League": {"at_least_2": 150},
        "Serie A": {"at_least_2": 149},
        "Other": {"at_least_2": 500},
    }

    assert _classification(summaries, coverage, firewall) == "H2H_DEVELOPMENT_HISTORY_INSUFFICIENT"
