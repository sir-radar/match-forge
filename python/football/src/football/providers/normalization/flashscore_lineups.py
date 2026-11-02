"""Source starter/bench groups; no inferred minutes or canonical membership."""

from __future__ import annotations

from typing import Any, Literal

from football.contracts.observations_v2 import LineupMemberV2
from football.providers.native.flashscore import FlashscoreLineupMember, feed_records
from football.providers.native.reader import native_record
from football.providers.normalization.common import ObservationCollector
from football.providers.normalization.participants import emit_lineup, emit_player

type _Role = Literal["STARTER", "BENCH", "COACH"]
_GROUPS: dict[tuple[str, str | None, str | None], _Role] = {
    ("Starting Lineups", "1", "1"): "STARTER",
    ("Substitutes", "1", "2"): "BENCH",
    ("Coaches", "4", None): "COACH",
}
_SIDES = {"1": "home", "2": "away"}


def lineups(output: ObservationCollector, payload: object) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("Flashscore lineups requires original feed bytes")
    rows = feed_records(
        payload.decode("utf-8"), {*FlashscoreLineupMember.__annotations__, "LB", "LGT", "LGK", "LC"}
    )
    role, side = None, None
    squads: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        path = f"feed:lineups/{index}"
        with output.record(path):
            if "LB" in row:
                role = _GROUPS.get((row["LB"], row.get("LGT"), row.get("LGK")))
                side = None
                if role is None:
                    output.finding(
                        "LINEUP_GROUP_UNKNOWN",
                        path,
                        "Unmapped source lineup group",
                        severity="WARNING",
                        evidence={"source_value": row["LB"]},
                    )
            if "LC" in row:
                side = _SIDES.get(row["LC"])
            if "LP" in row:
                if role is None or side is None:
                    raise ValueError("Lineup participant has no mapped group and explicit side")
                squad = squads.setdefault(side, {"members": [], "coaches": [], "formations": set()})
                _member(output, native_record(FlashscoreLineupMember, row), role, side, squad, path)
    if not squads:
        raise ValueError("Flashscore lineup feed has no mapped participants")
    for side, squad in squads.items():
        _lineup(output, side, squad)


def _member(
    output: ObservationCollector,
    row: FlashscoreLineupMember,
    role: _Role,
    side: str,
    squad: dict[str, Any],
    path: str,
) -> None:
    if row.get("LD"):
        squad["formations"].add(row["LD"])
    if role == "COACH":
        if row.get("LG") != "2":
            raise ValueError("Coach group conflicts with native participant type")
        squad["coaches"].append({"id": row["LP"], "name": row["LI"]})
        return
    if row.get("LG") != "1" and (row.get("LG"), row.get("LS")) != ("3", "Goalkeeper"):
        raise ValueError("Player group conflicts with native participant type")
    if any(member.player.provider_native_id == row["LP"] for member in squad["members"]):
        raise ValueError("Duplicate player in source starting/bench groups")
    team = output.context.reference(None, "feed:lineups/" + side)
    player = emit_player(output, {"name": row["LI"]}, path, team, native_id=row["LP"])
    squad["members"].append(LineupMemberV2(player=player, role=role))


def _lineup(output: ObservationCollector, side: str, squad: dict[str, Any]) -> None:
    formations = squad["formations"]
    if len(formations) > 1 or len(squad["coaches"]) > 1:
        raise ValueError("Conflicting formations or multiple unqualified coach roles")
    output.finding(
        "TEAM_ID_UNRESOLVED",
        "feed:lineups/" + side,
        "Source side has no native team ID in this feed",
        severity="WARNING",
    )
    emit_lineup(
        output,
        "feed:lineups/" + side,
        output.context.reference(None, "feed:lineups/" + side),
        squad["members"],
        coach=squad["coaches"][0] if squad["coaches"] else None,
        formation=next(iter(formations)) if formations else None,
        confirmed=False,
    )
