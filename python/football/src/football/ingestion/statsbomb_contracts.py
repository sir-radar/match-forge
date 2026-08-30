from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from football.ingestion.errors import CanonicalIngestionError
from football.ingestion.registration import VerifiedSource

_MATCH_PATH = re.compile(r"^data/matches/([1-9][0-9]*)/([1-9][0-9]*)\.json$")
_LINEUP_PATH = re.compile(r"^data/lineups/([1-9][0-9]*)\.json$")
_EVENT_PATH = re.compile(r"^data/events/([1-9][0-9]*)\.json$")
_CLOCK = re.compile(r"^([0-9]+):([0-5][0-9](?:\.[0-9]+)?)$")
_EVENT_CLOCK = re.compile(r"^([0-9]+):([0-5][0-9]):([0-5][0-9](?:\.[0-9]+)?)$")


@dataclass(frozen=True)
class CompetitionSeason:
    competition_id: str
    season_id: str
    competition_name: str
    country_name: str | None
    gender: str | None
    is_youth: bool | None
    is_international: bool | None
    season_name: str
    provider_available_at_raw: str | None
    provider_updated_at_raw: str | None
    source_path: str


@dataclass(frozen=True)
class Team:
    provider_id: str
    name: str
    gender: str | None
    country_provider_id: str | None


@dataclass(frozen=True)
class Match:
    provider_id: str
    competition_id: str
    season_id: str
    competition_name: str
    competition_country_name: str | None
    season_name: str
    match_date: date | None
    kick_off_local: time | None
    home_team: Team
    away_team: Team
    home_score: int | None
    away_score: int | None
    provider_status: str | None
    provider_360_status: str | None
    stage: str | None
    match_week: int | None
    data_version: str | None
    shot_fidelity_version: str | None
    xy_fidelity_version: str | None
    provider_updated_at_raw: str | None
    source_path: str


@dataclass(frozen=True)
class PositionStint:
    provider_position_id: str | None
    position_name: str
    period_from: int
    clock_from: timedelta
    period_to: int | None
    clock_to: timedelta | None
    start_reason: str | None
    end_reason: str | None


@dataclass(frozen=True)
class PlayerCard:
    card_type: str
    period: int | None
    event_clock: timedelta | None
    reason: str | None


@dataclass(frozen=True)
class LineupPlayer:
    provider_id: str
    full_name: str
    nickname: str | None
    country_provider_id: str | None
    jersey_number: int | None
    positions: tuple[PositionStint, ...]
    cards: tuple[PlayerCard, ...]

    @property
    def was_starter(self) -> bool:
        return any(position.start_reason == "Starting XI" for position in self.positions)


@dataclass(frozen=True)
class LineupTeam:
    provider_id: str
    name: str
    players: tuple[LineupPlayer, ...]


@dataclass(frozen=True)
class MatchLineup:
    provider_match_id: str
    teams: tuple[LineupTeam, ...]
    source_path: str


@dataclass(frozen=True)
class EventEntity:
    provider_id: str
    name: str


@dataclass(frozen=True)
class Event:
    provider_id: str
    event_index: int
    provider_event_type: str
    period: int
    event_clock: timedelta
    team: EventEntity | None
    player: EventEntity | None
    possession_team: EventEntity | None


@dataclass(frozen=True)
class MatchEvents:
    provider_match_id: str
    events: tuple[Event, ...]
    source_path: str


@dataclass(frozen=True)
class StatsBombBundle:
    competitions: tuple[CompetitionSeason, ...]
    matches: tuple[Match, ...]
    lineups: tuple[MatchLineup, ...]
    events: tuple[MatchEvents, ...]
    processed_paths: tuple[str, ...]


