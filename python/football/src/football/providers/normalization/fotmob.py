"""FotMob detail resources remain separate from fixture and result observations."""

from __future__ import annotations

import re
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
from football.product.provider_history_scopes import normalize_seasons
from football.providers.fotmob import _normalize_match, parse_fotmob_fixture
from football.providers.native.fotmob import (
    FotmobEvent,
    FotmobLineupSide,
    FotmobShot,
    FotmobStatistic,
)
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    optional_bool,
    text,
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


def fixtures(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    if "general" in root:
        with output.record("json:/general"):
            general = object_value(root["general"])
            header = object_value(root.get("header"))
            row = {
                "id": general.get("matchId"),
                "home": general.get("homeTeam"),
                "away": general.get("awayTeam"),
                "status": header.get("status"),
            }
            _fixture(
                output,
                row,
                {"id": general.get("leagueId"), "name": general.get("leagueName")},
                "json:/general",
                team_paths=("json:/general/homeTeam", "json:/general/awayTeam"),
                league_path="json:/general/leagueId",
            )
        return
    if "fixtures" in root:
        _league_fixtures(output, root)
        return
    if "leagues" not in root:
        raise ValueError("FotMob fixture response has no known fixture container")
    for li, value in enumerate(array(root.get("leagues"))):
        league = object_value(value)
        for mi, raw in enumerate(array(league.get("matches"))):
            path = f"json:/leagues/{li}/matches/{mi}"
            with output.record(path):
                _fixture(
                    output,
                    object_value(raw),
                    league,
                    path,
                    team_paths=(path + "/home", path + "/away"),
                    league_path=f"json:/leagues/{li}",
                )


def _league_fixtures(output: ObservationCollector, root: Mapping[str, Any]) -> None:
    details = object_value(root.get("details"))
    selected = text(details.get("selectedSeason"))
    requested = output.context.season_label
    if requested is not None and (
        selected is None or normalize_seasons([selected]) != normalize_seasons([requested])
    ):
        raise ValueError("FotMob selected season differs from requested scope")
    for i, raw in enumerate(array(object_value(root["fixtures"]).get("allMatches"))):
        path = f"json:/fixtures/allMatches/{i}"
        with output.record(path):
            _fixture(
                output,
                object_value(raw),
                details,
                path,
                team_paths=(path + "/home", path + "/away"),
                league_path="json:/details",
                season=selected,
            )


def _fixture(
    output: ObservationCollector,
    raw: Mapping[str, Any],
    league: Mapping[str, Any],
    path: str,
    *,
    team_paths: tuple[str, str],
    league_path: str,
    season: str | None = None,
) -> None:
    row = parse_fotmob_fixture(raw)
    _status_reason(row["status"])
    league_id = output.context.reference(league.get("id"), league_path).provider_native_id
    if league_id is None:
        raise ValueError("FotMob fixture requires a league ID")
    if (
        output.context.competition_native_id is not None
        and league_id != output.context.competition_native_id
    ):
        raise ValueError("FotMob competition differs from requested scope")
    fixture = _normalize_match(
        row, league_id, output.context.time.observed_at, None, text(league.get("name"))
    )
    if row["status"].get("awarded") is True:
        fixture = replace(fixture, status="AWARDED", result_score_basis="UNKNOWN")
    time = replace(output.context.time, provider_updated_at=fixture.source_updated_at)
    if row["status"].get("updatedAt") is not None and fixture.source_updated_at is None:
        output.finding(
            "PROVIDER_TIMESTAMP_UNRESOLVED",
            path + "/status/updatedAt",
            "Provider update timestamp cannot be interpreted safely",
            severity="WARNING",
            evidence={"source_value": row["status"]["updatedAt"]},
        )
    home = emit_team(output, row["home"], team_paths[0])
    away = emit_team(output, row["away"], team_paths[1])
    competition = output.context.reference(league_id, league_path)
    if fixture.provider_competition_name is not None:
        output.emit(
            CompetitionObservationV2,
            league_path,
            league_id,
            competition=competition,
            name=fixture.provider_competition_name,
        )
    ref = output.context.reference(fixture.provider_match_id, path)
    output.emit(
        FixtureObservationV2,
        path,
        fixture.provider_match_id,
        observation_time=time,
        fixture=ref,
        competition=competition,
        home_team=home,
        away_team=away,
        kickoff_at=fixture.kickoff_at,
        kickoff_precision="EXACT",
        status=fixture.status,
        season_label=season,
    )
    if fixture.status != "SCHEDULED":
        output.emit(
            ResultObservationV2,
            path,
            fixture.provider_match_id,
            observation_time=time,
            fixture=ref,
            status=fixture.status,
            score_basis=fixture.result_score_basis,
            home_goals=fixture.home_score,
            away_goals=fixture.away_score,
        )


def _status_reason(status: Mapping[str, Any]) -> None:
    reason = status.get("reason")
    label = text(object_value(reason).get("short")) if reason is not None else None
    known = {
        "HT",
        "HALF TIME",
        "HALF-TIME",
        "SUSP",
        "SUSPENDED",
        "INT",
        "INTERRUPTED",
        "PST",
        "POSTPONED",
        "ABD",
        "ABANDONED",
        "AWD",
        "AW",
        "AWARDED",
        "FT",
        "FULL TIME",
        "FULL-TIME",
        "AET",
        "AFTER EXTRA TIME",
        "AP",
        "PEN",
        "PENS",
        "AFTER PENALTIES",
        "CANCELLED",
        "CANC",
        "NS",
        "NOT STARTED",
    }
    if (
        label is not None
        and label.upper() not in known
        and not re.fullmatch(r"\d+(?:\+\d+)?['’]?", label)
    ):
        raise ValueError(f"unmapped FotMob status reason: {label}")


def _content(payload: object, resource: str) -> Mapping[str, Any] | None:
    root = object_value(payload)
    content = object_value(root.get("content"))
    value = content.get(resource)
    return object_value(value) if value is not None else None


def lineups(output: ObservationCollector, payload: object) -> None:
    lineup = _content(payload, "lineup")
    if lineup is None:
        return
    for side in ("homeTeam", "awayTeam"):
        if lineup.get(side) is None:
            continue
        path = f"json:/content/lineup/{side}"
        with output.record(path):
            row = native_record(FotmobLineupSide, lineup[side])
            team = emit_team(output, row, path)
            members: list[LineupMemberV2] = []
            roles: tuple[tuple[str, Literal["STARTER", "BENCH"]], ...] = (
                ("starters", "STARTER"),
                ("subs", "BENCH"),
            )
            for group, role in roles:
                for index, value in enumerate(array(row.get(group))):
                    player_path = f"{path}/{group}/{index}"
                    player = object_value(value)
                    ref = emit_player(output, player, player_path, team, native_id=player.get("id"))
                    members.append(
                        LineupMemberV2(
                            ref,
                            role,
                            position=position(output, player.get("positionId"), player_path),
                        )
                    )
            coach = object_value(row["coach"]) if row.get("coach") is not None else None
            emit_lineup(
                output,
                path,
                team,
                members,
                coach=coach,
                formation=row.get("formation"),
                confirmed=lineup.get("lineupType") == "confirmed",
            )


def shots(output: ObservationCollector, payload: object) -> None:
    shotmap = _content(payload, "shotmap")
    if shotmap is None:
        return
    for index, value in enumerate(array(shotmap.get("shots"))):
        path = f"json:/content/shotmap/shots/{index}"
        with output.record(path):
            row = native_record(FotmobShot, value)
            player = (
                output.context.reference(row["playerId"], path + "/playerId")
                if row.get("playerId") is not None
                else None
            )
            emit_shot(
                output,
                path,
                row.get("id"),
                team=output.context.reference(row["teamId"], path + "/teamId"),
                player=player,
                minute=row.get("min"),
                period=row.get("period"),
                expected_goals=row.get("expectedGoals"),
                outcome=shot_outcome(output, row.get("eventType"), path),
                own_goal=row.get("isOwnGoal"),
                coordinates="x" in row or "y" in row,
                body_part=row.get("shotType"),
                situation=row.get("situation"),
                expected_goals_on_target=row.get("expectedGoalsOnTarget"),
            )


def statistics(output: ObservationCollector, payload: object) -> None:
    stats = _content(payload, "stats")
    if stats is None:
        return
    general = object_value(object_value(payload).get("general"))
    for name, raw in object_value(stats.get("Periods")).items():
        path = f"json:/content/stats/Periods/{name}"
        with output.record(path):
            period = object_value(raw)
            values: list[dict[str, Any]] = [{}, {}]
            blocked: list[set[str]] = [set(), set()]
            for gi, group in enumerate(array(period.get("stats"))):
                for si, raw_stat in enumerate(array(object_value(group).get("stats"))):
                    key = f"{path}/stats/{gi}/stats/{si}"
                    with output.record(key):
                        row = native_record(FotmobStatistic, raw_stat)
                        if len(row["stats"]) != 2:
                            raise ValueError("FotMob statistic requires exactly two team values")
                        for i, value in enumerate(row["stats"]):
                            parsed = measurement(output, row["key"], value, key, TEAM_METRICS)
                            add_measurement(output, values[i], blocked[i], parsed, key)
            for i, side in enumerate(("homeTeam", "awayTeam")):
                team = object_value(general.get(side))
                emit_team_statistics(
                    output,
                    path,
                    output.context.reference(team.get("id"), "json:/general/" + side),
                    period_name(name),
                    values[i],
                )


def player_statistics(output: ObservationCollector, payload: object) -> None:
    players = _content(payload, "playerStats")
    if players is None:
        return
    for native_id, raw in players.items():
        path = f"json:/content/playerStats/{native_id}"
        with output.record(path):
            row = object_value(raw)
            team = output.context.reference(row.get("teamId"), path + "/teamId")
            player = emit_player(output, row, path, team, native_id=row.get("id", native_id))
            values = player_measurements(output, row.get("stats"), path)
            if values:
                output.emit(
                    statistic_contract(
                        values, PlayerStatisticObservationV2, PlayerStatisticObservationV3
                    ),
                    path,
                    row.get("id", native_id),
                    fixture=output.context.fixture(),
                    team=team,
                    player=player,
                    **values,
                )


def events(output: ObservationCollector, payload: object) -> None:
    facts = _content(payload, "matchFacts")
    if facts is None or facts.get("events") is None:
        return
    general = object_value(object_value(payload).get("general"))
    for index, raw in enumerate(array(object_value(facts["events"]).get("events"))):
        path = f"json:/content/matchFacts/events/events/{index}"
        with output.record(path):
            row = native_record(FotmobEvent, raw)
            if row.get("isPenaltyShootoutEvent") is True:
                output.finding(
                    "SHOOTOUT_EVENT_UNSUPPORTED",
                    path,
                    "Shootout event remains in raw evidence",
                    severity="WARNING",
                )
                continue
            kind = event_type(row["type"], row.get("card"))
            if kind is None:
                output.finding(
                    "EVENT_TYPE_UNKNOWN",
                    path,
                    "Unmapped event type",
                    evidence={"source_value": row["type"]},
                )
                continue
            is_home = optional_bool(row.get("isHome"))
            team_key = "homeTeam" if is_home else "awayTeam"
            team = object_value(general.get(team_key)) if is_home is not None else None
            player = row.get("player")
            output.emit(
                EventObservationV2,
                path,
                row.get("eventId"),
                fixture=output.context.fixture(),
                event_type=kind,
                team=output.context.reference(team.get("id"), "json:/general/" + team_key)
                if team is not None
                else None,
                player=output.context.reference(player.get("id"), path + "/player")
                if player is not None
                else None,
                minute=count(row.get("time")),
                added_time=count(row.get("overloadTime")),
                period=text(row.get("period")),
                own_goal=optional_bool(row.get("ownGoal")),
                penalty=optional_bool(row.get("isPenalty")),
            )
