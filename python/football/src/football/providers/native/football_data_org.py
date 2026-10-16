"""football-data.org v4 uses separate scheduled/played score and status fields."""

from typing import NotRequired, TypedDict


class FootballDataOrgTeam(TypedDict):
    id: int | None
    name: NotRequired[str | None]
    shortName: NotRequired[str | None]
    tla: NotRequired[str | None]


class FootballDataOrgCompetition(TypedDict):
    id: int
    code: NotRequired[str | None]
    name: NotRequired[str | None]
    type: NotRequired[str | None]


class FootballDataOrgScore(TypedDict, total=False):
    winner: str | None
    duration: str | None
    fullTime: dict[str, int | None]
    halfTime: dict[str, int | None]


class FootballDataOrgFixture(TypedDict):
    id: int
    utcDate: str
    status: str
    competition: FootballDataOrgCompetition
    homeTeam: FootballDataOrgTeam
    awayTeam: FootballDataOrgTeam
    score: FootballDataOrgScore
    season: NotRequired[dict[str, object]]


class FootballDataOrgStanding(TypedDict):
    position: int
    team: FootballDataOrgTeam
    playedGames: int
    won: int
    draw: int
    lost: int
    points: int
    goalsFor: int
    goalsAgainst: int
    goalDifference: int
