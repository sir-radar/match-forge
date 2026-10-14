"""Fill provisional display geography from verified retained provider bytes.

This current product metadata never establishes identity or history eligibility.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from psycopg import Connection

from football.product.api_football import continent_for_country
from football.product.domain import stable_id
from football.storage.raw import ImmutableFileStore

# Football country codes used in retained FotMob daily/league responses and the
# PitchAPI catalogue. Names follow the existing product country vocabulary.
# Unsupported codes stay unresolved; INT describes international competitions.
_COUNTRIES = {
    "ALB": "Albania",
    "ALG": "Algeria",
    "ARG": "Argentina",
    "ARM": "Armenia",
    "AUS": "Australia",
    "AUT": "Austria",
    "AZE": "Azerbaijan",
    "BAN": "Bangladesh",
    "BEL": "Belgium",
    "BIH": "Bosnia",
    "BLR": "Belarus",
    "BOL": "Bolivia",
    "BRA": "Brazil",
    "BUL": "Bulgaria",
    "CAN": "Canada",
    "CHI": "Chile",
    "CHN": "China",
    "COL": "Colombia",
    "CRC": "Costa-Rica",
    "CRO": "Croatia",
    "CYP": "Cyprus",
    "CZE": "Czech-Republic",
    "DEN": "Denmark",
    "ECU": "Ecuador",
    "EGY": "Egypt",
    "ENG": "England",
    "ESP": "Spain",
    "EST": "Estonia",
    "FIN": "Finland",
    "FRA": "France",
    "FRO": "Faroe-Islands",
    "GEO": "Georgia",
    "GER": "Germany",
    "GHA": "Ghana",
    "GRE": "Greece",
    "GUA": "Guatemala",
    "HON": "Honduras",
    "HUN": "Hungary",
    "IDN": "Indonesia",
    "IND": "India",
    "INT": "International",
    "INT-2": "International",
    "IRL": "Ireland",
    "IRN": "Iran",
    "IRQ": "Iraq",
    "ISL": "Iceland",
    "ISR": "Israel",
    "ITA": "Italy",
    "JPN": "Japan",
    "KAZ": "Kazakhstan",
    "KOR": "South-Korea",
    "KSA": "Saudi-Arabia",
    "KUW": "Kuwait",
    "LTU": "Lithuania",
    "LUX": "Luxembourg",
    "LVA": "Latvia",
    "MAR": "Morocco",
    "MDA": "Moldova",
    "MEX": "Mexico",
    "MKD": "Macedonia",
    "MNE": "Montenegro",
    "NED": "Netherlands",
    "NGA": "Nigeria",
    "NIR": "Northern-Ireland",
    "NOR": "Norway",
    "NZL": "New-Zealand",
    "PAN": "Panama",
    "PAR": "Paraguay",
    "PER": "Peru",
    "POL": "Poland",
    "POR": "Portugal",
    "QAT": "Qatar",
    "ROU": "Romania",
    "RSA": "South-Africa",
    "RUS": "Russia",
    "SCO": "Scotland",
    "SIN": "Singapore",
    "SLV": "El-Salvador",
    "SRB": "Serbia",
    "SUI": "Switzerland",
    "SVK": "Slovakia",
    "SVN": "Slovenia",
    "SWE": "Sweden",
    "TAN": "Tanzania",
    "THA": "Thailand",
    "TUN": "Tunisia",
    "TUR": "Turkey",
    "UAE": "United-Arab-Emirates",
    "UKR": "Ukraine",
    "URU": "Uruguay",
    "USA": "USA",
    "UZB": "Uzbekistan",
    "VEN": "Venezuela",
    "VIE": "Vietnam",
    "WAL": "Wales",
}


def country_name(code: Any) -> str | None:
    return _COUNTRIES.get(code.strip().upper()) if isinstance(code, str) else None


def geography_rows(provider: str, payload: Any) -> list[tuple[str, str]]:
    if not isinstance(payload, Mapping):
        return []
    if provider == "fotmob":
        details = payload.get("details")
        if isinstance(details, Mapping):
            return _league_rows([details], "country")
        return _league_rows(payload.get("leagues"), "ccode")
    if provider == "pitchapi":
        data = payload.get("data")
        return (
            _league_rows(data.get("leagues"), "country_code") if isinstance(data, Mapping) else []
        )
    raise ValueError("unsupported geography provider")


def _league_rows(values: Any, country_field: str) -> list[tuple[str, str]]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        identifier, code = value.get("id"), value.get(country_field)
        if type(identifier) not in (str, int) or not isinstance(code, str) or not code.strip():
            continue
        result.append((str(identifier), code.strip().upper()))
    return result


def _snapshot_geography(
    root: Path, provider: str, snapshot: tuple[Any, ...]
) -> list[tuple[str, str]]:
    _, relative, checksum, resource_checksum, size = snapshot
    if checksum != resource_checksum or not 0 < size <= 8_000_000:
        raise ValueError("geography snapshot registration is invalid")
    path = ImmutableFileStore(root).path_for(relative)
    if path.is_symlink():
        raise ValueError("geography snapshot must not be a symlink")
    with path.open("rb") as stream:
        raw = stream.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError("geography snapshot checksum or size mismatch")
    return geography_rows(provider, json.loads(raw))


def _retained_geography(
    connection: Connection[Any],
    data_root: Path,
    provider: str,
    evidence: dict[str, dict[str, set[str]]],
) -> list[str]:
    invalid = []
    snapshots = connection.execute(
        """SELECT s.id, s.manifest_path, s.manifest_sha256, r.sha256, r.size_bytes
           FROM football.source_snapshots s
           JOIN football.providers p ON p.id=s.provider_id
           JOIN football.source_resources r ON r.source_snapshot_id=s.id
             AND r.provider_path=s.source_identity
           WHERE p.code=%s AND s.status='validated' AND s.acquired_at <= statement_timestamp()
             AND r.parse_status='parsed' AND r.validation_status IN ('valid','warnings')
             AND (s.source_identity LIKE 'fixtures-%%' OR s.source_identity LIKE 'league-%%')
           ORDER BY s.acquired_at, s.id""",
        (provider,),
    ).fetchall()
    for snapshot in snapshots:
        try:
            rows = _snapshot_geography(data_root, provider, snapshot)
        except (OSError, ValueError):
            invalid.append(str(snapshot[0]))
            continue
        for identifier, code in rows:
            if identifier in evidence:
                evidence[identifier].setdefault(code, set()).add(str(snapshot[0]))
    return invalid


def _fill_country(
    connection: Connection[Any], competition: Any, country: str, codes: dict[str, set[str]]
) -> dict[str, Any] | None:
    continent = "World" if country == "International" else continent_for_country(country)
    updated = connection.execute(
        """UPDATE football.product_competitions SET country=%s, continent=%s,
                updated_at=GREATEST(updated_at, clock_timestamp())
           WHERE competition_id=%s AND metadata_status='PROVISIONAL'
             AND lower(country)='unknown' RETURNING competition_id""",
        (country, continent, competition),
    ).fetchone()
    if updated is None:
        return None
    return {
        "competition_id": str(competition),
        "country": country,
        "continent": continent,
        "source_snapshots": sorted({snapshot for ids in codes.values() for snapshot in ids}),
    }


def refresh_competition_geography(
    connection: Connection[Any], data_root: Path, provider: str
) -> dict[str, Any]:
    """Replay retained metadata without requests, identity admissions or forecasts."""
    if provider not in {"fotmob", "pitchapi"}:
        raise ValueError("unsupported geography provider")
    pending = connection.execute(
        """SELECT c.competition_id, m.provider_competition_id
           FROM football.product_competitions c
           JOIN football.competition_provider_mappings m ON m.competition_id=c.competition_id
           JOIN football.providers p ON p.id=m.provider_id
           WHERE p.code=%s AND m.valid_to IS NULL
             AND c.metadata_status='PROVISIONAL' AND lower(c.country)='unknown'
           ORDER BY c.competition_id""",
        (provider,),
    ).fetchall()
    pending = [
        row
        for row in pending
        if row[0] == stable_id("provider-scoped-competition", provider, row[1])
    ]
    evidence: dict[str, dict[str, set[str]]] = {row[1]: {} for row in pending}
    report: dict[str, Any] = {
        "updated": [],
        "unresolved": 0,
        "conflicting": [],
        "invalid_snapshots": [],
        "unsupported_codes": [],
    }
    if not pending:
        return report
    report["invalid_snapshots"] = _retained_geography(connection, data_root, provider, evidence)
    report["unsupported_codes"] = sorted(
        {code for codes in evidence.values() for code in codes if country_name(code) is None}
    )
    for competition, identifier in pending:
        codes = evidence[identifier]
        names = {country_name(code) for code in codes}
        if len(names) != 1 or None in names:
            report["unresolved"] += 1
            if len(names) > 1:
                report["conflicting"].append(identifier)
            continue
        country = names.pop()
        assert country is not None
        updated = _fill_country(connection, competition, country, codes)
        if updated is not None:
            report["updated"].append(updated)
    return report
