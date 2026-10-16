"""football-data.org v4 observations, including explicit awarded/non-played results."""

from __future__ import annotations

from dataclasses import replace

from football.contracts.observations_v2 import (
    FixtureObservationV2,
    ResultObservationV2,
    StandingObservationV2,
)
from football.providers.native.football_data_org import (
    FootballDataOrgFixture,
    FootballDataOrgStanding,
)
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    object_value,
    text,
    timestamp,
)
from football.providers.normalization.participants import emit_team

STATUS = {
    "SCHEDULED": "SCHEDULED",
    "TIMED": "SCHEDULED",
    "IN_PLAY": "LIVE",
    "PAUSED": "HALF_TIME",
    "EXTRA_TIME": "LIVE",
    "PENALTY_SHOOTOUT": "LIVE",
    "FINISHED": "FINISHED",
    "AWARDED": "AWARDED",
    "POSTPONED": "POSTPONED",
    "CANCELLED": "CANCELLED",
    "SUSPENDED": "SUSPENDED",
}


def fixtures(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    for index, raw in enumerate(array(root.get("matches"))):
        path = f"json:/matches/{index}"
        with output.record(path):
            row = native_record(FootballDataOrgFixture, raw)
            if row["status"] not in STATUS:
                raise ValueError(f"unmapped football-data.org status: {row['status']}")
            ref = output.context.reference(row["id"], path)
            time = output.context.time
            if row.get("lastUpdated") is not None:
                time = replace(time, provider_updated_at=timestamp(row["lastUpdated"]))
            home = emit_team(output, row["homeTeam"], path + "/homeTeam")
            away = emit_team(output, row["awayTeam"], path + "/awayTeam")
            output.emit(
                FixtureObservationV2,
                path,
                row["id"],
                observation_time=time,
                fixture=ref,
                competition=output.context.reference(
                    row["competition"]["id"], path + "/competition"
                ),
                home_team=home,
                away_team=away,
                status=STATUS[row["status"]],
                kickoff_at=timestamp(row["utcDate"]),
                kickoff_precision="EXACT",
            )
            if STATUS[row["status"]] != "SCHEDULED":
                score = row["score"]
                total = object_value(score.get("fullTime", {}))
                output.emit(
                    ResultObservationV2,
                    path,
                    row["id"],
                    observation_time=time,
                    fixture=ref,
                    status=STATUS[row["status"]],
                    score_basis={
                        "REGULAR": "REGULATION_90",
                        "EXTRA_TIME": "EXTRA_TIME",
                        "PENALTY_SHOOTOUT": "PENALTY_SHOOTOUT",
                    }.get(text(score.get("duration")) or "", "UNKNOWN"),
                    home_goals=total.get("home"),
                    away_goals=total.get("away"),
                )


def standings(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    competition = object_value(root.get("competition"))
    if output.context.season_label is None:
        raise ValueError("standing normalization requires an explicit season label")
    for si, raw in enumerate(array(root.get("standings"))):
        group = object_value(raw)
        if group.get("type") != "TOTAL":
            output.finding(
                "STANDING_SCOPE_UNSUPPORTED",
                f"json:/standings/{si}",
                "Only total standings fit this contract",
                severity="WARNING",
            )
            continue
        for ti, value in enumerate(array(group.get("table"))):
            path = f"json:/standings/{si}/table/{ti}"
            with output.record(path):
                row = native_record(FootballDataOrgStanding, value)
                team = emit_team(output, row["team"], path + "/team")
                output.emit(
                    StandingObservationV2,
                    path,
                    row["team"]["id"],
                    competition=output.context.reference(
                        competition.get("id"), "json:/competition"
                    ),
                    team=team,
                    season_label=output.context.season_label,
                    rank=row["position"],
                    played=row["playedGames"],
                    won=row["won"],
                    drawn=row["draw"],
                    lost=row["lost"],
                    goals_for=row["goalsFor"],
                    goals_against=row["goalsAgainst"],
                    points=row["points"],
                )
