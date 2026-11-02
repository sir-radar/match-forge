"""Inspected retained Sofascore sample envelopes, without live-access claims."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    EntityReferenceV2,
    EventObservationV2,
    FixtureObservationV2,
    LineupMemberV2,
    PlayerStatisticObservationV2,
    ResultObservationV2,
)
from football.contracts.observations_v3 import (
    PeriodScoreObservationV3,
    PlayerStatisticObservationV3,
)
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    optional_bool,
    required_text,
    timestamp,
)
from football.providers.normalization.events import event_type
from football.providers.normalization.measurements import (
    PLAYER_METRICS,
    TEAM_METRICS,
    add_measurement,
    emit_team_statistics,
    measurement,
    statistic_contract,
)
from football.providers.normalization.participants import emit_lineup, emit_player, emit_team

TEAM_KEYS = {
    **TEAM_METRICS,
    "totalshotsongoal": "total_shots",
    "shotsongoal": "shots_on_target",
    "shotsoffgoal": "shots_off_target",
    "bigchancecreated": "big_chances",
}
PLAYER_KEYS = {**PLAYER_METRICS, "goalassist": "assists"}


def retained_fixture(payload: object) -> str:
    root = object_value(payload)
    url = urlsplit(required_text(root.get("url")))
    match = re.fullmatch(
        r"/api/v1/event/([1-9][0-9]*)(?:/(statistics|lineups|incidents))?", url.path
    )
    if (url.scheme, url.netloc) != ("https", "www.sofascore.com") or not match or url.query:
        raise ValueError("retained Sofascore URL is outside the verified resource families")
    return match[1]


def _body(output: ObservationCollector, payload: object, family: str) -> Mapping[str, Any]:
    root = object_value(payload)
    native = retained_fixture(root)
    expected = f"https://www.sofascore.com/api/v1/event/{native}"
    if family != "event":
        expected += "/" + family
    if root["url"] != expected or native != output.context.fixture_native_id:
        raise ValueError("retained Sofascore resource conflicts with fixture/family scope")
    if root.get("status") != 200 or type(root.get("trimmed")) is not bool:
        raise ValueError("retained Sofascore sample requires successful status and trimming flag")
    if timestamp(root.get("fetched_at_utc")) > output.context.time.acquired_at:
        raise ValueError("retained Sofascore fetch clock is after acquisition")
    if root["trimmed"]:
        output.finding(
            "SOURCE_SAMPLE_TRIMMED", "json:/", "Published sample is incomplete", severity="WARNING"
        )
    body = object_value(root.get("body"))
    fields = ("home", "away") if family == "lineups" else (family,)
    if any(key not in body or body[key] is None for key in fields):
        raise ValueError("retained Sofascore body lacks its required resource fields")
    if not root["trimmed"] and _omitted(body):
        raise ValueError("retained Sofascore trimming flag contradicts omitted records")
    return body


def _omitted(value: object) -> bool:
    if isinstance(value, dict):
        return "__trimmed__" in value or any(_omitted(child) for child in value.values())
    if isinstance(value, list):
        return any(_omitted(child) for child in value)
    return False


def _items(
    output: ObservationCollector, value: object, path: str
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    for index, raw in enumerate(array(value)):
        key = f"{path}/{index}"
        row = object_value(raw)
        if "__trimmed__" in row:
            output.finding(
                "SOURCE_LIST_TRUNCATED",
                key,
                "Source sample omits list members",
                severity="WARNING",
                evidence=dict(row),
            )
        else:
            yield key, row


def _id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("Sofascore native identifier must be a positive integer")
    return value


def event(output: ObservationCollector, payload: object) -> None:
    row = object_value(_body(output, payload, "event").get("event"))
    native = _id(row.get("id"))
    if str(native) != output.context.fixture_native_id:
        raise ValueError("Sofascore event ID conflicts with retained URL")
    tournament = object_value(row.get("tournament"))
    sport = object_value(object_value(tournament.get("category")).get("sport"))
    if sport.get("slug") != "football":
        raise ValueError("Sofascore source is not football")
    league, season = (
        object_value(tournament.get("uniqueTournament")),
        object_value(row.get("season")),
    )
    comp = output.context.reference(
        _id(league.get("id")), "json:/body/event/tournament/uniqueTournament"
    )
    label = required_text(season.get("year"))
    if output.context.competition_native_id not in (
        None,
        comp.provider_native_id,
    ) or output.context.season_label not in (None, label):
        raise ValueError("Sofascore competition/season conflicts with requested scope")
    status = object_value(row.get("status"))
    if type(status.get("code")) is not int:
        raise ValueError("Sofascore event status code must be an integer")
    state = {("finished", 100): "FINISHED", ("notstarted", 0): "SCHEDULED"}.get(
        (required_text(status.get("type")), status["code"])
    )
    if state is None:
        raise ValueError("Sofascore event status has no verified mapping")
    home, away = (object_value(row.get(side + "Team")) for side in ("home", "away"))
    if _id(home.get("id")) == _id(away.get("id")):
        raise ValueError("Sofascore event has identical home/away IDs")
    kickoff = row.get("startTimestamp")
    if type(kickoff) is not int:
        raise ValueError("Sofascore kickoff requires its native Unix UTC timestamp")
    try:
        instant = datetime.fromtimestamp(kickoff, UTC)
    except (OverflowError, OSError) as error:
        raise ValueError("Sofascore kickoff timestamp is invalid") from error
    sides = [
        emit_team(output, team, "json:/body/event/" + side + "Team")
        for side, team in zip(("home", "away"), (home, away), strict=True)
    ]
    output.emit(
        CompetitionObservationV2,
        "json:/body/event/tournament",
        league["id"],
        competition=comp,
        name=required_text(league.get("name")),
        season_label=label,
    )
    output.emit(
        FixtureObservationV2,
        "json:/body/event",
        native,
        fixture=output.context.fixture(),
        competition=comp,
        home_team=sides[0],
        away_team=sides[1],
        kickoff_at=instant,
        kickoff_precision="EXACT",
        status=state,
        season_label=label,
    )
    if state == "FINISHED":
        _scores(output, row)


def _scores(output: ObservationCollector, row: Mapping[str, Any]) -> None:
    home, away = (object_value(row.get(side + "Score")) for side in ("home", "away"))
    output.emit(
        ResultObservationV2,
        "json:/body/event/score",
        fixture=output.context.fixture(),
        home_goals=count(home.get("current")),
        away_goals=count(away.get("current")),
        score_basis="UNKNOWN",
        status="FINISHED",
    )
    if home.get("period1") is not None and away.get("period1") is not None:
        output.emit(
            PeriodScoreObservationV3,
            "json:/body/event/score/period1",
            fixture=output.context.fixture(),
            period="FIRST_HALF",
            score_basis="UNKNOWN",
            home_goals=count(home["period1"]),
            away_goals=count(away["period1"]),
        )
    if "period2" in home or "period2" in away:
        output.finding(
            "SCORE_PERIOD_UNVERIFIED",
            "json:/body/event/score/period2",
            "Football period2 has no verified second-half goal meaning",
            severity="WARNING",
        )


def statistics(output: ObservationCollector, payload: object) -> None:
    body = _body(output, payload, "statistics")
    for path, group in _items(output, body.get("statistics"), "json:/body/statistics"):
        period = {"ALL": "FULL_MATCH", "1ST": "FIRST_HALF", "2ND": "SECOND_HALF"}.get(
            required_text(group.get("period"))
        )
        if period is None:
            raise ValueError("Sofascore statistic period has no verified mapping")
        for side in ("home", "away"):
            values: dict[str, Any] = {}
            blocked: set[str] = set()
            for group_path, section in _items(output, group.get("groups"), path + "/groups"):
                for key, row in _items(
                    output, section.get("statisticsItems"), group_path + "/statisticsItems"
                ):
                    parsed = measurement(
                        output, required_text(row.get("key")), row.get(side), key, TEAM_KEYS
                    )
                    add_measurement(output, values, blocked, parsed, key)
            team = output.context.reference(None, "json:/body/" + side)
            emit_team_statistics(output, path + "/" + side, team, period, values)


def lineups(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    body = _body(output, root, "lineups")
    confirmed = optional_bool(body.get("confirmed")) is True and root["trimmed"] is False
    for side in ("home", "away"):
        path = "json:/body/" + side
        group = object_value(body.get(side))
        rows = list(_items(output, group.get("players"), path + "/players"))
        team = output.context.reference(None, path)
        reported = sorted({_id(row["teamId"]) for _, row in rows if row.get("teamId") is not None})
        if reported:
            output.finding(
                "PLAYER_TEAM_SCOPE_UNVERIFIED",
                path,
                "Player teamId can name a club outside this fixture; not a match-team binding",
                severity="WARNING",
                evidence={"source_team_ids": reported},
            )
        members = []
        for key, row in rows:
            with output.record(key):
                player = object_value(row.get("player"))
                ref = emit_player(
                    output, player, key + "/player", team, native_id=_id(player.get("id"))
                )
                substitute = optional_bool(row.get("substitute"))
                if substitute is None:
                    raise ValueError("Sofascore lineup role is missing")
                members.append(LineupMemberV2(ref, "BENCH" if substitute else "STARTER"))
                _player_statistics(output, row.get("statistics"), team, ref, key)
        emit_lineup(
            output,
            path,
            team,
            members,
            coach=None,
            formation=group.get("formation"),
            confirmed=confirmed,
        )


def _player_statistics(
    output: ObservationCollector,
    raw: object,
    team: EntityReferenceV2,
    player: EntityReferenceV2,
    path: str,
) -> None:
    values: dict[str, Any] = {}
    for key, value in object_value({} if raw is None else raw).items():
        if key == "statisticsType":
            continue
        parsed = measurement(output, key, value, path + "/statistics/" + key, PLAYER_KEYS)
        if parsed is not None:
            values[parsed[0]] = parsed[1]
    if values:
        output.emit(
            statistic_contract(values, PlayerStatisticObservationV2, PlayerStatisticObservationV3),
            path + "/statistics",
            fixture=output.context.fixture(),
            team=team,
            player=player,
            **values,
        )


def incidents(output: ObservationCollector, payload: object) -> None:
    body = _body(output, payload, "incidents")
    for path, row in _items(output, body.get("incidents"), "json:/body/incidents"):
        if row.get("incidentType") == "period":
            continue
        with output.record(path):
            label = event_type(required_text(row.get("incidentType")), row.get("incidentClass"))
            if label is None:
                output.finding(
                    "EVENT_TYPE_UNSUPPORTED",
                    path,
                    "Unmapped Sofascore incident",
                    severity="WARNING",
                    evidence={"type": row.get("incidentType")},
                )
                continue
            home = optional_bool(row.get("isHome"))
            side = "home" if home else "away"
            team = (
                output.context.reference(None, "json:/body/" + side) if home is not None else None
            )
            player_ref = None
            if team is not None:
                for field in ("player", "playerIn", "playerOut"):
                    if row.get(field) is not None:
                        player = object_value(row[field])
                        ref = emit_player(
                            output,
                            player,
                            path + "/" + field,
                            team,
                            native_id=_id(player.get("id")),
                        )
                        if field == "player":
                            player_ref = ref
            output.emit(
                EventObservationV2,
                path,
                row.get("id"),
                fixture=output.context.fixture(),
                event_type=label,
                team=team,
                player=player_ref,
                minute=count(row.get("time")),
                added_time=count(row.get("addedTime")),
            )
