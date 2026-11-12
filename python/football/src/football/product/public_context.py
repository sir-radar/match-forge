"""Public context features from centrally eligible, provider-neutral facts."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from football.context.live import rest_context
from football.product.form import (
    DEFAULT_WINDOW,
    FORM_ORDER,
    FORM_POLICY_VERSION,
    team_form,
    window_matches,
)
from football.product.public_analytics import summarize_form, summarize_h2h


def _form_rows(form: dict[str, Any], window: str, *, played: bool) -> tuple[dict[str, Any], ...]:
    """Selected matches of one window; played=True reports the on-field score."""
    rows = []
    for match in window_matches(form, window):
        row = dict(match)
        if played:
            row["goals_for"] = row["played_goals_for"]
            row["goals_against"] = row["played_goals_against"]
        rows.append(row)
    return tuple(rows)


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
    if source.get("form_policy_version", FORM_POLICY_VERSION) != FORM_POLICY_VERSION:
        raise ValueError("context source was built for a different form policy")
    home_form, away_form = team_form(source, home_id), team_form(source, away_id)
    h2h = tuple(
        {
            key: row[key]
            for key in (
                "fixture_id",
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
        "home_form": list(_form_rows(home_form, DEFAULT_WINDOW, played=False)),
        "away_form": list(_form_rows(away_form, DEFAULT_WINDOW, played=False)),
        "form": {
            "policy_version": FORM_POLICY_VERSION,
            "order": FORM_ORDER,
            "default_window": DEFAULT_WINDOW,
            "home": home_form,
            "away": away_form,
        },
        "h2h": list(h2h),
        "h2h_summary": summarize_h2h(h2h),
        "home_team_statistics": summarize_form(
            _form_rows(home_form, "FORECAST_ELIGIBLE_ALL_5", played=True)
        ),
        "away_team_statistics": summarize_form(
            _form_rows(away_form, "FORECAST_ELIGIBLE_ALL_5", played=True)
        ),
        "coach_context": _coaches(source, kickoff),
        "rest_context": rest,
    }
