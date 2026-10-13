-- +goose Up
-- A linked admission corrects one team's effective identity, never its retained mapping row.
ALTER TABLE football.product_identity_admissions
    ADD COLUMN corrects_decision_id uuid REFERENCES football.product_provider_mapping_decisions (decision_id),
    ADD COLUMN target_mapping_id uuid REFERENCES football.team_provider_mappings (id),
    ADD CONSTRAINT product_identity_correction_pair CHECK (
        (corrects_decision_id IS NULL AND target_mapping_id IS NULL) OR
        (corrects_decision_id IS NOT NULL AND target_mapping_id IS NOT NULL
         AND entity_type = 'team' AND disposition IN ('CROSSWALK', 'REVOKED')));
CREATE UNIQUE INDEX product_identity_correction_retry_idx
    ON football.product_identity_admissions (mapping_id, evidence_sha256)
    WHERE corrects_decision_id IS NOT NULL AND disposition = 'CROSSWALK';

-- +goose StatementBegin
CREATE FUNCTION football.validate_product_identity_correction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.corrects_decision_id IS NULL THEN
        IF EXISTS (SELECT 1 FROM football.product_identity_admissions a
                   WHERE a.entity_type = NEW.entity_type AND a.mapping_id = NEW.mapping_id
                     AND a.corrects_decision_id IS NOT NULL) THEN
            RAISE EXCEPTION 'linked correction requires a linked continuation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.disposition = 'REVOKED' THEN RETURN NEW; END IF;
    IF NEW.evidence->>'contract' IS DISTINCT FROM 'ProductTeamIdentityCorrectionV1'
       OR jsonb_typeof(NEW.evidence->'context_resources') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'identity correction requires typed context evidence';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM football.product_provider_mapping_decisions d
        JOIN football.match_provider_mappings fixture
          ON fixture.id = (NEW.evidence->>'fixture_registration_id')::uuid
         AND fixture.match_id = d.candidate_fixture_id
        JOIN football.product_fixtures f ON f.fixture_id = fixture.match_id
        JOIN football.product_competitions c ON c.competition_id = f.competition_id
        JOIN football.matches match ON match.id = f.fixture_id
        JOIN football.seasons season ON season.id = match.season_id
        JOIN football.team_provider_mappings source ON source.id = NEW.mapping_id
         AND source.provider_id = fixture.provider_id
        JOIN football.providers sp ON sp.id = source.provider_id
        JOIN football.team_provider_mappings target ON target.id = NEW.target_mapping_id
        JOIN football.providers tp ON tp.id = target.provider_id
        WHERE d.decision_id = NEW.corrects_decision_id AND d.disposition = 'CONTRADICTORY'
          AND NEW.evidence->'original_decision' = to_jsonb(d)
          AND sp.code = NEW.provider_code AND source.provider_team_id = NEW.provider_entity_id
          AND source.source_snapshot_id = NEW.source_snapshot_id AND source.valid_to IS NULL
          AND source.mapping_confidence = 1 AND target.mapping_confidence = 1
          AND target.valid_to IS NULL AND target.team_id = NEW.canonical_id
          AND tp.code = NEW.evidence->'target_evidence'->>'provider'
          AND target.source_snapshot_id = (NEW.evidence->'target_evidence'->>'source_snapshot_id')::uuid
          AND target.provider_team_id = NEW.evidence->'target_evidence'->>'provider_entity_id'
          AND NEW.evidence->>'reason' = 'INCORRECT_PRIOR_MAPPING'
          AND NEW.evidence->>'orientation' IN ('HOME', 'AWAY')
          AND source.team_id = CASE NEW.evidence->>'orientation'
              WHEN 'HOME' THEN f.home_team_id ELSE f.away_team_id END
          AND (NEW.evidence->'context'->>'kickoff')::timestamptz = f.kickoff_at
          AND NEW.evidence->'context'->>'country' = c.country
          AND (NEW.evidence->'context'->>'season_start')::date = season.start_date
          AND (NEW.evidence->'context'->>'season_end')::date = season.end_date
    ) THEN RAISE EXCEPTION 'identity correction requires exact contradiction, source and target linkage'; END IF;
    IF EXISTS (SELECT 1 FROM football.product_identity_admissions a
               WHERE a.mapping_id = NEW.mapping_id AND a.corrects_decision_id IS NOT NULL) THEN
        RAISE EXCEPTION 'existing linked correction must be retried or explicitly revoked';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.evidence->'context_resources') item
        WHERE NOT EXISTS (
            SELECT 1 FROM football.source_resources r
            JOIN football.source_snapshots s ON s.id = r.source_snapshot_id
            JOIN football.providers p ON p.id = s.provider_id
            WHERE r.id = (item->>'source_resource_id')::uuid
              AND s.id = (item->>'source_snapshot_id')::uuid
              AND p.code = item->>'provider' AND r.sha256 = item->>'sha256'
              AND s.status = 'validated' AND r.parse_status = 'parsed'
              AND r.validation_status IN ('valid', 'warnings')
              AND r.acquired_at <= NEW.decided_at
        )
    ) OR jsonb_array_length(NEW.evidence->'context_resources') < 3 THEN
        RAISE EXCEPTION 'identity correction requires registered retained context resources';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER validate_product_identity_correction BEFORE INSERT ON football.product_identity_admissions
    FOR EACH ROW EXECUTE FUNCTION football.validate_product_identity_correction();

