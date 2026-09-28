from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_h2h_development_history_acquisition import (
    CONFIG_PATH,
    _classification,
    _groups,
    _load_config,
    _mapping_continuity,
)
from scripts.run_pitchapi_snapshot_v1_acquisition import SnapshotStop


def _coverage(two: int, three: int, per_competition: tuple[int, ...]) -> dict[str, object]:
    return {
        "coverage": {
            "at_least_2": {"count": two},
            "at_least_3": {"count": three},
        },
        "coverage_by_competition": {
            f"competition_{index}": {"at_least_2": count}
            for index, count in enumerate(per_competition)
        },
    }


def test_configuration_freezes_exact_history_scope_and_budget() -> None:
    config = _load_config(CONFIG_PATH)
    groups = _groups(config)

    assert {(group.competition, group.season) for group in groups} == {
        ("Premier League", "2023/2024"),
        ("La Liga", "2023/2024"),
        ("Serie A", "2023/2024"),
    }
    assert all(group.projected_targets == 0 for group in groups)
    assert config["expected_requests"] == 1144
    assert config["retry_allowance"] == 23
    assert config["hard_request_ceiling"] == 1167
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
