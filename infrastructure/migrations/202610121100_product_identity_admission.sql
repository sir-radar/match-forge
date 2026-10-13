-- +goose Up

CREATE TABLE football.product_identity_admissions (
    decision_id uuid PRIMARY KEY DEFAULT uuidv7(),
    entity_type text NOT NULL CHECK (entity_type IN ('team', 'competition')),
    mapping_id uuid NOT NULL,
    canonical_id uuid NOT NULL,
    provider_code text NOT NULL REFERENCES football.providers (code),
    provider_entity_id text NOT NULL CHECK (provider_entity_id <> ''),
    disposition text NOT NULL CHECK (disposition IN (
        'ORIGIN_ANCHOR', 'CROSSWALK', 'UNRESOLVED', 'CONTRADICTORY', 'REVOKED')),
    reason text NOT NULL CHECK (reason <> ''),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    source_observed_at timestamptz,
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    evidence_sha256 football.sha256_hex NOT NULL,
    CHECK (disposition NOT IN ('ORIGIN_ANCHOR', 'CROSSWALK') OR
           (source_observed_at IS NOT NULL AND evidence ? 'source_resource_id'
            AND evidence ? 'sha256' AND evidence ? 'provider_entity_id'))
);
CREATE INDEX product_identity_admission_mapping_idx ON football.product_identity_admissions
    (entity_type, mapping_id, decided_at DESC, decision_id DESC);

-- +goose StatementBegin
CREATE FUNCTION football.validate_product_identity_admission() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('product-identity-admission', 0));
    NEW.decided_at := clock_timestamp();
    IF NEW.disposition IN ('ORIGIN_ANCHOR', 'CROSSWALK') AND NOT EXISTS (
        SELECT 1 FROM football.source_resources r
        JOIN football.source_snapshots s ON s.id = r.source_snapshot_id
        JOIN football.providers p ON p.id = s.provider_id
        WHERE r.id = (NEW.evidence->>'source_resource_id')::uuid
          AND s.id = NEW.source_snapshot_id AND p.code = NEW.provider_code
          AND r.sha256 = NEW.evidence->>'sha256'
          AND NEW.provider_entity_id = NEW.evidence->>'provider_entity_id'
          AND s.status = 'validated' AND r.parse_status = 'parsed'
          AND r.validation_status IN ('valid', 'warnings')
    ) THEN
        RAISE EXCEPTION 'identity admission requires matching retained source evidence';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER validate_product_identity_admission BEFORE INSERT ON football.product_identity_admissions
    FOR EACH ROW EXECUTE FUNCTION football.validate_product_identity_admission();

