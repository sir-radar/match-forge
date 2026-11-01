"""Soccerway's independently verified project uses the shared source client format."""

from football.providers.sources.flashscore import FlashscoreSource


class SoccerwaySource(FlashscoreSource):
    PROVIDER = "soccerway"
    BASE_URL = "https://www.soccerway.com/"
    LEAGUE_PREFIX = ""
    PROJECT_ID = 2020
