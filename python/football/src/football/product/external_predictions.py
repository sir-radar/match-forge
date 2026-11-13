"""Compliant append-only import for owner-supplied external predictions."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg import Connection

from football.product.domain import (
    map_external_market,
    normalize_team_name,
    sha256_json,
    stable_id,
)


def settle_external_predictions(connection: Connection[Any], settled_at: datetime) -> int:
    """Compatibility entry point for bounded, checkpointed settlement work."""
    from football.product.external_prediction_recovery import settle_pending_predictions

    return settle_pending_predictions(connection, settled_at)


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
    fixture_reference_url: str | None = None
    source_kickoff_text: str | None = None
    conflicting_fixture_references: tuple[str, ...] = ()


def r2bet_match_id(reference: str | None) -> str | None:
    if not reference:
        return None
    try:
        url = urlsplit(reference)
    except ValueError:
        return None
    if url.scheme != "https" or url.netloc.lower() not in {"r2bet.com", "www.r2bet.com"}:
        return None
    match = re.fullmatch(r"/index\.php/match-details/([1-9][0-9]*)-[^/]+/[^/]+/?", url.path)
    return match[1] if match else None


def verified_r2bet_mapping(connection: Connection[Any], row: ImportedPrediction) -> UUID | None:
    """Corroborate the R2Bet link ID with independent native context in PostgreSQL."""
    match_id = r2bet_match_id(row.fixture_reference_url)
    if match_id is None or row.source_kickoff_text is None or row.conflicting_fixture_references:
        return None
    candidates = connection.execute(
        """SELECT mapping.id,f.kickoff_at,home.name,away.name,competition.name
        FROM football.match_provider_mappings mapping
        JOIN football.providers p ON p.id=mapping.provider_id AND p.code='api_football'
        JOIN football.source_snapshots snap ON snap.id=mapping.source_snapshot_id
            AND snap.provider_id=p.id AND snap.status='validated'
        JOIN football.product_effective_fixtures f ON f.fixture_id=mapping.match_id
        JOIN football.product_teams home ON home.team_id=f.home_team_id
        JOIN football.product_teams away ON away.team_id=f.away_team_id
        JOIN football.product_competitions competition
            ON competition.competition_id=f.competition_id
        WHERE mapping.provider_match_id=%s AND mapping.mapping_confidence=1
          AND mapping.mapping_method IN ('explicit_crosswalk','manual','deterministic')
          AND mapping.first_seen_at<=statement_timestamp() AND f.identity_status='VERIFIED'
          AND (
              ((mapping.valid_from IS NULL OR mapping.valid_from<=f.kickoff_at)
               AND (mapping.valid_to IS NULL OR mapping.valid_to>f.kickoff_at))
              OR EXISTS (SELECT 1 FROM football.external_reviewed_fixture_mappings reviewed
                  WHERE reviewed.mapping_id=mapping.id)
          )
          AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions resolution
              WHERE resolution.member_fixture_id=f.fixture_id AND resolution.active
              AND (resolution.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                   OR resolution.representative_fixture_id<>f.fixture_id))
        """,
        (match_id,),
    ).fetchall()
    confirmed = [
        mapping
        for mapping, kickoff, home, away, competition in candidates
        if _r2bet_context_matches(row, kickoff, home, away, competition)
    ]
    return cast(UUID, confirmed[0]) if len(confirmed) == 1 else None


def _r2bet_context_matches(
    row: ImportedPrediction,
    kickoff: datetime,
    home: str,
    away: str,
    competition: str,
) -> bool:
    # The archived R2Bet page displays the local kickoff in UTC+01:00.
    local = kickoff.astimezone(ZoneInfo("Africa/Lagos"))
    label = normalize_team_name(row.competition)
    league = normalize_team_name(competition)
    return (
        local.date() == row.prediction_date
        and local.strftime("%H:%M") == row.source_kickoff_text
        and normalize_team_name(home) == normalize_team_name(row.home_team)
        and normalize_team_name(away) == normalize_team_name(row.away_team)
        and (label == league or label.split(" ", 1)[-1] == league)
    )


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
    from football.product.external_prediction_recovery import refresh_prediction_binding

    # Serialize exact source revisions even when one request has extra fixture metadata.
    # The same source-content order serializes overlapping import batches.
    revisions = sorted(
        ((prediction_content_sha256(source_code, row), row) for row in rows),
        key=lambda item: item[0],
    )
    count = 0
    for digest, row in revisions:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('external-pick:' || %s,0))",
            (digest,),
        )
        prediction_id, inserted = _retain_prediction(connection, source_code, row, observed_at)
        capture = connection.execute(
            """INSERT INTO football.external_prediction_captures(prediction_id,observed_at)
            VALUES(%s,%s) ON CONFLICT(prediction_id,observed_at) DO NOTHING""",
            (prediction_id, observed_at),
        )
        enriched = record_fixture_evidence(connection, prediction_id, source_code, row, observed_at)
        if inserted or capture.rowcount or enriched:
            refresh_prediction_binding(connection, prediction_id)
        count += inserted
    connection.commit()
    return count


def _retain_prediction(
    connection: Connection[Any], source_code: str, row: ImportedPrediction, observed_at: datetime
) -> tuple[UUID, int]:
    revision = prediction_revision_sha256(source_code, row)
    retained = connection.execute(
        """SELECT prediction_id,revision_sha256=%s AS exact
        FROM football.external_predictions
        WHERE source_code=%s AND prediction_date=%s AND source_page=%s AND original_date_text=%s
          AND competition_text=%s AND home_team_text=%s AND away_team_text=%s
          AND market=%s AND selection=%s
        ORDER BY exact DESC LIMIT 2""",
        (
            revision,
            source_code,
            row.prediction_date,
            row.source_page,
            row.original_date_text,
            row.competition,
            row.home_team,
            row.away_team,
            row.market,
            row.selection,
        ),
    ).fetchall()
    if retained and (len(retained) == 1 or retained[0][1]):
        return cast(UUID, retained[0][0]), 0

    fixture, status, provenance = _match_fixture(connection, row)
    prediction_id = stable_id("external-prediction", revision)
    cursor = connection.execute(
        """INSERT INTO football.external_predictions (
            prediction_id,revision_sha256,source_code,source_page,prediction_date,original_date_text,
            collected_at,fixture_id,competition_text,home_team_text,away_team_text,market,selection,
            match_status,source_kickoff_at,source_timezone,provider_code,provider_fixture_id,
            mapping_provenance
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (revision_sha256) DO NOTHING""",
        (
            prediction_id,
            revision,
            source_code,
            row.source_page,
            row.prediction_date,
            row.original_date_text,
            observed_at,
            fixture,
            row.competition,
            row.home_team,
            row.away_team,
            row.market,
            row.selection,
            status,
            row.kickoff_at,
            row.source_timezone,
            row.provider_code,
            row.provider_fixture_id,
            json.dumps(provenance, sort_keys=True),
        ),
    )
    return prediction_id, cursor.rowcount


def record_fixture_evidence(
    connection: Connection[Any],
    prediction_id: UUID,
    source_code: str,
    row: ImportedPrediction,
    observed_at: datetime,
    *,
    archive_sha256: str | None = None,
) -> bool:
    """Retain new fixture facts independently of the immutable pick revision."""
    if not any(
        (
            row.provider_code,
            row.fixture_reference_url,
            row.source_kickoff_text,
            row.kickoff_at,
            row.conflicting_fixture_references,
        )
    ):
        return False
    native_id = r2bet_match_id(row.fixture_reference_url) if source_code == "r2bet" else None
    evidence = {
        "provider_code": row.provider_code,
        "provider_fixture_id": row.provider_fixture_id,
        "r2bet_match_id": native_id,
        "fixture_reference_url": row.fixture_reference_url,
        "source_kickoff_text": row.source_kickoff_text,
        "source_kickoff_at": row.kickoff_at.isoformat() if row.kickoff_at else None,
        "conflicting_references": sorted(row.conflicting_fixture_references),
        "archive_sha256": archive_sha256,
    }
    cursor = connection.execute(
        """INSERT INTO football.external_prediction_fixture_evidence (
            prediction_id,evidence_sha256,observed_at,provider_code,provider_fixture_id,
            r2bet_match_id,fixture_reference_url,source_kickoff_text,source_kickoff_at,
            conflicting_references,archive_sha256
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
        (
            prediction_id,
            sha256_json(evidence),
            observed_at,
            row.provider_code,
            row.provider_fixture_id,
            native_id,
            row.fixture_reference_url,
            row.source_kickoff_text,
            row.kickoff_at,
            evidence["conflicting_references"],
            archive_sha256,
        ),
    )
    return cursor.rowcount == 1


def prediction_content_sha256(source_code: str, row: ImportedPrediction) -> str:
    return sha256_json(_prediction_content(source_code, row))


def _prediction_content(source_code: str, row: ImportedPrediction) -> dict[str, str]:
    return {
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


def prediction_revision_sha256(source_code: str, row: ImportedPrediction) -> str:
    return sha256_json(
        {
            **_prediction_content(source_code, row),
            "kickoff_at": row.kickoff_at.isoformat() if row.kickoff_at else None,
            "source_timezone": row.source_timezone,
            "provider_code": row.provider_code,
            "provider_fixture_id": row.provider_fixture_id,
        }
    )


def provider_fixture_reference(value: str) -> tuple[str, str] | None:
    """Read only recognized provider-native URLs. Never fetch a supplied URL."""
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme != "https" or url.username is not None or url.password is not None:
        return None
    patterns = {
        "api.pitchapi.dev": ("pitchapi", r"/v1/matches/(m_[A-Za-z0-9]+)"),
        "api.football-data.org": ("football_data_org", r"/v4/matches/([1-9][0-9]*)"),
        "www.fotmob.com": ("fotmob", r"/matches/[^/]+/[A-Za-z0-9]+/?"),
        "fotmob.com": ("fotmob", r"/matches/[^/]+/[A-Za-z0-9]+/?"),
    }
    if url.netloc.lower() not in patterns:
        return None
    provider, pattern = patterns[url.netloc.lower()]
    path = re.fullmatch(pattern, url.path)
    if path is None:
        return None
    if provider == "fotmob":
        return (provider, url.fragment) if re.fullmatch(r"[1-9][0-9]*", url.fragment) else None
    return provider, path[1]


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
    reference = _optional_text(row.get("fixture_reference_url"), "fixture_reference_url")
    if (provider_code is None) != (provider_fixture_id is None):
        raise ValueError("provider_code and provider_fixture_id must be supplied together")
    native = provider_fixture_reference(reference) if reference else None
    if native and provider_code is not None and native != (provider_code, provider_fixture_id):
        raise ValueError("provider fixture URL conflicts with supplied native identity")
    if native:
        provider_code, provider_fixture_id = native
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
        fixture_reference_url=reference,
        source_kickoff_text=_optional_text(row.get("source_kickoff_text"), "source_kickoff_text"),
    )


def _match_fixture(
    connection: Connection[Any], row: ImportedPrediction
) -> tuple[object | None, str, dict[str, object]]:
    if row.conflicting_fixture_references:
        return None, "AMBIGUOUS", {"method": "CONFLICTING_NATIVE_REFERENCES"}
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
                  AND fixture.identity_status = 'VERIFIED'
                  AND (mapping.valid_from IS NULL OR mapping.valid_from <= fixture.kickoff_at)
                  AND (mapping.valid_to IS NULL OR mapping.valid_to > fixture.kickoff_at)
                  AND mapping.first_seen_at <= statement_timestamp()
                  AND (%s::timestamptz IS NULL OR fixture.kickoff_at=%s)
                  AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions resolution
                      WHERE resolution.member_fixture_id=fixture.fixture_id AND resolution.active
                      AND (resolution.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                           OR resolution.representative_fixture_id<>fixture.fixture_id))
                """,
                (row.provider_code, row.provider_fixture_id, row.kickoff_at, row.kickoff_at),
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
        return (
            None,
            "UNMATCHED",
            {
                "method": "VERIFIED_PROVIDER_ID",
                "candidate_count": 0,
                "reason": "no independently verified native fixture mapping",
            },
        )
    return None, "UNMATCHED", {"method": "INDEPENDENT_FIXTURE_REFERENCE_REQUIRED"}


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
