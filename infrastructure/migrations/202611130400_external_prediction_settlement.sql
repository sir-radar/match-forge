-- +goose Up
ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
    sync_type IN ('MVP_SYNC','OPENFOOTBALL','FOOTBALL_DATA_UK','HISTORY_BACKFILL',
        'FORECAST_REFRESH','CONTEXT_REPORTS','PUBLIC_REPORTS','EXTERNAL_PREDICTIONS',
        'EXTERNAL_PREDICTION_SETTLEMENT','FOTMOB_SYNC','PITCHAPI_SYNC','ALL_DATA',
        'MANUAL_BACKUP','STORAGE_LIFECYCLE')
);

-- Newly qualified scores or recorded conflicts can change settlement eligibility
-- even when the canonical fixture row itself has not changed.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_settlement_evidence_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid; fixture uuid; native_provider text; native_id text;
BEGIN
    IF TG_TABLE_NAME='product_match_history_decisions' THEN
        fixture:=NEW.fixture_id;
    ELSIF TG_TABLE_NAME='product_source_result_conflicts' THEN
        fixture:=NEW.canonical_match_id;
    ELSIF TG_TABLE_NAME='fixture_identity_resolutions' THEN
        fixture:=COALESCE(NEW.member_fixture_id,OLD.member_fixture_id);
    ELSE
        native_provider:=NEW.provider_code;
        native_id:=NEW.provider_match_id;
    END IF;
    FOR prediction IN SELECT ep.prediction_id FROM football.external_predictions ep
        WHERE (fixture IS NOT NULL AND (ep.fixture_id=fixture OR EXISTS (
            SELECT 1 FROM football.external_prediction_bindings binding
            WHERE binding.prediction_id=ep.prediction_id AND binding.fixture_id=fixture
        ))) OR (native_provider IS NOT NULL AND ep.provider_code=native_provider
                                     AND ep.provider_fixture_id=native_id)
        ORDER BY ep.prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    RETURN COALESCE(NEW,OLD);
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_history_decision
    AFTER INSERT ON football.product_match_history_decisions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_settlement_evidence_change();
CREATE TRIGGER enqueue_external_result_conflict
    AFTER INSERT ON football.product_source_result_conflicts
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_settlement_evidence_change();

CREATE INDEX external_prediction_native_fixture_idx
    ON football.external_predictions(provider_code,provider_fixture_id)
    WHERE provider_code IS NOT NULL;
CREATE INDEX external_prediction_original_fixture_idx
    ON football.external_predictions(fixture_id) WHERE fixture_id IS NOT NULL;
CREATE TRIGGER enqueue_external_native_observation
    AFTER INSERT ON football.product_provider_fixture_observations
    FOR EACH ROW WHEN (NEW.canonical_fixture_id IS NULL)
    EXECUTE FUNCTION football.enqueue_external_settlement_evidence_change();
CREATE TRIGGER enqueue_external_native_conflict
    AFTER INSERT ON football.product_provider_mapping_decisions
    FOR EACH ROW WHEN (NEW.disposition='CONTRADICTORY')
    EXECUTE FUNCTION football.enqueue_external_settlement_evidence_change();
CREATE TRIGGER enqueue_external_identity_resolution
    AFTER INSERT OR UPDATE OR DELETE ON football.fixture_identity_resolutions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_settlement_evidence_change();

-- The original mapping trigger handles explicit native IDs. R2Bet keeps its
-- source link as a candidate until independent context corroborates it.
CREATE INDEX external_r2bet_reference_idx ON football.external_predictions
    ((mapping_provenance->>'r2bet_match_id')) WHERE source_code='r2bet';
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_r2bet_mapping() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    IF EXISTS (SELECT 1 FROM football.providers WHERE id=NEW.provider_id AND code='api_football') THEN
        FOR prediction IN SELECT prediction_id FROM football.external_predictions
            WHERE source_code='r2bet'
              AND mapping_provenance->>'r2bet_match_id'=NEW.provider_match_id
            ORDER BY prediction_id
        LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_r2bet_mapping
    AFTER INSERT OR UPDATE ON football.match_provider_mappings
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_r2bet_mapping();

-- +goose Down
DROP TRIGGER enqueue_external_r2bet_mapping ON football.match_provider_mappings;
DROP FUNCTION football.enqueue_external_r2bet_mapping();
DROP INDEX football.external_r2bet_reference_idx;
DROP TRIGGER enqueue_external_identity_resolution ON football.fixture_identity_resolutions;
DROP TRIGGER enqueue_external_native_conflict ON football.product_provider_mapping_decisions;
DROP TRIGGER enqueue_external_native_observation ON football.product_provider_fixture_observations;
DROP INDEX football.external_prediction_original_fixture_idx;
DROP INDEX football.external_prediction_native_fixture_idx;
DROP TRIGGER enqueue_external_result_conflict ON football.product_source_result_conflicts;
DROP TRIGGER enqueue_external_history_decision ON football.product_match_history_decisions;
DROP FUNCTION football.enqueue_external_settlement_evidence_change();
ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
    sync_type IN ('MVP_SYNC','OPENFOOTBALL','FOOTBALL_DATA_UK','HISTORY_BACKFILL',
        'FORECAST_REFRESH','CONTEXT_REPORTS','PUBLIC_REPORTS','EXTERNAL_PREDICTIONS',
        'FOTMOB_SYNC','PITCHAPI_SYNC','ALL_DATA','MANUAL_BACKUP','STORAGE_LIFECYCLE')
) NOT VALID;
