"""Public page feeds only; no live-clock or settlement qualification is implied."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    FixtureObservationV2,
    ResultObservationV2,
)
from football.providers.native.flashscore import (
    FlashscoreLeague,
    FlashscoreMatch,
    environment_bytes,
    feed_records,
)
from football.providers.native.reader import native_record
from football.providers.normalization.common import (
    NormalizationContext,
    ObservationCollector,
    array,
    count,
    object_value,
    required_text,
)
from football.providers.normalization.participants import emit_team

_NAMED_KEYS = (
    frozenset(FlashscoreMatch.__annotations__)
    | frozenset(FlashscoreLeague.__annotations__)
    | {"SA"}
)


def validate_resource_scope(context: NormalizationContext, resource: str) -> None:
    prefix = {"statistics": "st", "events": "sui", "lineups": "li", "summary": "sur"}.get(resource)
    if prefix is not None and not context.resource_key.startswith("df_" + prefix + "_1_"):
        raise ValueError("Flashscore registered feed family conflicts with requested resource")


def json_bytes(raw: bytes) -> bytes:
    """Keep raw environment JSON for the pipeline's strict JSON validation."""
    page = raw.decode("utf-8")
    environment = environment_bytes(raw).decode("utf-8")
    archives = list(re.finditer(r"var\s+league_archive_data\s*=\s*", page))
    if len(archives) > 1:
        raise ValueError("Flashscore archive JSON is ambiguous")
    archive = _json_expression(page, archives[0].end()) if archives else "null"
    feeds = {name: _feed(page, name) for name in ("results", "fixtures")}
    encoded = json.dumps(feeds, ensure_ascii=False, separators=(",", ":"))
    return (
        '{"environment":' + environment + ',"archive":' + archive + ',"feeds":' + encoded + "}"
    ).encode("utf-8")


def _json_expression(page: str, start: int) -> str:
    _, end = json.JSONDecoder().raw_decode(page, start)
    return page[start:end]


def _feed(page: str, name: str) -> list[dict[str, str]]:
    pattern = r"cjs\.initialFeeds\['" + name + r"'\]\s*=\s*\{\s*data:\s*`([^`]*)`"
    matches = re.findall(pattern, page)
    if len(matches) != 1 or "${" in matches[0]:
        raise ValueError("Flashscore feed is absent, ambiguous or contains interpolation")
    return feed_records(matches[0], _NAMED_KEYS)


def league(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    environment = object_value(root.get("environment"))
    if type(environment.get("sport_id")) is not int or environment["sport_id"] != 1:
        raise ValueError("Flashscore page is not explicitly football")
    feeds = object_value(root.get("feeds"))
    for name in ("results", "fixtures"):
        rows = array(feeds.get(name))
        if name == "fixtures" and not rows:
            output.finding(
                "FEED_EMPTY",
                "feed:fixtures",
                "Source declared an empty fixtures feed",
                severity="INFO",
            )
            continue
        if len(rows) < 2 or object_value(rows[0]).get("SA") != "1":
            raise ValueError("Flashscore feed requires explicit football and league headers")
        header = native_record(FlashscoreLeague, rows[1])
        season = _scope(output, environment, root.get("archive"), header)
        output.emit(
            CompetitionObservationV2,
            "feed:" + name + "/league",
            header["ZEE"],
            competition=output.context.reference(header["ZEE"], "feed:" + name + "/league"),
            name=header["ZA"],
            season_label=season,
        )
        for index, raw in enumerate(rows[2:]):
            path = f"feed:{name}/{index}"
            with output.record(path):
                _match(output, native_record(FlashscoreMatch, raw), header, season, path)


def _scope(
    output: ObservationCollector,
    environment: Mapping[str, Any],
    archive: object,
    header: FlashscoreLeague,
) -> str:
    candidates = [
        object_value(s)
        for s in array(environment.get("season_list"))
        if object_value(s).get("id") == environment.get("selected_season_id")
    ]
    if len(candidates) != 1:
        raise ValueError("Flashscore selected season is absent or ambiguous")
    selected = candidates[0]
    season = required_text(selected.get("name"))
    if selected.get("pathname") != f"/standings/{header['ZE']}/{header['ZC']}/":
        raise ValueError("Flashscore feed stage differs from selected season")
    route = urlsplit(output.context.resource_key).path
    current_route = header["ZL"].lstrip("/") + "results/"
    if route.strip("/") != current_route.strip("/") and not _archive_route(archive, route, season):
        raise ValueError("Flashscore league path differs from registered request")
    if output.context.competition_native_id not in (
        None,
        header["ZEE"],
    ) or output.context.season_label not in (None, season):
        raise ValueError("Flashscore competition/season differs from requested scope")
    return season


def _archive_route(archive: object, route: str, season: str) -> bool:
    if archive is None:
        return False
    matches = [
        object_value(s)
        for s in array(object_value(archive).get("seasons"))
        if (required_text(object_value(s).get("url")).strip("/") + "/results") == route.strip("/")
    ]
    return len(matches) == 1 and required_text(matches[0].get("name")).endswith(" " + season)


def _match(
    output: ObservationCollector,
    row: FlashscoreMatch,
    header: FlashscoreLeague,
    season: str,
    path: str,
) -> None:
    if any(
        re.fullmatch(r"[A-Za-z0-9]+", native) is None
        for native in (row["AA"], row["PX"], row["PY"])
    ):
        raise ValueError("Flashscore fixture requires single explicit native participant IDs")
    if row["PX"] == row["PY"]:
        raise ValueError("Flashscore fixture reports the same team on both sides")
    status = {("3", "3"): "FINISHED", ("1", "1"): "SCHEDULED"}.get((row["AB"], row["AC"]))
    if status is None:
        raise ValueError("Flashscore event stage/type is not yet mapped")
    start = count(row["AD"])
    if start is None:
        raise ValueError("Flashscore match start epoch is required")
    try:
        kickoff = datetime.fromtimestamp(start, UTC)
    except (OverflowError, OSError) as error:
        raise ValueError("Flashscore match start epoch is out of range") from error
    home = emit_team(output, {"id": row["PX"], "name": row["AE"]}, path + "/home")
    away = emit_team(output, {"id": row["PY"], "name": row["AF"]}, path + "/away")
    fixture = output.context.reference(row["AA"], path)
    output.emit(
        FixtureObservationV2,
        path,
        row["AA"],
        fixture=fixture,
        competition=output.context.reference(header["ZEE"], path),
        home_team=home,
        away_team=away,
        kickoff_at=kickoff,
        kickoff_precision="EXACT",
        status=status,
        season_label=season,
    )
    if status == "FINISHED":
        output.emit(
            ResultObservationV2,
            path,
            row["AA"],
            fixture=fixture,
            status=status,
            score_basis="UNKNOWN",
            home_goals=count(row.get("AT")),
            away_goals=count(row.get("AU")),
        )
