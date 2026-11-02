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


def normalize(league: int = 39, season: int = 2024, groups: int = 1) -> NormalizationResult:
    row: dict[str, Any] = {
        "rank": 1,
        "team": {"id": 1, "name": "Team"},
        "points": -1,
        "all": {"played": 0, "win": 0, "draw": 0, "lose": 0, "goals": {"for": 0, "against": 0}},
        "home": {"played": 123},
        "update": "2025-05-26T00:00:00+00:00",
    }
    raw = json.dumps(
        {
            "errors": [],
            "response": [
                {
                    "league": {
                        "id": league,
                        "season": season,
                        "standings": [[row] for _ in range(groups)],
                    }
                }
            ],
        }
    ).encode()
    source = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")
    now = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "api_football", None, source, source, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="/standings?league=39&season=2024",
        competition_native_id="39",
        season_label="2024",
    )
    return normalize_resource(context, "standings", raw)


def test_api_standings_retain_all_scope_points_and_known_clock() -> None:
    result = normalize()
    assert not result.findings
    item = next(o for o in result.observations if o.CONTRACT == "StandingObservationV2")
    assert item.to_dict()["played"] == 0 and item.to_dict()["points"] == -1
    assert item.time.provider_updated_at == datetime(2025, 5, 26, tzinfo=UTC)
    assert item.time.known_at == datetime(2026, 11, 1, tzinfo=UTC)
    assert item.time.event_time is None


@pytest.mark.parametrize("league,season", [(40, 2024), (39, 2025)])
def test_api_standings_reject_conflicting_scope(league: int, season: int) -> None:
    result = normalize(league, season)
    assert not result.observations and result.findings


def test_group_standings_do_not_become_global_competition_ranks() -> None:
    result = normalize(groups=2)
    assert not result.observations
    assert result.findings[0].rule_code == "MF_NORM_STANDING_SCOPE_UNSUPPORTED"