-- +goose StatementBegin
CREATE FUNCTION football.product_team_identity_at(mapping_key uuid, knowledge_time timestamptz)
RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT a.canonical_id FROM football.product_identity_admissions a
    WHERE a.entity_type = 'team' AND a.mapping_id = mapping_key
      AND a.decided_at <= knowledge_time AND a.source_observed_at <= knowledge_time
      AND a.disposition IN ('ORIGIN_ANCHOR', 'CROSSWALK')
      AND NOT EXISTS (SELECT 1 FROM football.product_identity_admissions later
          WHERE later.entity_type = 'team' AND later.mapping_id = mapping_key
            AND later.decided_at <= knowledge_time
            AND (later.decided_at, later.decision_id) > (a.decided_at, a.decision_id))
$$;
-- +goose StatementEnd
CREATE VIEW football.product_effective_team_mappings AS
    SELECT m.*, COALESCE(football.product_team_identity_at(m.id, statement_timestamp()), m.team_id)
                    AS effective_team_id
    FROM football.team_provider_mappings m;
CREATE VIEW football.product_effective_team_aliases AS
    SELECT a.provider_code, a.provider_team_id, a.normalized_name, a.country,
           COALESCE(m.effective_team_id, a.team_id) AS team_id
    FROM football.product_team_aliases a
    LEFT JOIN football.providers p ON p.code = a.provider_code
    LEFT JOIN football.product_effective_team_mappings m
      ON m.provider_id = p.id AND m.provider_team_id = a.provider_team_id AND m.valid_to IS NULL;

-- +goose StatementBegin
CREATE FUNCTION football.product_fixture_team_at(fixture_key uuid, source_team uuid, knowledge_time timestamptz)
RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN count(DISTINCT effective) = 1 THEN (array_agg(DISTINCT effective))[1]
                ELSE source_team END
    FROM (
        SELECT football.product_team_identity_at(m.id, knowledge_time) effective
        FROM football.team_provider_mappings m
        JOIN football.match_provider_mappings f ON f.provider_id = m.provider_id
        WHERE f.match_id = fixture_key AND m.team_id = source_team
          AND m.created_at <= knowledge_time AND f.created_at <= knowledge_time
    ) identities
$$;
-- +goose StatementEnd

