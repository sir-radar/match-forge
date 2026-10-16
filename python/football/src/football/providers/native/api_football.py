"""API-Football v3 native records; values have not been normalized."""

from typing import NotRequired, TypedDict


class ApiFootballTeam(TypedDict):
    id: int | None
    name: NotRequired[str | None]


class ApiFootballPlayer(TypedDict):
    id: int | None
    name: NotRequired[str | None]
    pos: NotRequired[str | None]
    grid: NotRequired[str | None]
    type: NotRequired[str | None]
    reason: NotRequired[str | None]


class ApiFootballCoach(TypedDict):
    id: int | None
    name: NotRequired[str | None]


class ApiFootballLeague(TypedDict):
    id: int
    name: NotRequired[str | None]
    country: NotRequired[str | None]
    season: NotRequired[int]
    round: NotRequired[str | None]
    type: NotRequired[str | None]


class ApiFootballCountry(TypedDict, total=False):
    name: str | None
    code: str | None
    flag: str | None


class ApiFootballSeason(TypedDict):
    year: int
    current: NotRequired[bool]
    start: NotRequired[str | None]
    end: NotRequired[str | None]
    coverage: NotRequired[dict[str, object]]


class ApiFootballCompetition(TypedDict):
    league: ApiFootballLeague
    country: NotRequired[ApiFootballCountry]
    seasons: NotRequired[list[ApiFootballSeason]]


class ApiFootballFixtureStatus(TypedDict):
    short: str
    long: NotRequired[str | None]
    elapsed: NotRequired[int | None]


class ApiFootballVenue(TypedDict, total=False):
    id: int | None
    name: str | None
    city: str | None


class ApiFootballFixtureMetadata(TypedDict):
    id: int
    date: str
    status: ApiFootballFixtureStatus
    venue: NotRequired[ApiFootballVenue | None]


class ApiFootballTeams(TypedDict):
    home: ApiFootballTeam
    away: ApiFootballTeam


class ApiFootballGoals(TypedDict):
    home: int | None
    away: int | None


class ApiFootballFixture(TypedDict):
    fixture: ApiFootballFixtureMetadata
    league: ApiFootballLeague
    teams: ApiFootballTeams
    goals: ApiFootballGoals
    score: NotRequired[dict[str, object]]


class ApiFootballLineupPlayer(TypedDict):
    player: ApiFootballPlayer


class ApiFootballLineup(TypedDict):
    team: ApiFootballTeam
    formation: NotRequired[str | None]
    coach: NotRequired[ApiFootballCoach | None]
    startXI: NotRequired[list[ApiFootballLineupPlayer]]
    substitutes: NotRequired[list[ApiFootballLineupPlayer]]


class ApiFootballInjury(TypedDict):
    player: ApiFootballPlayer
    team: ApiFootballTeam
    fixture: NotRequired[dict[str, object]]
    league: NotRequired[ApiFootballLeague]


class ApiFootballStatisticValue(TypedDict):
    type: str
    value: float | str | None


class ApiFootballStatistic(TypedDict):
    team: ApiFootballTeam
    statistics: list[ApiFootballStatisticValue]


class ApiFootballStanding(TypedDict):
    rank: int
    team: ApiFootballTeam
    points: int
    all: dict[str, object]
    goalsDiff: NotRequired[int]
