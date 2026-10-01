"""Bulk OpenFootball football.json discovery, parsing, caching, and import."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection

from football.product.historical_backfill import (
    BackfillSummary,
    HistoricalBackfillStore,
    HistoricalMatch,
    KickoffPrecision,
    date_only_timestamp,
)

PROVIDER_CODE = "openfootball"
REPOSITORY_URL = "https://github.com/openfootball/football.json.git"
PARSER_VERSION = "openfootball-product-v1"
_SEASON = re.compile(r"^(?:19|20)\d{2}(?:[-_]\d{2,4})?$")
_COUNTRIES = {
    "at": "Austria",
    "be": "Belgium",
    "br": "Brazil",
    "ch": "Switzerland",
    "cz": "Czech Republic",
    "de": "Germany",
    "dk": "Denmark",
    "en": "England",
    "es": "Spain",
    "fr": "France",
    "gr": "Greece",
    "ie": "Ireland",
    "it": "Italy",
    "jp": "Japan",
    "mx": "Mexico",
    "nl": "Netherlands",
    "no": "Norway",
    "pl": "Poland",
    "pt": "Portugal",
    "ro": "Romania",
    "ru": "Russia",
    "sco": "Scotland",
    "se": "Sweden",
    "tr": "Turkey",
    "us": "USA",
}
_TIMEZONES = {
    "Austria": "Europe/Vienna",
    "Belgium": "Europe/Brussels",
    "Brazil": "America/Sao_Paulo",
    "Switzerland": "Europe/Zurich",
    "Czech Republic": "Europe/Prague",
    "Germany": "Europe/Berlin",
    "Denmark": "Europe/Copenhagen",
    "England": "Europe/London",
    "Spain": "Europe/Madrid",
    "France": "Europe/Paris",
    "Greece": "Europe/Athens",
    "Ireland": "Europe/Dublin",
    "Italy": "Europe/Rome",
    "Japan": "Asia/Tokyo",
    "Mexico": "America/Mexico_City",
    "Netherlands": "Europe/Amsterdam",
    "Norway": "Europe/Oslo",
    "Poland": "Europe/Warsaw",
    "Portugal": "Europe/Lisbon",
    "Romania": "Europe/Bucharest",
    "Russia": "Europe/Moscow",
    "Scotland": "Europe/London",
    "Sweden": "Europe/Stockholm",
    "Turkey": "Europe/Istanbul",
    "USA": "America/New_York",
}


@dataclass(frozen=True, slots=True)
class OpenFootballCatalogEntry:
    provider: str
    source_revision: str
    season: str
    source_file: Path
    competition_name: str
    match_count: int
    completed_match_count: int


def update_mirror(mirror: Path, repository: str = REPOSITORY_URL) -> str:
    mirror.parent.mkdir(parents=True, exist_ok=True)
    if (mirror / ".git").exists():
        subprocess.run(
            ["git", "-C", str(mirror), "fetch", "--depth=1", "origin", "master"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(mirror), "checkout", "--detach", "FETCH_HEAD"],
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(
            ["git", "clone", "--depth=1", repository, str(mirror)],
            check=True,
            capture_output=True,
        )
    result = subprocess.run(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("OpenFootball mirror returned an invalid source revision")
    return revision


def discover_catalog(root: Path, source_revision: str) -> list[OpenFootballCatalogEntry]:
    catalog: list[OpenFootballCatalogEntry] = []
    if not root.is_dir():
        raise ValueError(f"OpenFootball mirror does not exist: {root}")
    for season_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if not _SEASON.fullmatch(season_dir.name):
            continue
        for source_file in sorted(season_dir.glob("*.json")):
            try:
                payload = json.loads(source_file.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
                continue
            matches = payload["matches"]
            completed = sum(_completed(match) for match in matches if isinstance(match, dict))
            catalog.append(
                OpenFootballCatalogEntry(
                    provider=PROVIDER_CODE,
                    source_revision=source_revision,
                    season=season_dir.name,
                    source_file=source_file,
                    competition_name=str(payload.get("name") or source_file.stem),
                    match_count=len(matches),
                    completed_match_count=completed,
                )
            )
    return catalog


def parse_competition(entry: OpenFootballCatalogEntry) -> list[HistoricalMatch]:
    payload = json.loads(entry.source_file.read_text(encoding="utf-8-sig"))
    competition_id = entry.source_file.stem
    country = _COUNTRIES.get(competition_id.split(".", 1)[0], "World")
    division = _division(competition_id)
    parsed: list[HistoricalMatch] = []
    for index, raw in enumerate(payload["matches"], start=1):
        if not isinstance(raw, dict):
            continue
        score = raw.get("score")
        full_time = score.get("ft") if isinstance(score, dict) else None
        if (
            not isinstance(full_time, list)
            or len(full_time) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in full_time
            )
        ):
            continue
        home = _team_name(raw.get("team1"))
        away = _team_name(raw.get("team2"))
        if not home or not away or home == away:
            continue
        kickoff, precision = _kickoff(raw, country)
        source_path = f"{entry.season}/{entry.source_file.name}"
        parsed.append(
            HistoricalMatch(
                provider_match_id=f"{source_path}#{index}",
                provider_competition_id=competition_id,
                competition_name=entry.competition_name,
                country=country,
                division=division,
                season=entry.season,
                home_team_id=home,
                home_team_name=home,
                away_team_id=away,
                away_team_name=away,
                kickoff_at=kickoff,
                kickoff_precision=precision,
                home_goals=full_time[0],
                away_goals=full_time[1],
                source_path=source_path,
            )
        )
    return parsed


def run_backfill(
    connection: Connection[Any],
    *,
    mirror: Path,
    data_root: Path,
    season: str | None = None,
    competition: str | None = None,
    country: str | None = None,
    update: bool = True,
) -> dict[str, object]:
    revision = update_mirror(mirror) if update else _local_revision(mirror)
    catalog = discover_catalog(mirror, revision)
    selected = [
        item
        for item in catalog
        if (season is None or item.season == season)
        and (competition is None or competition.casefold() in item.competition_name.casefold())
        and (
            country is None
            or _COUNTRIES.get(item.source_file.stem.split(".", 1)[0], "World").casefold()
            == country.casefold()
        )
    ]
    summary = BackfillSummary(
        provider=PROVIDER_CODE,
        source_revision=revision,
        resources_discovered=len(catalog),
        seasons=len({item.season for item in selected}),
        competitions=len({item.source_file.stem for item in selected}),
    )
    observed_at = datetime.now(UTC)
    store = HistoricalBackfillStore(connection, PROVIDER_CODE, "OpenFootball", PARSER_VERSION)
    snapshot = store.ensure_snapshot(
        source_identity=REPOSITORY_URL,
        source_revision=revision,
        acquired_at=observed_at,
        manifest_path=f"openfootball/{revision}/catalog.json",
        repository=REPOSITORY_URL,
        git_sha=revision,
    )
    for item in selected:
        payload = item.source_file.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        provider_path = f"{item.season}/{item.source_file.name}"
        cache_path = data_root / PROVIDER_CODE / revision / provider_path
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not cache_path.exists():
            cache_path.write_bytes(payload)
        if store.resource_already_imported(provider_path, digest):
            summary.resources_cached += 1
            continue
        store.record_resource(
            snapshot_id=snapshot,
            provider_path=provider_path,
            payload=payload,
            media_type="application/json",
            acquired_at=observed_at,
        )
        summary.resources_changed += 1
        matches = parse_competition(item)
        summary.matches_parsed += len(matches)
        for match in matches:
            result = store.import_match(match, snapshot, observed_at)
            _count_result(summary, result)
    summary.competition_mappings_created = store.competition_mappings_created
    summary.team_mappings_created = store.team_mappings_created
    connection.commit()
    return summary.to_dict()


def _kickoff(raw: dict[str, object], country: str) -> tuple[datetime, KickoffPrecision]:
    day = datetime.strptime(str(raw["date"]), "%Y-%m-%d")
    raw_time = raw.get("time")
    if isinstance(raw_time, str) and re.fullmatch(r"\d{1,2}:\d{2}", raw_time):
        hour, minute = (int(part) for part in raw_time.split(":"))
        local = day.replace(
            hour=hour,
            minute=minute,
            tzinfo=ZoneInfo(_TIMEZONES.get(country, "UTC")),
        )
        return local.astimezone(UTC), "EXACT"
    return date_only_timestamp(day.replace(tzinfo=UTC)), "DATE_ONLY"


def _team_name(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        candidate = value.get("name") or value.get("title")
        return candidate.strip() if isinstance(candidate, str) else ""
    return ""


def _completed(match: dict[str, object]) -> bool:
    score = match.get("score")
    full_time = score.get("ft") if isinstance(score, dict) else None
    return (
        isinstance(full_time, list)
        and len(full_time) == 2
        and all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in full_time
        )
    )


def _division(provider_competition_id: str) -> int | None:
    suffix = provider_competition_id.rsplit(".", 1)[-1]
    return int(suffix) if suffix.isdigit() and int(suffix) > 0 else None


def _local_revision(mirror: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _count_result(summary: BackfillSummary, result: str) -> None:
    if result == "inserted":
        summary.matches_inserted += 1
    elif result == "existing":
        summary.matches_existing += 1
    elif result == "conflict":
        summary.result_conflicts += 1
    else:
        summary.mapping_failures += 1
