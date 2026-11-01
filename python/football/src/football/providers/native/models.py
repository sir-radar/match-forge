"""Native JSON codecs, not declarations of enabled provider capabilities."""

from typing import Any

from football.providers.native.api_football import (
    ApiFootballCoach,
    ApiFootballCompetition,
    ApiFootballFixture,
    ApiFootballInjury,
    ApiFootballLineup,
    ApiFootballPlayer,
    ApiFootballStanding,
    ApiFootballStatistic,
    ApiFootballTeam,
)
from football.providers.native.espn import EspnCompetition, EspnCompetitor, EspnEvent, EspnTeam
from football.providers.native.football_data_org import (
    FootballDataOrgCompetition,
    FootballDataOrgFixture,
    FootballDataOrgStanding,
    FootballDataOrgTeam,
)
from football.providers.native.fotmob import (
    FotmobCompetition,
    FotmobEvent,
    FotmobFixture,
    FotmobLineup,
    FotmobPlayer,
    FotmobShot,
    FotmobStatistic,
    FotmobTeam,
)
from football.providers.native.openfootball import OpenFootballCompetition, OpenFootballMatch
from football.providers.native.pitchapi import (
    PitchApiCompetition,
    PitchApiEvent,
    PitchApiMatch,
    PitchApiShot,
    PitchApiStatistic,
    PitchApiTeam,
)
from football.providers.native.understat import (
    UnderstatMatch,
    UnderstatRoster,
    UnderstatShot,
    UnderstatTeam,
)
from football.providers.native.whoscored import WhoScoredMatch, WhoScoredTournament

NATIVE_MODELS: dict[str, type[Any]] = {
    model.__name__: model
    for model in (
        WhoScoredMatch,
        WhoScoredTournament,
        EspnCompetition,
        EspnCompetitor,
        EspnEvent,
        EspnTeam,
        UnderstatMatch,
        UnderstatTeam,
        UnderstatShot,
        UnderstatRoster,
        ApiFootballCoach,
        ApiFootballCompetition,
        ApiFootballFixture,
        ApiFootballInjury,
        ApiFootballLineup,
        ApiFootballPlayer,
        ApiFootballStanding,
        ApiFootballStatistic,
        ApiFootballTeam,
        FootballDataOrgCompetition,
        FootballDataOrgFixture,
        FootballDataOrgStanding,
        FootballDataOrgTeam,
        FotmobCompetition,
        FotmobEvent,
        FotmobFixture,
        FotmobLineup,
        FotmobPlayer,
        FotmobShot,
        FotmobStatistic,
        FotmobTeam,
        OpenFootballCompetition,
        OpenFootballMatch,
        PitchApiCompetition,
        PitchApiEvent,
        PitchApiMatch,
        PitchApiShot,
        PitchApiStatistic,
        PitchApiTeam,
    )
}
