"""Provider-neutral live event and match-statistic projections."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True, slots=True, kw_only=True)
class LiveUpdate:
    """Bound fixture facts with a qualified global match clock, not an HTTP clock."""

    provider: str
    status: str
    home_score: int | None
    away_score: int | None
    minute: int | None
    added_time: int | None
    source_updated_at: datetime | None
    known_by: datetime | None  # Conservative bound, not a substituted football timestamp.


def _football_clock_order(current: LiveUpdate, incoming: LiveUpdate) -> int | None:
    if current.minute is None or incoming.minute is None:
        return None
    if current.minute != incoming.minute:
        return 1 if incoming.minute > current.minute else -1
    if current.added_time is None or incoming.added_time is None:
        return None
    return (incoming.added_time > current.added_time) - (incoming.added_time < current.added_time)


def _live_facts(update: LiveUpdate) -> tuple[object, ...]:
    return update.status, update.home_score, update.away_score, update.minute, update.added_time


def _source_clock_order(current: LiveUpdate, incoming: LiveUpdate) -> int | None:
    if current.provider and current.provider != incoming.provider:
        return None
    old, new = _valid_source_clock(current), _valid_source_clock(incoming)
    if old is not None and new is not None:
        return (new > old) - (new < old)
    # Retained acquisition or a canonical receipt bounds when those facts could change.
    # It is never substituted for a missing provider update timestamp.
    if old is not None and incoming.known_by is not None and incoming.known_by < old:
        return -1
    if new is not None and current.known_by is not None and new > current.known_by:
        return 1
    return None


def _valid_source_clock(update: LiveUpdate) -> datetime | None:
    value = update.source_updated_at
    if value is None or update.known_by is None or value > update.known_by:
        return None
    return value


def live_update_order(
    current: LiveUpdate, incoming: LiveUpdate
) -> Literal["NEWER", "SAME", "STALE", "CONFLICT", "UNORDERED"]:
    """Order proven updates; lifecycle/identity/authority owners still approve writes.

    Re-fetching an unchanged body does not change its original knowledge time.
    Added time remains separate: 45+8 precedes global match minute 46.
    """
    source = _source_clock_order(current, incoming)
    if source == 1:
        return "NEWER"
    if source == -1:
        return "STALE"
    if source == 0:
        return "SAME" if _live_facts(current) == _live_facts(incoming) else "CONFLICT"
    clock = _football_clock_order(current, incoming)
    if clock:
        return "NEWER" if clock > 0 else "STALE"
    if _live_facts(current) == _live_facts(incoming):
        return "SAME"
    if incoming.status == "FINISHED" and current.status not in {
        "FINISHED",
        "CANCELLED",
        "ABANDONED",
        "AWARDED",
    }:
        return "NEWER"
    if current.status == "SCHEDULED" and incoming.status in {"LIVE", "HALF_TIME"}:
        return "NEWER"
    if (
        current.minute is not None
        and incoming.minute == current.minute
        and current.added_time == incoming.added_time
    ):
        return "CONFLICT"
    return "UNORDERED"


def normalize_events(
    provider: str,
    provider_match_id: str,
    payload: Mapping[str, Any] | list[Any],
    *,
    home_provider_team_id: str,
    away_provider_team_id: str,
) -> dict[str, Any]:
    rows = _event_rows(provider, payload)
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        event = _normalize_event(
            provider,
            provider_match_id,
            row,
            home_provider_team_id,
            away_provider_team_id,
        )
        if event is not None and event["id"] not in seen:
            seen.add(event["id"])
            events.append(event)
    return {"events": events}


def normalize_statistics(provider: str, payload: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    statistics: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for period, row in _stat_rows(provider, payload):
        original = _text(row.get("key"))
        metric = _metric_key(original)
        if metric is None or (period, metric) in seen:
            continue
        home, away = _stat_values(provider, row)
        if home is None and away is None:
            continue
        seen.add((period, metric))
        statistics.append(
            {
                "metric": metric,
                "label": _text(row.get("title")) or metric.replace("_", " ").title(),
                "period": period,
                "home": home,
                "away": away,
                "unit": "percent" if metric == "possession" else "number",
                "original_field": original,
                "available": True,
            }
        )
    return {"statistics": statistics}


def _event_rows(provider: str, payload: Mapping[str, Any] | list[Any]) -> list[Mapping[str, Any]]:
    values: Any
    if isinstance(payload, list):
        values = payload
    elif provider == "fotmob":
        nested = payload.get("events")
        values = nested.get("events") if isinstance(nested, Mapping) else nested
    else:
        values = payload.get("events")
    return [row for row in values or [] if isinstance(row, Mapping)]


def _normalize_event(
    provider: str,
    match_id: str,
    row: Mapping[str, Any],
    home_team_id: str,
    away_team_id: str,
) -> dict[str, Any] | None:
    raw_type = _text(row.get("type" if provider == "fotmob" else "event_type"))
    card = _text(row.get("card"))
    event_type = _event_type(raw_type, card)
    if event_type is None:
        return None
    shootout = bool(row.get("isPenaltyShootoutEvent")) or "shootout" in raw_type.casefold()
    if shootout:
        return None
    player = row.get("player")
    player_map = player if isinstance(player, Mapping) else {}
    player_id = _text(player_map.get("id") or row.get("playerId")) or None
    player_name = _text(player_map.get("name") or row.get("fullName") or row.get("nameStr")) or None
    minute = _integer(row.get("time" if provider == "fotmob" else "minute"), 180)
    added = _integer(row.get("overloadTime" if provider == "fotmob" else "minute_added"), 30)
    if provider == "fotmob":
        provider_team_id = home_team_id if bool(row.get("isHome")) else away_team_id
    else:
        provider_team_id = _text(row.get("team_id"))
    side = (
        "HOME"
        if provider_team_id == home_team_id
        else "AWAY"
        if provider_team_id == away_team_id
        else None
    )
    provider_event_id = _text(row.get("eventId" if provider == "fotmob" else "id"))
    if not provider_event_id:
        stable_facts = {
            "match_id": match_id,
            "type": raw_type,
            "card": card,
            "period": row.get("period"),
            "minute": minute,
            "added_time": added,
            "team_id": provider_team_id,
            "player_id": player_id,
            "player_name": player_name,
            "own_goal": row.get("ownGoal" if provider == "fotmob" else "is_own_goal"),
            "penalty": row.get("isPenalty" if provider == "fotmob" else "is_penalty"),
            "disallowed": row.get("disallowed"),
        }
        provider_event_id = hashlib.sha256(
            json.dumps(stable_facts, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
    disallowed = event_type == "DISALLOWED_GOAL" or bool(row.get("disallowed"))
    return {
        "id": f"{provider}:{provider_event_id}",
        "provider_event_id": provider_event_id,
        "type": event_type,
        "team_side": side,
        "provider_team_id": provider_team_id or None,
        "player_id": player_id,
        "player_name": player_name,
        "minute": minute,
        "added_time": added,
        "period": _text(row.get("period")) or None,
        "own_goal": bool(row.get("ownGoal" if provider == "fotmob" else "is_own_goal")),
        "penalty": bool(row.get("isPenalty" if provider == "fotmob" else "is_penalty")),
        "disallowed": disallowed,
    }


def _event_type(value: str, card: str) -> str | None:
    label = f"{value} {card}".casefold().replace("_", "")
    if "disallowed" in label or "cancelledgoal" in label:
        return "DISALLOWED_GOAL"
    if "goal" in label:
        return "GOAL"
    if "red" in label:
        return "RED_CARD"
    if "yellow" in label or "card" in label:
        return "YELLOW_CARD"
    if "substitution" in label or label.strip() == "sub":
        return "SUBSTITUTION"
    return None


def _stat_rows(
    provider: str, payload: Mapping[str, Any] | list[Any]
) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(payload, Mapping):
        return []
    periods = payload.get("Periods" if provider == "fotmob" else "periods")
    if provider == "fotmob":
        return _fotmob_stat_rows(periods)
    return _pitchapi_stat_rows(periods)


def _fotmob_stat_rows(periods: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(periods, Mapping):
        return []
    result: list[tuple[str, Mapping[str, Any]]] = []
    for name, period in periods.items():
        if not isinstance(period, Mapping):
            continue
        for group in period.get("stats") or []:
            if isinstance(group, Mapping):
                result.extend(
                    (_period(str(name)), row)
                    for row in group.get("stats") or []
                    if isinstance(row, Mapping)
                )
    return result


def _pitchapi_stat_rows(periods: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(periods, Sequence):
        return []
    result: list[tuple[str, Mapping[str, Any]]] = []
    for period in periods:
        if not isinstance(period, Mapping):
            continue
        name = _period(_text(period.get("period") or period.get("title")))
        for group in period.get("groups") or []:
            if isinstance(group, Mapping):
                result.extend(
                    (name, row) for row in group.get("items") or [] if isinstance(row, Mapping)
                )
    return result


def _metric_key(value: str) -> str | None:
    compact = re.sub(r"[^a-z0-9]", "", value.casefold())
    aliases = {
        "ballpossesion": "possession",
        "ballpossession": "possession",
        "possession": "possession",
        "totalshots": "total_shots",
        "shotsontarget": "shots_on_target",
        "expectedgoals": "expected_goals",
        "corners": "corners",
        "fouls": "fouls",
        "foulscommitted": "fouls",
        "yellowcards": "yellow_cards",
        "redcards": "red_cards",
        "bigchance": "big_chances",
        "bigchances": "big_chances",
        "keepersaves": "saves",
        "saves": "saves",
    }
    return aliases.get(compact)


def _stat_values(provider: str, row: Mapping[str, Any]) -> tuple[float | None, float | None]:
    if provider == "fotmob":
        values = row.get("stats")
        if isinstance(values, Sequence) and len(values) >= 2:
            return _number(values[0]), _number(values[1])
        return None, None
    return _number(row.get("home")), _number(row.get("away"))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.match(r"^\s*(-?\d+(?:\.\d+)?)", value)
        if match:
            return float(match.group(1))
    return None


def _integer(value: Any, maximum: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= maximum:
        return value
    if isinstance(value, str):
        match = re.match(r"^(\d+)", value.strip())
        if match and int(match.group(1)) <= maximum:
            return int(match.group(1))
    return None


def _period(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]", "", value.casefold())
    return {"all": "FULL_MATCH", "firsthalf": "FIRST_HALF", "secondhalf": "SECOND_HALF"}.get(
        compact, value.upper() or "FULL_MATCH"
    )


def _text(value: Any) -> str:
    if isinstance(value, (str, int)):
        return str(value).strip()
    return ""
