"""Emit named football measurements without guessing missing provider semantics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from football.contracts.observations_v2 import (
    EntityReferenceV2,
    ExpectedGoalsObservationV2,
    ShotObservationV2,
    TeamStatisticObservationV2,
)
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    number,
    object_value,
    optional_bool,
    required_text,
    text,
)

TEAM_METRICS = {
    "ballpossesion": "possession",
    "ballpossession": "possession",
    "possession": "possession",
    "totalshots": "total_shots",
    "shotsontarget": "shots_on_target",
    "corners": "corners",
    "fouls": "fouls",
    "foulscommitted": "fouls",
    "yellowcards": "yellow_cards",
    "redcards": "red_cards",
    "bigchance": "big_chances",
    "bigchances": "big_chances",
    "keepersaves": "saves",
    "saves": "saves",
    "expectedgoals": "expected_goals",
}
PLAYER_METRICS = {
    "minutesplayed": "minutes_played",
    "totalshots": "shots",
    "goals": "goals",
    "assists": "assists",
    "yellowcards": "yellow_cards",
    "redcards": "red_cards",
}


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def period_name(value: str) -> str:
    return {"all": "FULL_MATCH", "firsthalf": "FIRST_HALF", "secondhalf": "SECOND_HALF"}.get(
        compact(value), value
    )


def measurement(
    output: ObservationCollector, key: str, value: object, path: str, vocabulary: Mapping[str, str]
) -> tuple[str, float | int] | None:
    name = vocabulary.get(compact(key))
    if name is None:
        output.finding(
            "STATISTIC_UNSUPPORTED",
            path,
            "Source statistic has no named contract field",
            severity="WARNING",
            evidence={"source_key": key},
        )
        return None
    parsed = (
        number(value, percent=True)
        if name in ("possession", "expected_goals", "minutes_played")
        else count(value)
    )
    return (name, parsed) if parsed is not None else None


def add_measurement(
    output: ObservationCollector,
    values: dict[str, Any],
    blocked: set[str],
    parsed: tuple[str, float | int] | None,
    path: str,
) -> None:
    if parsed is None:
        return
    name, value = parsed
    if name in values and values[name] == value:
        output.finding(
            "STATISTIC_REPEATED",
            path,
            "Repeated source measurements agree",
            severity="INFO",
            evidence={"field": name},
        )
        return
    if name in values or name in blocked:
        values.pop(name, None)
        blocked.add(name)
        output.finding(
            "STATISTIC_DUPLICATE",
            path,
            "Duplicate measurement is ambiguous",
            evidence={"field": name},
        )
    else:
        values[name] = value


def emit_team_statistics(
    output: ObservationCollector,
    path: str,
    team: EntityReferenceV2,
    period: str,
    values: dict[str, Any],
) -> None:
    values = dict(values)
    xg = values.pop("expected_goals", None)
    if xg is not None:
        if period == "FULL_MATCH":
            output.emit(
                ExpectedGoalsObservationV2,
                path,
                fixture=output.context.fixture(),
                team=team,
                scope="MATCH_TOTAL",
                expected_goals=xg,
            )
        else:
            output.finding(
                "XG_SCOPE_UNSUPPORTED",
                path,
                "Partial-period xG has no match-total meaning",
                severity="WARNING",
                evidence={"period": period},
            )
    if values:
        output.emit(
            TeamStatisticObservationV2,
            path,
            fixture=output.context.fixture(),
            team=team,
            period=period,
            **values,
        )


def emit_shot(
    output: ObservationCollector,
    path: str,
    native_id: object,
    *,
    team: EntityReferenceV2,
    player: EntityReferenceV2 | None,
    minute: object,
    period: object,
    expected_goals: object,
    outcome: str | None,
    penalty: object = None,
    own_goal: object = None,
    coordinates: bool = False,
    second: object = None,
    normalized_coordinates: tuple[float | None, float | None] = (None, None),
) -> None:
    if coordinates:
        output.finding(
            "COORDINATE_FRAME_UNKNOWN",
            path,
            "Retained coordinates lack a verified normalization frame",
            severity="WARNING",
        )
    xg = number(expected_goals)
    item = output.emit(
        ShotObservationV2,
        path,
        native_id,
        fixture=output.context.fixture(),
        team=team,
        player=player,
        minute=count(minute),
        second=count(second),
        x_norm=normalized_coordinates[0],
        y_norm=normalized_coordinates[1],
        period=text(period),
        expected_goals=xg,
        outcome=outcome,
        is_penalty=optional_bool(penalty),
        is_own_goal=optional_bool(own_goal),
    )
    if item is not None and xg is not None:
        output.emit(
            ExpectedGoalsObservationV2,
            path,
            native_id,
            fixture=output.context.fixture(),
            team=team,
            shot=output.context.reference(native_id, path),
            scope="SHOT",
            expected_goals=xg,
        )


def shot_outcome(output: ObservationCollector, value: object, path: str) -> str | None:
    if value is None:
        return None
    label = compact(text(value) or "")
    outcome = {
        "goal": "GOAL",
        "attemptsaved": "SAVED",
        "saved": "SAVED",
        "blocked": "BLOCKED",
        "miss": "OFF_TARGET",
        "offtarget": "OFF_TARGET",
        "post": "POST",
    }.get(label)
    if outcome is None:
        output.finding(
            "SHOT_OUTCOME_UNKNOWN",
            path,
            "Unmapped shot outcome",
            severity="WARNING",
            evidence={"source_value": value},
        )
    return outcome


def player_measurements(output: ObservationCollector, groups: object, path: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    blocked: set[str] = set()
    for gi, group in enumerate(array(groups)):
        for key, raw_stat in object_value(object_value(group).get("stats")).items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            field = f"{path}/stats/{gi}/stats/{escaped}"
            with output.record(field):
                stat = object_value(raw_stat)
                if stat.get("key") is None:
                    output.finding(
                        "STATISTIC_UNSUPPORTED",
                        field,
                        "Source item is not a named scalar measurement",
                        severity="WARNING",
                        evidence={"source_key": key},
                    )
                    continue
                parsed = measurement(
                    output,
                    required_text(stat.get("key")),
                    object_value(stat.get("stat")).get("value"),
                    field,
                    PLAYER_METRICS,
                )
                add_measurement(output, values, blocked, parsed, field)
    return values
