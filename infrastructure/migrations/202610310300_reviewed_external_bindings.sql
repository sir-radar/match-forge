-- +goose Up
CREATE VIEW football.product_prematch_forecasts AS
SELECT forecast.* FROM football.product_forecasts forecast
JOIN football.product_fixtures fixture ON fixture.fixture_id=forecast.fixture_id
WHERE forecast.created_at<fixture.kickoff_at
    AND forecast.football_cutoff<=forecast.created_at
    AND forecast.knowledge_cutoff<=forecast.created_at;

-- A reviewed source capture may bind to independent verified native evidence.
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
            AND (mapping.valid_from IS NULL OR mapping.valid_from<=fixture.kickoff_at)
            AND (mapping.valid_to IS NULL OR mapping.valid_to>fixture.kickoff_at)
            AND mapping.first_seen_at<=statement_timestamp()
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
CREATE FUNCTION football.enqueue_reviewed_external_mapping_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    FOR prediction IN SELECT DISTINCT prediction_id FROM football.external_prediction_bindings
        WHERE mapping_id=NEW.id ORDER BY prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_reviewed_external_mapping_change AFTER UPDATE ON football.match_provider_mappings
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_reviewed_external_mapping_change();

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.public_comparison_source(prediction_key uuid)
RETURNS jsonb LANGUAGE sql STABLE SET timezone='UTC' AS $$
    SELECT jsonb_build_object('prediction_id',ep.prediction_id,'market',ep.market,
        'selection',ep.selection,'fixture_id',ep.effective_fixture_id,'binding_id',ep.binding_id,
        'date_status',ep.date_status,'forecast_id',f.forecast_id,
        'forecast_payload_sha256',f.payload_sha256,'probabilities',f.probabilities)
    FROM football.external_prediction_effective ep
    LEFT JOIN football.product_fixtures fixture ON fixture.fixture_id=ep.effective_fixture_id
    LEFT JOIN LATERAL (
        SELECT forecast_id,payload_sha256,probabilities FROM football.product_prematch_forecasts
        WHERE fixture_id=ep.effective_fixture_id AND fixture.identity_status='VERIFIED'
            AND ep.date_status IN ('VERIFIED','NOT_APPLICABLE')
        ORDER BY created_at DESC,forecast_id DESC LIMIT 1
    ) f ON true WHERE ep.prediction_id=prediction_key;
$$;
-- +goose StatementEnd
SELECT football.enqueue_external_prediction_refresh(prediction_id)
    FROM football.external_predictions ORDER BY prediction_id;

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'reviewed external binding history is retained; roll forward'; END $$;
-- +goose StatementEnd
