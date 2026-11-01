"""Named ESPN team/player measurements and explicitly typed key events."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from football.contracts.observations_v2 import (
    EntityReferenceV2,
    EventObservationV2,
    LineupMemberV2,
    PlayerStatisticObservationV2,
)
from football.contracts.observations_v3 import PlayerStatisticObservationV3
from football.providers.native.espn import EspnTeam
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    optional_bool,
    required_text,
)
from football.providers.normalization.measurements import (
    PLAYER_METRICS,
    TEAM_METRICS,
    add_measurement,
    emit_team_statistics,
    measurement,
    statistic_contract,
)
from football.providers.normalization.participants import emit_lineup, emit_player, emit_team

_TEAM = {
    **TEAM_METRICS,
    "woncorners": "corners",
    "possessionpct": "possession",
    "totalpasses": "passes",
    "totaltackles": "tackles",
    "totalclearance": "clearances",
}
_PLAYER = {
    **PLAYER_METRICS,
    "totalgoals": "goals",
    "goalassists": "assists",
    "foulscommitted": "fouls",
}


def team_reference(
    output: ObservationCollector,
    raw: Mapping[str, Any],
    path: str,
    allowed: Mapping[str, EntityReferenceV2] | None = None,
) -> EntityReferenceV2:
    row = native_record(EspnTeam, raw)
    if allowed is not None and row["id"] not in allowed:
        raise ValueError("ESPN detail team is absent from the fixture participants")
    return emit_team(output, {"id": row["id"], "name": row["displayName"]}, path)


def _values(
    output: ObservationCollector, rows: object, vocabulary: Mapping[str, str], path: str
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    blocked: set[str] = set()
    for index, raw in enumerate(array(rows)):
        field = f"{path}/statistics/{index}"
        with output.record(field):
            row = object_value(raw)
            parsed = measurement(
                output, required_text(row.get("name")), row.get("displayValue"), field, vocabulary
            )
            add_measurement(output, values, blocked, parsed, field)
    return values


def statistics(
    output: ObservationCollector, rows: object, team: EntityReferenceV2, path: str
) -> None:
    emit_team_statistics(output, path, team, "FULL_MATCH", _values(output, rows, _TEAM, path))


def rosters(
    output: ObservationCollector, rows: object, teams: Mapping[str, EntityReferenceV2]
) -> None:
    for ti, raw in enumerate(array(rows)):
        path = f"json:/rosters/{ti}"
        with output.record(path):
            row = object_value(raw)
            team = team_reference(output, object_value(row.get("team")), path + "/team", teams)
            members: list[LineupMemberV2] = []
            for pi, raw_player in enumerate(array(row.get("roster"))):
                field = f"{path}/roster/{pi}"
                with output.record(field):
                    _player(output, object_value(raw_player), team, members, field)
            emit_lineup(
                output,
                path,
                team,
                members,
                coach=None,
                formation=row.get("formation"),
                confirmed=False,
            )


def _player(
    output: ObservationCollector,
    row: Mapping[str, Any],
    team: EntityReferenceV2,
    members: list[LineupMemberV2],
    path: str,
) -> None:
    athlete = object_value(row.get("athlete"))
    native = required_text(athlete.get("id"))
    player = emit_player(
        output,
        {"name": required_text(athlete.get("displayName"))},
        path + "/athlete",
        team,
        native_id=native,
    )
    starter = optional_bool(row.get("starter"))
    if starter is not None:
        members.append(LineupMemberV2(player=player, role="STARTER" if starter else "BENCH"))
    values = _values(output, row.get("stats"), _PLAYER, path)
    if values:
        output.emit(
            statistic_contract(values, PlayerStatisticObservationV2, PlayerStatisticObservationV3),
            path,
            native,
            fixture=output.context.fixture(),
            player=player,
            team=team,
            **values,
        )


def events(
    output: ObservationCollector, rows: object, teams: Mapping[str, EntityReferenceV2]
) -> None:
    for index, raw in enumerate(array(rows)):
        path = f"json:/keyEvents/{index}"
        with output.record(path):
            row = object_value(raw)
            kind = _event_type(output, row, path)
            if kind is None:
                continue
            team = object_value(row.get("team", {})).get("id")
            if team is not None and team not in teams:
                raise ValueError("ESPN event team is absent from fixture participants")
            clock = required_text(object_value(row.get("clock")).get("displayValue"))
            minute = re.fullmatch(r"([0-9]+)'(?:\+([0-9]+)')?", clock)
            if minute is None:
                raise ValueError("ESPN event minute has no verified display-clock format")
            output.emit(
                EventObservationV2,
                path,
                required_text(row.get("id")),
                fixture=output.context.fixture(),
                event_type=kind,
                team=teams[team] if team is not None else None,
                player=_participant(output, row.get("participants"), path),
                minute=int(minute[1]),
                added_time=int(minute[2]) if minute[2] else None,
                period=_period(row.get("period")),
                own_goal=optional_bool(row.get("ownGoal")),
                penalty=optional_bool(row.get("penaltyKick")),
            )


def _event_type(output: ObservationCollector, row: Mapping[str, Any], path: str) -> str | None:
    if optional_bool(row.get("shootout")) is True:
        output.finding(
            "EVENT_SHOOTOUT_UNSUPPORTED",
            path,
            "Shootout event has no ordinary goal meaning",
            severity="WARNING",
        )
        return None
    if optional_bool(row.get("scoringPlay")) is True:
        return "GOAL"
    label = required_text(object_value(row.get("type")).get("type"))
    kind = {
        "yellow-card": "YELLOW_CARD",
        "red-card": "RED_CARD",
        "substitution": "SUBSTITUTION",
    }.get(label)
    if kind is None:
        output.finding(
            "EVENT_TYPE_UNKNOWN",
            path,
            "Unmapped ESPN key event",
            severity="WARNING",
            evidence={"source_type": label},
        )
    return kind


def _period(value: object) -> str | None:
    period = count(object_value(value).get("number"))
    return str(period) if period is not None else None


def _participant(output: ObservationCollector, rows: object, path: str) -> EntityReferenceV2 | None:
    participants = array(rows)
    if len(participants) != 1:
        if participants:
            output.finding(
                "PARTICIPANT_ROLE_UNKNOWN",
                path,
                "Multiple participants have no verified event roles",
                severity="WARNING",
            )
        return None
    native = object_value(object_value(participants[0]).get("athlete")).get("id")
    return output.context.reference(required_text(native), path + "/participants/0/athlete")