-- Keep all original fields; only the read projection resolves qualified team identities.
-- The explicit column list below is generated from the current product_fixtures contract.

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.product_mapping_trusted(kind text, mapping_key uuid, canonical_key uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT a.disposition IN ('ORIGIN_ANCHOR', 'CROSSWALK')
                           AND a.canonical_id = canonical_key AND s.status = 'validated'
                           AND r.parse_status = 'parsed' AND r.validation_status IN ('valid', 'warnings')
                           AND r.sha256 = a.evidence->>'sha256'
                           AND NOT EXISTS (
                               SELECT 1 FROM jsonb_array_elements(
                                   COALESCE(a.evidence->'context_resources', '[]'::jsonb)) item
                               WHERE NOT EXISTS (
                                   SELECT 1 FROM football.source_resources cr
                                   JOIN football.source_snapshots cs ON cs.id = cr.source_snapshot_id
                                   WHERE cr.id = (item->>'source_resource_id')::uuid
                                     AND cr.sha256 = item->>'sha256' AND cs.status = 'validated'
                                     AND cr.parse_status = 'parsed'
                                     AND cr.validation_status IN ('valid', 'warnings')))
                    FROM (SELECT * FROM football.product_identity_admissions
                          WHERE entity_type = kind AND mapping_id = mapping_key
                          ORDER BY decided_at DESC, decision_id DESC LIMIT 1) a
                    LEFT JOIN football.source_snapshots s ON s.id = a.source_snapshot_id
                    LEFT JOIN football.source_resources r
                      ON r.id = (a.evidence->>'source_resource_id')::uuid), false)
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_admission_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.record_product_history_decision(h.fixture_id)
    FROM football.product_team_match_history h
    WHERE (NEW.entity_type = 'competition' AND h.competition_id = NEW.canonical_id)
       OR (NEW.entity_type = 'team' AND (NEW.canonical_id IN (h.home_team_id, h.away_team_id)
           OR EXISTS (SELECT 1 FROM football.team_provider_mappings m WHERE m.id = NEW.mapping_id
                      AND m.team_id IN (h.home_team_id, h.away_team_id))))
    ORDER BY h.fixture_id;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.revoke_changed_product_mapping() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text := CASE TG_TABLE_NAME WHEN 'team_provider_mappings' THEN 'team' ELSE 'competition' END;
BEGIN
    IF TG_OP = 'UPDATE' AND (to_jsonb(OLD) - 'last_seen_at') = (to_jsonb(NEW) - 'last_seen_at') THEN
        RETURN NEW;
    END IF;
    INSERT INTO football.product_identity_admissions (
        entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
        disposition, reason, source_snapshot_id, source_observed_at, evidence, evidence_sha256,
        corrects_decision_id, target_mapping_id)
    SELECT a.entity_type, a.mapping_id, a.canonical_id, a.provider_code, a.provider_entity_id,
           'REVOKED', 'MAPPING_CHANGED_REVALIDATION_REQUIRED', a.source_snapshot_id,
           a.source_observed_at, a.evidence, a.evidence_sha256, a.corrects_decision_id, a.target_mapping_id
    FROM (SELECT DISTINCT ON (entity_type, mapping_id) * FROM football.product_identity_admissions
          ORDER BY entity_type, mapping_id, decided_at DESC, decision_id DESC) a
    WHERE (a.entity_type = kind AND a.mapping_id = OLD.id)
       OR (kind = 'team' AND a.target_mapping_id = OLD.id AND a.disposition = 'CROSSWALK');
    RETURN COALESCE(NEW, OLD);
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.revoke_changed_correction_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE snapshot_key uuid := (to_jsonb(NEW)->> CASE TG_TABLE_NAME
    WHEN 'source_snapshots' THEN 'id' ELSE 'source_snapshot_id' END)::uuid;
BEGIN
    IF TG_TABLE_NAME = 'source_resources' AND
       (to_jsonb(OLD)->'sha256', to_jsonb(OLD)->'parse_status', to_jsonb(OLD)->'validation_status') =
       (to_jsonb(NEW)->'sha256', to_jsonb(NEW)->'parse_status', to_jsonb(NEW)->'validation_status') THEN
        RETURN NEW;
    END IF;
    INSERT INTO football.product_identity_admissions (
        entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
        disposition, reason, source_snapshot_id, source_observed_at, evidence, evidence_sha256,
        corrects_decision_id, target_mapping_id)
    SELECT a.entity_type, a.mapping_id, a.canonical_id, a.provider_code, a.provider_entity_id,
           'REVOKED', 'CORRECTION_SOURCE_CHANGED', a.source_snapshot_id, a.source_observed_at,
           a.evidence, a.evidence_sha256, a.corrects_decision_id, a.target_mapping_id
    FROM (SELECT DISTINCT ON (entity_type, mapping_id) * FROM football.product_identity_admissions
          ORDER BY entity_type, mapping_id, decided_at DESC, decision_id DESC) a
    WHERE a.corrects_decision_id IS NOT NULL AND a.disposition = 'CROSSWALK'
      AND (a.source_snapshot_id = snapshot_key OR EXISTS (
          SELECT 1 FROM jsonb_array_elements(a.evidence->'context_resources') item
          WHERE (item->>'source_snapshot_id')::uuid = snapshot_key));
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER revoke_changed_correction_source AFTER UPDATE OF status ON football.source_snapshots
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION football.revoke_changed_correction_source();
CREATE TRIGGER revoke_changed_correction_resource AFTER UPDATE OF sha256, parse_status, validation_status
    ON football.source_resources FOR EACH ROW EXECUTE FUNCTION football.revoke_changed_correction_source();