def parse_statsbomb_bundle(source: VerifiedSource) -> StatsBombBundle:
    competitions: list[CompetitionSeason] = []
    matches: list[Match] = []
    lineups: list[MatchLineup] = []
    events: list[MatchEvents] = []
    processed: list[str] = []
    for path in sorted(source.payloads):
        if path == "data/competitions.json":
            competitions.extend(_parse_competitions(source.payloads[path], path))
            processed.append(path)
            continue
        if match_path := _MATCH_PATH.fullmatch(path):
            matches.extend(
                _parse_matches(
                    source.payloads[path],
                    path,
                    (match_path.group(1), match_path.group(2)),
                )
            )
            processed.append(path)
            continue
        if lineup_path := _LINEUP_PATH.fullmatch(path):
            lineups.append(_parse_lineup(source.payloads[path], path, lineup_path.group(1)))
            processed.append(path)
            continue
        if event_path := _EVENT_PATH.fullmatch(path):
            events.append(_parse_events(source.payloads[path], path, event_path.group(1)))
            processed.append(path)
    if not processed:
        raise CanonicalIngestionError("source manifest has no supported canonical resources")
    _require_unique((match.provider_id for match in matches), "match")
    _require_unique((lineup.provider_match_id for lineup in lineups), "lineup")
    _require_unique((resource.provider_match_id for resource in events), "event resource")
    _require_unique(
        (event.provider_id for resource in events for event in resource.events),
        "event",
    )
    supplemented_competitions = _supplement_competitions(competitions, matches)
    return StatsBombBundle(
        competitions=supplemented_competitions,
        matches=tuple(sorted(matches, key=lambda item: int(item.provider_id))),
        lineups=tuple(sorted(lineups, key=lambda item: int(item.provider_match_id))),
        events=tuple(sorted(events, key=lambda item: int(item.provider_match_id))),
        processed_paths=tuple(processed),
    )


def _parse_competitions(payload: bytes, path: str) -> list[CompetitionSeason]:
    rows = _json_array(payload, path)
    return [
        _parse_competition(_object(row, f"{path}[{index}]"), path) for index, row in enumerate(rows)
    ]


def _parse_competition(row: dict[str, object], path: str) -> CompetitionSeason:
    return CompetitionSeason(
        competition_id=_identifier(row, "competition_id"),
        season_id=_identifier(row, "season_id"),
        competition_name=_string(row, "competition_name"),
        country_name=_optional_string(row, "country_name"),
        gender=_optional_string(row, "competition_gender"),
        is_youth=_optional_bool(row, "competition_youth"),
        is_international=_optional_bool(row, "competition_international"),
        season_name=_string(row, "season_name"),
        provider_available_at_raw=_optional_string(row, "match_available"),
        provider_updated_at_raw=_optional_string(row, "match_updated"),
        source_path=path,
    )


def _parse_matches(
    payload: bytes,
    path: str,
    path_identity: tuple[str, str],
) -> list[Match]:
    rows = _json_array(payload, path)
    matches = [
        _parse_match(_object(row, f"{path}[{index}]"), path) for index, row in enumerate(rows)
    ]
    for match in matches:
        if (match.competition_id, match.season_id) != path_identity:
            raise CanonicalIngestionError(
                f"match {match.provider_id} does not belong to source path {path}"
            )
    return matches


def _parse_match(row: dict[str, object], path: str) -> Match:
    competition = _nested_object(row, "competition")
    season = _nested_object(row, "season")
    metadata = _optional_object(row, "metadata")
    stage = _optional_object(row, "competition_stage")
    home_score = _optional_nonnegative_int(row, "home_score")
    away_score = _optional_nonnegative_int(row, "away_score")
    if (home_score is None) != (away_score is None):
        raise CanonicalIngestionError("match scores must both be present or both be null")
    return Match(
        provider_id=_identifier(row, "match_id"),
        competition_id=_identifier(competition, "competition_id"),
        season_id=_identifier(season, "season_id"),
        competition_name=_string(competition, "competition_name"),
        competition_country_name=_optional_string(competition, "country_name"),
        season_name=_string(season, "season_name"),
        match_date=_optional_date(row, "match_date"),
        kick_off_local=_optional_time(row, "kick_off"),
        home_team=_parse_team(_nested_object(row, "home_team"), "home"),
        away_team=_parse_team(_nested_object(row, "away_team"), "away"),
        home_score=home_score,
        away_score=away_score,
        provider_status=_optional_string(row, "match_status"),
        provider_360_status=_optional_string(row, "match_status_360"),
        stage=_optional_string(stage, "name"),
        match_week=_optional_positive_int(row, "match_week"),
        data_version=_optional_string(metadata, "data_version"),
        shot_fidelity_version=_optional_string(metadata, "shot_fidelity_version"),
        xy_fidelity_version=_optional_string(metadata, "xy_fidelity_version"),
        provider_updated_at_raw=_optional_string(row, "last_updated"),
        source_path=path,
    )


