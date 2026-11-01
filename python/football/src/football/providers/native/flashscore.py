"""Named Flashscore feed keys, verified against the source client's exports."""

import json
import re
from collections.abc import Collection
from typing import NotRequired, TypedDict


def environment_bytes(raw: bytes) -> bytes:
    page = raw.decode("utf-8")
    assignments = list(re.finditer(r"window\.environment\s*=\s*", page))
    if len(assignments) != 1:
        raise ValueError("Flashscore page requires one environment JSON object")
    start = assignments[0].end()
    _, end = json.JSONDecoder().raw_decode(page, start)
    return page[start:end].encode("utf-8")


def feed_records(feed: str, fields: Collection[str]) -> list[dict[str, str]]:
    rows = []
    for block in feed.split("¬~"):
        row: dict[str, str] = {}
        for cell in block.split("¬"):
            key, separator, value = cell.partition("÷")
            if key not in fields:
                continue
            if not separator or key in row:
                raise ValueError("Flashscore named feed field is malformed or duplicated")
            row[key] = value
        if row:
            rows.append(row)
    return rows


def feed_cells(feed: str) -> list[list[tuple[str, str]]]:
    blocks = []
    for block in feed.split("¬~"):
        cells = []
        for cell in block.split("¬"):
            if not cell:
                continue
            key, separator, value = cell.partition("÷")
            if not separator:
                raise ValueError("Flashscore feed cell has no value delimiter")
            cells.append((key, value))
        if cells:
            blocks.append(cells)
    return blocks


class FlashscoreIncidentActor(TypedDict):
    IE: str
    IM: NotRequired[str]
    IF: NotRequired[str]


class FlashscoreIncident(TypedDict):
    III: str
    IA: str
    IB: str
    ID: NotRequired[str]
    actors: list[FlashscoreIncidentActor]


class FlashscoreLineupMember(TypedDict):
    LP: str
    LI: str
    LG: NotRequired[str]
    LD: NotRequired[str]
    LS: NotRequired[str]


class FlashscoreSummary(TypedDict):
    AC: str
    BA: NotRequired[str]
    BB: NotRequired[str]
    BC: NotRequired[str]
    BD: NotRequired[str]


class FlashscoreStatistic(TypedDict):
    SD: str
    SG: str
    SH: NotRequired[str]
    SI: NotRequired[str]


class FlashscoreProject(TypedDict):
    id: int


class FlashscoreFeedResolver(TypedDict):
    default_url: str


class FlashscoreApp(TypedDict):
    project: FlashscoreProject
    project_type: FlashscoreProject
    feed_sign: str
    feed_resolver: FlashscoreFeedResolver


class FlashscoreConfig(TypedDict):
    app: FlashscoreApp


class FlashscoreMatchPage(TypedDict):
    event_id_c: str
    sport_id: int
    config: FlashscoreConfig


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
