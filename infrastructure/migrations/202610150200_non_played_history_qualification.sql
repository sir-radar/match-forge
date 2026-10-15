-- +goose Up

-- Preserve source results and prior decisions when a canonical fixture is
-- confirmed as awarded, abandoned or cancelled. Status reviews create a new
-- dated qualification decision; they do not rewrite historical cutoffs.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_history_decisions(fixture_keys uuid[]) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('product-identity-admission', 0));
    INSERT INTO football.product_match_history_decisions (
        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
        home_goals, away_goals, home_xg, away_xg, source_provider_code,
        source_snapshot_id, source_kickoff_precision, eligible, reason, source_known_at)
    SELECT proposed.* FROM (
    SELECT h.fixture_id, h.competition_id, COALESCE(hm.identity, h.home_team_id) AS home_team_id,
           COALESCE(am.identity, h.away_team_id) AS away_team_id, h.kickoff_at,
           h.home_goals, h.away_goals, h.home_xg, h.away_xg, h.source_provider_code,
           h.source_snapshot_id, h.source_kickoff_precision,
           s.status = 'validated' AND COALESCE(f.identity_status, 'VERIFIED') = 'VERIFIED'
           AND COALESCE(f.status NOT IN ('AWARDED', 'ABANDONED', 'CANCELLED'), true)
           AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
               WHERE r.member_fixture_id = h.fixture_id AND r.active
                 AND (r.resolution_status NOT IN ('UNIQUE', 'DUPLICATE_RESOLVED')
                      OR r.representative_fixture_id <> h.fixture_id))
           AND EXISTS (SELECT 1 FROM football.competition_provider_mappings m
               WHERE m.competition_id = h.competition_id AND m.provider_id = s.provider_id
                 AND m.valid_to IS NULL AND m.mapping_confidence = 1
                 AND football.product_mapping_trusted('competition', m.id, m.competition_id))
           AND COALESCE(hm.trusted, false)
           AND COALESCE(am.trusted, false) AS eligible,
           CASE WHEN f.status IN ('AWARDED', 'ABANDONED', 'CANCELLED')
                THEN 'non-played terminal status' ELSE 'ProductIdentityTrustV1' END AS reason, s.acquired_at AS source_known_at
    FROM football.product_team_match_history h
    JOIN football.source_snapshots s ON s.id = h.source_snapshot_id
    LEFT JOIN football.product_fixtures f ON f.fixture_id = h.fixture_id
    LEFT JOIN LATERAL (
        SELECT CASE WHEN count(DISTINCT effective.identity) = 1
                    THEN min(effective.identity::text)::uuid END AS identity,
               count(DISTINCT effective.identity) = 1 AND bool_and(
                   football.product_mapping_trusted('team', mapping.id, effective.identity)) AS trusted
        FROM football.team_provider_mappings mapping
        CROSS JOIN LATERAL (SELECT COALESCE(
            football.product_team_identity_at(mapping.id, clock_timestamp()),
            mapping.team_id) AS identity) effective
        WHERE mapping.team_id = h.home_team_id AND mapping.provider_id = s.provider_id
          AND mapping.valid_to IS NULL
    ) hm ON true
    LEFT JOIN LATERAL (
        SELECT CASE WHEN count(DISTINCT effective.identity) = 1
                    THEN min(effective.identity::text)::uuid END AS identity,
               count(DISTINCT effective.identity) = 1 AND bool_and(
                   football.product_mapping_trusted('team', mapping.id, effective.identity)) AS trusted
        FROM football.team_provider_mappings mapping
        CROSS JOIN LATERAL (SELECT COALESCE(
            football.product_team_identity_at(mapping.id, clock_timestamp()),
            mapping.team_id) AS identity) effective
        WHERE mapping.team_id = h.away_team_id AND mapping.provider_id = s.provider_id
          AND mapping.valid_to IS NULL
    ) am ON true
    WHERE h.fixture_id = ANY(fixture_keys)) proposed
    WHERE NOT EXISTS (
        SELECT 1 FROM (SELECT * FROM football.product_match_history_decisions
                      WHERE fixture_id = proposed.fixture_id
                      ORDER BY decided_at DESC, decision_id DESC LIMIT 1) previous
        WHERE (to_jsonb(previous) - 'decision_id' - 'decided_at') = to_jsonb(proposed)
    ) ORDER BY proposed.fixture_id;
END;
$$;
-- +goose StatementEnd

DROP TRIGGER record_product_fixture_qualification ON football.product_fixtures;
CREATE TRIGGER record_product_fixture_qualification
    AFTER INSERT OR UPDATE OF identity_status, status ON football.product_fixtures
    FOR EACH ROW EXECUTE FUNCTION football.record_product_history_change();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'non-played history qualification is a forward-only migration'; END $$;
-- +goose StatementEnd