def _supplement_competitions(
    competitions: list[CompetitionSeason], matches: list[Match]
) -> tuple[CompetitionSeason, ...]:
    rows = list(competitions)
    existing_pairs = {(row.competition_id, row.season_id) for row in rows}
    existing_competitions = {row.competition_id: row for row in rows}
    matches_by_pair: dict[tuple[str, str], list[Match]] = {}
    for match in matches:
        matches_by_pair.setdefault((match.competition_id, match.season_id), []).append(match)
    for pair in sorted(matches_by_pair, key=lambda item: (int(item[0]), int(item[1]))):
        if pair in existing_pairs:
            continue
        group = matches_by_pair[pair]
        competition_name = _required_match_value(group, "competition_name")
        country_name = _one_match_value(group, "competition_country_name")
        season_name = _required_match_value(group, "season_name")
        source_path = _required_match_value(group, "source_path")
        catalog = existing_competitions.get(pair[0])
        gender = catalog.gender if catalog else _match_gender(group)
        rows.append(
            CompetitionSeason(
                competition_id=pair[0],
                season_id=pair[1],
                competition_name=catalog.competition_name if catalog else competition_name,
                country_name=catalog.country_name if catalog else country_name,
                gender=gender,
                is_youth=catalog.is_youth if catalog else None,
                is_international=catalog.is_international if catalog else None,
                season_name=season_name,
                provider_available_at_raw=None,
                provider_updated_at_raw=_latest_match_update(group),
                source_path=source_path,
            )
        )
        existing_pairs.add(pair)
    return tuple(rows)


def _one_match_value(matches: list[Match], field_name: str) -> str | None:
    values = {getattr(match, field_name) for match in matches}
    if len(values) != 1:
        pair = (matches[0].competition_id, matches[0].season_id)
        raise CanonicalIngestionError(
            f"match-list competition season {pair} has conflicting {field_name}"
        )
    value = values.pop()
    if value is not None and not isinstance(value, str):
        raise AssertionError(f"unexpected match field type: {field_name}")
    return value


def _required_match_value(matches: list[Match], field_name: str) -> str:
    value = _one_match_value(matches, field_name)
    if value is None:
        raise AssertionError(f"required match field is missing: {field_name}")
    return value


def _match_gender(matches: list[Match]) -> str | None:
    values = {
        gender
        for match in matches
        for gender in (match.home_team.gender, match.away_team.gender)
        if gender is not None
    }
    if len(values) > 1:
        pair = (matches[0].competition_id, matches[0].season_id)
        raise CanonicalIngestionError(
            f"match-list competition season {pair} has conflicting team genders"
        )
    return values.pop() if values else None


def _latest_match_update(matches: list[Match]) -> str | None:
    values = [
        match.provider_updated_at_raw
        for match in matches
        if match.provider_updated_at_raw is not None
    ]
    return max(values) if values else None


def _parse_team(row: dict[str, object], side: str) -> Team:
    country = _optional_object(row, "country")
    return Team(
        provider_id=_identifier(row, f"{side}_team_id"),
        name=_string(row, f"{side}_team_name"),
        gender=_optional_string(row, f"{side}_team_gender"),
        country_provider_id=_optional_identifier(country, "id"),
    )


def _parse_lineup(payload: bytes, path: str, provider_match_id: str) -> MatchLineup:
    rows = _json_array(payload, path)
    teams = tuple(
        _parse_lineup_team(_object(row, f"{path}[{index}]")) for index, row in enumerate(rows)
    )
    team_ids = [team.provider_id for team in teams]
    if len(team_ids) != len(set(team_ids)):
        raise CanonicalIngestionError(f"lineup contains duplicate teams: {path}")
    return MatchLineup(provider_match_id, teams, path)


