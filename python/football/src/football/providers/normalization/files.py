"""Historical file observations retain row/field references instead of name IDs."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping
from datetime import UTC
from typing import Any
from zoneinfo import ZoneInfo

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    EntityReferenceV2,
    FixtureObservationV2,
    OddsObservationV2,
    ResultObservationV2,
    TeamObservationV2,
)
from football.product.football_data_uk import _DIVISIONS, _TIMEZONES, _parse_date, csv_members
from football.product.historical_backfill import date_only_timestamp
from football.product.openfootball import _COUNTRIES, _kickoff, _team_name
from football.product.openfootball import _TIMEZONES as OPENFOOTBALL_TIMEZONES
from football.providers.football_data_uk_csv import _read_csv
from football.providers.native.openfootball import OpenFootballMatch
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    number,
    object_value,
    required_text,
    text,
)


def openfootball(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    competition = output.context.competition_native_id
    if competition is None:
        raise ValueError("OpenFootball normalization requires its catalog competition code")
    for index, raw in enumerate(array(root.get("matches"))):
        path = f"json:/matches/{index}"
        with output.record(path):
            row: Mapping[str, Any] = native_record(OpenFootballMatch, raw)
            teams = [required_text(_team_name(row[key])) for key in ("team1", "team2")]
            if teams[0] == teams[1]:
                raise ValueError("source fixture contains identical team names")
            refs = [output.context.reference(None, path + "/" + key) for key in ("team1", "team2")]
            for i, name in enumerate(teams):
                output.emit(
                    TeamObservationV2, refs[i].source_record_key or path, team=refs[i], name=name
                )
            country = _COUNTRIES.get(competition.split(".")[0])
            if (
                row.get("time") is not None
                and country not in OPENFOOTBALL_TIMEZONES
                and competition != "uefa.cl"
            ):
                raise ValueError("OpenFootball local kickoff has no verified timezone")
            kickoff, precision = _kickoff(
                dict(row),
                country or "World",
                competition_id=competition,
            )
            score = row.get("score")
            goals = score.get("ft") if score else None
            if goals is not None and len(goals) != 2:
                raise ValueError("OpenFootball full-time score requires two values")
            ref = output.context.reference(None, path)
            comp_ref = output.context.reference(competition, "request:competition")
            if root.get("name") is not None:
                output.emit(
                    CompetitionObservationV2,
                    "json:/name",
                    competition,
                    competition=comp_ref,
                    name=text(root["name"]),
                    season_label=output.context.season_label,
                )
            output.emit(
                FixtureObservationV2,
                path,
                fixture=ref,
                competition=comp_ref,
                home_team=refs[0],
                away_team=refs[1],
                kickoff_at=kickoff,
                kickoff_precision=precision,
                status="FINISHED" if goals is not None else "SCHEDULED",
                season_label=output.context.season_label,
                round=text(row.get("round")),
            )
            if goals is not None:
                output.emit(
                    ResultObservationV2,
                    path,
                    fixture=ref,
                    status="FINISHED",
                    score_basis="REGULATION_90",
                    home_goals=goals[0],
                    away_goals=goals[1],
                )


def _csv_rows(payload: object) -> list[dict[str, str]]:
    if not isinstance(payload, bytes):
        raise ValueError("CSV normalization requires source bytes")
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = payload.decode("cp1252")
    header, rows = _read_csv(decoded.encode("utf-8"))
    if len(set(header)) != len(header) or any(not field for field in header):
        raise ValueError("CSV header contains duplicate or empty fields")
    return [dict(zip(header, row, strict=True)) for row in rows]


def football_data_uk(output: ObservationCollector, payload: object) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("CSV normalization requires source bytes")
    members = csv_members(payload) if zipfile.is_zipfile(io.BytesIO(payload)) else [(None, payload)]
    for member, raw in members:
        prefix = f"zip:{member}#" if member is not None else ""
        with output.record(prefix or "csv:"):
            _football_data_uk_rows(output, raw, prefix)


def _football_data_uk_rows(output: ObservationCollector, payload: bytes, prefix: str) -> None:
    for index, row in enumerate(_csv_rows(payload), start=1):
        path = f"{prefix}csv:record/{index}"
        with output.record(path):
            division = required_text(row.get("Div"))
            if (
                output.context.competition_native_id is not None
                and division != output.context.competition_native_id
            ):
                raise ValueError("CSV competition differs from requested scope")
            home, away = required_text(row.get("HomeTeam")), required_text(row.get("AwayTeam"))
            if home == away:
                raise ValueError("CSV contains identical team names")
            refs = [
                output.context.reference(None, path + "/" + key) for key in ("HomeTeam", "AwayTeam")
            ]
            if output.resource == "statistics":
                _csv_statistics(output, row, path, refs)
            elif output.resource == "odds":
                _csv_odds(output, row, path)
            else:
                _csv_fixture(output, row, path, refs, division)


def _csv_fixture(
    output: ObservationCollector,
    row: Mapping[str, str],
    path: str,
    refs: list[EntityReferenceV2],
    division: str,
) -> None:
    day = _parse_date(required_text(row.get("Date")))
    name, country, _ = _DIVISIONS.get(division, (division, None, None))
    raw_time = row.get("Time", "")
    precision = "DATE_ONLY"
    kickoff = date_only_timestamp(day.replace(tzinfo=UTC))
    if raw_time:
        if not re.fullmatch(r"\d{1,2}:\d{2}", raw_time) or country not in _TIMEZONES:
            raise ValueError("CSV kickoff time or timezone is not supported")
        hour, minute = (int(value) for value in raw_time.split(":"))
        kickoff = day.replace(
            hour=hour, minute=minute, tzinfo=ZoneInfo(_TIMEZONES[country])
        ).astimezone(UTC)
        precision = "EXACT"
    goals = count(row.get("FTHG")), count(row.get("FTAG"))
    if (goals[0] is None) != (goals[1] is None):
        raise ValueError("CSV result requires both scores or neither")
    if goals[0] is not None and goals[1] is not None:
        expected = "H" if goals[0] > goals[1] else "A" if goals[1] > goals[0] else "D"
        if row.get("FTR") not in (None, "", expected):
            raise ValueError("CSV result label contradicts the score")
    for i, key in enumerate(("HomeTeam", "AwayTeam")):
        output.emit(
            TeamObservationV2, path + "/" + key, team=refs[i], name=row[key], country=country
        )
    ref = output.context.reference(None, path)
    comp = output.context.reference(division, path + "/Div")
    output.emit(
        CompetitionObservationV2,
        path + "/Div",
        division,
        competition=comp,
        name=name,
        country=country,
    )
    output.emit(
        FixtureObservationV2,
        path,
        fixture=ref,
        competition=comp,
        home_team=refs[0],
        away_team=refs[1],
        kickoff_at=kickoff,
        kickoff_precision=precision,
        status="FINISHED" if goals[0] is not None else "SCHEDULED",
        season_label=output.context.season_label,
    )
    if goals[0] is not None:
        output.emit(
            ResultObservationV2,
            path,
            fixture=ref,
            status="FINISHED",
            score_basis="REGULATION_90",
            home_goals=goals[0],
            away_goals=goals[1],
        )


def _csv_statistics(
    output: ObservationCollector, row: Mapping[str, str], path: str, refs: list[EntityReferenceV2]
) -> None:
    from football.contracts.observations_v2 import TeamStatisticObservationV2

    columns = {
        "S": "total_shots",
        "ST": "shots_on_target",
        "C": "corners",
        "F": "fouls",
        "Y": "yellow_cards",
        "R": "red_cards",
    }
    for i, prefix in enumerate(("H", "A")):
        values: dict[str, Any] = {
            field: count(row.get(prefix + suffix))
            for suffix, field in columns.items()
            if row.get(prefix + suffix) not in (None, "")
        }
        if values:
            output.emit(
                TeamStatisticObservationV2,
                path,
                fixture=output.context.reference(None, path),
                team=refs[i],
                period="FULL_MATCH",
                **values,
            )


def _csv_odds(output: ObservationCollector, row: Mapping[str, str], path: str) -> None:
    values = [number(row.get("B365" + side)) for side in ("H", "D", "A")]
    if any(value is not None for value in values):
        output.emit(
            OddsObservationV2,
            path,
            fixture=output.context.reference(None, path),
            bookmaker="Bet365",
            market="1X2",
            home_decimal=values[0],
            draw_decimal=values[1],
            away_decimal=values[2],
        )
