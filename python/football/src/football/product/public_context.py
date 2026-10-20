"""Public context features from centrally eligible, provider-neutral facts."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from football.context.live import rest_context
from football.product.public_analytics import summarize_form, summarize_h2h


def _form(history: list[dict[str, Any]], team_id: str) -> tuple[dict[str, Any], ...]:
    matches = []
    for row in history:
        if team_id not in (row["home_team_id"], row["away_team_id"]):
            continue
        home = row["home_team_id"] == team_id
        goals_for = row["home_goals"] if home else row["away_goals"]
        goals_against = row["away_goals"] if home else row["home_goals"]
        matches.append(
            {
                "kickoff_at": row["kickoff_at"],
                "opponent": row["away_team"] if home else row["home_team"],
                "venue": "HOME" if home else "AWAY",
                "goals_for": goals_for,
                "goals_against": goals_against,
                "result": "W"
                if goals_for > goals_against
                else "L"
                if goals_for < goals_against
                else "D",
            }
        )
        if len(matches) == 5:
            break
    return tuple(matches)


def _coaches(source: dict[str, Any], kickoff: datetime) -> list[dict[str, Any]]:
    result = []
    order = {source["home_team_id"]: 0, source["away_team_id"]: 1}
    for row in sorted(source["coaches"], key=lambda item: order[item["team_id"]]):
        prior = tuple(datetime.fromisoformat(item["kickoff_at"]) for item in row["prior_lineups"])
        result.append(
            {
                "team_id": row["team_id"],
                "coach_id": row["coach_id"],
                "coach_tenure_days": int(
                    (kickoff - min(prior, default=kickoff)).total_seconds() / 86400
                ),
                "matches_under_coach": len(prior),
                "coach_changed_recently": len(prior) < 5,
            }
        )
    return result


def context_features(source: dict[str, Any]) -> dict[str, Any]:
    kickoff = datetime.fromisoformat(source["kickoff_at"])
    history = source["history"]
    if any(row["fixture_id"] == source["fixture_id"] for row in history):
        raise ValueError("target outcomes cannot enter context features")
    home_id, away_id = source["home_team_id"], source["away_team_id"]
    home, away = _form(history, home_id), _form(history, away_id)
    h2h = tuple(
        {
            key: row[key]
            for key in (
                "kickoff_at",
                "home_team",
                "away_team",
                "home_goals",
                "away_goals",
                "home_xg",
                "away_xg",
            )
        }
        for row in history
        if {row["home_team_id"], row["away_team_id"]} == {home_id, away_id}
    )[:10]
    rest = {}
    upcoming = {row["team_id"]: row["next_kickoff"] for row in source["upcoming"]}
    for team_id in (home_id, away_id):
        prior = tuple(
            datetime.fromisoformat(row["kickoff_at"])
            for row in history
            if team_id in (row["home_team_id"], row["away_team_id"])
        )
        next_at = upcoming.get(team_id)
        rest[team_id] = asdict(
            rest_context(kickoff, prior, (datetime.fromisoformat(next_at),) if next_at else ())
        )
    return {
        "fixture_id": source["fixture_id"],
        "home_form": list(home),
        "away_form": list(away),
        "h2h": list(h2h),
        "h2h_summary": summarize_h2h(h2h),
        "home_team_statistics": summarize_form(home),
        "away_team_statistics": summarize_form(away),
        "coach_context": _coaches(source, kickoff),
        "rest_context": rest,
    }
