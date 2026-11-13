"""Recover exact retained R2Bet picks from separately acquired dated source pages."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection

from football.product.domain import sha256_json
from football.product.external_prediction_recovery import bind_reviewed_prediction
from football.product.external_prediction_sources import ParserBrokenError, parse_r2bet
from football.product.external_predictions import (
    ImportedPrediction,
    prediction_revision_sha256,
    verified_r2bet_mapping,
)


def _retained_r2bet_pages(connection: Connection[Any]) -> list[tuple[date, str]]:
    return connection.execute(
        """SELECT DISTINCT prediction_date, source_page
        FROM football.external_prediction_effective
        WHERE source_code='r2bet' AND effective_fixture_id IS NULL
          AND source_page='https://r2bet.com/index.php/best_football_prediction?dt='
              || to_char(prediction_date,'YYYY-MM-DD')
        ORDER BY prediction_date,source_page"""
    ).fetchall()


def _exact_archive_rows(
    day: date,
    page: str,
    raw: bytes,
) -> Iterable[tuple[str, ImportedPrediction]]:
    rows: dict[str, list[ImportedPrediction]] = defaultdict(list)
    for row in parse_r2bet(raw.decode("utf-8"), day, page):
        rows[prediction_revision_sha256("r2bet", row)].append(row)
    for digest, candidates in rows.items():
        if len(candidates) == 1:
            yield digest, candidates[0]


def recover_external_prediction_bindings(
    connection: Connection[Any],
    archive: Path,
    *,
    audit_only: bool,
) -> dict[str, Any]:
    """Process one already-retained dated page at a time with idempotent binding writes."""
    with connection.transaction():
        pages = _retained_r2bet_pages(connection)
    counts: Counter[str] = Counter()
    candidates: list[dict[str, str]] = []
    for day, page in pages:
        path = archive / f"r2bet-{day}.html"
        if not path.is_file():
            counts["PAGE_UNAVAILABLE"] += 1
            continue
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        try:
            rows = tuple(_exact_archive_rows(day, page, raw))
        except (UnicodeDecodeError, ParserBrokenError):
            counts["PAGE_INVALID"] += 1
            continue
        counts["PAGES_VERIFIED"] += 1
        with connection.transaction():
            recovered = _recover_page(connection, rows, checksum, audit_only=audit_only)
        counts.update(record["disposition"] for record in recovered)
        candidates.extend(recovered)
    return {"pages": len(pages), "counts": dict(counts), "predictions": candidates}


def _recover_page(
    connection: Connection[Any],
    rows: tuple[tuple[str, ImportedPrediction], ...],
    checksum: str,
    *,
    audit_only: bool,
) -> list[dict[str, str]]:
    recovered = []
    for digest, row in rows:
        # Pre-provider imports used the same source facts with a smaller digest.
        legacy = sha256_json(
            {
                "source": "r2bet",
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
        captures = connection.execute(
            """SELECT prediction_id FROM football.external_prediction_effective
            WHERE revision_sha256 IN (%s,%s) AND source_code='r2bet'
              AND effective_fixture_id IS NULL AND provider_code IS NULL
              AND source_kickoff_at IS NULL""",
            (digest, legacy),
        ).fetchall()
        if len(captures) != 1:
            continue
        prediction_id: UUID = captures[0][0]
        mapping = verified_r2bet_mapping(connection, row)
        disposition = "MAPPING_NOT_VERIFIED"
        if mapping is not None:
            disposition = "BINDING_ELIGIBLE"
            if not audit_only:
                reason = f"R2Bet exact archived revision {checksum} {row.fixture_reference_url}"
                if bind_reviewed_prediction(connection, prediction_id, mapping, reason=reason):
                    disposition = "BOUND"
        recovered.append(
            {
                "prediction_id": str(prediction_id),
                "mapping_id": str(mapping) if mapping else "",
                "disposition": disposition,
                "source_sha256": checksum,
            }
        )
    return recovered
