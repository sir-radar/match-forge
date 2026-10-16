"""OpenFootball football.json has names and file/row locators, not team IDs."""

from typing import NotRequired, TypedDict


class OpenFootballTeam(TypedDict, total=False):
    name: str
    title: str


class OpenFootballScore(TypedDict, total=False):
    ht: list[int]
    ft: list[int]


class OpenFootballMatch(TypedDict):
    date: str
    team1: str | OpenFootballTeam
    team2: str | OpenFootballTeam
    time: NotRequired[str | None]
    round: NotRequired[str | None]
    score: NotRequired[OpenFootballScore]


class OpenFootballCompetition(TypedDict):
    matches: list[OpenFootballMatch]
    name: NotRequired[str | None]
