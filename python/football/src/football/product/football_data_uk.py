"""Bulk Football-Data.co.uk catalog discovery, CSV/ZIP parsing, and import."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
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

PROVIDER_CODE = "football_data_uk"
INDEX_URL = "https://www.football-data.co.uk/downloadm.php"
PARSER_VERSION = "football-data-uk-product-v1"

# Stable provider codes are mapping metadata, not the discovery catalog.
_DIVISIONS: dict[str, tuple[str, str, int | None]] = {
    "E0": ("Premier League", "England", 1),
    "E1": ("Championship", "England", 2),
    "E2": ("League One", "England", 3),
    "E3": ("League Two", "England", 4),
    "EC": ("National League", "England", 5),
    "SC0": ("Premiership", "Scotland", 1),
    "D1": ("Bundesliga", "Germany", 1),
    "D2": ("2. Bundesliga", "Germany", 2),
    "SP1": ("LaLiga", "Spain", 1),
    "SP2": ("Segunda Division", "Spain", 2),
    "I1": ("Serie A", "Italy", 1),
    "I2": ("Serie B", "Italy", 2),
    "F1": ("Ligue 1", "France", 1),
    "F2": ("Ligue 2", "France", 2),
    "N1": ("Eredivisie", "Netherlands", 1),
    "P1": ("Primeira Liga", "Portugal", 1),
    "B1": ("First Division A", "Belgium", 1),
    "T1": ("Super Lig", "Turkey", 1),
    "G1": ("Super League", "Greece", 1),
}
_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y")
_TIMEZONES = {
    "Argentina": "America/Argentina/Buenos_Aires",
    "Austria": "Europe/Vienna",
    "Belgium": "Europe/Brussels",
    "Brazil": "America/Sao_Paulo",
    "China": "Asia/Shanghai",
    "Denmark": "Europe/Copenhagen",
    "England": "Europe/London",
    "Finland": "Europe/Helsinki",
    "France": "Europe/Paris",
    "Germany": "Europe/Berlin",
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
    "Scotland": "Europe/London",
    "Spain": "Europe/Madrid",
    "Sweden": "Europe/Stockholm",
    "Switzerland": "Europe/Zurich",
    "Turkey": "Europe/Istanbul",
    "USA": "America/New_York",
}


@dataclass(frozen=True, slots=True)
class FootballDataResource:
    url: str
    season: str | None
    country: str | None
    division: str | None
    archive: bool


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def discover_resources(html: bytes | str, base_url: str = INDEX_URL) -> list[FootballDataResource]:
    parser = _LinkParser()
    parser.feed(html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html)
    resources: dict[str, FootballDataResource] = {}
    for link in parser.links:
        url = urllib.parse.urljoin(base_url, link)
        parsed = urllib.parse.urlparse(url)
        lower_path = parsed.path.casefold()
        if not lower_path.endswith((".csv", ".zip")):
            continue
        parts = [part for part in parsed.path.split("/") if part]
        season = next((part for part in parts if re.fullmatch(r"\d{4}", part)), None)
        filename = Path(parsed.path).name
        division = Path(filename).stem.upper() if lower_path.endswith(".csv") else None
        resources[url] = FootballDataResource(
            url=url,
            season=_season_label(season),
            country=_country_from_path(parts),
            division=division,
            archive=lower_path.endswith(".zip"),
        )
    return sorted(resources.values(), key=lambda item: item.url)


def discover_catalog(
    index_url: str = INDEX_URL, max_pages: int = 100
) -> list[FootballDataResource]:
    origin = urllib.parse.urlparse(index_url).netloc
    pending = [index_url]
    visited: set[str] = set()
    resources: dict[str, FootballDataResource] = {}
    while pending and len(visited) < max_pages:
        page = pending.pop(0)
        if page in visited:
            continue
        visited.add(page)
        payload = _download(page)
        for resource in discover_resources(payload, page):
            resources[resource.url] = resource
        parser = _LinkParser()
        parser.feed(payload.decode("utf-8", errors="replace"))
        for link in parser.links:
            candidate = urllib.parse.urljoin(page, link)
            parsed = urllib.parse.urlparse(candidate)
            if parsed.netloc != origin or candidate in visited:
                continue
            discovery_target = f"{parsed.path}?{parsed.query}"
            if parsed.path.casefold().endswith((".php", ".html", ".htm")) and re.search(
                r"data|download|result|league|argentina|brazil|china|japan|usa|world",
                discovery_target,
                re.IGNORECASE,
            ):
                pending.append(candidate)
    return sorted(resources.values(), key=lambda item: item.url)


def parse_csv_resource(
    payload: bytes,
    *,
    source_path: str,
    season: str | None,
    country_hint: str | None = None,
    division_hint: str | None = None,
) -> list[HistoricalMatch]:
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        text = payload.decode("cp1252", errors="strict")
    reader = csv.DictReader(io.StringIO(text))
    parsed: list[HistoricalMatch] = []
    for index, row in enumerate(reader, start=2):
        division = (row.get("Div") or division_hint or "").strip().upper()
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        home_goals = _score(row.get("FTHG"))
        away_goals = _score(row.get("FTAG"))
        if not division or not home or not away or home == away:
            continue
        if home_goals is None or away_goals is None:
            continue
        raw_date = (row.get("Date") or "").strip()
        try:
            day = _parse_date(raw_date)
        except ValueError:
            continue
        competition_name, mapped_country, numeric_division = _DIVISIONS.get(
            division, (division, country_hint or "World", _division_number(division))
        )
        country = country_hint or mapped_country
        raw_time = (row.get("Time") or "").strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", raw_time):
            hour, minute = (int(value) for value in raw_time.split(":"))
            timezone = ZoneInfo(_TIMEZONES.get(country, "UTC"))
            kickoff = day.replace(hour=hour, minute=minute, tzinfo=timezone).astimezone(UTC)
            precision: KickoffPrecision = "EXACT"
        else:
            kickoff = date_only_timestamp(day.replace(tzinfo=UTC))
            precision = "DATE_ONLY"
        inferred_season = season or _season_from_date(day)
        parsed.append(
            HistoricalMatch(
                provider_match_id=f"{source_path}#{index}",
                provider_competition_id=division,
                competition_name=competition_name,
                country=country,
                division=numeric_division,
                season=inferred_season,
                home_team_id=home,
                home_team_name=home,
                away_team_id=away,
                away_team_name=away,
                kickoff_at=kickoff,
                kickoff_precision=precision,
                home_goals=home_goals,
                away_goals=away_goals,
                source_path=source_path,
            )
        )
    return parsed


def csv_members(payload: bytes) -> Iterable[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in sorted(archive.namelist()):
            if name.casefold().endswith(".csv") and not name.endswith("/"):
                yield name, archive.read(name)


def run_backfill(
    connection: Connection[Any],
    *,
    data_root: Path,
    season: str | None = None,
    competition: str | None = None,
    country: str | None = None,
    index_url: str = INDEX_URL,
) -> dict[str, object]:
    catalog = discover_catalog(index_url)
    selected = [
        resource
        for resource in catalog
        if (season is None or resource.season == season)
        and (
            competition is None
            or (
                resource.division is not None
                and resource.division.casefold() == competition.casefold()
            )
        )
        and (country is None or (resource.country or "").casefold() == country.casefold())
    ]
    summary = BackfillSummary(
        provider=PROVIDER_CODE,
        resources_discovered=len(catalog),
        seasons=len({resource.season for resource in selected if resource.season}),
        competitions=len({resource.division for resource in selected if resource.division}),
    )
    observed_at = datetime.now(UTC)
    store = HistoricalBackfillStore(
        connection, PROVIDER_CODE, "Football-Data.co.uk", PARSER_VERSION
    )
    parsed_competitions: set[str] = set()
    parsed_seasons: set[str] = set()
    for resource in selected:
        provider_path = urllib.parse.urlparse(resource.url).path.lstrip("/")
        if _is_closed_season(resource.season, observed_at) and store.resource_path_already_imported(
            provider_path
        ):
            summary.resources_cached += 1
            continue
        payload = _download(resource.url)
        digest = hashlib.sha256(payload).hexdigest()
        extension = ".zip" if resource.archive else ".csv"
        cache_path = (
            data_root / PROVIDER_CODE / (resource.season or "unknown") / f"{digest}{extension}"
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not cache_path.exists():
            cache_path.write_bytes(payload)
        snapshot = store.ensure_snapshot(
            source_identity=resource.url,
            source_revision=digest,
            acquired_at=observed_at,
            manifest_path=str(cache_path.relative_to(data_root)),
        )
        if store.resource_already_imported(provider_path, digest):
            summary.resources_cached += 1
            continue
        store.record_resource(
            snapshot_id=snapshot,
            provider_path=provider_path,
            payload=payload,
            media_type="application/zip" if resource.archive else "text/csv",
            acquired_at=observed_at,
        )
        summary.resources_changed += 1
        if resource.archive:
            summary.zip_files += 1
            sources = list(csv_members(payload))
        else:
            sources = [(Path(provider_path).name, payload)]
        summary.csv_files += len(sources)
        for member_name, csv_payload in sources:
            matches = parse_csv_resource(
                csv_payload,
                source_path=f"{provider_path}!{member_name}" if resource.archive else provider_path,
                season=resource.season,
                country_hint=resource.country,
                division_hint=resource.division,
            )
            summary.matches_parsed += len(matches)
            for match in matches:
                parsed_competitions.add(match.provider_competition_id)
                parsed_seasons.add(match.season)
                result = store.import_match(match, snapshot, observed_at)
                _count_result(summary, result)
    summary.competitions = len(parsed_competitions)
    summary.seasons = len(parsed_seasons)
    summary.competition_mappings_created = store.competition_mappings_created
    summary.team_mappings_created = store.team_mappings_created
    connection.commit()
    return summary.to_dict()


def _download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MatchForge/1.0 historical-backfill"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def _parse_date(value: str) -> datetime:
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    raise ValueError(f"unsupported Football-Data.co.uk date: {value!r}")


def _score(value: str | None) -> int | None:
    if value is None or not re.fullmatch(r"\d+", value.strip()):
        return None
    return int(value)


def _season_label(value: str | None) -> str | None:
    if value is None:
        return None
    start = int(value[:2])
    end = int(value[2:])
    century = 1900 if start >= 70 else 2000
    return f"{century + start}-{(century if end >= start else century + 100) + end}"


def _season_from_date(value: datetime) -> str:
    start = value.year if value.month >= 7 else value.year - 1
    return f"{start}-{start + 1}"


def _is_closed_season(season: str | None, observed_at: datetime) -> bool:
    if season is None:
        return False
    current_start = observed_at.year if observed_at.month >= 7 else observed_at.year - 1
    return season != f"{current_start}-{current_start + 1}"


def _country_from_path(parts: list[str]) -> str | None:
    joined = " ".join(parts).casefold()
    names = {
        "argentina": "Argentina",
        "austria": "Austria",
        "brazil": "Brazil",
        "china": "China",
        "denmark": "Denmark",
        "finland": "Finland",
        "ireland": "Ireland",
        "japan": "Japan",
        "mexico": "Mexico",
        "norway": "Norway",
        "poland": "Poland",
        "romania": "Romania",
        "sweden": "Sweden",
        "switzerland": "Switzerland",
        "usa": "USA",
    }
    return next((country for key, country in names.items() if key in joined), None)


def _division_number(code: str) -> int | None:
    match = re.search(r"(\d+)$", code)
    return int(match.group(1)) if match else None


def _count_result(summary: BackfillSummary, result: str) -> None:
    if result == "inserted":
        summary.matches_inserted += 1
    elif result == "existing":
        summary.matches_existing += 1
    elif result == "conflict":
        summary.result_conflicts += 1
    elif result == "identity_conflict":
        summary.identity_conflicts += 1
    else:
        summary.mapping_failures += 1
