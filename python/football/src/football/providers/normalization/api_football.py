"""API-Football v3 fixture, lineup and availability observations."""

from __future__ import annotations

from typing import Literal

from football.contracts.observations_v2 import (
    AvailabilityObservationV2,
    CompetitionObservationV2,
    EntityReferenceV2,
    FixtureObservationV2,
    LineupMemberV2,
    ResultObservationV2,
)
from football.providers.native.api_football import (
    ApiFootballCompetition,
    ApiFootballFixture,
    ApiFootballInjury,
    ApiFootballLineup,
)
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    text,
    timestamp,
)
from football.providers.normalization.participants import (
    emit_lineup,
    emit_player,
    emit_team,
    position,
)

STATUS = {
    "TBD": "SCHEDULED",
    "NS": "SCHEDULED",
    "1H": "LIVE",
    "2H": "LIVE",
    "ET": "LIVE",
    "BT": "LIVE",
    "P": "LIVE",
    "LIVE": "LIVE",
    "HT": "HALF_TIME",
    "SUSP": "SUSPENDED",
    "INT": "INTERRUPTED",
    "FT": "FINISHED",
    "AET": "FINISHED",
    "PEN": "FINISHED",
    "PST": "POSTPONED",
    "CANC": "CANCELLED",
    "ABD": "ABANDONED",
    "AWD": "AWARDED",
    "WO": "AWARDED",
}


def _rows(payload: object) -> list[object]:
    root = object_value(payload)
    errors = root.get("errors")
    if errors not in (None, [], {}):
        raise ValueError("API-Football response contains provider errors")
    return array(root.get("response"))


def fixtures(output: ObservationCollector, payload: object) -> None:
    for index, raw in enumerate(_rows(payload)):
        path = f"json:/response/{index}"
        with output.record(path):
            row = native_record(ApiFootballFixture, raw)
            fixture, league = row["fixture"], row["league"]
            short = fixture["status"]["short"]
            if short not in STATUS:
                raise ValueError(f"unmapped API-Football status: {short}")
            competition = output.context.reference(league["id"], path + "/league")
            home = emit_team(output, row["teams"]["home"], path + "/teams/home")
            away = emit_team(output, row["teams"]["away"], path + "/teams/away")
            ref = output.context.reference(fixture["id"], path + "/fixture")
            output.emit(
                FixtureObservationV2,
                path,
                fixture["id"],
                fixture=ref,
                competition=competition,
                home_team=home,
                away_team=away,
                kickoff_at=timestamp(fixture["date"]),
                kickoff_precision="EXACT",
                status=STATUS[short],
                season_label=str(league["season"]) if "season" in league else None,
                round=text(league.get("round")),
            )
            if STATUS[short] != "SCHEDULED":
                output.emit(
                    ResultObservationV2,
                    path,
                    fixture["id"],
                    fixture=ref,
                    status=STATUS[short],
                    score_basis={
                        "FT": "REGULATION_90",
                        "AET": "EXTRA_TIME",
                        "PEN": "PENALTY_SHOOTOUT",
                    }.get(short, "UNKNOWN"),
                    home_goals=count(row["goals"]["home"]),
                    away_goals=count(row["goals"]["away"]),
                )


def competitions(output: ObservationCollector, payload: object) -> None:
    for index, raw in enumerate(_rows(payload)):
        path = f"json:/response/{index}"
        with output.record(path):
            row = native_record(ApiFootballCompetition, raw)
            league = row["league"]
            country = row.get("country")
            output.emit(
                CompetitionObservationV2,
                path,
                league["id"],
                competition=output.context.reference(league["id"], path + "/league"),
                name=text(league.get("name")),
                country=text(country.get("name")) if country else None,
                competition_type=text(league.get("type")),
            )


def availability(output: ObservationCollector, payload: object) -> None:
    for index, raw in enumerate(_rows(payload)):
        path = f"json:/response/{index}"
        with output.record(path):
            row = native_record(ApiFootballInjury, raw)
            player = row["player"]
            kind = text(player.get("type"))
            states = {"Missing Fixture": "UNAVAILABLE_OTHER", "Doubtful": "AVAILABILITY_UNVERIFIED"}
            if kind not in states:
                raise ValueError(f"unmapped API-Football availability type: {kind}")
            fixture = row.get("fixture")
            ref: EntityReferenceV2 | None
            if fixture is not None and fixture.get("id") is not None:
                ref = output.context.reference(fixture["id"], path + "/fixture")
                if (
                    output.context.fixture_native_id is not None
                    and ref.provider_native_id != output.context.fixture_native_id
                ):
                    raise ValueError("availability fixture conflicts with requested scope")
            else:
                ref = (
                    output.context.fixture()
                    if output.context.fixture_native_id is not None
                    else None
                )
            team = emit_team(output, row["team"], path + "/team")
            player_ref = emit_player(
                output, player, path + "/player", team, native_id=player.get("id")
            )
            output.emit(
                AvailabilityObservationV2,
                path,
                player.get("id"),
                fixture=ref,
                team=team,
                player=player_ref,
                availability_type="OTHER",
                availability_state=states[kind],
                reason=text(player.get("reason")),
            )


def lineups(output: ObservationCollector, payload: object) -> None:
    for index, raw in enumerate(_rows(payload)):
        path = f"json:/response/{index}"
        with output.record(path):
            row = native_record(ApiFootballLineup, raw)
            team = emit_team(output, row["team"], path + "/team")
            members: list[LineupMemberV2] = []
            roles: tuple[tuple[str, Literal["STARTER", "BENCH"]], ...] = (
                ("startXI", "STARTER"),
                ("substitutes", "BENCH"),
            )
            for group, role in roles:
                for pi, raw_player in enumerate(array(row.get(group))):
                    player_path = f"{path}/{group}/{pi}/player"
                    player = object_value(object_value(raw_player).get("player"))
                    ref = emit_player(output, player, player_path, team, native_id=player.get("id"))
                    members.append(
                        LineupMemberV2(
                            ref,
                            role,
                            position=position(output, player.get("pos"), player_path),
                            grid_position=text(player.get("grid")),
                        )
                    )
            emit_lineup(
                output,
                path,
                team,
                members,
                coach=row.get("coach"),
                formation=row.get("formation"),
                confirmed=True,
            )
