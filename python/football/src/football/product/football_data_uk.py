"""Bulk Football-Data.co.uk catalog discovery, CSV/ZIP parsing, and import."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import stat
import urllib.parse
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from math import isfinite
from pathlib import Path, PurePosixPath
from time import monotonic
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
from football.product.historical_manifest import publish_manifest
from football.product.identity_admission import admit_provider_mappings
from football.providers.base import UrllibHttpTransport, read_bounded
from football.storage.transactions import require_idle_connection

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
    if max_pages <= 0:
        raise ValueError("catalogue page budget must be positive")
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
    if any(page not in visited for page in pending):
        raise ValueError("catalogue page budget exhausted before discovery completed")
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


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    compressed_bytes: int = 2 * 1024 * 1024
    extracted_bytes: int = 16 * 1024 * 1024
    entries: int = 128
    file_bytes: int = 1024 * 1024
    ratio: float = 32
    extraction_seconds: float = 5

    def __post_init__(self) -> None:
        sizes = (self.compressed_bytes, self.extracted_bytes, self.entries, self.file_bytes)
        if any(not isinstance(value, int) or value <= 0 for value in sizes):
            raise ValueError("archive size/count limits must be positive integers")
        if any(
            not isfinite(value) or value <= 0 for value in (self.ratio, self.extraction_seconds)
        ):
            raise ValueError("archive ratio/duration limits must be positive and finite")

    @classmethod
    def from_env(cls) -> ArchiveLimits:
        return cls(
            compressed_bytes=int(os.getenv("MATCHFORGE_ARCHIVE_COMPRESSED_BYTES", "2097152")),
            extracted_bytes=int(os.getenv("MATCHFORGE_ARCHIVE_EXTRACTED_BYTES", "16777216")),
            entries=int(os.getenv("MATCHFORGE_ARCHIVE_ENTRIES", "128")),
            file_bytes=int(os.getenv("MATCHFORGE_ARCHIVE_FILE_BYTES", "1048576")),
            ratio=float(os.getenv("MATCHFORGE_ARCHIVE_RATIO", "32")),
            extraction_seconds=float(os.getenv("MATCHFORGE_ARCHIVE_EXTRACTION_SECONDS", "5")),
        )


def _check_archive_member(member: zipfile.ZipInfo, limits: ArchiveLimits) -> None:
    name = member.orig_filename
    path = PurePosixPath(name.replace("\\", "/"))
    if "\x00" in name or path.is_absolute() or ".." in path.parts or ":" in name:
        raise ValueError("unsafe archive member path")
    mode = stat.S_IFMT(member.external_attr >> 16)
    if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise ValueError("unsafe archive member link/type")
    if member.flag_bits & 1 or member.compress_type not in (
        zipfile.ZIP_STORED,
        zipfile.ZIP_DEFLATED,
    ):
        raise ValueError("unsupported encrypted/compressed archive member")
    if member.file_size > limits.file_bytes:
        raise ValueError("archive member size limit exceeded")
    if member.file_size > limits.ratio * member.compress_size:
        raise ValueError("archive decompression ratio limit exceeded")


def _check_archive(archive: zipfile.ZipFile, payload_size: int, limits: ArchiveLimits) -> None:
    members = archive.infolist()
    if len(members) > limits.entries:
        raise ValueError("archive entry limit exceeded")
    names = [member.filename.casefold() for member in members]
    if len(set(names)) != len(names):
        raise ValueError("duplicate archive member path")
    total = sum(member.file_size for member in members)
    if total > limits.extracted_bytes or total > limits.ratio * payload_size:
        raise ValueError("archive total expansion limit exceeded")
    for member in members:
        _check_archive_member(member, limits)


def csv_members(
    payload: bytes, *, limits: ArchiveLimits | None = None
) -> Iterable[tuple[str, bytes]]:
    bounds = limits or ArchiveLimits.from_env()
    if len(payload) > bounds.compressed_bytes:
        raise ValueError("archive compressed size limit exceeded")
    deadline = monotonic() + bounds.extraction_seconds
    members: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        _check_archive(archive, len(payload), bounds)
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ValueError("archive extraction deadline exceeded")
            if member.filename.casefold().endswith(".csv") and not member.is_dir():
                with archive.open(member) as resource:
                    decoded = read_bounded(
                        resource, max_bytes=bounds.file_bytes, timeout_seconds=remaining
                    )
                members.append((member.filename, decoded))
        if monotonic() >= deadline:
            raise ValueError("archive extraction deadline exceeded")
    return members


def _parse_download(
    resource: FootballDataResource, provider_path: str, payload: bytes
) -> tuple[list[HistoricalMatch], int]:
    """Finish CSV/archive parsing before registering a successfully parsed resource."""
    sources = (
        list(csv_members(payload)) if resource.archive else [(Path(provider_path).name, payload)]
    )
    matches = []
    for member_name, csv_payload in sources:
        matches.extend(
            parse_csv_resource(
                csv_payload,
                source_path=f"{provider_path}!{member_name}" if resource.archive else provider_path,
                season=resource.season,
                country_hint=resource.country,
                division_hint=resource.division,
            )
        )
    return matches, len(sources)


def run_backfill(
    connection: Connection[Any],
    *,
    data_root: Path,
    season: str | None = None,
    competition: str | None = None,
    country: str | None = None,
    index_url: str = INDEX_URL,
) -> dict[str, object]:
    require_idle_connection(connection, "Football-Data.co.uk backfill")
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
        connection,
        PROVIDER_CODE,
        "Football-Data.co.uk",
        PARSER_VERSION,
        data_root=data_root,
    )
    parsed_competitions: set[str] = set()
    parsed_seasons: set[str] = set()
    for resource in selected:
        provider_path = urllib.parse.urlparse(resource.url).path.lstrip("/")
        if _is_closed_season(resource.season, observed_at) and store.resource_path_already_imported(
            provider_path
        ):
            summary.resources_cached += 1
            connection.commit()
            continue
        connection.commit()
        payload = _download(resource.url)
        observed_at = datetime.now(UTC)
        digest = hashlib.sha256(payload).hexdigest()
        extension = ".zip" if resource.archive else ".csv"
        cache_path = (
            data_root / PROVIDER_CODE / (resource.season or "unknown") / f"{digest}{extension}"
        )
        manifest_path = publish_manifest(
            data_root,
            provider=PROVIDER_CODE,
            source_identity=resource.url,
            source_revision=digest,
            acquired_at=observed_at,
            resources=[(provider_path, str(cache_path.relative_to(data_root)), payload)],
        )
        matches, csv_files = _parse_download(resource, provider_path, payload)
        snapshot = store.ensure_snapshot(
            source_identity=resource.url,
            source_revision=digest,
            acquired_at=observed_at,
            manifest_path=manifest_path,
        )
        if store.resource_already_imported(provider_path, digest):
            summary.resources_cached += 1
            connection.commit()
            continue
        resource_id = store.record_resource(
            snapshot_id=snapshot,
            provider_path=provider_path,
            payload=payload,
            media_type="application/zip" if resource.archive else "text/csv",
            acquired_at=observed_at,
            import_pending=True,
        )
        connection.commit()
        summary.resources_changed += 1
        summary.zip_files += int(resource.archive)
        summary.csv_files += csv_files
        summary.matches_parsed += len(matches)
        for match in matches:
            parsed_competitions.add(match.provider_competition_id)
            parsed_seasons.add(match.season)
            result = store.import_match(match, snapshot, observed_at)
            _count_result(summary, result)
            connection.commit()
        store.complete_resource_import(resource_id)
        connection.commit()
    summary.competitions = len(parsed_competitions)
    summary.seasons = len(parsed_seasons)
    summary.competition_mappings_created = store.competition_mappings_created
    summary.team_mappings_created = store.team_mappings_created
    admit_provider_mappings(connection, data_root, PROVIDER_CODE, commit_each=True)
    connection.commit()
    return summary.to_dict()


def _download(url: str) -> bytes:
    return UrllibHttpTransport(user_agent="MatchForge/1.0 historical-backfill").get(
        url, timeout_seconds=60, max_bytes=8 * 1024 * 1024
    )


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