-- +goose StatementBegin
CREATE FUNCTION football.revoke_correction_on_new_conflict() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO football.product_identity_admissions (
        entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
        disposition, reason, source_snapshot_id, source_observed_at, evidence, evidence_sha256,
        corrects_decision_id, target_mapping_id)
    SELECT a.entity_type, a.mapping_id, a.canonical_id, a.provider_code, a.provider_entity_id,
           'REVOKED', 'CORRECTION_NEW_CONFLICT', a.source_snapshot_id, a.source_observed_at,
           a.evidence, a.evidence_sha256, a.corrects_decision_id, a.target_mapping_id
    FROM (SELECT DISTINCT ON (entity_type, mapping_id) * FROM football.product_identity_admissions
          ORDER BY entity_type, mapping_id, decided_at DESC, decision_id DESC) a
    JOIN football.product_provider_mapping_decisions original ON original.decision_id = a.corrects_decision_id
    WHERE a.disposition = 'CROSSWALK' AND original.candidate_fixture_id = NEW.candidate_fixture_id;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER revoke_correction_on_new_conflict AFTER INSERT ON football.product_provider_mapping_decisions
    FOR EACH ROW WHEN (NEW.disposition = 'CONTRADICTORY')
    EXECUTE FUNCTION football.revoke_correction_on_new_conflict();

-- +goose StatementBegin
CREATE FUNCTION football.revoke_correction_on_target_admission() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO football.product_identity_admissions (
        entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
        disposition, reason, source_snapshot_id, source_observed_at, evidence, evidence_sha256,
        corrects_decision_id, target_mapping_id)
    SELECT a.entity_type, a.mapping_id, a.canonical_id, a.provider_code, a.provider_entity_id,
           'REVOKED', 'CORRECTION_TARGET_REVOKED', a.source_snapshot_id, a.source_observed_at,
           a.evidence, a.evidence_sha256, a.corrects_decision_id, a.target_mapping_id
    FROM (SELECT DISTINCT ON (entity_type, mapping_id) * FROM football.product_identity_admissions
          ORDER BY entity_type, mapping_id, decided_at DESC, decision_id DESC) a
    WHERE a.disposition = 'CROSSWALK' AND a.target_mapping_id = NEW.mapping_id;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER revoke_correction_on_target_admission AFTER INSERT ON football.product_identity_admissions
    FOR EACH ROW WHEN (NEW.entity_type = 'team' AND NEW.disposition NOT IN ('ORIGIN_ANCHOR', 'CROSSWALK'))
    EXECUTE FUNCTION football.revoke_correction_on_target_admission();

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_history_decision(fixture_key uuid) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('history-qualification:' || fixture_key::text, 0));
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
    WHERE h.fixture_id = fixture_key) proposed
    WHERE NOT EXISTS (
        SELECT 1 FROM (SELECT * FROM football.product_match_history_decisions
                      WHERE fixture_id = fixture_key
                      ORDER BY decided_at DESC, decision_id DESC LIMIT 1) previous
        WHERE (to_jsonb(previous) - 'decision_id' - 'decided_at') = to_jsonb(proposed)
    );
END;
$$;
-- +goose StatementEnd

CREATE VIEW football.product_effective_fixtures AS
    SELECT f.fixture_id,
           f.competition_id,
           football.product_fixture_team_at(f.fixture_id, f.home_team_id, statement_timestamp()) AS home_team_id,
           football.product_fixture_team_at(f.fixture_id, f.away_team_id, statement_timestamp()) AS away_team_id,
           f.kickoff_at,
           f.status,
           f.home_score,
           f.away_score,
           f.venue,
           f.round_name,
           f.forecast_availability,
           f.updated_at,
           f.result_score_basis,
           f.identity_status
    FROM football.product_fixtures f;

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'team identity corrections are a forward-only migration'; END $$;
-- +goose StatementEnd
