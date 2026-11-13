-- +goose Up
CREATE TABLE football.external_prediction_fixture_evidence (
    prediction_id uuid NOT NULL REFERENCES football.external_predictions(prediction_id),
    evidence_sha256 football.sha256_hex NOT NULL,
    observed_at timestamptz NOT NULL CHECK (isfinite(observed_at)),
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    provider_code text,
    provider_fixture_id text,
    r2bet_match_id text,
    fixture_reference_url text,
    source_kickoff_text text,
    source_kickoff_at timestamptz,
    conflicting_references text[] NOT NULL,
    archive_sha256 football.sha256_hex,
    PRIMARY KEY (prediction_id,evidence_sha256),
    CHECK ((provider_code IS NULL) = (provider_fixture_id IS NULL))
);
CREATE INDEX external_fixture_evidence_native_idx
    ON football.external_prediction_fixture_evidence(provider_code,provider_fixture_id,prediction_id)
    WHERE provider_code IS NOT NULL;
CREATE INDEX external_fixture_evidence_r2bet_idx
    ON football.external_prediction_fixture_evidence(r2bet_match_id,prediction_id)
    WHERE r2bet_match_id IS NOT NULL;
CREATE TRIGGER external_immutable BEFORE UPDATE OR DELETE
    ON football.external_prediction_fixture_evidence
    FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER external_no_truncate BEFORE TRUNCATE
    ON football.external_prediction_fixture_evidence
    FOR EACH STATEMENT EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER external_publication BEFORE INSERT
    ON football.external_prediction_fixture_evidence
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();
CREATE TRIGGER enqueue_external_fixture_evidence AFTER INSERT
    ON football.external_prediction_fixture_evidence
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_prediction_change();

CREATE VIEW football.external_prediction_fixture_identity AS
SELECT ep.prediction_id,
    coalesce(ep.provider_code,supplement.provider_code) AS provider_code,
    coalesce(ep.provider_fixture_id,supplement.provider_fixture_id) AS provider_fixture_id,
    coalesce(ep.source_kickoff_at,supplement.kickoff_at) AS kickoff_at,
    (ep.mapping_provenance->>'method') IS NOT DISTINCT FROM 'CONFLICTING_NATIVE_REFERENCES'
        OR supplement.conflicting AS conflicting
FROM football.external_predictions ep
CROSS JOIN LATERAL (
    SELECT min(e.provider_code) AS provider_code,
        min(e.provider_fixture_id) AS provider_fixture_id,
        min(e.source_kickoff_at) AS kickoff_at,
        count(DISTINCT (e.provider_code,e.provider_fixture_id))
            FILTER (WHERE e.provider_code IS NOT NULL)>1
        OR count(DISTINCT e.r2bet_match_id)>1
        OR count(DISTINCT e.source_kickoff_at)>1
        OR coalesce(bool_or(cardinality(e.conflicting_references)>0
            OR (ep.provider_code IS NOT NULL AND e.provider_code IS NOT NULL
                AND (ep.provider_code,ep.provider_fixture_id)<>(e.provider_code,e.provider_fixture_id))
            OR (ep.source_kickoff_at IS NOT NULL AND e.source_kickoff_at<>ep.source_kickoff_at)
            OR (ep.mapping_provenance->>'r2bet_match_id')<>e.r2bet_match_id),false) AS conflicting
    FROM football.external_prediction_fixture_evidence e
    WHERE e.prediction_id=ep.prediction_id
) supplement;

-- Dispatch the same durable work for late references, native observations,
-- mapping rekeys and links. Both prior and current keys can have dependants.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_fixture_evidence_dependants(
    native_provider text, native_id text
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    FOR prediction IN
        SELECT prediction_id FROM football.external_prediction_fixture_evidence
            WHERE provider_code=native_provider AND provider_fixture_id=native_id
        UNION
        SELECT prediction_id FROM football.external_prediction_fixture_evidence
            WHERE native_provider='api_football' AND r2bet_match_id=native_id
        ORDER BY prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_fixture_evidence_mapping() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP<>'DELETE' THEN
        PERFORM football.enqueue_external_fixture_evidence_dependants(
            (SELECT code FROM football.providers WHERE id=NEW.provider_id),NEW.provider_match_id);
    END IF;
    IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND (OLD.provider_id,OLD.provider_match_id)
                                         IS DISTINCT FROM (NEW.provider_id,NEW.provider_match_id)) THEN
        PERFORM football.enqueue_external_fixture_evidence_dependants(
            (SELECT code FROM football.providers WHERE id=OLD.provider_id),OLD.provider_match_id);
    END IF;
    RETURN coalesce(NEW,OLD);
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_fixture_evidence_mapping
    AFTER INSERT OR UPDATE OR DELETE ON football.match_provider_mappings
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_fixture_evidence_mapping();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_fixture_evidence_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.enqueue_external_fixture_evidence_dependants(NEW.provider_code,NEW.provider_match_id);
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_fixture_evidence_observation
    AFTER INSERT ON football.product_provider_fixture_observations
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_fixture_evidence_observation();
CREATE TRIGGER enqueue_external_fixture_evidence_decision
    AFTER INSERT ON football.product_provider_mapping_decisions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_fixture_evidence_observation();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'external fixture evidence is retained; roll forward'; END $$;
-- +goose StatementEnd
