-- +goose Up

-- Serialize qualification with admissions using one transaction lock, including
-- single-fixture ingestion. A competition admission must not retain one lock
-- per historical fixture. The eligibility predicate and decision times stay intact.
-- +goose StatementBegin
CREATE FUNCTION football.record_product_history_decisions(fixture_keys uuid[]) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('product-identity-admission', 0));
    INSERT INTO football.product_match_history_decisions (
        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
        home_goals, away_goals, home_xg, away_xg, source_provider_code,
        source_snapshot_id, source_kickoff_precision, eligible, reason, source_known_at)
    SELECT proposed.* FROM (
    SELECT h.fixture_id, h.competition_id, COALESCE(football.product_team_identity_at(hm.id, clock_timestamp()), h.home_team_id) AS home_team_id,
           COALESCE(football.product_team_identity_at(am.id, clock_timestamp()), h.away_team_id) AS away_team_id, h.kickoff_at,
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
           AND football.product_mapping_trusted('team', hm.id,
               COALESCE(football.product_team_identity_at(hm.id, clock_timestamp()), h.home_team_id))
           AND football.product_mapping_trusted('team', am.id,
               COALESCE(football.product_team_identity_at(am.id, clock_timestamp()), h.away_team_id)) AS eligible,
           'ProductIdentityTrustV1'::text AS reason, s.acquired_at AS source_known_at
    FROM football.product_team_match_history h
    JOIN football.source_snapshots s ON s.id = h.source_snapshot_id
    LEFT JOIN football.product_fixtures f ON f.fixture_id = h.fixture_id
    LEFT JOIN football.team_provider_mappings hm
      ON hm.team_id = h.home_team_id AND hm.provider_id = s.provider_id AND hm.valid_to IS NULL
    LEFT JOIN football.team_provider_mappings am
      ON am.team_id = h.away_team_id AND am.provider_id = s.provider_id AND am.valid_to IS NULL
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

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_history_decision(fixture_key uuid) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.record_product_history_decisions(ARRAY[fixture_key]);
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_admission_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original_team uuid;
BEGIN
    IF NEW.entity_type = 'competition' THEN
        PERFORM football.record_product_history_decisions(ARRAY(
            SELECT fixture_id FROM football.product_team_match_history
            WHERE competition_id = NEW.canonical_id ORDER BY fixture_id));
    ELSE
        SELECT team_id INTO original_team FROM football.team_provider_mappings
        WHERE id = NEW.mapping_id;
        PERFORM football.record_product_history_decisions(ARRAY(
            SELECT fixture_id FROM football.product_team_match_history
            WHERE home_team_id IN (NEW.canonical_id, original_team)
               OR away_team_id IN (NEW.canonical_id, original_team)
            ORDER BY fixture_id));
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- Prospective decisions remain inspectable; preserve the shared lock ordering.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'bounded history qualification is a forward-only migration'; END $$;
-- +goose StatementEnd
