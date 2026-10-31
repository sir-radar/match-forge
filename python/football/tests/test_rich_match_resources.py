from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource


def normalize(provider: str, resource: str, payload: object) -> NormalizationResult:
    if provider == "fotmob" and isinstance(payload, dict):
        payload = {**payload, "general": {**payload.get("general", {}), "matchId": 123}}
    raw = json.dumps(payload).encode()
    source = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")
    now = datetime(2026, 10, 16, 12, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            provider, None, source, source, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="match-m_abcdef-shots" if provider == "pitchapi" else "test-resource",
        fixture_native_id="m_abcdef" if provider == "pitchapi" else "123",
    )
    result = normalize_resource(context, resource, raw)
    assert result == normalize_resource(context, resource, raw)
    return result


def stats_payload(provider: str, rows: list[tuple[str, object, object]]) -> dict[str, Any]:
    if provider == "fotmob":
        return {
            "general": {"homeTeam": {"id": 1}, "awayTeam": {"id": 2}},
            "content": {
                "stats": {
                    "Periods": {
                        "All": {
                            "stats": [
                                {
                                    "stats": [
                                        {"key": key, "stats": [home, away]}
                                        for key, home, away in rows
                                    ]
                                }
                            ]
                        }
                    }
                }
            },
        }
    return {
        "data": {
            "home_team": {"id": "h"},
            "away_team": {"id": "a"},
            "periods": [
                {
                    "period": "All",
                    "groups": [
                        {
                            "items": [
                                {"key": key, "home": home, "away": away} for key, home, away in rows
                            ]
                        }
                    ],
                }
            ],
        }
    }


@pytest.mark.parametrize("provider", ["fotmob", "pitchapi"])
def test_rich_team_statistics_keep_counts_percentages_and_missing_separate(provider: str) -> None:
    payload = stats_payload(
        provider,
        [
            ("passes", None, None),
            ("passes", 100, 0),
            ("accurate_passes", "75 (75%)", "0 (0%)"),
            ("Offsides", 0, None),
            ("ShotsOffTarget", 2, 0),
            ("blocked_shots", 1, 0),
            ("matchstats.headers.tackles", 7, 1),
            ("shots_woodwork", 0, None),
            ("expected_goals_on_target", 1.4, 0),
            ("player_throws", 4, 2),
        ],
    )
    result = normalize(provider, "statistics", payload)
    home, away = [json.loads(o.to_bytes()) for o in result.observations]
    assert home["contract"] == "TeamStatisticObservationV3"
    assert home["passes"] == 100 and home["accurate_passes"] == 75
    assert away["passes"] == away["accurate_passes"] == 0
    assert home["offsides"] == 0 and away["offsides"] is None
    assert home["expected_goals_on_target"] == 1.4
    assert home["throw_ins"] is None
    assert any(f.evidence.get("source_key") == "player_throws" for f in result.findings)


@pytest.mark.parametrize("value", ["3 (101%)", "3 (NaN%)", "3 broken", True, -1])
def test_rich_count_formats_reject_invalid_values(value: object) -> None:
    result = normalize(
        "fotmob", "statistics", stats_payload("fotmob", [("accurate_passes", value, 0)])
    )
    assert any(f.rule_code == "MF_NORM_SOURCE_RECORD_INVALID" for f in result.findings)
    assert not result.observations


@pytest.mark.parametrize("provider", ["fotmob", "pitchapi"])
def test_rich_player_values_use_reported_pass_total_and_preserve_xg_zero(provider: str) -> None:
    player = {
        "id": 1,
        "name": "Player",
        "teamId": 2,
        "stats": [
            {
                "stats": {
                    "Accurate passes": {
                        "key": "accurate_passes",
                        "stat": {
                            "type": "fractionWithPercentage",
                            "total": 12,
                            "value": 10,
                        },
                    },
                    "SOT": {"key": "ShotsOnTarget", "stat": {"type": "integer", "value": 0}},
                    "xG": {"key": "expected_goals", "stat": {"type": "double", "value": 0}},
                }
            }
        ],
    }
    payload = (
        {"content": {"playerStats": {"1": player}}}
        if provider == "fotmob"
        else {
            "data": [
                {
                    "player": {"id": "p1", "name": "Player"},
                    "team_id": "t2",
                    "stats": player["stats"],
                }
            ]
        }
    )
    result = normalize(provider, "player_statistics", payload)
    stat = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "PlayerStatisticObservationV3"
    )
    assert stat["passes"] == 12 and stat["accurate_passes"] == 10
    assert stat["expected_goals"] == stat["shots_on_target"] == 0
    assert stat["player"]["canonical_id"] is None


@pytest.mark.parametrize("provider", ["fotmob", "pitchapi"])
def test_shots_retain_reported_body_situation_and_zero_xgot(provider: str) -> None:
    payload: dict[str, Any]
    if provider == "fotmob":
        payload = {
            "content": {
                "shotmap": {
                    "shots": [
                        {
                            "teamId": 2,
                            "shotType": "LeftFoot",
                            "situation": "UnmappedSituation",
                            "expectedGoalsOnTarget": 0,
                        }
                    ]
                }
            }
        }
    else:
        payload = {
            "data": {
                "periods": [
                    {
                        "period": "FirstHalf",
                        "shots": [
                            {
                                "team_id": "t2",
                                "shot_type": "LeftFoot",
                                "situation": "UnmappedSituation",
                                "expected_goals_on_target": 0,
                            }
                        ],
                    }
                ]
            }
        }
    result = normalize(provider, "shots", payload)
    shot = json.loads(result.observations[0].to_bytes())
    assert shot["contract"] == "ShotObservationV3"
    assert shot["body_part"] == "LeftFoot" and shot["situation"] == "UnmappedSituation"
    assert shot["expected_goals_on_target"] == 0
    assert shot["versions"]["semantic_version"] is None


@pytest.mark.parametrize("value", [1.01, -0.01, True])
def test_invalid_shot_xgot_is_quarantined(value: object) -> None:
    result = normalize(
        "fotmob",
        "shots",
        {
            "content": {
                "shotmap": {
                    "shots": [{"teamId": 2, "expectedGoals": 0.1, "expectedGoalsOnTarget": value}]
                }
            }
        },
    )
    assert not result.observations
    assert any(f.severity == "QUARANTINE" for f in result.findings)


def test_rich_conflicting_duplicates_remove_only_the_ambiguous_measurement() -> None:
    result = normalize(
        "fotmob",
        "statistics",
        stats_payload(
            "fotmob",
            [
                ("passes", 100, 0),
                ("accurate_passes", "75 (75%)", "0 (0%)"),
                ("accurate_passes", "74 (74%)", "0 (0%)"),
            ],
        ),
    )
    home, away = [json.loads(o.to_bytes()) for o in result.observations]
    assert home["passes"] == 100 and home.get("accurate_passes") is None
    assert away["accurate_passes"] == 0
    assert any(f.rule_code == "MF_NORM_STATISTIC_DUPLICATE" for f in result.findings)
