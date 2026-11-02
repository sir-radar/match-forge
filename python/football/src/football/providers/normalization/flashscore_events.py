"""Explicit Flashscore incident actors; shootouts and ambiguous sides stay held."""

from __future__ import annotations

import re
from typing import Any

from football.contracts.observations_v2 import EventObservationV2
from football.providers.native.flashscore import FlashscoreIncident, feed_cells
from football.providers.native.reader import native_record
from football.providers.normalization.common import ObservationCollector, count, required_text

_KINDS = {
    "1": "YELLOW_CARD",
    "2": "RED_CARD",
    "3": "GOAL",
    "4": "GOAL",
    "6": "SUBSTITUTION",
    "10": "GOAL",
    "362": "DISALLOWED_GOAL",
}
_PERIODS = {"1st Half": "FIRST_HALF", "2nd Half": "SECOND_HALF"}
_SIDES = {"1": "home", "2": "away"}


def events(output: ObservationCollector, payload: object) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("Flashscore incidents requires original feed bytes")
    output.finding(
        "TEAM_ID_UNRESOLVED",
        "feed:events",
        "Incident sides have no native team IDs in this feed",
        severity="WARNING",
    )
    period = None
    seen = False
    for index, cells in enumerate(feed_cells(payload.decode("utf-8"))):
        path = f"feed:events/{index}"
        with output.record(path):
            if cells[0][0] == "AC":
                period = _PERIODS.get(cells[0][1])
                if period is None:
                    output.finding(
                        "PERIOD_UNSUPPORTED",
                        path,
                        "Unmapped or shootout period; ordinary events held",
                        severity="WARNING",
                        evidence={"source_value": cells[0][1]},
                    )
            elif cells[0][0] == "III":
                seen = True
                if period is None:
                    output.finding(
                        "EVENT_PERIOD_UNQUALIFIED",
                        path,
                        "Incident has no qualified ordinary football period",
                        severity="WARNING",
                    )
                    continue
                row = native_record(FlashscoreIncident, _incident(cells))
                _events(output, row, period, path)
    if not seen:
        raise ValueError("Flashscore incident feed has no native incident groups")


def _incident(cells: list[tuple[str, str]]) -> dict[str, Any]:
    row: dict[str, Any] = {"actors": []}
    for key, value in cells:
        if key == "IE":
            row["actors"].append({"IE": value})
        elif key in ("III", "IA", "IB", "ID"):
            if key in row:
                raise ValueError("Duplicate native incident header field")
            row[key] = value
        elif key in ("IM", "IF"):
            if not row["actors"] or key in row["actors"][-1]:
                raise ValueError("Incident actor field is duplicated or has no native type")
            row["actors"][-1][key] = value
    return row


def _clock(row: FlashscoreIncident) -> tuple[int, int | None]:
    match = re.fullmatch(r"([0-9]+)(?:\+([0-9]+))?'", row["IB"])
    if match is None:
        raise ValueError("Unmapped Flashscore incident display clock")
    display_added = int(match[2]) if match[2] else None
    explicit_added = count(row.get("ID"))
    if display_added is not None and explicit_added not in (None, display_added):
        raise ValueError("Incident display and explicit added-time values conflict")
    return int(match[1]), display_added if display_added is not None else explicit_added


def _events(output: ObservationCollector, row: FlashscoreIncident, period: str, path: str) -> None:
    minute, added = _clock(row)
    side = _SIDES.get(row["IA"])
    for index, actor in enumerate(row["actors"]):
        kind = _KINDS.get(actor["IE"])
        if kind is None:
            output.finding(
                "EVENT_ACTOR_TYPE_UNSUPPORTED",
                path + f"/actors/{index}",
                "Actor role retained without a separate ordinary event",
                severity="WARNING",
                evidence={"source_type": actor["IE"]},
            )
            continue
        own = actor["IE"] == "4"
        team = None
        if side is not None and not own:
            team = output.context.reference(None, "feed:events/" + side)
        else:
            output.finding(
                "EVENT_TEAM_ROLE_UNKNOWN",
                path,
                "Own-goal beneficiary or unknown side cannot establish actor team",
                severity="WARNING",
            )
        player = (
            output.context.reference(required_text(actor["IM"]), path + f"/actors/{index}")
            if actor.get("IM")
            else None
        )
        output.emit(
            EventObservationV2,
            path + f"/actors/{index}",
            row["III"],
            fixture=output.context.fixture(),
            event_type=kind,
            team=team,
            player=player,
            minute=minute,
            added_time=added,
            period=period,
            own_goal=True if own else None,
            penalty=True if actor["IE"] == "10" else None,
        )
