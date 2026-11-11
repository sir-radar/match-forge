"""Recent form under one policy: which matches count, in what order, on which score.

Every window is selected from the same merged candidates so official, played and
forecast-eligible form cannot drift apart. The caller supplies facts that were
already qualified for the cutoff; nothing here reads a provider or a database.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from football.contracts.source import canonical_json_bytes, sha256_bytes

FORM_POLICY_VERSION = "form-policy-v1"
FORM_ORDER = "NEWEST_FIRST"
DEFAULT_WINDOW = "OFFICIAL_ALL_5"
STALE_AFTER = timedelta(days=180)

# key: (basis, scope, venue, requested)
WINDOWS: dict[str, tuple[str, str, str, int]] = {
    "OFFICIAL_ALL_5": ("OFFICIAL", "ALL_COMPETITIONS", "ALL", 5),
    "OFFICIAL_ALL_10": ("OFFICIAL", "ALL_COMPETITIONS", "ALL", 10),
    "OFFICIAL_COMPETITION_5": ("OFFICIAL", "SAME_COMPETITION", "ALL", 5),
    "OFFICIAL_HOME_5": ("OFFICIAL", "ALL_COMPETITIONS", "HOME", 5),
    "OFFICIAL_AWAY_5": ("OFFICIAL", "ALL_COMPETITIONS", "AWAY", 5),
    "PLAYED_ALL_5": ("PLAYED", "ALL_COMPETITIONS", "ALL", 5),
    "FORECAST_ELIGIBLE_ALL_5": ("FORECAST_ELIGIBLE", "ALL_COMPETITIONS", "ALL", 5),
}


_FRIENDLY = re.compile(r"\bfriendl(y|ies)\b", re.IGNORECASE)


def competition_scope(competition_type: str, name: str) -> str:
    """Python twin of football.product_competition_scope; parity is tested."""
    if _FRIENDLY.search(name):
        return "FRIENDLY"
    return competition_type if competition_type in ("LEAGUE", "CUP") else "UNCLASSIFIED"


def _outcome(goals_for: int, goals_against: int) -> str:
    if goals_for > goals_against:
        return "W"
    return "L" if goals_for < goals_against else "D"


def _candidate(
    team_id: str, official: dict[str, Any] | None, played: dict[str, Any] | None
) -> dict[str, Any]:
    """One match from the team's side, keeping the official and on-field scores apart."""
    row = official or played
    assert row is not None
    home = row["home_team_id"] == team_id
    score = official or played
    assert score is not None
    official_score = (score["home_goals"], score["away_goals"])
    field_score = (played["home_goals"], played["away_goals"]) if played else official_score
    if not home:
        official_score, field_score = official_score[::-1], field_score[::-1]
    awarded = official is not None and official["status"] == "AWARDED"
    basis = official["score_basis"] if official else "REGULATION_90"
    if played is not None and not awarded:
        basis = "REGULATION_90"
    shootout = basis == "PENALTY_SHOOTOUT"
    return {
        "fixture_id": row["fixture_id"],
        "kickoff_at": row["kickoff_at"],
        "kickoff_precision": (played or {}).get("source_kickoff_precision", "EXACT"),
        "opponent": row["away_team"] if home else row["home_team"],
        "opponent_id": row["away_team_id"] if home else row["home_team_id"],
        "venue": "HOME" if home else "AWAY",
        "goals_for": official_score[0],
        "goals_against": official_score[1],
        "result": "D" if shootout else _outcome(*official_score),
        "result_class": ("AWARDED_AFTER_PLAY" if played else "AWARDED") if awarded else "PLAYED",
        "score_basis": basis,
        "competition_id": row["competition_id"],
        "verification": "QUALIFIED_HISTORY" if played else "CANONICAL_RESULT",
        "played_goals_for": field_score[0],
        "played_goals_against": field_score[1],
    }


def team_candidates(source: dict[str, Any], team_id: str) -> list[dict[str, Any]]:
    """Merge qualified played history with official results, newest first."""
    played = {
        row["fixture_id"]: row
        for row in source["history"]
        if team_id in (row["home_team_id"], row["away_team_id"])
    }
    official = {
        row["fixture_id"]: row
        for row in source.get("results", ())
        if team_id in (row["home_team_id"], row["away_team_id"])
    }
    scopes = source.get("competition_scopes", {})
    rows = []
    for fixture_id in played.keys() | official.keys():
        row = _candidate(team_id, official.get(fixture_id), played.get(fixture_id))
        row["competition_scope"] = scopes.get(row["competition_id"], "UNCLASSIFIED")
        rows.append(row)
    rows.sort(key=lambda row: row["fixture_id"])
    rows.sort(key=lambda row: datetime.fromisoformat(row["kickoff_at"]), reverse=True)
    return rows


def _in_basis(row: dict[str, Any], basis: str) -> bool:
    if basis == "FORECAST_ELIGIBLE":
        return bool(row["verification"] == "QUALIFIED_HISTORY" and row["result_class"] == "PLAYED")
    if row["competition_scope"] == "FRIENDLY":
        return False
    if basis == "OFFICIAL":
        return True
    return bool(
        row["result_class"] != "AWARDED"
        and (row["verification"] == "QUALIFIED_HISTORY" or row["score_basis"] != "UNKNOWN")
    )


