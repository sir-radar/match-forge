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
               ), eligible_sides AS (
                   SELECT home_team_id team_id,h.* FROM eligible h
                   UNION ALL SELECT away_team_id,h.* FROM eligible h
               ), team_counts AS (
                   SELECT t.fixture_id,side.team_id,count(h.fixture_id) matches
                   FROM targets t CROSS JOIN LATERAL (
                       VALUES(t.effective_home),(t.effective_away)) side(team_id)
                   JOIN eligible_sides h ON h.team_id=side.team_id
                     AND h.known_at<=%(cutoff)s
                     AND ((h.source_kickoff_precision='EXACT' AND h.kickoff_at<t.kickoff_at)
                       OR (h.source_kickoff_precision='DATE_ONLY'
                           AND h.kickoff_at::date<t.kickoff_at::date))
                   GROUP BY t.fixture_id,side.team_id
               ), pair_counts AS (
                   SELECT t.fixture_id,count(h.fixture_id) matches
                   FROM targets t JOIN eligible h
                     ON LEAST(h.home_team_id,h.away_team_id)=
                        LEAST(t.effective_home,t.effective_away)
                    AND GREATEST(h.home_team_id,h.away_team_id)=
                        GREATEST(t.effective_home,t.effective_away)
                    AND h.known_at<=%(cutoff)s
                     AND ((h.source_kickoff_precision='EXACT' AND h.kickoff_at<t.kickoff_at)
                       OR (h.source_kickoff_precision='DATE_ONLY'
                           AND h.kickoff_at::date<t.kickoff_at::date))
                   GROUP BY t.fixture_id
               )
               SELECT fixture.fixture_id::text, home.name AS home_team, away.name AS away_team,
                      fixture.kickoff_at, fixture.identity_status, fixture.forecast_availability,
                      competition.name AS competition, competition.metadata_status,
                      competition.geographic_scope, fixture.superseded,
                      COALESCE(hc.matches,0) home_history, COALESCE(ac.matches,0) away_history,
                      COALESCE(pc.matches,0) qualified_h2h,
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
               LEFT JOIN team_counts hc ON hc.fixture_id=fixture.fixture_id
                 AND hc.team_id=fixture.effective_home
               LEFT JOIN team_counts ac ON ac.fixture_id=fixture.fixture_id
                 AND ac.team_id=fixture.effective_away
               LEFT JOIN pair_counts pc ON pc.fixture_id=fixture.fixture_id
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
        "provider_history_depth": provider_history_depth(connection, cutoff),
    }


def provider_history_depth(connection: Connection[Any], cutoff: datetime) -> list[dict[str, Any]]:
    """Report qualification separately from advertised depth and request failures."""
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(
            """WITH eligible AS MATERIALIZED (
                 SELECT * FROM football.product_eligible_history_at(%s)
               ), history AS (
                 SELECT h.source_provider_code provider,h.competition_id,
                   count(*) retained_results,count(e.fixture_id) qualified_results,
                   min(h.kickoff_at)::text earliest_retained_result,
                   min(e.kickoff_at)::text earliest_qualified_result
                 FROM football.product_team_match_history h
                 LEFT JOIN eligible e USING(fixture_id) GROUP BY 1,2
               ), observations AS (
                 SELECT provider_code,provider_competition_id,
                   count(DISTINCT provider_match_id) provider_fixtures,
                   count(DISTINCT provider_match_id) FILTER (
                     WHERE canonical_fixture_id IS NULL) unmatched_fixtures,
                   count(DISTINCT o.provider_match_id) FILTER (WHERE NOT EXISTS (
                     SELECT 1 FROM football.providers p
                     JOIN football.product_effective_team_mappings home ON home.provider_id=p.id
                       AND home.provider_team_id=o.provider_home_team_id AND home.valid_to IS NULL
                     JOIN football.product_effective_team_mappings away ON away.provider_id=p.id
                       AND away.provider_team_id=o.provider_away_team_id AND away.valid_to IS NULL
                     WHERE p.code=o.provider_code
                       AND football.product_mapping_trusted('team',home.id,home.effective_team_id)
                       AND football.product_mapping_trusted('team',away.id,away.effective_team_id)
                   )) team_blocked_fixtures
                 FROM football.product_provider_fixture_observations o GROUP BY 1,2
               ), scopes AS (
                 SELECT provider_code,provider_competition_id,count(*) advertised_scopes,
                   count(*) FILTER (WHERE status='SUCCEEDED') completed_scopes,
                   count(*) FILTER (WHERE status='FAILED' AND last_error NOT LIKE 'BLOCKED%%'
                     AND last_error <> 'ADVERTISED_BUT_UNUSABLE') request_failed_scopes,
                   jsonb_agg(jsonb_build_object('season',season_label,'status',status,
                       'first_blocker',last_error,'summary',summary)
                       ORDER BY season_label DESC) season_states
                 FROM football.product_provider_history_scopes GROUP BY 1,2
               ) SELECT p.code provider,m.provider_competition_id,c.name competition,
                 m.competition_id::text,COALESCE(h.retained_results,0) retained_results,
                 COALESCE(h.qualified_results,0) qualified_results,
                 h.earliest_retained_result,h.earliest_qualified_result,
                 COALESCE(o.provider_fixtures,0) provider_fixtures,
                 COALESCE(s.advertised_scopes,0) advertised_scopes,
                 COALESCE(s.completed_scopes,0) completed_scopes,
                 COALESCE(s.season_states,'[]'::jsonb) season_states,
                 CASE
                   WHEN NOT football.product_mapping_trusted('competition',m.id,m.competition_id)
                     THEN 'COMPETITION_CROSSWALK_UNRESOLVED'
                   WHEN COALESCE(h.qualified_results,0)>0 THEN 'QUALIFIED'
                   WHEN COALESCE(s.request_failed_scopes,0)>0 THEN 'PROVIDER_REQUEST_FAILED'
                   WHEN COALESCE(o.team_blocked_fixtures,0)>0 THEN 'TEAM_IDENTITIES_UNRESOLVED'
                   WHEN COALESCE(o.unmatched_fixtures,0)>0 THEN 'FIXTURE_IDENTITY_CONFLICT'
                   WHEN COALESCE(h.retained_results,0)>0 THEN 'HISTORY_NOT_ADMITTED'
                   WHEN COALESCE(o.provider_fixtures,0)>0 THEN 'TEAM_IDENTITIES_UNRESOLVED'
                   WHEN COALESCE(s.advertised_scopes,0)>0 THEN 'ADVERTISED_ONLY'
                   ELSE 'NO_RETAINED_FIXTURE_ROWS' END first_blocker
               FROM football.competition_provider_mappings m
               JOIN football.providers p ON p.id=m.provider_id
               JOIN football.product_competitions c USING(competition_id)
               LEFT JOIN history h ON h.provider=p.code AND h.competition_id=m.competition_id
               LEFT JOIN observations o ON o.provider_code=p.code
                 AND o.provider_competition_id=m.provider_competition_id
               LEFT JOIN scopes s ON s.provider_code=p.code
                 AND s.provider_competition_id=m.provider_competition_id
               WHERE m.valid_to IS NULL ORDER BY p.code,m.provider_competition_id""",
            (cutoff,),
        ).fetchall()
