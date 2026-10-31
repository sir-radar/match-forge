"""PitchAPI resource normalizers operating only on retained native values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Literal

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    EventObservationV2,
    FixtureObservationV2,
    LineupMemberV2,
    PlayerStatisticObservationV2,
    ResultObservationV2,
)
from football.contracts.observations_v3 import PlayerStatisticObservationV3
from football.providers.native.pitchapi import (
    PitchApiEvent,
    PitchApiLineupSide,
    PitchApiShot,
    PitchApiStatistic,
)
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    optional_bool,
    required_text,
    text,
    timestamp,
)
from football.providers.normalization.events import event_type
from football.providers.normalization.measurements import (
    TEAM_METRICS,
    add_measurement,
    emit_shot,
    emit_team_statistics,
    measurement,
    period_name,
    player_measurements,
    shot_outcome,
    statistic_contract,
)
from football.providers.normalization.participants import (
    emit_lineup,
    emit_player,
    emit_team,
    position,
)
from football.providers.pitchapi import _status, parse_pitchapi_match


def fixtures(output: ObservationCollector, payload: object) -> None:
    data = object_value(object_value(payload).get("data"))
    rows = array(data["matches"]) if "matches" in data else [data]
    for index, value in enumerate(rows):
        path = f"json:/data/matches/{index}" if "matches" in data else "json:/data"
        with output.record(path):
            row = parse_pitchapi_match(object_value(value))
            league = object_value(row.get("league") or data.get("league"))
            league_path = path + "/league" if row.get("league") is not None else "json:/data/league"
            if (
                output.context.competition_native_id is not None
                and str(league.get("id")) != output.context.competition_native_id
            ):
                raise ValueError("PitchAPI competition differs from requested scope")
            status = _status(row["status"].casefold())
            time = output.context.time
            if row.get("updated_at") is not None:
                time = replace(time, provider_updated_at=timestamp(row["updated_at"]))
            home = emit_team(output, row["home_team"], path + "/home_team")
            away = emit_team(output, row["away_team"], path + "/away_team")
            competition = output.context.reference(league.get("id"), league_path)
            if league.get("name") is not None:
                output.emit(
                    CompetitionObservationV2,
                    league_path,
                    league.get("id"),
                    competition=competition,
                    name=text(league["name"]),
                )
            ref = output.context.reference(row["id"], path)
            output.emit(
                FixtureObservationV2,
                path,
                row["id"],
                observation_time=time,
                fixture=ref,
                competition=competition,
                home_team=home,
                away_team=away,
                kickoff_at=timestamp(row["time_utc"]),
                status=status,
                kickoff_precision="EXACT",
            )
            if status != "SCHEDULED":
                output.emit(
                    ResultObservationV2,
                    path,
                    row["id"],
                    observation_time=time,
                    fixture=ref,
                    status=status,
                    score_basis="UNKNOWN",
                    home_goals=count(row.get("score_home")),
                    away_goals=count(row.get("score_away")),
                )


def shots(output: ObservationCollector, payload: object) -> None:
    data = object_value(object_value(payload).get("data"))
    for pi, value in enumerate(array(data.get("periods"))):
        period = object_value(value)
        for si, raw in enumerate(array(period.get("shots"))):
            path = f"json:/data/periods/{pi}/shots/{si}"
            with output.record(path):
                row = native_record(PitchApiShot, raw)
                player = row.get("player")
                player_ref = None
                if player is not None:
                    player_ref = output.context.reference(
                        object_value(player).get("id"), path + "/player"
                    )
                emit_shot(
                    output,
                    path,
                    row.get("id"),
                    team=output.context.reference(row["team_id"], path + "/team_id"),
                    player=player_ref,
                    minute=row.get("minute"),
                    period=period.get("period"),
                    expected_goals=row.get("expected_goals"),
                    outcome=shot_outcome(output, row.get("event_type"), path),
                    own_goal=row.get("is_own_goal"),
                    coordinates="x" in row or "y" in row,
                    body_part=row.get("shot_type"),
                    situation=row.get("situation"),
                    expected_goals_on_target=row.get("expected_goals_on_target"),
                )


def lineups(output: ObservationCollector, payload: object) -> None:
    data = object_value(object_value(payload).get("data"))
    for side in ("home", "away"):
        if data.get(side) is None:
            continue
        path = f"json:/data/{side}"
        with output.record(path):
            row = native_record(PitchApiLineupSide, data[side])
            team = emit_team(
                output, object_value(data.get(side + "_team")), "json:/data/" + side + "_team"
            )
            members: list[LineupMemberV2] = []
            roles: tuple[tuple[str, Literal["STARTER", "BENCH"]], ...] = (
                ("starters", "STARTER"),
                ("subs", "BENCH"),
            )
            for group, role in roles:
                for index, raw in enumerate(array(row.get(group))):
                    player_path = f"{path}/{group}/{index}"
                    player = object_value(raw)
                    ref = emit_player(
                        output, player, player_path, team, native_id=player.get("player_id")
                    )
                    members.append(
                        LineupMemberV2(
                            ref,
                            role=role,
                            position=position(output, player.get("position_id"), player_path),
                        )
                    )
            coach = object_value(row["coach"]) if row.get("coach") is not None else None
            confirmed = optional_bool(row.get("confirmed")) is True
            emit_lineup(
                output,
                path,
                team,
                members,
                coach=coach,
                formation=row.get("formation"),
                confirmed=confirmed,
            )


def statistics(output: ObservationCollector, payload: object) -> None:
    data = object_value(object_value(payload).get("data"))
    for pi, raw in enumerate(array(data.get("periods"))):
        path = f"json:/data/periods/{pi}"
        with output.record(path):
            period = object_value(raw)
            name = period_name(required_text(period.get("period")))
            sides: dict[str, dict[str, Any]] = {"home": {}, "away": {}}
            blocked: dict[str, set[str]] = {"home": set(), "away": set()}
            for gi, group in enumerate(array(period.get("groups"))):
                for si, item in enumerate(array(object_value(group).get("items"))):
                    key = f"{path}/groups/{gi}/items/{si}"
                    with output.record(key):
                        row: Mapping[str, Any] = native_record(PitchApiStatistic, item)
                        for side in sides:
                            parsed = measurement(output, row["key"], row[side], key, TEAM_METRICS)
                            add_measurement(output, sides[side], blocked[side], parsed, key)
            for side, values in sides.items():
                team_path = "json:/data/" + side + "_team"
                team = object_value(data.get(side + "_team"))
                emit_team_statistics(
                    output, path, output.context.reference(team.get("id"), team_path), name, values
                )


def player_statistics(output: ObservationCollector, payload: object) -> None:
    for index, raw in enumerate(array(object_value(payload).get("data"))):
        path = f"json:/data/{index}"
        with output.record(path):
            row = object_value(raw)
            player = object_value(row.get("player"))
            team = output.context.reference(row.get("team_id"), path + "/team_id")
            ref = emit_player(output, player, path + "/player", team, native_id=player.get("id"))
            values = player_measurements(output, row.get("stats"), path)
            if values:
                output.emit(
                    statistic_contract(
                        values, PlayerStatisticObservationV2, PlayerStatisticObservationV3
                    ),
                    path,
                    player.get("id"),
                    fixture=output.context.fixture(),
                    team=team,
                    player=ref,
                    **values,
                )


def events(output: ObservationCollector, payload: object) -> None:
    data = object_value(object_value(payload).get("data"))
    for index, raw in enumerate(array(data.get("events"))):
        path = f"json:/data/events/{index}"
        with output.record(path):
            row = native_record(PitchApiEvent, raw)
            event = event_type(row["event_type"], row.get("card"))
            if event is None:
                output.finding(
                    "EVENT_TYPE_UNKNOWN",
                    path,
                    "Unmapped event type",
                    evidence={"source_value": row["event_type"]},
                )
                continue
            player = row.get("player")
            output.emit(
                EventObservationV2,
                path,
                row.get("id"),
                fixture=output.context.fixture(),
                event_type=event,
                team=output.context.reference(row["team_id"], path + "/team_id")
                if row.get("team_id") is not None
                else None,
                player=output.context.reference(object_value(player).get("id"), path + "/player")
                if player is not None
                else None,
                minute=count(row.get("minute")),
                added_time=count(row.get("minute_added")),
                period=text(row.get("period")),
                own_goal=optional_bool(row.get("is_own_goal")),
                penalty=optional_bool(row.get("is_penalty")),
            )
