"""Read the fixture catalogue for EXTERNAL_PREDICTION_CONTEXTUAL_MATCHING_V1.

Only team, competition, kickoff and identity-resolution facts are read. Status and
scores are never selected, so the association cannot depend on the outcome.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from psycopg import Cursor

from football.product.external_match_context import country_key
from football.product.external_prediction_matching import (
    CandidateFixture,
    Decision,
    SourcePrediction,
    decide,
    search_window,
)

CANDIDATE_FIXTURES = """
WITH selected AS (
    SELECT fixture_id FROM football.product_fixtures
    WHERE kickoff_at>=%(start)s AND kickoff_at<%(end)s
    UNION SELECT canonical_fixture_id FROM football.product_provider_fixture_observations
    WHERE canonical_fixture_id IS NOT NULL AND kickoff_at>=%(start)s AND kickoff_at<%(end)s
), fixtures AS MATERIALIZED (
    SELECT f.* FROM selected JOIN football.product_fixtures f USING (fixture_id)
), aliases AS (
    SELECT team_id,array_agg(DISTINCT normalized_name ORDER BY normalized_name) AS names
    FROM football.product_team_aliases
    WHERE team_id IN (SELECT home_team_id FROM fixtures UNION SELECT away_team_id FROM fixtures)
    GROUP BY team_id
), earlier AS (
    SELECT o.canonical_fixture_id AS fixture_id,
        array_agg(DISTINCT o.kickoff_at ORDER BY o.kickoff_at) AS kickoffs
    FROM football.product_provider_fixture_observations o
    JOIN fixtures f ON f.fixture_id=o.canonical_fixture_id
    WHERE o.kickoff_at<>f.kickoff_at GROUP BY o.canonical_fixture_id
)
SELECT f.fixture_id,f.kickoff_at,f.identity_status,
    ARRAY[home.name]||coalesce(home_alias.names,'{}') AS home_names,
    ARRAY[away.name]||coalesce(away_alias.names,'{}') AS away_names,
    c.name AS competition_name,c.country,c.competition_type,c.division,
    r.resolution_status,
    CASE WHEN r.resolution_status='DUPLICATE_RESOLVED' THEN r.representative_fixture_id
         ELSE f.fixture_id END AS effective_fixture_id,
    coalesce(earlier.kickoffs,'{}') AS earlier_kickoffs
FROM fixtures f
JOIN football.product_teams home ON home.team_id=f.home_team_id
JOIN football.product_teams away ON away.team_id=f.away_team_id
JOIN football.product_competitions c ON c.competition_id=f.competition_id
LEFT JOIN aliases home_alias ON home_alias.team_id=f.home_team_id
LEFT JOIN aliases away_alias ON away_alias.team_id=f.away_team_id
LEFT JOIN earlier ON earlier.fixture_id=f.fixture_id
LEFT JOIN football.fixture_identity_resolutions r ON r.member_fixture_id=f.fixture_id AND r.active
ORDER BY f.kickoff_at,f.fixture_id
"""

SOURCE_FACTS = """
SELECT ep.prediction_id,ep.source_code,ep.prediction_date,ep.competition_text,
    ep.home_team_text,ep.away_team_text,identity.kickoff_at AS source_kickoff_at,
    identity.conflicting OR ep.match_status='AMBIGUOUS' AS conflicting_evidence
FROM football.external_predictions ep
JOIN football.external_prediction_fixture_identity identity USING (prediction_id)
"""


def load_countries(cursor: Cursor[dict[str, Any]]) -> frozenset[str]:
    rows = cursor.execute("SELECT DISTINCT country FROM football.product_competitions").fetchall()
    return frozenset(country_key(row["country"]) for row in rows)


def load_candidates(
    cursor: Cursor[dict[str, Any]], start: date, end: date
) -> list[CandidateFixture]:
    """Fixtures whose current or earlier observed kickoff falls in [start, end)."""
    bounds = {
        "start": datetime.combine(start, time.min, UTC),
        "end": datetime.combine(end, time.min, UTC),
    }
    return [_candidate(row) for row in cursor.execute(CANDIDATE_FIXTURES, bounds).fetchall()]


def source_facts(cursor: Cursor[dict[str, Any]], prediction_id: UUID) -> SourcePrediction:
    row = cursor.execute(SOURCE_FACTS + " WHERE ep.prediction_id=%s", (prediction_id,)).fetchone()
    if row is None:
        raise ValueError("external prediction not found")
    return source_prediction(row)


def source_prediction(row: dict[str, Any]) -> SourcePrediction:
    return SourcePrediction(
        source_code=row["source_code"],
        prediction_date=row["prediction_date"],
        competition=row["competition_text"],
        home_team=row["home_team_text"],
        away_team=row["away_team_text"],
        source_kickoff_at=row["source_kickoff_at"],
        conflicting_evidence=bool(row["conflicting_evidence"]),
    )


def contextual_decision(
    cursor: Cursor[dict[str, Any]], prediction_id: UUID
) -> tuple[SourcePrediction, Decision]:
    """Evaluate one prediction against the catalogue visible to this transaction."""
    source = source_facts(cursor, prediction_id)
    start, end = search_window(source.prediction_date)
    return source, decide(source, load_candidates(cursor, start, end), load_countries(cursor))


def _candidate(row: dict[str, Any]) -> CandidateFixture:
    return CandidateFixture(
        fixture_id=row["fixture_id"],
        kickoff_at=row["kickoff_at"],
        home_names=tuple(row["home_names"]),
        away_names=tuple(row["away_names"]),
        competition_name=row["competition_name"],
        competition_country=row["country"],
        competition_type=row["competition_type"],
        division=row["division"],
        identity_status=row["identity_status"],
        effective_fixture_id=row["effective_fixture_id"],
        resolution_status=row["resolution_status"],
        earlier_kickoffs=tuple(row["earlier_kickoffs"]),
    )
