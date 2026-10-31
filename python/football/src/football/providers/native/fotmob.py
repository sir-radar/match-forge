"""Observed FotMob JSON fields, before status/clock/score normalization."""

from typing import NotRequired, TypedDict


class FotmobTeam(TypedDict):
    id: int | str
    name: NotRequired[str | None]
    longName: NotRequired[str | None]
    shortName: NotRequired[str | None]
    score: NotRequired[int | None]


class FotmobReason(TypedDict, total=False):
    short: str | None
    long: str | None


class FotmobLiveTime(TypedDict, total=False):
    short: str | None
    long: str | None


class FotmobStatus(TypedDict):
    utcTime: str
    started: bool
    finished: bool
    cancelled: bool
    awarded: NotRequired[bool]
    reason: NotRequired[FotmobReason | None]
    liveTime: NotRequired[FotmobLiveTime | None]
    scoreStr: NotRequired[str | None]
    updatedAt: NotRequired[str | int | float | None]


class FotmobFixture(TypedDict):
    id: int | str
    home: FotmobTeam
    away: FotmobTeam
    status: FotmobStatus


class FotmobCompetition(TypedDict, total=False):
    id: int | str
    primaryId: int | str
    name: str | None
    matches: list[FotmobFixture]


class FotmobPlayer(TypedDict):
    id: int | str
    name: NotRequired[str | None]
    positionId: NotRequired[int | None]


class FotmobLineupSide(TypedDict, total=False):
    id: int | str
    name: str | None
    starters: list[FotmobPlayer]
    subs: list[FotmobPlayer]
    coach: FotmobPlayer | None
    formation: str | None


class FotmobLineup(TypedDict, total=False):
    home: FotmobLineupSide
    away: FotmobLineupSide
    homeTeam: FotmobLineupSide
    awayTeam: FotmobLineupSide
    lineupType: str


class FotmobEventPlayer(TypedDict):
    id: int | str | None
    name: NotRequired[str | None]


class FotmobEvent(TypedDict):
    type: str
    eventId: NotRequired[int | str | None]
    time: NotRequired[int | None]
    overloadTime: NotRequired[int | None]
    isHome: NotRequired[bool | None]
    player: NotRequired[FotmobEventPlayer | None]
    card: NotRequired[str | None]
    isPenaltyShootoutEvent: NotRequired[bool | None]


class FotmobShot(TypedDict):
    teamId: int | str
    id: NotRequired[int | str]
    playerId: NotRequired[int | str | None]
    expectedGoals: NotRequired[float | None]
    isOnTarget: NotRequired[bool | None]
    shotType: NotRequired[str | None]
    situation: NotRequired[str | None]
    expectedGoalsOnTarget: NotRequired[float | None]


class FotmobStatistic(TypedDict):
    key: str
    stats: list[float | str | None]
    title: NotRequired[str | None]
