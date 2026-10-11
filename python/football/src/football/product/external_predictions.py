"""Compliant append-only import for owner-supplied external predictions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from psycopg import Connection

from football.product.domain import map_external_market, normalize_team_name, sha256_json, stable_id


@dataclass(frozen=True, slots=True)
class ImportedPrediction:
    source_page: str
    prediction_date: date
    original_date_text: str
    competition: str
    home_team: str
    away_team: str
    market: str
    selection: str
    kickoff_at: datetime | None = None
    source_timezone: str | None = None
    provider_code: str | None = None
    provider_fixture_id: str | None = None


def parse_import(path: Path) -> tuple[ImportedPrediction, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("external prediction import must be a JSON array")
    return tuple(_parse_row(cast(Mapping[str, Any], row)) for row in payload)


def import_predictions(
    connection: Connection[Any],
    rows: Sequence[ImportedPrediction],
    *,
    source_code: str = "manual_import",
    collected_at: datetime | None = None,
) -> int:
    observed_at = collected_at or datetime.now(UTC)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("collected_at must include a timezone")
    count = 0
    for row in rows:
        fixture_id, match_status, provenance = _match_fixture(connection, row)
        revision_sha = prediction_revision_sha256(source_code, row)
        prediction_id = stable_id("external-prediction", revision_sha)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.external_predictions (
                    prediction_id, revision_sha256, source_code, source_page,
                    prediction_date, original_date_text, collected_at, fixture_id,
                    competition_text, home_team_text, away_team_text, market,
                    selection, match_status, source_kickoff_at, source_timezone,
                    provider_code, provider_fixture_id, mapping_provenance
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (revision_sha256) DO NOTHING
                """,
                (
                    prediction_id,
                    revision_sha,
                    source_code,
                    row.source_page,
                    row.prediction_date,
                    row.original_date_text,
                    observed_at,
                    fixture_id,
                    row.competition,
                    row.home_team,
                    row.away_team,
                    row.market,
                    row.selection,
                    match_status,
                    row.kickoff_at,
                    row.source_timezone,
                    row.provider_code,
                    row.provider_fixture_id,
                    json.dumps(provenance, sort_keys=True),
                ),
            )
            count += cursor.rowcount
    connection.commit()
    return count


def prediction_revision_sha256(source_code: str, row: ImportedPrediction) -> str:
    return sha256_json(
        {
            "source": source_code,
            "source_page": row.source_page,
            "prediction_date": row.prediction_date.isoformat(),
            "original_date_text": row.original_date_text,
            "competition": row.competition,
            "home_team": row.home_team,
            "away_team": row.away_team,
            "market": row.market,
            "selection": row.selection,
            "kickoff_at": row.kickoff_at.isoformat() if row.kickoff_at else None,
            "source_timezone": row.source_timezone,
            "provider_code": row.provider_code,
            "provider_fixture_id": row.provider_fixture_id,
        }
    )


def _parse_row(row: Mapping[str, Any]) -> ImportedPrediction:
    required = (
        "source_page",
        "prediction_date",
        "original_date_text",
        "competition",
        "home_team",
        "away_team",
        "selection",
    )
    if any(
        not isinstance(row.get(field), str) or not str(row[field]).strip() for field in required
    ):
        raise ValueError("external prediction import has missing text fields")
    normalized = map_external_market(str(row["selection"]))
    if normalized is None:
        raise ValueError(f"unsupported external selection: {row['selection']}")
    market, selection = normalized
    kickoff_at = _optional_kickoff(row.get("kickoff_at"))
    source_timezone = _optional_text(row.get("source_timezone"), "source_timezone")
    provider_code = _optional_text(row.get("provider_code"), "provider_code")
    provider_fixture_id = _optional_text(row.get("provider_fixture_id"), "provider_fixture_id")
    if (provider_code is None) != (provider_fixture_id is None):
        raise ValueError("provider_code and provider_fixture_id must be supplied together")
    return ImportedPrediction(
        source_page=str(row["source_page"]),
        prediction_date=date.fromisoformat(str(row["prediction_date"])),
        original_date_text=str(row["original_date_text"]),
        competition=str(row["competition"]),
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        market=market,
        selection=selection,
        kickoff_at=kickoff_at,
        source_timezone=source_timezone,
        provider_code=provider_code,
        provider_fixture_id=provider_fixture_id,
    )


