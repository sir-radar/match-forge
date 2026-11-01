"""Observed Understat league JSON, before identity or time qualification."""

from typing import NotRequired, TypedDict


class UnderstatTeam(TypedDict):
    id: str
    title: str


class UnderstatSides(TypedDict):
    h: str | None
    a: str | None


class UnderstatMatch(TypedDict):
    id: str
    isResult: bool
    h: UnderstatTeam
    a: UnderstatTeam
    goals: UnderstatSides
    xG: UnderstatSides
    datetime: str


class UnderstatShot(TypedDict):
    id: str | None
    match_id: str
    player_id: str | None
    h_a: str
    minute: str | None
    result: str
    xG: str | None
    shotType: str | None
    situation: str | None
    X: NotRequired[str | None]
    Y: NotRequired[str | None]


class UnderstatRoster(TypedDict):
    player_id: str
    team_id: str
    player: str
    h_a: str
