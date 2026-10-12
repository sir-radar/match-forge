"""Fixture-level reasons why stored history is not usable for forecasting."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from football.product.domain import MINIMUM_HISTORY_MATCHES


def history_coverage(
    connection: Connection[Any], cutoff: datetime | None = None
) -> dict[str, object]:
    cutoff = cutoff or datetime.now(UTC)
    with connection.cursor(row_factory=dict_row) as cursor:
        fixtures = cursor.execute(
            """SELECT fixture.fixture_id::text, home.name AS home_team, away.name AS away_team,
                      fixture.kickoff_at, fixture.identity_status, fixture.forecast_availability,
                      competition.name AS competition, competition.metadata_status,
                      counts.home_history, counts.away_history,
                      counts.home_raw, counts.away_raw
               FROM football.product_fixtures fixture
               JOIN football.product_teams home ON home.team_id = fixture.home_team_id
               JOIN football.product_teams away ON away.team_id = fixture.away_team_id
               JOIN football.product_competitions competition
                 ON competition.competition_id = fixture.competition_id
               CROSS JOIN LATERAL (
                   SELECT count(*) FILTER (WHERE history.home_team_id = fixture.home_team_id
                           OR history.away_team_id = fixture.home_team_id) AS home_raw,
                          count(*) FILTER (WHERE history.home_team_id = fixture.away_team_id
                           OR history.away_team_id = fixture.away_team_id) AS away_raw,
                          count(*) FILTER (WHERE eligible.fixture_id IS NOT NULL
                           AND eligible.known_at <= %(cutoff)s AND
                           (history.home_team_id = fixture.home_team_id
                            OR history.away_team_id = fixture.home_team_id)) AS home_history,
                          count(*) FILTER (WHERE eligible.fixture_id IS NOT NULL
                           AND eligible.known_at <= %(cutoff)s AND
                           (history.home_team_id = fixture.away_team_id
                            OR history.away_team_id = fixture.away_team_id)) AS away_history
                   FROM football.product_team_match_history history
                   LEFT JOIN football.product_eligible_match_history eligible
                     ON eligible.fixture_id = history.fixture_id
                   WHERE (history.home_team_id IN (fixture.home_team_id, fixture.away_team_id)
                          OR history.away_team_id IN (fixture.home_team_id, fixture.away_team_id))
                     AND ((history.source_kickoff_precision = 'EXACT'
                           AND history.kickoff_at < fixture.kickoff_at)
                          OR (history.source_kickoff_precision = 'DATE_ONLY'
                              AND history.kickoff_at::date < fixture.kickoff_at::date))
               ) counts
               WHERE fixture.status = 'SCHEDULED' AND fixture.kickoff_at > %(cutoff)s
               ORDER BY fixture.kickoff_at, fixture.fixture_id""",
            {"cutoff": cutoff},
        ).fetchall()
        unmatched = cursor.execute(
            """SELECT observation.observation_id::text,
                      observation.source_snapshot_id::text,
                      observation.provider_code, observation.provider_match_id,
                      observation.provider_home_team_name, observation.provider_away_team_name,
                      CASE WHEN observation.provider_home_team_name IS NULL
                             OR observation.provider_away_team_name IS NULL
                             OR observation.provider_competition_name IS NULL
                           THEN 'MISSING_PROVIDER_IDENTITY_FIELDS'
                           WHEN decision.reason = 'historical admission failed'
                           THEN decision.reason || ': ' || COALESCE(decision.error, 'unknown')
                           ELSE COALESCE(decision.reason, 'no stored mapping decision')
                      END AS reason,
                      decision.reason AS review_reason
               FROM football.product_provider_fixture_observations observation
               LEFT JOIN LATERAL (
                   SELECT reason, evidence->>'error' AS error
                   FROM football.product_provider_mapping_decisions decision
                   WHERE decision.provider_code = observation.provider_code
                     AND decision.provider_match_id = observation.provider_match_id
                   ORDER BY decision.created_at DESC, decision.decision_id DESC LIMIT 1
               ) decision ON true
               WHERE observation.provider_code = 'pitchapi'
                 AND observation.canonical_fixture_id IS NULL
               ORDER BY observation.provider_match_id, observation.observed_at DESC"""
        ).fetchall()
        totals = cursor.execute(
            """SELECT
               (SELECT count(*) FROM football.product_team_match_history) AS imported_history,
               (SELECT count(*) FROM football.product_eligible_match_history
                WHERE known_at <= %s) AS eligible_history,
               (SELECT count(*) FROM football.product_fixtures
                WHERE identity_status = 'PROVISIONAL') AS provisional_fixtures""",
            (cutoff,),
        ).fetchone()
    for fixture in fixtures:
        fixture["kickoff_at"] = fixture["kickoff_at"].isoformat()
        if fixture["identity_status"] != "VERIFIED":
            fixture["reason"] = "PROVISIONAL_IDENTITY"
        elif min(fixture["home_history"], fixture["away_history"]) < MINIMUM_HISTORY_MATCHES:
            fixture["reason"] = "FEWER_THAN_TEN_ELIGIBLE_MATCHES"
        else:
            fixture["reason"] = "HISTORY_PREREQUISITE_MET"
    return {
        "knowledge_cutoff": cutoff.isoformat(),
        "minimum_history_matches": MINIMUM_HISTORY_MATCHES,
        "totals": totals,
        "upcoming_fixtures": fixtures,
        "fixture_reasons": dict(Counter(fixture["reason"] for fixture in fixtures)),
        "pitchapi_unmatched": unmatched,
        "pitchapi_unmatched_matches": len({row["provider_match_id"] for row in unmatched}),
        "pitchapi_unmatched_reasons": dict(Counter(row["reason"] for row in unmatched)),
    }