def _match_fixture(
    connection: Connection[Any], row: ImportedPrediction
) -> tuple[object | None, str, dict[str, object]]:
    if row.provider_code and row.provider_fixture_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.match_id
                FROM football.match_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                JOIN football.product_fixtures fixture ON fixture.fixture_id = mapping.match_id
                WHERE provider.code = %s AND mapping.provider_match_id = %s
                  AND mapping.mapping_method IN ('explicit_crosswalk', 'manual', 'deterministic')
                  AND mapping.mapping_confidence = 1
                """,
                (row.provider_code, row.provider_fixture_id),
            )
            matches = cursor.fetchall()
        if len(matches) == 1:
            return (
                matches[0][0],
                "MATCHED",
                {
                    "method": "VERIFIED_PROVIDER_ID",
                    "provider_code": row.provider_code,
                    "provider_fixture_id": row.provider_fixture_id,
                },
            )
        if len(matches) > 1:
            return (
                None,
                "AMBIGUOUS",
                {
                    "method": "VERIFIED_PROVIDER_ID",
                    "candidate_count": len(matches),
                },
            )
    with connection.cursor() as cursor:
        if row.kickoff_at is not None:
            cursor.execute(
                """
                SELECT pf.fixture_id, home.name, away.name
                FROM football.product_fixtures pf
                JOIN football.product_teams home ON home.team_id = pf.home_team_id
                JOIN football.product_teams away ON away.team_id = pf.away_team_id
                JOIN football.product_competitions pc ON pc.competition_id = pf.competition_id
                WHERE pf.kickoff_at BETWEEN %s AND %s
                  AND lower(pc.name) = lower(%s)
                ORDER BY pf.kickoff_at, pf.fixture_id
                """,
                (
                    row.kickoff_at - timedelta(minutes=15),
                    row.kickoff_at + timedelta(minutes=15),
                    row.competition,
                ),
            )
            method = "KICKOFF_TEAM_COMPETITION_15_MINUTES"
        else:
            cursor.execute(
                """
            SELECT pf.fixture_id, home.name, away.name
            FROM football.product_fixtures pf
            JOIN football.product_teams home ON home.team_id = pf.home_team_id
            JOIN football.product_teams away ON away.team_id = pf.away_team_id
            JOIN football.product_competitions pc ON pc.competition_id = pf.competition_id
            WHERE pf.kickoff_at >= %s::date AND pf.kickoff_at < %s::date + interval '1 day'
              AND lower(pc.name) = lower(%s)
            ORDER BY pf.kickoff_at, pf.fixture_id
            """,
                (row.prediction_date, row.prediction_date, row.competition),
            )
            method = "DATE_TEAM_COMPETITION_LEGACY"
        candidates = cursor.fetchall()
    matching = [
        candidate
        for candidate in candidates
        if normalize_team_name(candidate[1]) == normalize_team_name(row.home_team)
        and normalize_team_name(candidate[2]) == normalize_team_name(row.away_team)
    ]
    if len(matching) == 1:
        return matching[0][0], "MATCHED", {"method": method, "candidate_count": 1}
    return (
        None,
        "AMBIGUOUS" if len(matching) > 1 else "UNMATCHED",
        {
            "method": method,
            "candidate_count": len(matching),
        },
    )


def _optional_kickoff(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("kickoff_at must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("kickoff_at must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("kickoff_at must include a timezone")
    return parsed.astimezone(UTC)


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def unique_fixture_id(
    candidates: Sequence[tuple[object, str, str]], row: ImportedPrediction
) -> object | None:
    matches = [
        fixture_id
        for fixture_id, home_name, away_name in candidates
        if normalize_team_name(home_name) == normalize_team_name(row.home_team)
        and normalize_team_name(away_name) == normalize_team_name(row.away_team)
    ]
    return matches[0] if len(matches) == 1 else None
