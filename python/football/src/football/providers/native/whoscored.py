"""Observed public WhoScored league fixture JSON embedded in HTML."""

from typing import NotRequired, TypedDict


class WhoScoredMatch(TypedDict):
    id: int
    stageId: int
    status: int
    elapsed: str
    period: int
    startTimeUtc: str
    homeTeamId: int
    homeTeamName: str
    awayTeamId: int
    awayTeamName: str
    homeScore: int | None
    awayScore: int | None
    homeYellowCards: NotRequired[int | None]
    awayYellowCards: NotRequired[int | None]
    homeRedCards: NotRequired[int | None]
    awayRedCards: NotRequired[int | None]


class WhoScoredTournament(TypedDict):
    tournamentId: int
    stageId: int
    seasonId: int
    tournamentName: str
    seasonName: str
    matches: list[WhoScoredMatch]
