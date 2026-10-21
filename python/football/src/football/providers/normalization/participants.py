"""Participants are source references until independent canonical resolution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from football.contracts.observations_v2 import (
    CoachObservationV2,
    EntityReferenceV2,
    FormationObservationV2,
    LineupMemberV2,
    LineupObservationV2,
    PlayerObservationV2,
    TeamObservationV2,
)
from football.providers.normalization.common import ObservationCollector, text


def emit_team(output: ObservationCollector, row: Mapping[str, Any], path: str) -> EntityReferenceV2:
    ref = output.context.reference(row.get("id"), path)
    if row.get("name") is not None:
        output.emit(TeamObservationV2, path, row.get("id"), team=ref, name=text(row["name"]))
    return ref


def emit_player(
    output: ObservationCollector,
    row: Mapping[str, Any],
    path: str,
    team: EntityReferenceV2,
    *,
    native_id: object,
) -> EntityReferenceV2:
    ref = output.context.reference(native_id, path)
    if row.get("name") is not None:
        output.emit(
            PlayerObservationV2, path, native_id, player=ref, team=team, name=text(row["name"])
        )
    return ref


def position(output: ObservationCollector, value: object, path: str) -> str | None:
    if value is None:
        return None
    output.finding(
        "POSITION_MAPPING_UNKNOWN",
        path,
        "Provider position has no verified shared mapping",
        severity="WARNING",
        evidence={"source_value": value},
    )
    return None


def emit_lineup(
    output: ObservationCollector,
    path: str,
    team: EntityReferenceV2,
    members: list[LineupMemberV2],
    *,
    coach: Mapping[str, Any] | None,
    formation: object,
    confirmed: bool,
) -> None:
    coach_ref = None
    if coach is not None:
        coach_path = path + "/coach"
        coach_ref = output.context.reference(coach.get("id"), coach_path)
        output.emit(
            CoachObservationV2,
            coach_path,
            coach.get("id"),
            coach=coach_ref,
            team=team,
            name=text(coach.get("name")),
        )
    reported_formation = text(formation)
    output.emit(
        LineupObservationV2,
        path,
        fixture=output.context.fixture(),
        team=team,
        players=tuple(members),
        coach=coach_ref,
        formation=reported_formation,
        lineup_mode="CONFIRMED" if confirmed else "UNKNOWN",
    )
    if confirmed and reported_formation is not None:
        output.emit(
            FormationObservationV2,
            path,
            fixture=output.context.fixture(),
            team=team,
            formation=reported_formation,
            mode="CONFIRMED",
        )
