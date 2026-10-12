"""Development-only forecast preview using point-in-time eligible provider resources."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection

from football.product.domain import FinishedMatch, forecast_from_history, forecast_payload


def development_provider_preview(
    connection: Connection[Any],
    fixture_id: UUID,
    knowledge_cutoff: datetime,
    artifact_path: Path,
    *,
    provider_code: str = "pitchapi",
) -> dict[str, object]:
    if provider_code not in {"pitchapi", "fotmob"}:
        raise ValueError("feature provider must be pitchapi or fotmob")
    if knowledge_cutoff.tzinfo is None or knowledge_cutoff.utcoffset() is None:
        raise ValueError("knowledge_cutoff must include a timezone")
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT kickoff_at, home_team_id, away_team_id
                 FROM football.product_fixtures WHERE fixture_id = %s""",
            (fixture_id,),
        )
        target = cursor.fetchone()
        if target is None:
            raise ValueError("target fixture does not exist")
        target_kickoff, home_team_id, away_team_id = target
        if knowledge_cutoff >= target_kickoff:
            raise ValueError("knowledge_cutoff must precede target kickoff")
        cursor.execute(
            """SELECT fixture_id, kickoff_at, home_team_id, away_team_id,
                      home_goals, away_goals, home_xg, away_xg
                 FROM football.product_eligible_match_history
                WHERE ((source_kickoff_precision = 'EXACT' AND kickoff_at < %(cutoff)s)
                       OR (source_kickoff_precision = 'DATE_ONLY'
                           AND kickoff_at::date < %(cutoff)s::date))
                  AND known_at <= %(cutoff)s
                  AND (home_team_id IN (%(home)s, %(away)s)
                       OR away_team_id IN (%(home)s, %(away)s))
                ORDER BY kickoff_at, fixture_id""",
            {"cutoff": knowledge_cutoff, "home": home_team_id, "away": away_team_id},
        )
        history = [FinishedMatch(*row) for row in cursor.fetchall()]
        cursor.execute(
            """SELECT DISTINCT ON (resource.canonical_fixture_id, resource.provider_code,
                                    resource.resource_type)
                      resource.canonical_fixture_id, resource.provider_code,
                      resource.provider_match_id, resource.resource_type,
                      resource.observed_at, resource.known_at, resource.payload
                 FROM football.product_provider_resource_observations resource
                 JOIN football.product_eligible_match_history history
                   ON history.fixture_id = resource.canonical_fixture_id
                WHERE resource.canonical_fixture_id <> %s
                  AND history.kickoff_at < %s
                  AND history.known_at <= %s
                  AND (history.home_team_id IN (%s, %s)
                       OR history.away_team_id IN (%s, %s))
                  AND resource.development_only
                  AND resource.provider_code = %s
                  AND resource.point_in_time_eligibility = 'ELIGIBLE'
                  AND resource.known_at IS NOT NULL AND resource.known_at <= %s
                  AND EXISTS (
                      SELECT 1 FROM football.match_provider_mappings mapping
                      JOIN football.providers provider ON provider.id = mapping.provider_id
                      WHERE provider.code = resource.provider_code
                        AND mapping.provider_match_id = resource.provider_match_id
                        AND mapping.match_id = resource.canonical_fixture_id
                        AND mapping.valid_to IS NULL
                        AND COALESCE(mapping.valid_from, mapping.first_seen_at) <= %s
                  )
                ORDER BY resource.canonical_fixture_id, resource.provider_code,
                         resource.resource_type, resource.known_at DESC,
                         resource.resource_observation_id DESC""",
            (
                fixture_id,
                knowledge_cutoff,
                knowledge_cutoff,
                home_team_id,
                away_team_id,
                home_team_id,
                away_team_id,
                provider_code,
                knowledge_cutoff,
                knowledge_cutoff,
            ),
        )
        resources = cursor.fetchall()

    xg_by_fixture, evidence, totals = _consume_resources(connection, history, resources)
    supplemented = [
        FinishedMatch(
            item.fixture_id,
            item.kickoff_at,
            item.home_team_id,
            item.away_team_id,
            item.home_goals,
            item.away_goals,
            *(xg_by_fixture.get(item.fixture_id, (None, None))),
        )
        for item in history
    ]
    baseline = forecast_from_history(
        artifact_path=artifact_path,
        target_kickoff=target_kickoff,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        history=history,
    )
    preview = forecast_from_history(
        artifact_path=artifact_path,
        target_kickoff=target_kickoff,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        history=supplemented,
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    return {
        "mode": "DEVELOPMENT_PROVIDER_FEATURE_PREVIEW",
        "feature_provider": provider_code,
        "xg_definition": "provider shot expected goals; no cross-provider xG blending",
        "canonical_fixture_id": str(fixture_id),
        "knowledge_cutoff": knowledge_cutoff.isoformat(),
        "target_kickoff": target_kickoff.isoformat(),
        "model": {
            "artifact": str(artifact_path),
            "model_family": artifact.get("model_family", "pitchapi-v3-reference"),
            "algorithm_version": artifact.get("algorithm_version", "unknown"),
            "uses_provider_xg": artifact.get("parameters", {}).get("beta_xg_for", 0) != 0,
        },
        "feature_values": totals | {"xg_matches_supplemented": len(xg_by_fixture)},
        "resource_evidence": evidence,
        "baseline_forecast": forecast_payload(baseline) if baseline else None,
        "provider_feature_forecast": forecast_payload(preview) if preview else None,
        "production_forecasts_modified": False,
    }


def _consume_resources(
    connection: Connection[Any], history: list[FinishedMatch], resources: list[Any]
) -> tuple[dict[UUID, tuple[float, float]], list[dict[str, object]], dict[str, int]]:
    aliases = _team_aliases(connection)
    xg_by_fixture: dict[UUID, tuple[float, float]] = {}
    evidence: list[dict[str, object]] = []
    totals = {
        "shots": 0,
        "shots_on_target": 0,
        "lineup_players": 0,
        "rated_players": 0,
        "h2h_resources": 0,
    }
    for canonical_id, provider, match_id, kind, observed_at, known_at, payload in resources:
        summary: dict[str, object]
        if kind == "SHOTS":
            summary = _shot_features(payload, provider_code=provider)
            shot_count = summary["shots"]
            on_target_count = summary["shots_on_target"]
            assert isinstance(shot_count, int) and isinstance(on_target_count, int)
            totals["shots"] += shot_count
            totals["shots_on_target"] += on_target_count
            match = next((item for item in history if item.fixture_id == canonical_id), None)
            if match is not None:
                teams = aliases.get(provider, {})
                by_team = summary["xg_by_team"]
                assert isinstance(by_team, dict)
                home_xg = sum(
                    v for key, v in by_team.items() if teams.get(key) == match.home_team_id
                )
                away_xg = sum(
                    v for key, v in by_team.items() if teams.get(key) == match.away_team_id
                )
                if (home_xg or away_xg) and all(key in teams for key in by_team):
                    xg_by_fixture[canonical_id] = (home_xg, away_xg)
        elif kind == "LINEUPS":
            players = _lineup_players(payload)
            totals["lineup_players"] += players
            summary = {"lineup_players": players}
        elif kind == "PLAYER_RATINGS":
            players = len(payload) if isinstance(payload, list) else 0
            totals["rated_players"] += players
            summary = {"rated_players": players}
        elif kind == "H2H":
            totals["h2h_resources"] += 1
            summary = {"available": True}
        else:
            continue
        evidence.append(
            {
                "canonical_fixture_id": str(canonical_id),
                "provider": provider,
                "provider_match_id": match_id,
                "resource_type": kind,
                "observed_at": observed_at.isoformat(),
                "known_at": known_at.isoformat(),
                "eligibility": "ELIGIBLE",
                "features": summary,
            }
        )
    return xg_by_fixture, evidence, totals


def _team_aliases(connection: Connection[Any]) -> dict[str, dict[str, UUID]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT provider.code, mapping.provider_team_id, mapping.team_id
                 FROM football.team_provider_mappings mapping
                 JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE mapping.mapping_confidence = 1 AND mapping.valid_to IS NULL"""
        )
        result: dict[str, dict[str, UUID]] = {}
        for provider, provider_team_id, team_id in cursor.fetchall():
            result.setdefault(provider, {})[provider_team_id] = team_id
        return result


def _provider_shots(payload: object, provider_code: str) -> list[Mapping[str, Any]]:
    shots: list[Mapping[str, Any]] = []
    if provider_code == "fotmob" and isinstance(payload, list):
        shots = [item for item in payload if isinstance(item, Mapping)]
    elif isinstance(payload, Mapping):
        periods = payload.get("periods")
        if isinstance(periods, list):
            for period in periods:
                if isinstance(period, Mapping) and isinstance(period.get("shots"), list):
                    shots.extend(item for item in period["shots"] if isinstance(item, Mapping))
        elif isinstance(payload.get("shots"), list):
            shots.extend(item for item in payload["shots"] if isinstance(item, Mapping))
    return shots


def _shot_features(payload: object, *, provider_code: str = "pitchapi") -> dict[str, object]:
    shots = _provider_shots(payload, provider_code)
    xg_by_team: dict[str, float] = {}
    on_target = 0
    for shot in shots:
        team_id = shot.get("teamId" if provider_code == "fotmob" else "team_id")
        if provider_code == "fotmob" and isinstance(team_id, int):
            team_id = str(team_id)
        xg = shot.get("expectedGoals" if provider_code == "fotmob" else "expected_goals")
        if isinstance(team_id, str) and isinstance(xg, (int, float)) and not isinstance(xg, bool):
            if not math.isfinite(xg) or not 0 <= xg <= 1:
                raise ValueError("provider shot expected goals must be finite and in [0, 1]")
            xg_by_team[team_id] = xg_by_team.get(team_id, 0.0) + float(xg)
        on_target += int(
            shot.get("isOnTarget" if provider_code == "fotmob" else "is_on_target") is True
        )
    total_xg = sum(xg_by_team.values())
    return {
        "shots": len(shots),
        "shots_on_target": on_target,
        "total_xg": total_xg,
        "average_shot_xg": total_xg / len(shots) if shots else 0.0,
        "xg_by_team": xg_by_team,
    }


def _lineup_players(payload: object) -> int:
    if not isinstance(payload, Mapping):
        return 0
    total = 0
    for key in ("home", "away"):
        side = payload.get(key)
        if isinstance(side, Mapping) and isinstance(side.get("starters"), list):
            total += len(side["starters"])
    return total