def _in_scope(row: dict[str, Any], scope: str, venue: str, competition_id: str) -> bool:
    if scope == "SAME_COMPETITION" and row["competition_id"] != competition_id:
        return False
    return venue in ("ALL", row["venue"])


def _ambiguous(first: dict[str, Any], second: dict[str, Any]) -> bool:
    if first["kickoff_at"] == second["kickoff_at"]:
        return True
    same_day = first["kickoff_at"][:10] == second["kickoff_at"][:10]
    return same_day and "DATE_ONLY" in (first["kickoff_precision"], second["kickoff_precision"])


def _score_conflict(row: dict[str, Any]) -> bool:
    official = (row["goals_for"], row["goals_against"])
    played = (row["played_goals_for"], row["played_goals_against"])
    return bool(row["result_class"] == "PLAYED" and official != played)


def _flags(
    selected: list[dict[str, Any]],
    next_row: dict[str, Any] | None,
    pending: list[dict[str, Any]],
    kickoff: datetime,
    requested: int,
) -> list[str]:
    flags = set()
    ordered = [*selected, *([next_row] if next_row else [])]
    if any(_ambiguous(a, b) for a, b in zip(ordered, ordered[1:], strict=False)):
        flags.add("ORDER_AMBIGUOUS")
    oldest = datetime.fromisoformat(selected[-1]["kickoff_at"]) if selected else None
    if oldest and kickoff - oldest > STALE_AFTER:
        flags.add("STALE")
    if any(
        len(selected) < requested
        or oldest is None
        or datetime.fromisoformat(row["kickoff_at"]) >= oldest
        for row in pending
    ):
        flags.add("RESULT_PENDING")
    checks = (
        ("SCORE_CONFLICT", _score_conflict),
        ("UNQUALIFIED_RESULT", lambda row: row["verification"] != "QUALIFIED_HISTORY"),
        ("AWARDED_INCLUDED", lambda row: row["result_class"] != "PLAYED"),
        ("UNKNOWN_SCORE_BASIS", lambda row: row["score_basis"] == "UNKNOWN"),
        ("UNCLASSIFIED_COMPETITION", lambda row: row["competition_scope"] == "UNCLASSIFIED"),
    )
    flags.update(name for name, test in checks if any(test(row) for row in selected))
    return sorted(flags)


def _window(
    key: str,
    candidates: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    target: dict[str, Any],
    team_id: str,
) -> dict[str, Any]:
    basis, scope, venue, requested = WINDOWS[key]
    eligible = [
        row
        for row in candidates
        if _in_basis(row, basis) and _in_scope(row, scope, venue, target["competition_id"])
    ]
    selected = eligible[:requested]
    use_field = basis != "OFFICIAL"
    results = [
        _outcome(row["played_goals_for"], row["played_goals_against"])
        if use_field
        else row["result"]
        for row in selected
    ]
    kickoff = datetime.fromisoformat(target["kickoff_at"])
    next_row = eligible[requested] if len(eligible) > requested else None
    coverage = "EMPTY" if not selected else "COMPLETE" if len(selected) == requested else "PARTIAL"
    fingerprint = sha256_bytes(
        canonical_json_bytes(
            {
                "policy_version": FORM_POLICY_VERSION,
                "window": key,
                "team_id": team_id,
                "target_fixture_id": target["fixture_id"],
                "selected": [
                    [row["fixture_id"], result]
                    for row, result in zip(selected, results, strict=True)
                ],
            }
        )
    )
    return {
        "basis": basis,
        "scope": scope,
        "venue": venue,
        "requested": requested,
        "actual": len(selected),
        "coverage": coverage,
        "flags": _flags(selected, next_row, pending, kickoff, requested),
        "results": "".join(results),
        "fixture_ids": [row["fixture_id"] for row in selected],
        "oldest_kickoff_at": selected[-1]["kickoff_at"] if selected else None,
        "fingerprint": fingerprint,
    }


def team_form(source: dict[str, Any], team_id: str) -> dict[str, Any]:
    """Every governed window for one team, each traceable to its selected fixtures."""
    candidates = team_candidates(source, team_id)
    pending = [row for row in source.get("pending_results", ()) if row["team_id"] == team_id]
    target = {key: source.get(key) for key in ("fixture_id", "competition_id", "kickoff_at")}
    windows = {key: _window(key, candidates, pending, target, team_id) for key in WINDOWS}
    used = {fixture_id for window in windows.values() for fixture_id in window["fixture_ids"]}
    return {
        "team_id": team_id,
        "windows": windows,
        "matches": [row for row in candidates if row["fixture_id"] in used],
        "pending_fixture_ids": [row["fixture_id"] for row in pending],
    }


def window_matches(form: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    """The selected matches of one window, in served order."""
    by_id = {row["fixture_id"]: row for row in form["matches"]}
    return tuple(by_id[fixture_id] for fixture_id in form["windows"][key]["fixture_ids"])
