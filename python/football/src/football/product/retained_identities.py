"""Native identity extraction from exact retained StatsBomb resource formats."""

from __future__ import annotations

from football.ingestion.errors import CanonicalIngestionError
from football.ingestion.statsbomb_contracts import (
    _LINEUP_PATH,
    _MATCH_PATH,
    _parse_competitions,
    _parse_lineup,
    _parse_matches,
)
from football.providers.native.espn import EspnCompetitor
from football.providers.native.reader import native_json


def statsbomb_identifiers(payload: bytes, path: str) -> dict[tuple[str, str | None], set[str]]:
    """Reuse native parsers; source recognition grants no canonical identity trust."""
    native_json(payload)  # Reject duplicate keys before the existing parsers read the same bytes.
    try:
        return _statsbomb_index(payload, path)
    except CanonicalIngestionError as error:
        raise ValueError(str(error)) from error


def _statsbomb_index(payload: bytes, path: str) -> dict[tuple[str, str | None], set[str]]:
    if path == "data/competitions.json":
        rows = _parse_competitions(payload, path)
        return {("competition", None): {row.competition_id for row in rows}}
    if scope := _MATCH_PATH.fullmatch(path):
        matches = _parse_matches(payload, path, (scope.group(1), scope.group(2)))
        native_ids = [row.provider_id for row in matches]
        if len(native_ids) != len(set(native_ids)):
            raise ValueError("duplicate native match identity in source path")
        return {
            ("competition", None): {row.competition_id for row in matches},
            ("team", None): {
                team.provider_id for row in matches for team in (row.home_team, row.away_team)
            },
            ("match", None): set(native_ids),
        }
    if scope := _LINEUP_PATH.fullmatch(path):
        lineup = _parse_lineup(payload, path, scope.group(1))
        players = [player.provider_id for team in lineup.teams for player in team.players]
        if len(players) != len(set(players)):
            raise ValueError("native player appears for multiple teams in one lineup")
        return {
            ("team", None): {team.provider_id for team in lineup.teams},
            ("player", None): set(players),
        }
    return {}


def espn_summary_identifiers(payload: bytes, path: str) -> dict[tuple[str, str | None], set[str]]:
    """Read the one requested summary, excluding news, related fixtures and boxscores."""
    from urllib.parse import parse_qs, urlsplit

    from football.providers.native.espn import EspnEvent
    from football.providers.native.reader import native_record

    route = urlsplit(path)
    parts = route.path.split("/")
    if route.scheme or route.netloc or len(parts) != 2 or parts[1] != "summary":
        return {}
    query = parse_qs(route.query, keep_blank_values=True)
    value = native_json(payload)
    if not isinstance(value, dict) or not isinstance(value.get("header"), dict):
        raise ValueError("ESPN summary requires a header")
    header = value["header"]
    event = native_record(EspnEvent, header)
    league = header.get("league")
    if not isinstance(league, dict) or league.get("slug") != parts[0]:
        raise ValueError("ESPN summary league differs from source path")
    if query != {"event": [event["id"]]} or len(event["competitions"]) != 1:
        raise ValueError("ESPN summary event differs from requested resource")
    competition = event["competitions"][0]
    if competition["id"] != event["id"]:
        raise ValueError("ESPN summary competition differs from event")
    teams = _espn_summary_teams(competition["competitors"])
    native = league.get("id")
    if not isinstance(native, str) or not native.isascii() or not native.isdecimal():
        raise ValueError("ESPN summary requires its native league ID")
    return {("competition", None): {native}, ("team", None): teams, ("match", None): {event["id"]}}


def _espn_summary_teams(competitors: list[EspnCompetitor]) -> set[str]:
    if len(competitors) != 2 or {row["homeAway"] for row in competitors} != {"home", "away"}:
        raise ValueError("ESPN summary requires two distinct sides")
    if any(row["id"] != row["team"]["id"] for row in competitors):
        raise ValueError("ESPN competitor and team IDs conflict")
    teams = {row["team"]["id"] for row in competitors}
    if len(teams) != 2 or any(not native.isascii() or not native.isdecimal() for native in teams):
        raise ValueError("ESPN summary requires distinct native team IDs")
    return teams
