"""Observed API-Football match resources; no canonical or market qualification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from football.contracts.observations_v2 import EventObservationV2, PlayerStatisticObservationV2
from football.contracts.observations_v3 import PlayerStatisticObservationV3
from football.providers.native.api_football import ApiFootballStatistic
from football.providers.native.reader import native_record
from football.providers.normalization.api_football import _rows
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    required_text,
)
from football.providers.normalization.measurements import (
    TEAM_METRICS,
    add_measurement,
    emit_team_statistics,
    measurement,
    statistic_contract,
)
from football.providers.normalization.participants import emit_player, emit_team

_TEAM_METRICS = {
    **TEAM_METRICS,
    "shotsongoal": "shots_on_target",
    "shotsoffgoal": "shots_off_target",
    "cornerkicks": "corners",
    "goalkeepersaves": "saves",
    "totalpasses": "passes",
    "passesaccurate": "accurate_passes",
}
_EVENT_TYPES = {
    ("Goal", "Normal Goal"): "GOAL",
    ("Goal", "Own Goal"): "GOAL",
    ("Goal", "Penalty"): "GOAL",
    ("Card", "Yellow Card"): "YELLOW_CARD",
    ("Card", "Red Card"): "RED_CARD",
    ("Card", "Second Yellow card"): "RED_CARD",
    ("Var", "Goal cancelled"): "DISALLOWED_GOAL",
}


def statistics(output: ObservationCollector, payload: object) -> None:
    for index, raw in enumerate(_rows(payload)):
        path = f"json:/response/{index}"
        with output.record(path):
            row = native_record(ApiFootballStatistic, raw)
            team = emit_team(output, row["team"], path + "/team")
            values: dict[str, Any] = {}
            blocked: set[str] = set()
            for si, stat in enumerate(row["statistics"]):
                field = f"{path}/statistics/{si}"
                with output.record(field):
                    if stat["type"] == "Passes %":
                        output.finding(
                            "STATISTIC_UNSUPPORTED",
                            field,
                            "Source pass percentage is distinct from a pass count",
                            severity="WARNING",
                            evidence={"source_key": stat["type"]},
                        )
                        continue
                    parsed = measurement(output, stat["type"], stat["value"], field, _TEAM_METRICS)
                    add_measurement(output, values, blocked, parsed, field)
            emit_team_statistics(output, path, team, "FULL_MATCH", values)


def events(output: ObservationCollector, payload: object) -> None:
    for index, raw in enumerate(_rows(payload)):
        path = f"json:/response/{index}"
        with output.record(path):
            row = object_value(raw)
            kind, detail = required_text(row.get("type")), required_text(row.get("detail"))
            event = "SUBSTITUTION" if kind == "subst" else _EVENT_TYPES.get((kind, detail))
            if event is None:
                output.finding(
                    "EVENT_TYPE_UNKNOWN",
                    path,
                    "Unmapped source event",
                    evidence={
                        "type": kind,
                        "detail": detail,
                    },
                )
                continue
            team = object_value(row.get("team"))
            player = object_value(row["player"]) if row.get("player") is not None else None
            clock = object_value(row.get("time"))
            output.emit(
                EventObservationV2,
                path,
                fixture=output.context.fixture(),
                event_type=event,
                team=output.context.reference(team.get("id"), path + "/team"),
                player=output.context.reference(player.get("id"), path + "/player")
                if player
                else None,
                minute=count(clock.get("elapsed")),
                added_time=count(clock.get("extra")),
                own_goal=detail == "Own Goal" if event == "GOAL" else None,
                penalty=detail == "Penalty" if event == "GOAL" else None,
            )


def player_statistics(output: ObservationCollector, payload: object) -> None:
    for ti, raw in enumerate(_rows(payload)):
        path = f"json:/response/{ti}"
        with output.record(path):
            row = object_value(raw)
            team = emit_team(output, object_value(row.get("team")), path + "/team")
            for pi, raw_player in enumerate(array(row.get("players"))):
                field = f"{path}/players/{pi}"
                with output.record(field):
                    player = object_value(raw_player)
                    native = object_value(player.get("player"))
                    ref = emit_player(
                        output, native, field + "/player", team, native_id=native.get("id")
                    )
                    stats = array(player.get("statistics"))
                    if len(stats) != 1:
                        output.finding(
                            "PLAYER_STATISTIC_SCOPE_UNKNOWN",
                            field,
                            "Expected one match statistic group; appearance not inferred",
                        )
                        continue
                    values = _player_values(object_value(stats[0]))
                    if any(value is not None for value in values.values()):
                        output.emit(
                            statistic_contract(
                                values, PlayerStatisticObservationV2, PlayerStatisticObservationV3
                            ),
                            field,
                            native.get("id"),
                            fixture=output.context.fixture(),
                            team=team,
                            player=ref,
                            **values,
                        )


def _player_values(row: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "minutes_played": ("games", "minutes"),
        "shots": ("shots", "total"),
        "shots_on_target": ("shots", "on"),
        "goals": ("goals", "total"),
        "assists": ("goals", "assists"),
        "saves": ("goals", "saves"),
        "passes": ("passes", "total"),
        "tackles": ("tackles", "total"),
        "interceptions": ("tackles", "interceptions"),
        "fouls": ("fouls", "committed"),
        "yellow_cards": ("cards", "yellow"),
        "red_cards": ("cards", "red"),
    }
    return {
        field: count(object_value(row.get(group, {})).get(key))
        for field, (group, key) in fields.items()
    }