def _parse_events(payload: bytes, path: str, provider_match_id: str) -> MatchEvents:
    rows = _json_array(payload, path)
    events = tuple(_parse_event(_object(row, f"{path}[{index}]")) for index, row in enumerate(rows))
    indexes = [event.event_index for event in events]
    if len(indexes) != len(set(indexes)):
        raise CanonicalIngestionError(f"event resource contains duplicate event indexes: {path}")
    _require_unique((event.provider_id for event in events), "event")
    return MatchEvents(
        provider_match_id=provider_match_id,
        events=tuple(sorted(events, key=lambda event: event.event_index)),
        source_path=path,
    )


def _parse_event(row: dict[str, object]) -> Event:
    event_type = _nested_object(row, "type")
    return Event(
        provider_id=_uuid_identifier(row, "id"),
        event_index=_positive_int(row, "index"),
        provider_event_type=_string(event_type, "name"),
        period=_positive_int(row, "period"),
        event_clock=_event_timestamp(row, "timestamp"),
        team=_event_entity(row, "team"),
        player=_event_entity(row, "player"),
        possession_team=_event_entity(row, "possession_team"),
    )


def _event_entity(row: dict[str, object], field: str) -> EventEntity | None:
    value = row.get(field)
    if value is None:
        return None
    entity = _object(value, field)
    return EventEntity(
        provider_id=_identifier(entity, "id"),
        name=_string(entity, "name"),
    )


def _parse_lineup_team(row: dict[str, object]) -> LineupTeam:
    lineup = _array(row, "lineup")
    players = tuple(
        _parse_lineup_player(_object(player, f"lineup[{index}]"))
        for index, player in enumerate(lineup)
    )
    player_ids = [player.provider_id for player in players]
    if len(player_ids) != len(set(player_ids)):
        raise CanonicalIngestionError("team lineup contains duplicate players")
    return LineupTeam(
        provider_id=_identifier(row, "team_id"),
        name=_string(row, "team_name"),
        players=players,
    )


def _parse_lineup_player(row: dict[str, object]) -> LineupPlayer:
    country = _optional_object(row, "country")
    positions = tuple(
        _parse_position(_object(item, f"positions[{index}]"))
        for index, item in enumerate(_array(row, "positions"))
    )
    cards = tuple(
        _parse_card(_object(item, f"cards[{index}]"))
        for index, item in enumerate(_array(row, "cards"))
    )
    return LineupPlayer(
        provider_id=_identifier(row, "player_id"),
        full_name=_string(row, "player_name"),
        nickname=_optional_string(row, "player_nickname"),
        country_provider_id=_optional_identifier(country, "id"),
        jersey_number=_optional_positive_int(row, "jersey_number"),
        positions=positions,
        cards=cards,
    )


def _parse_position(row: dict[str, object]) -> PositionStint:
    period_from = _positive_int(row, "from_period")
    clock_from = _clock(row, "from", required=True)
    period_to = _optional_positive_int(row, "to_period")
    clock_to = _clock(row, "to", required=False)
    if (period_to is None) != (clock_to is None):
        raise CanonicalIngestionError("position to_period and to must both be null or present")
    if clock_from is None:
        raise CanonicalIngestionError("position from is required")
    return PositionStint(
        provider_position_id=_optional_identifier(row, "position_id"),
        position_name=_string(row, "position"),
        period_from=period_from,
        clock_from=clock_from,
        period_to=period_to,
        clock_to=clock_to,
        start_reason=_optional_string(row, "start_reason"),
        end_reason=_optional_string(row, "end_reason"),
    )


def _parse_card(row: dict[str, object]) -> PlayerCard:
    return PlayerCard(
        card_type=_string(row, "card_type"),
        period=_optional_positive_int(row, "period"),
        event_clock=_clock(row, "time", required=False),
        reason=_optional_string(row, "reason"),
    )


