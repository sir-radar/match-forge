"""Named Flashscore feed keys, verified against the source client's exports."""

from typing import NotRequired, TypedDict


class FlashscoreMatch(TypedDict):
    AA: str
    AD: str
    AB: str
    AC: str
    AE: str
    AF: str
    PX: str
    PY: str
    AT: NotRequired[str]
    AU: NotRequired[str]


class FlashscoreLeague(TypedDict):
    ZA: str
    ZEE: str
    ZC: str
    ZE: str
    ZL: str
