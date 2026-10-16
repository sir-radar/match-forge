"""Capability implementations reuse existing clients and their acquisition controls."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from urllib.parse import urlencode

from football.product.api_football import ApiFootballClient, ApiResponse
from football.product.football_data_org import FootballDataOrgClient, FootballDataResponse
from football.providers.base import ProviderConfigurationError
from football.providers.fotmob import FotmobClient, FotmobResponse
from football.providers.pitchapi import PitchApiClient, PitchApiResponse
from football.providers.sources.contracts import ProviderPayload, numeric_identifier


class FotmobSource:
    def __init__(self, client: FotmobClient) -> None:
        self.client = client

    def fixtures(self, day: date) -> ProviderPayload:
        return _fotmob(self.client.matches_by_date(day))

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        return _fotmob(self.client.league(provider_competition_id, season))

    def competitions(self) -> ProviderPayload:
        return _fotmob(self.client.all_leagues())

    def team(self, provider_team_id: str) -> ProviderPayload:
        return _fotmob(self.client.team(provider_team_id))

    def player(self, provider_player_id: str) -> ProviderPayload:
        return _fotmob(self.client.player(provider_player_id))

    def lineups(self, provider_match_id: str) -> ProviderPayload:
        return _fotmob(self.client.match_details(provider_match_id))

    def events(self, provider_match_id: str) -> ProviderPayload:
        return _fotmob(self.client.match_details(provider_match_id))

    def shots(self, provider_match_id: str) -> ProviderPayload:
        return _fotmob(self.client.match_details(provider_match_id))

    def expected_goals(self, provider_match_id: str) -> ProviderPayload:
        return _fotmob(self.client.match_details(provider_match_id))

    def statistics(self, provider_match_id: str) -> ProviderPayload:
        return _fotmob(self.client.match_details(provider_match_id))


def _fotmob(response: FotmobResponse) -> ProviderPayload:
    return ProviderPayload(
        provider="fotmob",
        resource_key=response.resource_url,
        acquired_at=response.fetched_at,
        raw=response.raw,
        media_type=response.content_type,
        cache_max_age_seconds=response.cache_max_age_seconds,
    )


class PitchApiSource:
    def __init__(self, client: PitchApiClient) -> None:
        self.client = client

    def fixtures(self, day: date) -> ProviderPayload:
        return _pitchapi(self.client.matches_by_date(day, status="all"))

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        return _pitchapi(
            self.client.league_matches(
                provider_competition_id,
                season=season,
                status="played",
            )
        )

    def competitions(self) -> ProviderPayload:
        return _pitchapi(self.client.leagues())

    def lineups(self, provider_match_id: str) -> ProviderPayload:
        return _pitchapi(self.client.match_resource(provider_match_id, "lineups"))

    def events(self, provider_match_id: str) -> ProviderPayload:
        return _pitchapi(self.client.match_resource(provider_match_id, "events"))

    def shots(self, provider_match_id: str) -> ProviderPayload:
        return _pitchapi(self.client.match_resource(provider_match_id, "shots"))

    def expected_goals(self, provider_match_id: str) -> ProviderPayload:
        return _pitchapi(self.client.match_resource(provider_match_id, "shots"))

    def statistics(self, provider_match_id: str) -> ProviderPayload:
        return _pitchapi(self.client.match_resource(provider_match_id, "stats"))


def _pitchapi(response: PitchApiResponse) -> ProviderPayload:
    return ProviderPayload(
        provider="pitchapi",
        resource_key=response.path,
        acquired_at=response.fetched_at,
        raw=response.raw,
        media_type="application/json",
    )


class ApiFootballSource:
    def __init__(self, client: ApiFootballClient) -> None:
        self.client = client

    def fixtures(self, day: date) -> ProviderPayload:
        return _api(self.client.fixtures_for_date(day), {"date": day.isoformat()})

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        league, year = numeric_identifier(provider_competition_id), numeric_identifier(season)
        return _api(
            self.client.finished_fixtures(league, year),
            {
                "league": str(league),
                "season": str(year),
                "status": "FT",
            },
        )

    def competitions(self) -> ProviderPayload:
        return _api(self.client.competitions(), {"current": "true"})

    def lineups(self, provider_match_id: str) -> ProviderPayload:
        fixture = numeric_identifier(provider_match_id)
        return _api(self.client.lineups(fixture), {"fixture": str(fixture)})

    def availability(self, provider_match_id: str) -> ProviderPayload:
        fixture = numeric_identifier(provider_match_id)
        return _api(self.client.injuries(fixture), {"fixture": str(fixture)})

    def standings(self, provider_competition_id: str, season: str) -> ProviderPayload:
        league, year = numeric_identifier(provider_competition_id), numeric_identifier(season)
        return _api(
            self.client.standings(league, year),
            {
                "league": str(league),
                "season": str(year),
            },
        )


def _api(response: ApiResponse, query: Mapping[str, str]) -> ProviderPayload:
    return ProviderPayload(
        provider="api_football",
        resource_key=_key(response.path, query),
        acquired_at=response.fetched_at,
        raw=response.raw,
        media_type="application/json",
        remaining_requests=response.remaining_day,
        minute_remaining=response.remaining_minute,
    )


class FootballDataOrgSource:
    def __init__(self, client: FootballDataOrgClient, *, competition_code: str) -> None:
        if not competition_code:
            raise ProviderConfigurationError("football-data.org competition scope is required")
        self.client, self.competition_code = client, competition_code

    def fixtures(self, day: date) -> ProviderPayload:
        return _org(
            self.client.fixtures_for_date(day, self.competition_code),
            {
                "dateFrom": day.isoformat(),
                "dateTo": day.isoformat(),
            },
        )

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        self._scope(provider_competition_id)
        year = numeric_identifier(season)
        return _org(
            self.client.finished_matches(provider_competition_id, year),
            {
                "season": str(year),
                "status": "FINISHED",
            },
        )

    def standings(self, provider_competition_id: str, season: str) -> ProviderPayload:
        self._scope(provider_competition_id)
        year = numeric_identifier(season)
        return _org(self.client.standings(provider_competition_id, year), {"season": str(year)})

    def _scope(self, competition: str) -> None:
        if competition != self.competition_code:
            raise ProviderConfigurationError("request differs from the configured competition")


def _org(response: FootballDataResponse, query: Mapping[str, str]) -> ProviderPayload:
    return ProviderPayload(
        provider="football_data_org",
        resource_key=_key(response.path, query),
        acquired_at=response.fetched_at,
        raw=response.raw,
        media_type="application/json",
    )


def _key(path: str, query: Mapping[str, str]) -> str:
    return path + (("?" + urlencode(sorted(query.items()))) if query else "")
