from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from football.validation.pitchapi import PitchApiSeasonScope

import scripts.run_pitchapi_multi_domain_development_acquisition as multi_domain
from scripts.run_h2h_development_history_acquisition import (
    CONFIG_PATH,
    _bundesliga_extension_decision,
    _load_config,
    _regular_season_structure,
    _select_regular_season_manifest,
)
from scripts.run_pitchapi_multi_domain_development_acquisition import _provider_resource_id
from scripts.run_pitchapi_snapshot_v1_acquisition import Resource, SnapshotStop


def _regular_matches(team_count: int) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    index = 0
    for home in range(team_count):
        for away in range(team_count):
            if home == away:
                continue
            index += 1
            matches.append(
                {
                    "id": f"m_{index}",
                    "date": "2023-01-01",
                    "time_utc": (
                        f"2023-01-{1 + (index - 1) // 24:02d}T{(index - 1) % 24:02d}:00:00Z"
                    ),
                    "status": "finished",
                    "home_team": {"id": f"t_{home}"},
                    "away_team": {"id": f"t_{away}"},
                    "score_home": 0,
                    "score_away": 0,
                }
            )
    return matches


def _exclusion() -> dict[str, object]:
    config = json.loads(CONFIG_PATH.read_text())
    return cast(dict[str, object], config["postseason_exclusions"][0])


def _serie_a_payload() -> tuple[dict[str, Any], dict[str, Any]]:
    matches = _regular_matches(20)
    matches.append(
        {
            "id": "m_3ir3kE",
            "date": "2023-06-11",
            "time_utc": "2023-06-11T18:45:00Z",
            "status": "finished",
            "home_team": {"id": "t_2QVYlo"},
            "away_team": {"id": "t_0YcbNh"},
            "score_home": 1,
            "score_away": 3,
        }
    )
    manifest = {
        "data": {
            "league": {"id": "l_0ALvwF", "name": "Serie A", "season": "2022/2023"},
            "matches": matches,
        }
    }
    detail = {
        "data": {
            "id": "m_3ir3kE",
            "league": {"id": "l_0ALvwF", "name": "Serie A"},
            "season": "2022/2023",
            "home_team": {"id": "t_2QVYlo", "name": "Spezia"},
            "away_team": {"id": "t_0YcbNh", "name": "Hellas Verona"},
            "time_utc": "2023-06-11T18:45:00Z",
            "status": "finished",
            "round_name": "final",
            "has_playoff": False,
        }
    }
    return manifest, detail


def test_v3_configuration_is_frozen_and_request_budget_balances() -> None:
    config = _load_config(CONFIG_PATH)

    assert config["authorization"] == "MATCHFORGE_H2H_DEVELOPMENT_HISTORY_ACQUISITION_V3"
    assert config["expected_requests"] == 382
    assert config["shot_requests"] == 380
    rule = cast(dict[str, object], config["regular_season_eligibility_rule"])
    assert rule["on_ambiguous_classification"] == ("PROVIDER_COMPETITION_STAGE_AMBIGUOUS")


def test_regular_season_structure_requires_complete_directed_schedule() -> None:
    matches = _regular_matches(18)

    assert _regular_season_structure(matches) == {
        "status": "PASS",
        "fixture_count": 306,
        "team_count": 18,
        "expected_double_round_robin_fixtures": 306,
        "unique_directed_pairs": 306,
        "duplicate_directed_pairs": 0,
        "self_matches": 0,
    }
    assert _regular_season_structure([*matches, matches[0]])["status"] == "FAIL"


def test_verified_relegation_playoff_is_excluded_before_selection() -> None:
    manifest, detail = _serie_a_payload()
    scope = PitchApiSeasonScope("serie_a_2022_23", "l_0ALvwF", "2022/2023", 380)

    selection, _, validation_scope, excluded = _select_regular_season_manifest(
        manifest, scope, 380, detail, _exclusion()
    )

    assert len(selection.ordered_matches) == 380
    assert validation_scope.expected_match_count == 380
    assert all(match["id"] != "m_3ir3kE" for match in selection.ordered_matches)
    assert excluded["classification"] == (
        "POSTSEASON_FIXTURE_EXCLUDED_BY_FROZEN_COMPETITION_STAGE_RULE"
    )
    assert cast(dict[str, object], excluded["provider_detail"])["round_name"] == "final"


def test_stage_mismatch_fails_closed() -> None:
    manifest, detail = _serie_a_payload()
    detail["data"]["round_name"] = "38"
    scope = PitchApiSeasonScope("serie_a_2022_23", "l_0ALvwF", "2022/2023", 380)

    with pytest.raises(SnapshotStop, match="PROVIDER_COMPETITION_STAGE_AMBIGUOUS"):
        _select_regular_season_manifest(manifest, scope, 380, detail, _exclusion())


def test_match_detail_has_stable_provider_resource_identity() -> None:
    resource = Resource(
        "match_detail:serie_a_2022_23:m_3ir3kE",
        "serie_a_2022_23",
        "match_detail",
        "/v1/matches/m_3ir3kE",
        "2026-09-28T00:00:00Z",
        "a" * 64,
        1,
        "raw.json",
        "b" * 64,
        1,
        "normalized.json",
    )

    assert _provider_resource_id(resource, {}) == "m_3ir3kE"


def test_bundesliga_extension_is_blocked_by_frozen_firewall() -> None:
    assessment = _bundesliga_extension_decision(
        {
            "coverage": {"at_least_2": {"count": 593}},
            "coverage_by_competition": {"Bundesliga": {"target_count": 431, "at_least_2": 169}},
        }
    )

    assert assessment["can_mathematically_close_gap"] is True
    assert assessment["v5_protected_scope_intersection"] is True
    assert assessment["prior_spent_scope_intersection"] is True
    assert assessment["acquisition_permitted"] is False
    assert assessment["decision"] == "DO_NOT_ACQUIRE_FROZEN_FIREWALL_WOULD_FAIL"


def test_frozen_scope_firewall_uses_tracked_contract_without_local_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(multi_domain, "V5_ROOT", tmp_path / "missing")

    assert ("bundesliga", "2023/2024") in multi_domain._v5_evaluation_scopes()
    assert ("bundesliga", "2021/2022") in multi_domain._prior_spent_scopes()


def test_v2_result_and_report_remain_unchanged() -> None:
    expected = {
        Path(
            "docs/evidence/matchforge-h2h-development-history-acquisition-v2-result-2026-09-28.json"
        ): ("90e38f596f414ba85532e23ff68c6a1d49cd727b172932701772e0e5e629354d"),
        Path(
            "docs/evidence/matchforge-h2h-development-history-acquisition-v2-result-2026-09-28.md"
        ): ("c2b0cec2efea6fb47fd77113a085bde89b3b05066f180bde84c2ef49234dff70"),
    }

    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in expected} == expected