def _json_array(payload: bytes, path: str) -> list[object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CanonicalIngestionError(f"source resource is not valid UTF-8 JSON: {path}") from error
    if not isinstance(value, list):
        raise CanonicalIngestionError(f"source resource must contain a JSON array: {path}")
    return value


def _require_unique(values: Iterable[object], label: str) -> None:
    identifiers = list(values)
    if len(identifiers) != len(set(identifiers)):
        raise CanonicalIngestionError(f"source contains duplicate {label} identifiers")


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CanonicalIngestionError(f"{field} must be a JSON object")
    return value


def _array(row: dict[str, object], field: str) -> list[object]:
    value = row.get(field)
    if not isinstance(value, list):
        raise CanonicalIngestionError(f"{field} must be a JSON array")
    return value


def _nested_object(row: dict[str, object], field: str) -> dict[str, object]:
    if field not in row:
        raise CanonicalIngestionError(f"{field} is required")
    return _object(row[field], field)


def _optional_object(row: dict[str, object], field: str) -> dict[str, object]:
    value = row.get(field)
    if value is None:
        return {}
    return _object(value, field)


def _string(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise CanonicalIngestionError(f"{field} must be a non-empty string")
    return value


def _optional_string(row: dict[str, object], field: str) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CanonicalIngestionError(f"{field} must be null or a non-empty string")
    return value


def _positive_int(row: dict[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CanonicalIngestionError(f"{field} must be a positive integer")
    return value


def _optional_positive_int(row: dict[str, object], field: str) -> int | None:
    if row.get(field) is None:
        return None
    return _positive_int(row, field)


def _optional_nonnegative_int(row: dict[str, object], field: str) -> int | None:
    value = row.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CanonicalIngestionError(f"{field} must be null or a non-negative integer")
    return value


def _identifier(row: dict[str, object], field: str) -> str:
    return str(_positive_int(row, field))


def _uuid_identifier(row: dict[str, object], field: str) -> str:
    value = _string(row, field)
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise CanonicalIngestionError(f"{field} must be a UUID") from error
    if str(parsed) != value:
        raise CanonicalIngestionError(f"{field} must be a canonical lowercase UUID")
    return value


def _optional_identifier(row: dict[str, object], field: str) -> str | None:
    value = _optional_positive_int(row, field)
    return str(value) if value is not None else None


def _optional_bool(row: dict[str, object], field: str) -> bool | None:
    value = row.get(field)
    if value is not None and not isinstance(value, bool):
        raise CanonicalIngestionError(f"{field} must be null or a boolean")
    return value


def _optional_date(row: dict[str, object], field: str) -> date | None:
    value = _optional_string(row, field)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CanonicalIngestionError(f"{field} must be an ISO date") from error


def _optional_time(row: dict[str, object], field: str) -> time | None:
    value = _optional_string(row, field)
    if value is None:
        return None
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise CanonicalIngestionError(f"{field} must be an ISO local time") from error
    if parsed.tzinfo is not None:
        raise CanonicalIngestionError(f"{field} must not include a timezone")
    return parsed


def _clock(row: dict[str, object], field: str, *, required: bool) -> timedelta | None:
    value = _optional_string(row, field)
    if value is None:
        if required:
            raise CanonicalIngestionError(f"{field} is required")
        return None
    match = _CLOCK.fullmatch(value)
    if match is None:
        raise CanonicalIngestionError(f"{field} must use minute:second format")
    try:
        seconds = Decimal(match.group(2))
    except InvalidOperation as error:
        raise CanonicalIngestionError(f"{field} has an invalid second value") from error
    return timedelta(minutes=int(match.group(1)), seconds=float(seconds))


def _event_timestamp(row: dict[str, object], field: str) -> timedelta:
    value = _string(row, field)
    match = _EVENT_CLOCK.fullmatch(value)
    if match is None:
        raise CanonicalIngestionError(f"{field} must use hour:minute:second format")
    try:
        seconds = Decimal(match.group(3))
    except InvalidOperation as error:
        raise CanonicalIngestionError(f"{field} has an invalid second value") from error
    return timedelta(
        hours=int(match.group(1)),
        minutes=int(match.group(2)),
        seconds=float(seconds),
    )
