from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.run_firewall_safe_h2h_history_extension import (
    CONFIG_PATH,
    LA_LIGA_2023_24_NORMALIZED_SHA256,
    V1_PRIMARY,
    _candidate_manifest_assessment,
    _load_config,
    _target_pair_completeness,
)
from scripts.run_pitchapi_snapshot_v1_acquisition import SnapshotStop


def _retained_manifest() -> dict[str, Any]:
    path = (
        V1_PRIMARY
        / "normalized"
        / "sha256"
        / LA_LIGA_2023_24_NORMALIZED_SHA256[:2]
        / f"{LA_LIGA_2023_24_NORMALIZED_SHA256}.json"
    )
    if path.exists():
        return cast(dict[str, Any], json.loads(path.read_text()))
    return _synthetic_retained_manifest()


def _synthetic_retained_manifest() -> dict[str, Any]:
    teams = [
        ("t_06N2GA", "Mallorca"),
        ("t_1pKstK", "Girona"),
        *((f"t_{index:02d}", f"Team {index:02d}") for index in range(18)),
    ]
    matches = []
    for home_id, home_name in teams:
        for away_id, away_name in teams:
            if home_id == away_id or (home_id, away_id) == ("t_06N2GA", "t_1pKstK"):
                continue
            match_id = (
                "m_326Zfh"
                if (home_id, away_id) == ("t_1pKstK", "t_06N2GA")
                else f"m_{home_id}_{away_id}"
            )
            matches.append(
                {
                    "id": match_id,
                    "status": "finished",
                    "time_utc": "2023-01-01T00:00:00Z",
                    "score_home": 0,
                    "score_away": 0,
                    "home_team": {"id": home_id, "name": home_name},
                    "away_team": {"id": away_id, "name": away_name},
                }
            )
    return {"data": {"matches": matches}}


def test_extension_configuration_freezes_pair_rule_and_request_budget() -> None:
    config = _load_config(CONFIG_PATH)

    assert config["authorization"] == "MATCHFORGE_FIREWALL_SAFE_H2H_HISTORY_EXTENSION_V1"
    assert config["expected_requests"] == 379
    assert config["season_manifest_requests"] == 1
    assert config["shot_requests"] == 378
    rule = cast(dict[str, object], config["target_pair_history_completeness"])
    assert rule["scope"] == "ALL_H2H_HISTORY_COMPETITIONS_AND_SCOPES"
    assert rule["affected_target_disposition"] == "H2H_HISTORY_INCOMPLETE"


def test_retained_laliga_manifest_quarantines_only_incomplete_pair() -> None:
    config = _load_config(CONFIG_PATH)
    assessment, eligible = _target_pair_completeness(_retained_manifest(), config)

    assert assessment["status"] == "PASS_WITH_TARGET_PAIR_QUARANTINE"
    assert assessment["provider_finished_fixtures"] == 379
    assert assessment["eligible_fixtures"] == 378
    assert assessment["missing_directed_fixtures"] == [
        {
            "away_team_id": "t_1pKstK",
            "away_team_name": "Girona",
            "home_team_id": "t_06N2GA",
            "home_team_name": "Mallorca",
        }
    ]
    assert assessment["quarantined_present_fixture_ids"] == ["m_326Zfh"]
    assert len(eligible) == 378
    assert all(str(match["id"]) != "m_326Zfh" for match in eligible)


def test_unfrozen_missing_pair_fails_closed() -> None:
    config = _load_config(CONFIG_PATH)
    payload = _retained_manifest()
    matches = cast(list[dict[str, object]], payload["data"]["matches"])
    payload["data"]["matches"] = matches[:-1]

    with pytest.raises(SnapshotStop, match="TARGET_PAIR_COMPLETENESS_MISMATCH"):
        _target_pair_completeness(payload, config)


def test_complete_candidate_manifest_has_no_pair_quarantine() -> None:
    matches: list[dict[str, object]] = []
    for home in range(3):
        for away in range(3):
            if home == away:
                continue
            matches.append(
                {
                    "id": f"m_{home}_{away}",
                    "status": "finished",
                    "time_utc": "2023-01-01T00:00:00Z",
                    "score_home": 0,
                    "score_away": 0,
                    "home_team": {"id": f"t_{home}", "name": f"Team {home}"},
                    "away_team": {"id": f"t_{away}", "name": f"Team {away}"},
                }
            )

    assessment = _candidate_manifest_assessment(
        {"data": {"matches": matches}}, expected_team_count=3
    )

    assert assessment["status"] == "COMPLETE"
    assert assessment["finished_fixtures"] == 6
    assert assessment["missing_directed_fixtures"] == []


def test_v3_evidence_hashes_remain_frozen() -> None:
    expected = {
        Path(
            "docs/evidence/matchforge-h2h-development-history-acquisition-v3-result-2026-09-28.json"
        ): "dfdcc133a482a7c51b738eaf9bfc5f983ed655578999567e2f99632610395b55",
        Path(
            "docs/evidence/matchforge-h2h-development-history-acquisition-v3-result-2026-09-28.md"
        ): "87ceaa4fa7fff3e1257380a545b921b0eb56d351168d6fcf088d9b9908984b61",
        Path(
            "docs/evaluation/matchforge-h2h-development-history-acquisition-v3-configuration.json"
        ): "f81c68b8f44e3f692dc76129773876c176d56313eeb56d719a6c609a8237ef50",
    }

    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in expected} == expected
