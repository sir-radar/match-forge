"""Observed ESPN identifiers, explicit home/away roles and match status."""

from typing import NotRequired, TypedDict


class EspnTeam(TypedDict):
    id: str
    displayName: str


class EspnCompetitor(TypedDict):
    id: str
    homeAway: str
    team: EspnTeam
    score: NotRequired[str]


class EspnStatusType(TypedDict):
    name: str
    state: str
    completed: bool


class EspnStatus(TypedDict):
    type: EspnStatusType


class EspnCompetition(TypedDict):
    id: str
    date: str
    timeValid: NotRequired[bool]
    status: EspnStatus
    competitors: list[EspnCompetitor]


class EspnEvent(TypedDict):
    id: str
    season: dict[str, object]
    competitions: list[EspnCompetition]
    timeValid: NotRequired[bool]
