"""ESPN match facts with source IDs; no identity or historical eligibility claims."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    EntityReferenceV2,
    FixtureObservationV2,
    ResultObservationV2,
)
from football.providers.native.espn import EspnCompetition, EspnEvent
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    required_text,
    timestamp,
)
from football.providers.normalization.espn_details import (
    events,
    rosters,
    statistics,
    team_reference,
)


def scoreboard(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    leagues = array(root.get("leagues"))
    if len(leagues) != 1 or "events" not in root:
        raise ValueError("ESPN scoreboard requires one explicit league and an events array")
    league = object_value(leagues[0])
    for index, raw in enumerate(array(root["events"])):
        path = f"json:/events/{index}"
        with output.record(path):
            row = native_record(EspnEvent, raw)
            child = ObservationCollector(
                replace(output.context, fixture_native_id=row["id"]), output.resource
            )
            _match(child, row, league, path)
            output.observations.extend(child.observations)
            output.findings.extend(child.findings)
            output.records_seen += child.records_seen


def summary(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    header = object_value(root.get("header"))
    row = native_record(EspnEvent, header)
    _, teams, played = _match(output, row, object_value(header.get("league")), "json:/header")
    if not played:
        return
    for index, raw in enumerate(array(object_value(root.get("boxscore", {})).get("teams"))):
        path = f"json:/boxscore/teams/{index}"
        with output.record(path):
            group = object_value(raw)
            team = team_reference(output, object_value(group.get("team")), path + "/team", teams)
            statistics(output, group.get("statistics"), team, path)
    rosters(output, root.get("rosters"), teams)
    events(output, root.get("keyEvents"), teams)


def _scope(
    output: ObservationCollector, row: EspnEvent, league: Mapping[str, Any]
) -> tuple[EntityReferenceV2, str]:
    native = required_text(league.get("id"))
    slug = required_text(league.get("slug"))
    season_value = count(row["season"].get("year"))
    if season_value is None:
        raise ValueError("ESPN event requires its reported season year")
    season = str(season_value)
    route = urlsplit(output.context.resource_key).path.split("/")
    if len(route) != 2 or route[0] != slug:
        raise ValueError("ESPN registered route conflicts with its reported league slug")
    if output.context.competition_native_id not in (
        None,
        native,
    ) or output.context.season_label not in (None, season):
        raise ValueError("ESPN competition/season conflicts with requested scope")
    ref = output.context.reference(native, "json:/league")
    output.emit(
        CompetitionObservationV2,
        "json:/league",
        native,
        competition=ref,
        name=required_text(league.get("name")),
        season_label=season,
    )
    return ref, season


def _match(
    output: ObservationCollector, row: EspnEvent, league: Mapping[str, Any], path: str
) -> tuple[EspnCompetition, dict[str, EntityReferenceV2], bool]:
    if len(row["competitions"]) != 1:
        raise ValueError("ESPN event requires one competition")
    comp = row["competitions"][0]
    if comp["id"] != row["id"] or row["id"] != output.context.fixture_native_id:
        raise ValueError("ESPN event/competition IDs conflict with fixture scope")
    status = comp["status"]["type"]
    states = {
        ("STATUS_FULL_TIME", "post", True): "FINISHED",
        ("STATUS_SCHEDULED", "pre", False): "SCHEDULED",
    }
    normalized = states.get((status["name"], status["state"], status["completed"]))
    if normalized is None:
        raise ValueError("ESPN source status is not yet mapped")
    competition, season = _scope(output, row, league)
    sides = _sides(comp)
    teams = {
        side["team"]["id"]: team_reference(output, side["team"], path + "/competitors/" + label)
        for label, side in sides.items()
    }
    home, away = (teams[sides[label]["team"]["id"]] for label in ("home", "away"))
    if comp.get("timeValid", row.get("timeValid")) is not True:
        raise ValueError("ESPN kickoff requires explicit valid-time evidence")
    output.emit(
        FixtureObservationV2,
        path,
        row["id"],
        fixture=output.context.fixture(),
        competition=competition,
        home_team=home,
        away_team=away,
        kickoff_at=timestamp(comp["date"]),
        kickoff_precision="EXACT",
        status=normalized,
        season_label=season,
    )
    played = normalized == "FINISHED"
    if played:
        _outcomes(output, comp, sides, teams, path)
    return comp, teams, played


def _sides(comp: EspnCompetition) -> dict[str, Any]:
    sides = {row["homeAway"]: row for row in comp["competitors"]}
    if len(comp["competitors"]) != 2 or set(sides) != {"home", "away"}:
        raise ValueError("ESPN fixture requires unique explicit home and away roles")
    if sides["home"]["team"]["id"] == sides["away"]["team"]["id"]:
        raise ValueError("ESPN fixture reports the same team on both sides")
    if any(row["id"] != row["team"]["id"] for row in sides.values()):
        raise ValueError("ESPN competitor and team IDs conflict")
    return sides


def _outcomes(
    output: ObservationCollector,
    comp: EspnCompetition,
    sides: dict[str, Any],
    teams: dict[str, EntityReferenceV2],
    path: str,
) -> None:
    output.emit(
        ResultObservationV2,
        path,
        comp["id"],
        fixture=output.context.fixture(),
        status="FINISHED",
        score_basis="UNKNOWN",
        home_goals=count(sides["home"].get("score")),
        away_goals=count(sides["away"].get("score")),
    )
    for label, row in sides.items():
        statistics(
            output, row.get("statistics"), teams[row["team"]["id"]], path + "/competitors/" + label
        )
