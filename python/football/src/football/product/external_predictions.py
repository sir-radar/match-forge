"""Compliant append-only import for owner-supplied external predictions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
        fixture_id = _match_fixture(connection, row)
        revision_sha = prediction_revision_sha256(source_code, row)
        prediction_id = stable_id("external-prediction", revision_sha)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.external_predictions (
                    prediction_id, revision_sha256, source_code, source_page,
                    prediction_date, original_date_text, collected_at, fixture_id,
                    competition_text, home_team_text, away_team_text, market,
                    selection, match_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s)
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
                    "MATCHED" if fixture_id is not None else "UNMATCHED",
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
    return ImportedPrediction(
        source_page=str(row["source_page"]),
        prediction_date=date.fromisoformat(str(row["prediction_date"])),
        original_date_text=str(row["original_date_text"]),
        competition=str(row["competition"]),
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        market=market,
        selection=selection,
    )


def _match_fixture(connection: Connection[Any], row: ImportedPrediction) -> object | None:
    with connection.cursor() as cursor:
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
        candidates = cursor.fetchall()
    return unique_fixture_id(candidates, row)


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
