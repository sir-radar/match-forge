"""Understat source quantities remain separate from canonical/model eligibility."""

from __future__ import annotations

import gzip
import io
import re
import zlib
from datetime import datetime
from urllib.parse import urlsplit

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    EntityReferenceV2,
    ExpectedGoalsObservationV2,
    FixtureObservationV2,
    ResultObservationV2,
)
from football.ingestion.registration import MAX_SOURCE_RESOURCE_BYTES
from football.product.historical_backfill import date_only_timestamp
from football.providers.native.reader import native_record
from football.providers.native.understat import UnderstatMatch, UnderstatRoster, UnderstatShot
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    number,
    object_value,
)
from football.providers.normalization.measurements import emit_shot
from football.providers.normalization.participants import emit_player, emit_team


def json_bytes(raw: bytes) -> bytes:
    if not raw.startswith(b"\x1f\x8b"):
        return raw
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            result = compressed.read(MAX_SOURCE_RESOURCE_BYTES + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError("invalid compressed Understat resource") from error
    if len(result) > MAX_SOURCE_RESOURCE_BYTES:
        raise ValueError("decoded Understat resource exceeds the source byte limit")
    return result


def results(output: ObservationCollector, payload: object) -> None:
    scope = re.fullmatch(
        r"getLeagueData/([A-Za-z_]+)/([1-9][0-9]*)",
        urlsplit(output.context.resource_key).path.lstrip("/"),
    )
    if scope is None:
        raise ValueError("Understat league resource requires its registered request scope")
    league, season = scope.groups()
    if output.context.competition_native_id not in (
        None,
        league,
    ) or output.context.season_label not in (None, season):
        raise ValueError("Understat league/season differs from requested scope")
    competition = output.context.reference(league, "request:competition")
    output.emit(
        CompetitionObservationV2,
        "request:competition",
        league,
        competition=competition,
        name=league,
        season_label=season,
    )
    root = object_value(payload)
    if "dates" not in root:
        raise ValueError("Understat league response has no dates array")
    for index, raw in enumerate(array(root["dates"])):
        path = f"json:/dates/{index}"
        with output.record(path):
            row = native_record(UnderstatMatch, raw)
            if row["h"]["id"] == row["a"]["id"]:
                raise ValueError("Understat fixture reports the same native team on both sides")
            home = emit_team(output, {"id": row["h"]["id"], "name": row["h"]["title"]}, path + "/h")
            away = emit_team(output, {"id": row["a"]["id"], "name": row["a"]["title"]}, path + "/a")
            fixture = output.context.reference(row["id"], path)
            output.emit(
                FixtureObservationV2,
                path,
                row["id"],
                fixture=fixture,
                competition=competition,
                home_team=home,
                away_team=away,
                kickoff_at=date_only_timestamp(datetime.fromisoformat(row["datetime"])),
                kickoff_precision="DATE_ONLY",
                status="FINISHED" if row["isResult"] else "SCHEDULED",
                season_label=season,
            )
            if row["isResult"]:
                output.emit(
                    ResultObservationV2,
                    path,
                    row["id"],
                    fixture=fixture,
                    status="FINISHED",
                    score_basis="UNKNOWN",
                    home_goals=count(row["goals"]["h"]),
                    away_goals=count(row["goals"]["a"]),
                )
                for side, team, value in (("h", home, row["xG"]["h"]), ("a", away, row["xG"]["a"])):
                    xg = number(value)
                    if xg is not None:
                        output.emit(
                            ExpectedGoalsObservationV2,
                            path + "/xG/" + side,
                            fixture=fixture,
                            team=team,
                            scope="MATCH_TOTAL",
                            expected_goals=xg,
                        )


def shots(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    shotmap = object_value(root.get("shots"))
    rosters = object_value(root.get("rosters"))
    for side in ("h", "a"):
        team = _roster_team(output, rosters.get(side), side)
        for index, raw in enumerate(array(shotmap.get(side))):
            path = f"json:/shots/{side}/{index}"
            with output.record(path):
                row = native_record(UnderstatShot, raw)
                if row["match_id"] != output.context.fixture_native_id or row["h_a"] != side:
                    raise ValueError("Understat shot fixture/side conflicts with its scope")
                outcome = {
                    "Goal": "GOAL",
                    "MissedShots": "OFF_TARGET",
                    "SavedShot": "SAVED",
                    "BlockedShot": "BLOCKED",
                }.get(row["result"])
                if outcome is None:
                    output.finding(
                        "SHOT_OUTCOME_UNKNOWN",
                        path,
                        "Unmapped Understat shot outcome",
                        severity="WARNING",
                        evidence={"source_value": row["result"]},
                    )
                if object_value(raw).get("player_assisted"):
                    output.finding(
                        "ASSIST_ID_UNAVAILABLE",
                        path + "/player_assisted",
                        "Source assistant label has no native ID; no name-based attribution",
                        severity="WARNING",
                    )
                emit_shot(
                    output,
                    path,
                    row["id"],
                    team=team,
                    player=output.context.reference(row["player_id"], path + "/player_id")
                    if row["player_id"]
                    else None,
                    minute=row["minute"],
                    period=None,
                    expected_goals=row["xG"],
                    outcome=outcome,
                    coordinates="X" in row or "Y" in row,
                    body_part=row["shotType"],
                    situation=row["situation"],
                )


def _roster_team(output: ObservationCollector, raw: object, side: str) -> EntityReferenceV2:
    path = "json:/rosters/" + side
    rows = object_value(raw)
    parsed = {key: native_record(UnderstatRoster, row) for key, row in rows.items()}
    if any(row["h_a"] != side for row in parsed.values()):
        raise ValueError("Understat roster side conflicts with its source group")
    teams = {row["team_id"] for row in parsed.values()}
    native = next(iter(teams)) if len(teams) == 1 else None
    team = output.context.reference(native, path)
    if native is None:
        output.finding(
            "TEAM_ID_UNRESOLVED",
            path,
            "Roster does not prove one native team ID",
            severity="WARNING",
        )
    for key, row in parsed.items():
        emit_player(
            output, {"name": row["player"]}, path + "/" + key, team, native_id=row["player_id"]
        )
    return team
