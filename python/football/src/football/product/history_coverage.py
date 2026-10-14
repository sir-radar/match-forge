"""Fixture-level reasons why stored history is not usable for forecasting."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from football.product.domain import MINIMUM_HISTORY_MATCHES
from football.product.identity_admission import fixture_identity_blockers


def history_coverage(
    connection: Connection[Any], cutoff: datetime | None = None
) -> dict[str, object]:
    cutoff = cutoff or datetime.now(UTC)
    with connection.cursor(row_factory=dict_row) as cursor:
        fixtures = cursor.execute(
            """WITH eligible AS MATERIALIZED (
                   SELECT * FROM football.product_eligible_history_at(%(cutoff)s)
               ), targets AS MATERIALIZED (
                   SELECT f.*,
                     EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
                         WHERE r.member_fixture_id=f.fixture_id AND r.active
                           AND r.member_fixture_id<>r.representative_fixture_id
                           AND r.created_at<=%(cutoff)s) superseded,
                     football.product_fixture_team_at(f.fixture_id, f.home_team_id,
                         %(cutoff)s) effective_home,
                     football.product_fixture_team_at(f.fixture_id, f.away_team_id,
                         %(cutoff)s) effective_away
                   FROM football.product_fixtures f
                   WHERE f.status='SCHEDULED' AND f.kickoff_at>%(cutoff)s
               )
               SELECT fixture.fixture_id::text, home.name AS home_team, away.name AS away_team,
                      fixture.kickoff_at, fixture.identity_status, fixture.forecast_availability,
                      competition.name AS competition, competition.metadata_status,
                      competition.geographic_scope, fixture.superseded,
                      qualified.home_history, qualified.away_history, qualified.qualified_h2h,
                      counts.home_raw, counts.away_raw, counts.raw_h2h
               FROM targets fixture
               JOIN football.product_teams home ON home.team_id = fixture.effective_home
               JOIN football.product_teams away ON away.team_id = fixture.effective_away
               JOIN football.product_competitions competition
                 ON competition.competition_id = fixture.competition_id
               CROSS JOIN LATERAL (
                   SELECT count(*) FILTER (WHERE history.home_team_id = fixture.effective_home
                           OR history.away_team_id = fixture.effective_home) AS home_raw,
                          count(*) FILTER (WHERE history.home_team_id = fixture.effective_away
                           OR history.away_team_id = fixture.effective_away) AS away_raw,
                          count(*) FILTER (WHERE
                            (history.home_team_id=fixture.effective_home
                             AND history.away_team_id=fixture.effective_away) OR
                            (history.home_team_id=fixture.effective_away
                             AND history.away_team_id=fixture.effective_home)) raw_h2h
                   FROM football.product_team_match_history history
                   WHERE (history.home_team_id IN (fixture.effective_home, fixture.effective_away)
                          OR history.away_team_id IN
                             (fixture.effective_home, fixture.effective_away))
                     AND ((history.source_kickoff_precision = 'EXACT'
                           AND history.kickoff_at < fixture.kickoff_at)
                          OR (history.source_kickoff_precision = 'DATE_ONLY'
                              AND history.kickoff_at::date < fixture.kickoff_at::date))
               ) counts
               CROSS JOIN LATERAL (
                   SELECT count(*) FILTER (WHERE fixture.effective_home IN
                              (h.home_team_id,h.away_team_id)) home_history,
                          count(*) FILTER (WHERE fixture.effective_away IN
                              (h.home_team_id,h.away_team_id)) away_history,
                          count(*) FILTER (WHERE
                            (h.home_team_id=fixture.effective_home
                             AND h.away_team_id=fixture.effective_away) OR
                            (h.home_team_id=fixture.effective_away
                             AND h.away_team_id=fixture.effective_home)) qualified_h2h
                   FROM eligible h WHERE h.known_at <= %(cutoff)s
                     AND (fixture.effective_home IN (h.home_team_id,h.away_team_id)
                          OR fixture.effective_away IN (h.home_team_id,h.away_team_id))
                     AND ((h.source_kickoff_precision='EXACT' AND h.kickoff_at<fixture.kickoff_at)
                       OR (h.source_kickoff_precision='DATE_ONLY'
                           AND h.kickoff_at::date<fixture.kickoff_at::date))
               ) qualified
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
               (SELECT count(*) FROM football.product_eligible_history_at(%s)
                WHERE known_at <= %s) AS eligible_history,
               (SELECT count(*) FROM football.product_fixtures
                WHERE identity_status = 'PROVISIONAL') AS provisional_fixtures""",
            (cutoff, cutoff),
        ).fetchone()
    identity = fixture_identity_blockers(
        connection, [UUID(f["fixture_id"]) for f in fixtures], cutoff
    )
    for fixture in fixtures:
        fixture["kickoff_at"] = fixture["kickoff_at"].isoformat()
        if fixture["geographic_scope"] is None:
            fixture["reason"] = "CANONICAL_FIXTURE_GEOGRAPHY_REQUIRED"
        elif fixture["superseded"]:
            fixture["reason"] = "FIXTURE_REPRESENTATION_SUPERSEDED"
        elif fixture["identity_status"] != "VERIFIED":
            fixture["reason"] = "PROVISIONAL_IDENTITY"
        elif identity.get(UUID(fixture["fixture_id"])) is not None:
            fixture["reason"] = identity[UUID(fixture["fixture_id"])]
        elif fixture["home_history"] < MINIMUM_HISTORY_MATCHES:
            fixture["reason"] = "HOME_HISTORY_BELOW_CHAMPION_MINIMUM"
        elif fixture["away_history"] < MINIMUM_HISTORY_MATCHES:
            fixture["reason"] = "AWAY_HISTORY_BELOW_CHAMPION_MINIMUM"
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
