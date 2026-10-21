"""PitchAPI retains its own IDs, snake-case fields and period resources."""

from typing import NotRequired, TypedDict


class PitchApiTeam(TypedDict):
    id: str
    name: str


class PitchApiCompetition(TypedDict):
    id: str
    name: NotRequired[str | None]


class PitchApiMatch(TypedDict):
    id: str
    time_utc: str
    status: str
    home_team: PitchApiTeam
    away_team: PitchApiTeam
    league: NotRequired[PitchApiCompetition | None]
    score_home: NotRequired[int | None]
    score_away: NotRequired[int | None]
    minute: NotRequired[int | None]
    added_time: NotRequired[int | None]
    period: NotRequired[str | None]
    updated_at: NotRequired[str | None]


class PitchApiEvent(TypedDict):
    event_type: str
    id: NotRequired[str | int | None]
    team_id: NotRequired[str | None]
    minute: NotRequired[int | None]
    minute_added: NotRequired[int | None]


class PitchApiShot(TypedDict):
    team_id: str
    id: NotRequired[str | int]
    expected_goals: NotRequired[float | None]
    is_on_target: NotRequired[bool | None]


class PitchApiStatistic(TypedDict):
    key: str
    home: float | str | None
    away: float | str | None
    title: NotRequired[str | None]


class PitchApiCoach(TypedDict, total=False):
    id: str | None
    name: str | None


class PitchApiLineupPlayer(TypedDict):
    player_id: str
    name: NotRequired[str | None]
    position_id: NotRequired[int | None]
    shirt_number: NotRequired[str | None]


class PitchApiLineupSide(TypedDict, total=False):
    confirmed: bool
    formation: str | None
    coach: PitchApiCoach | None
    starters: list[PitchApiLineupPlayer]
    subs: list[PitchApiLineupPlayer]
