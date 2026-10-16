-- +goose Up

-- Aliases must agree on effective identity and trust. Emit one dated decision
-- per history row instead of contradictory decisions from a Cartesian join.
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
           'ProductIdentityTrustV1'::text AS reason, s.acquired_at AS source_known_at
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


-- Reconciled source members remain stored, but do not block their proven representative.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.guard_product_history_fixture_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM football.product_team_match_history existing
        WHERE existing.fixture_id <> NEW.fixture_id AND existing.kickoff_at = NEW.kickoff_at
          AND (existing.home_team_id IN (NEW.home_team_id, NEW.away_team_id)
               OR existing.away_team_id IN (NEW.home_team_id, NEW.away_team_id))
          AND NOT EXISTS (
              SELECT 1 FROM football.fixture_identity_resolutions resolution
              WHERE resolution.member_fixture_id = existing.fixture_id AND resolution.active
                AND resolution.resolution_status = 'DUPLICATE_RESOLVED'
                AND resolution.representative_fixture_id = NEW.fixture_id)
    ) THEN
        RAISE EXCEPTION 'unresolved canonical fixture identity conflict at team/timestamp';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- Existing dated decisions must remain available to historical readers.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'history alias qualification is a forward-only migration'; END $$;
-- +goose StatementEnd
