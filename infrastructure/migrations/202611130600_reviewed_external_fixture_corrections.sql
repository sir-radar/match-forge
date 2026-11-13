-- +goose Up
-- A reviewed replacement can qualify retrospective settlement after kickoff.
-- Its historical mapping and the resolution must identify the same native match.
CREATE VIEW football.external_reviewed_fixture_mappings AS
SELECT DISTINCT replacement.id AS mapping_id
FROM football.fixture_identity_resolutions resolution
JOIN football.product_provider_mapping_decisions decision
  ON decision.decision_id::text=resolution.evidence_json->>'provider_mapping_decision_id'
 AND (decision.disposition='MANUAL_ACCEPTED' OR (
     decision.disposition='AUTO_ACCEPTED' AND decision.evidence->>'rule'=
       'admitted_competition_home_away_exact_kickoff_native_fixture_id'))
 AND decision.candidate_fixture_id=resolution.representative_fixture_id
JOIN football.providers p ON p.code=decision.provider_code
JOIN football.match_provider_mappings original ON original.provider_id=p.id
 AND original.provider_match_id=decision.provider_match_id
 AND original.match_id=resolution.member_fixture_id
JOIN football.match_provider_mappings replacement ON replacement.provider_id=p.id
 AND replacement.provider_match_id=original.provider_match_id
 AND replacement.match_id=resolution.representative_fixture_id
 AND replacement.mapping_method='manual' AND replacement.mapping_confidence=1
 AND replacement.valid_to IS NULL AND replacement.valid_from=original.valid_to
 AND replacement.source_snapshot_id=decision.source_snapshot_id
JOIN football.source_snapshots snap ON snap.id=replacement.source_snapshot_id
 AND snap.provider_id=p.id AND snap.status='validated'
JOIN football.product_fixtures fixture ON fixture.fixture_id=replacement.match_id
JOIN football.product_fixtures old_fixture ON old_fixture.fixture_id=original.match_id
WHERE resolution.active AND resolution.resolution_status='DUPLICATE_RESOLVED'
 AND resolution.member_fixture_id<>resolution.representative_fixture_id
 AND resolution.evidence_json->>'provider'=p.code
 AND resolution.evidence_json->>'provider_match_id'=original.provider_match_id
 AND resolution.evidence_json->>'original_fixture_id'=original.match_id::text
 AND resolution.evidence_json->>'reviewed_fixture_id'=replacement.match_id::text
 AND resolution.evidence_json->>'source_snapshot_id'=snap.id::text
 AND fixture.kickoff_at=old_fixture.kickoff_at
 AND (original.valid_from IS NULL OR original.valid_from<=fixture.kickoff_at)
 AND original.valid_to>fixture.kickoff_at
 AND original.mapping_confidence=1
 AND original.mapping_method IN ('explicit_crosswalk','manual','deterministic')
 AND NOT EXISTS (
     SELECT 1 FROM football.product_provider_mapping_decisions conflict
     WHERE conflict.provider_code=p.code AND conflict.provider_match_id=original.provider_match_id
       AND conflict.disposition='CONTRADICTORY' AND conflict.created_at>=decision.created_at
 )
 AND decision.created_at<=statement_timestamp()
 AND resolution.created_at<=statement_timestamp()
 AND NOT EXISTS (
     SELECT 1 FROM football.fixture_identity_resolutions target
     WHERE target.member_fixture_id=fixture.fixture_id AND target.active
       AND (target.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
            OR target.representative_fixture_id<>fixture.fixture_id)
 );

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.check_external_prediction_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.match_status='MATCHED' AND NOT EXISTS (
        SELECT 1 FROM football.external_predictions ep
        JOIN football.match_provider_mappings mapping ON mapping.id=NEW.mapping_id
        JOIN football.providers provider ON provider.id=mapping.provider_id
        JOIN football.product_fixtures fixture ON fixture.fixture_id=mapping.match_id
        WHERE ep.prediction_id=NEW.prediction_id AND fixture.fixture_id=NEW.fixture_id
            AND mapping.mapping_confidence=1
            AND mapping.mapping_method IN ('explicit_crosswalk','manual','deterministic')
            AND fixture.identity_status='VERIFIED'
            AND mapping.first_seen_at<=statement_timestamp()
            AND (
                ((mapping.valid_from IS NULL OR mapping.valid_from<=fixture.kickoff_at)
                 AND (mapping.valid_to IS NULL OR mapping.valid_to>fixture.kickoff_at))
                OR (NEW.evidence->>'method'='REVIEWED_VERIFIED_PROVIDER_ID' AND EXISTS (
                    SELECT 1 FROM football.external_reviewed_fixture_mappings reviewed
                    WHERE reviewed.mapping_id=mapping.id))
            )
            AND ((provider.code=ep.provider_code AND mapping.provider_match_id=ep.provider_fixture_id)
                OR (ep.provider_code IS NULL AND ep.provider_fixture_id IS NULL
                    AND NEW.evidence->>'method'='REVIEWED_VERIFIED_PROVIDER_ID'
                    AND length(btrim(NEW.evidence->>'review_reason'))>0
                    AND NEW.evidence->>'source_revision_sha256'=ep.revision_sha256
                    AND NEW.evidence->>'source_snapshot_id'=mapping.source_snapshot_id::text))
    ) THEN RAISE EXCEPTION 'external binding requires independently verified provider mapping';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_reviewed_fixture_resolution() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP<>'DELETE' THEN
        PERFORM football.enqueue_external_fixture_evidence_dependants(
            NEW.evidence_json->>'provider',NEW.evidence_json->>'provider_match_id');
    END IF;
    IF TG_OP<>'INSERT' THEN
        PERFORM football.enqueue_external_fixture_evidence_dependants(
            OLD.evidence_json->>'provider',OLD.evidence_json->>'provider_match_id');
    END IF;
    RETURN coalesce(NEW,OLD);
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_reviewed_fixture_resolution
    AFTER INSERT OR UPDATE OR DELETE ON football.fixture_identity_resolutions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_reviewed_fixture_resolution();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'reviewed external fixture bindings are retained; roll forward'; END $$;
-- +goose StatementEnd