CREATE TABLE football.product_match_history_decisions (
    decision_id uuid PRIMARY KEY DEFAULT uuidv7(),
    LIKE football.product_team_match_history INCLUDING DEFAULTS INCLUDING CONSTRAINTS,
    eligible boolean NOT NULL,
    reason text NOT NULL,
    source_known_at timestamptz NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX product_history_decision_fixture_idx ON football.product_match_history_decisions
    (fixture_id, decided_at DESC, decision_id DESC);
CREATE INDEX product_history_decision_home_idx ON football.product_match_history_decisions
    (home_team_id, kickoff_at, decided_at);
CREATE INDEX product_history_decision_away_idx ON football.product_match_history_decisions
    (away_team_id, kickoff_at, decided_at);

-- +goose StatementBegin
CREATE FUNCTION football.stamp_product_history_decision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.decided_at := clock_timestamp();
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER stamp_product_history_decision BEFORE INSERT ON football.product_match_history_decisions
    FOR EACH ROW EXECUTE FUNCTION football.stamp_product_history_decision();

CREATE TRIGGER product_identity_admissions_append_only BEFORE UPDATE OR DELETE
    ON football.product_identity_admissions FOR EACH ROW
    EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
CREATE TRIGGER product_history_decisions_append_only BEFORE UPDATE OR DELETE
    ON football.product_match_history_decisions FOR EACH ROW
    EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
CREATE TRIGGER product_provider_mapping_decisions_append_only BEFORE UPDATE OR DELETE
    ON football.product_provider_mapping_decisions FOR EACH ROW
    EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
CREATE TRIGGER check_worker_publication BEFORE INSERT ON football.product_identity_admissions
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();
CREATE TRIGGER check_worker_publication BEFORE INSERT ON football.product_match_history_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();

-- +goose StatementBegin
CREATE FUNCTION football.product_mapping_trusted(kind text, mapping_key uuid, canonical_key uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT a.disposition IN ('ORIGIN_ANCHOR', 'CROSSWALK')
                           AND a.canonical_id = canonical_key AND s.status = 'validated'
                           AND r.parse_status = 'parsed' AND r.validation_status IN ('valid', 'warnings')
                           AND r.sha256 = a.evidence->>'sha256'
                    FROM (SELECT * FROM football.product_identity_admissions
                          WHERE entity_type = kind AND mapping_id = mapping_key
                          ORDER BY decided_at DESC, decision_id DESC LIMIT 1) a
                    LEFT JOIN football.source_snapshots s ON s.id = a.source_snapshot_id
                    LEFT JOIN football.source_resources r
                      ON r.id = (a.evidence->>'source_resource_id')::uuid), false)
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.record_product_history_decision(fixture_key uuid) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('history-qualification:' || fixture_key::text, 0));
    INSERT INTO football.product_match_history_decisions (
        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
        home_goals, away_goals, home_xg, away_xg, source_provider_code,
        source_snapshot_id, source_kickoff_precision, eligible, reason, source_known_at)
    SELECT proposed.* FROM (
    SELECT h.fixture_id, h.competition_id, h.home_team_id, h.away_team_id, h.kickoff_at,
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
           AND EXISTS (SELECT 1 FROM football.team_provider_mappings m
               WHERE m.team_id = h.home_team_id AND m.provider_id = s.provider_id
                 AND m.valid_to IS NULL AND m.mapping_confidence = 1
                 AND football.product_mapping_trusted('team', m.id, m.team_id))
           AND EXISTS (SELECT 1 FROM football.team_provider_mappings m
               WHERE m.team_id = h.away_team_id AND m.provider_id = s.provider_id
                 AND m.valid_to IS NULL AND m.mapping_confidence = 1
                 AND football.product_mapping_trusted('team', m.id, m.team_id)) AS eligible,
           'ProductIdentityTrustV1'::text AS reason, s.acquired_at AS source_known_at
    FROM football.product_team_match_history h
    JOIN football.source_snapshots s ON s.id = h.source_snapshot_id
    LEFT JOIN football.product_fixtures f ON f.fixture_id = h.fixture_id
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

-- +goose StatementBegin
CREATE FUNCTION football.record_product_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.record_product_history_decision(NEW.fixture_id);
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER record_product_history_change AFTER INSERT OR UPDATE
    ON football.product_team_match_history FOR EACH ROW
    EXECUTE FUNCTION football.record_product_history_change();
CREATE TRIGGER record_product_fixture_qualification AFTER INSERT OR UPDATE OF identity_status
    ON football.product_fixtures FOR EACH ROW
    EXECUTE FUNCTION football.record_product_history_change();

-- +goose StatementBegin
CREATE FUNCTION football.record_product_resolution_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.record_product_history_decision(COALESCE(NEW.member_fixture_id, OLD.member_fixture_id));
    RETURN COALESCE(NEW, OLD);
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER record_product_resolution_change AFTER INSERT OR UPDATE OR DELETE
    ON football.fixture_identity_resolutions FOR EACH ROW
    EXECUTE FUNCTION football.record_product_resolution_change();

-- +goose StatementBegin
CREATE FUNCTION football.record_product_source_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE snapshot_key uuid := (to_jsonb(NEW)->> CASE TG_TABLE_NAME
    WHEN 'source_snapshots' THEN 'id' ELSE 'source_snapshot_id' END)::uuid;
BEGIN
    PERFORM football.record_product_history_decision(h.fixture_id)
    FROM football.product_team_match_history h
    WHERE h.source_snapshot_id = snapshot_key OR EXISTS (
        SELECT 1 FROM football.product_identity_admissions a
        WHERE a.source_snapshot_id = snapshot_key
          AND ((a.entity_type = 'competition' AND a.canonical_id = h.competition_id)
               OR (a.entity_type = 'team' AND a.canonical_id IN (h.home_team_id, h.away_team_id)))
    ) ORDER BY h.fixture_id;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER record_product_source_validation AFTER UPDATE OF status ON football.source_snapshots
    FOR EACH ROW EXECUTE FUNCTION football.record_product_source_change();
CREATE TRIGGER record_product_resource_validation AFTER UPDATE OF sha256, parse_status, validation_status
    ON football.source_resources FOR EACH ROW EXECUTE FUNCTION football.record_product_source_change();

-- +goose StatementBegin
CREATE FUNCTION football.record_product_admission_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.record_product_history_decision(h.fixture_id)
    FROM football.product_team_match_history h
    WHERE (NEW.entity_type = 'competition' AND h.competition_id = NEW.canonical_id)
       OR (NEW.entity_type = 'team' AND NEW.canonical_id IN (h.home_team_id, h.away_team_id))
    ORDER BY h.fixture_id;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER record_product_admission_change AFTER INSERT ON football.product_identity_admissions
    FOR EACH ROW EXECUTE FUNCTION football.record_product_admission_change();

-- +goose StatementBegin
CREATE FUNCTION football.revoke_changed_product_mapping() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text := CASE TG_TABLE_NAME WHEN 'team_provider_mappings' THEN 'team' ELSE 'competition' END;
BEGIN
    IF (to_jsonb(OLD) - 'last_seen_at') = (to_jsonb(NEW) - 'last_seen_at') THEN
        RETURN NEW;
    END IF;
    INSERT INTO football.product_identity_admissions (
        entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
        disposition, reason, source_snapshot_id, source_observed_at, evidence, evidence_sha256)
    SELECT kind, OLD.id, a.canonical_id, a.provider_code, a.provider_entity_id,
           'REVOKED', 'MAPPING_CHANGED_REVALIDATION_REQUIRED', a.source_snapshot_id,
           a.source_observed_at, a.evidence, a.evidence_sha256
    FROM football.product_identity_admissions a
    WHERE a.entity_type = kind AND a.mapping_id = OLD.id
    ORDER BY a.decided_at DESC, a.decision_id DESC LIMIT 1;
    RETURN COALESCE(NEW, OLD);
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER revoke_changed_team_mapping AFTER UPDATE OR DELETE ON football.team_provider_mappings
    FOR EACH ROW EXECUTE FUNCTION football.revoke_changed_product_mapping();
CREATE TRIGGER revoke_changed_competition_mapping AFTER UPDATE OR DELETE ON football.competition_provider_mappings
    FOR EACH ROW EXECUTE FUNCTION football.revoke_changed_product_mapping();

-- Missing old admission times are never reconstructed or backdated. Retained rows start denied.
-- Byte-verified existing mappings are admitted by the migration companion under this same policy.
SELECT football.record_product_history_decision(fixture_id) FROM football.product_team_match_history;

DROP VIEW football.product_eligible_match_history;
-- +goose StatementBegin
CREATE FUNCTION football.product_eligible_history_at(knowledge_time timestamptz)
RETURNS TABLE (
    fixture_id uuid, competition_id uuid, home_team_id uuid, away_team_id uuid,
    kickoff_at timestamptz, home_goals smallint, away_goals smallint,
    home_xg double precision, away_xg double precision, source_provider_code text,
    source_snapshot_id uuid, source_kickoff_precision text, known_at timestamptz)
LANGUAGE sql STABLE AS $$
    SELECT e.fixture_id, e.competition_id, e.home_team_id, e.away_team_id, e.kickoff_at,
           e.home_goals, e.away_goals, e.home_xg, e.away_xg, e.source_provider_code,
           e.source_snapshot_id, e.source_kickoff_precision,
           GREATEST(e.source_known_at, e.decided_at)
    FROM (SELECT DISTINCT ON (d.fixture_id) d.*
          FROM football.product_match_history_decisions d WHERE d.decided_at <= knowledge_time
          ORDER BY d.fixture_id, d.decided_at DESC, d.decision_id DESC) e
    WHERE e.eligible AND e.source_known_at <= knowledge_time
$$;
-- +goose StatementEnd
CREATE VIEW football.product_eligible_match_history AS
    SELECT * FROM football.product_eligible_history_at(statement_timestamp());

-- +goose Down
-- This preserves dated decisions and frozen historical eligibility; downgrade is intentionally denied.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'product identity admission is a forward-only migration'; END $$;
-- +goose StatementEnd
