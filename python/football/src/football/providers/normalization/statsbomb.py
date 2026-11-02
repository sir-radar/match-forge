"""Reuse StatsBomb native parsers; never assign a timezone to a local clock."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

from football.contracts.observations_v2 import (
    CoachObservationV2,
    CompetitionObservationV2,
    EventObservationV2,
    LineupMemberV2,
    ResultObservationV2,
)
from football.contracts.observations_v3 import RefereeObservationV3
from football.ingestion.statsbomb_contracts import (
    Match,
    _parse_competition,
    _parse_event,
    _parse_lineup_team,
    _parse_match,
)
from football.normalization.statsbomb_events import _KNOWN_EVENT_TYPES, _coordinates, _location
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    text,
    timestamp,
)
from football.providers.normalization.measurements import emit_shot
from football.providers.normalization.participants import emit_lineup, emit_player, emit_team


def competitions(output: ObservationCollector, payload: object) -> None:
    for i, raw in enumerate(array(payload)):
        path = f"json:/{i}"
        with output.record(path):
            row = _parse_competition(dict(object_value(raw)), output.context.resource_key)
            output.emit(
                CompetitionObservationV2,
                path,
                row.competition_id,
                competition=output.context.reference(row.competition_id, path),
                name=row.competition_name,
                country=row.country_name,
                season_label=row.season_name,
            )


def results(output: ObservationCollector, payload: object) -> None:
    for i, raw in enumerate(array(payload)):
        path = f"json:/{i}"
        with output.record(path):
            row = _parse_match(dict(object_value(raw)), output.context.resource_key)
            if (
                output.context.competition_native_id is not None
                and row.competition_id != output.context.competition_native_id
            ):
                raise ValueError("StatsBomb competition conflicts with requested scope")
            for side, team in (("home_team", row.home_team), ("away_team", row.away_team)):
                emit_team(output, {"id": team.provider_id, "name": team.name}, path + "/" + side)
            time = output.context.time
            if row.provider_updated_at_raw is not None:
                try:
                    time = replace(time, provider_updated_at=timestamp(row.provider_updated_at_raw))
                except ValueError:
                    output.finding(
                        "PROVIDER_TIMESTAMP_UNRESOLVED",
                        path + "/last_updated",
                        "Provider update lacks a verified timezone",
                        severity="WARNING",
                        evidence={"source_value": row.provider_updated_at_raw},
                    )
            if row.home_score is not None:
                output.emit(
                    ResultObservationV2,
                    path,
                    row.provider_id,
                    observation_time=time,
                    fixture=output.context.reference(row.provider_id, path),
                    status="FINISHED",
                    score_basis="UNKNOWN",
                    home_goals=row.home_score,
                    away_goals=row.away_score,
                )
            _match_context(output, object_value(raw), row, path)
            output.finding(
                "KICKOFF_TIMEZONE_UNRESOLVED",
                path,
                "StatsBomb local kickoff needs timezone evidence for an exact UTC fixture",
                severity="WARNING",
            )


def _match_context(
    output: ObservationCollector, raw: Mapping[str, object], match: Match, path: str
) -> None:
    referee = raw.get("referee")
    if referee is not None:
        key = path + "/referee"
        with output.record(key):
            referee = object_value(referee)
            if referee.get("id") is None and text(referee.get("name")) is None:
                raise ValueError("reported referee requires an ID or name")
            output.emit(
                RefereeObservationV3,
                key,
                referee.get("id"),
                fixture=output.context.reference(match.provider_id, path + "/match_id"),
                referee=output.context.reference(referee.get("id"), key),
                name=text(referee.get("name")),
            )
    for side, team in (("home_team", match.home_team), ("away_team", match.away_team)):
        key = path + "/" + side + "/managers"
        with output.record(key):
            managers = array(object_value(raw[side]).get("managers", []))
            for i, manager in enumerate(managers):
                coach_key = key + f"/{i}"
                with output.record(coach_key):
                    coach = object_value(manager)
                    if coach.get("id") is None and text(coach.get("name")) is None:
                        raise ValueError("reported manager requires an ID or name")
                    output.emit(
                        CoachObservationV2,
                        coach_key,
                        coach.get("id"),
                        coach=output.context.reference(coach.get("id"), coach_key),
                        team=output.context.reference(team.provider_id, path + "/" + side),
                        name=text(coach.get("name")),
                    )


def lineups(output: ObservationCollector, payload: object) -> None:
    for i, raw in enumerate(array(payload)):
        path = f"json:/{i}"
        with output.record(path):
            parsed = _parse_lineup_team(dict(object_value(raw)))
            team = emit_team(output, {"id": parsed.provider_id, "name": parsed.name}, path)
            members: list[LineupMemberV2] = []
            for pi, player in enumerate(parsed.players):
                key = f"{path}/lineup/{pi}"
                ref = emit_player(
                    output, {"name": player.full_name}, key, team, native_id=player.provider_id
                )
                role: Literal["STARTER", "BENCH"] = "STARTER" if player.was_starter else "BENCH"
                members.append(LineupMemberV2(ref, role))
            emit_lineup(output, path, team, members, coach=None, formation=None, confirmed=True)


def events(output: ObservationCollector, payload: object) -> None:
    for i, raw in enumerate(array(payload)):
        path = f"json:/{i}"
        with output.record(path):
            row = object_value(raw)
            parsed = _parse_event(dict(row))
            kind = _event_type(row)
            if kind is None:
                known = object_value(row.get("type")).get("id") in _KNOWN_EVENT_TYPES
                output.finding(
                    "EVENT_TYPE_UNSUPPORTED" if known else "EVENT_TYPE_UNKNOWN",
                    path,
                    "Event remains in the source; this contract has no matching event type",
                    severity="INFO" if known else "QUARANTINE",
                    evidence={"source_value": parsed.provider_event_type},
                )
                continue
            if parsed.period == 5:
                output.finding(
                    "SHOOTOUT_EVENT_UNSUPPORTED",
                    path,
                    "Shootout event remains in raw evidence",
                    severity="WARNING",
                )
                continue
            output.emit(
                EventObservationV2,
                path,
                parsed.provider_id,
                fixture=output.context.fixture(),
                event_type=kind,
                team=output.context.reference(parsed.team.provider_id, path + "/team")
                if parsed.team
                else None,
                player=output.context.reference(parsed.player.provider_id, path + "/player")
                if parsed.player
                else None,
                minute=count(row.get("minute")),
                period=str(parsed.period),
            )


def _event_type(row: object) -> str | None:
    value = object_value(row)
    kind = object_value(value.get("type")).get("name")
    if kind in ("Own Goal Against", "Own Goal For"):
        return "GOAL"
    if kind == "Substitution":
        return "SUBSTITUTION"
    if (
        kind == "Shot"
        and object_value(object_value(value.get("shot")).get("outcome")).get("name") == "Goal"
    ):
        return "GOAL"
    if kind in ("Foul Committed", "Bad Behaviour"):
        field = "foul_committed" if kind == "Foul Committed" else "bad_behaviour"
        card = object_value(value.get(field, {})).get("card")
        if card is not None:
            return {
                "Yellow Card": "YELLOW_CARD",
                "Second Yellow": "RED_CARD",
                "Red Card": "RED_CARD",
            }.get(text(object_value(card).get("name")) or "")
    return None


def shots(output: ObservationCollector, payload: object) -> None:
    for i, raw in enumerate(array(payload)):
        path = f"json:/{i}"
        with output.record(path):
            row = object_value(raw)
            parsed = _parse_event(dict(row))
            if parsed.provider_event_type != "Shot":
                continue
            if parsed.period == 5:
                output.finding(
                    "SHOOTOUT_EVENT_UNSUPPORTED",
                    path,
                    "Shootout shot remains in raw evidence",
                    severity="WARNING",
                )
                continue
            shot = object_value(row.get("shot"))
            location = _coordinates(_location(dict(row)))
            if location[4] == "out_of_bounds":
                raise ValueError("StatsBomb shot coordinates are outside 120x80")
            outcome = object_value(shot.get("outcome")).get("name")
            mapped = {
                "Goal": "GOAL",
                "Saved": "SAVED",
                "Saved to Post": "SAVED",
                "Saved Off Target": "SAVED",
                "Blocked": "BLOCKED",
                "Off T": "OFF_TARGET",
                "Wayward": "OFF_TARGET",
                "Post": "POST",
            }.get(text(outcome) or "")
            if mapped is None:
                output.finding(
                    "SHOT_OUTCOME_UNKNOWN",
                    path,
                    "Unmapped shot outcome",
                    severity="WARNING",
                    evidence={"source_value": outcome},
                )
            if parsed.team is None:
                raise ValueError("StatsBomb shot requires a team")
            emit_shot(
                output,
                path,
                parsed.provider_id,
                team=output.context.reference(parsed.team.provider_id, path + "/team"),
                player=output.context.reference(parsed.player.provider_id, path + "/player")
                if parsed.player
                else None,
                minute=row.get("minute"),
                second=row.get("second"),
                period=str(parsed.period),
                expected_goals=shot.get("statsbomb_xg"),
                outcome=mapped,
                normalized_coordinates=(location[2], location[3]),
            )
