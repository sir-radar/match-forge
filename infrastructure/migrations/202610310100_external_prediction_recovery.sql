-- +goose Up

INSERT INTO football.external_prediction_sources
    (source_code,name,base_url,public_predictions,prediction_date_available,login_required,
     paid_content,automated_access_status,adapter_status,known_issues,checked_at)
VALUES('manual_import','Owner import','',false,true,false,false,'REVIEW_REQUIRED','DISABLED',
    'Owner-supplied records only; no automated collector or public-source verification.',clock_timestamp())
ON CONFLICT(source_code) DO NOTHING;

-- Source selections and all earlier settlements remain unchanged. New revisions
-- carry an explicit per-selection sequence so a return to an earlier result is
-- a new correction, independent of the caller's acquisition clock.
ALTER TABLE football.external_prediction_result_revisions
    ADD COLUMN revision_sequence bigint CHECK (revision_sequence>0),
    ADD COLUMN previous_result_revision_id uuid,
    ADD CONSTRAINT external_result_prediction_revision_unique UNIQUE(result_revision_id,prediction_id),
    ADD CONSTRAINT external_result_sequence_unique UNIQUE(prediction_id,revision_sequence),
    ADD CONSTRAINT external_result_predecessor_fk FOREIGN KEY(previous_result_revision_id,prediction_id)
        REFERENCES football.external_prediction_result_revisions(result_revision_id,prediction_id);
CREATE INDEX external_result_current_idx ON football.external_prediction_result_revisions
    (prediction_id,revision_sequence DESC NULLS LAST,settled_at DESC,result_revision_id DESC);
CREATE VIEW football.external_prediction_latest_results AS
    SELECT DISTINCT ON (prediction_id) * FROM football.external_prediction_result_revisions
    ORDER BY prediction_id,revision_sequence DESC NULLS LAST,settled_at DESC,result_revision_id DESC;

CREATE TABLE football.external_prediction_bindings (
    binding_id uuid PRIMARY KEY DEFAULT uuidv7(),
    prediction_id uuid NOT NULL REFERENCES football.external_predictions(prediction_id),
    previous_binding_id uuid UNIQUE,
    fixture_id uuid REFERENCES football.product_fixtures(fixture_id),
    mapping_id uuid REFERENCES football.match_provider_mappings(id),
    match_status text NOT NULL CHECK(match_status IN ('MATCHED','UNMATCHED')),
    evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'),
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(binding_id,prediction_id),
    FOREIGN KEY(previous_binding_id,prediction_id)
        REFERENCES football.external_prediction_bindings(binding_id,prediction_id),
    CHECK ((match_status='MATCHED' AND fixture_id IS NOT NULL AND mapping_id IS NOT NULL)
        OR (match_status='UNMATCHED' AND fixture_id IS NULL AND mapping_id IS NULL))
);
CREATE UNIQUE INDEX external_binding_root_idx ON football.external_prediction_bindings(prediction_id)
    WHERE previous_binding_id IS NULL;
CREATE INDEX external_binding_fixture_idx ON football.external_prediction_bindings(fixture_id,prediction_id);
CREATE INDEX external_binding_latest_idx ON football.external_prediction_bindings
    (prediction_id,decided_at DESC,binding_id DESC);

-- +goose StatementBegin
CREATE FUNCTION football.check_external_prediction_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.match_status='MATCHED' AND NOT EXISTS (
        SELECT 1 FROM football.external_predictions ep
        JOIN football.providers provider ON provider.code=ep.provider_code
        JOIN football.match_provider_mappings mapping ON mapping.id=NEW.mapping_id
            AND mapping.provider_id=provider.id AND mapping.provider_match_id=ep.provider_fixture_id
        JOIN football.product_fixtures fixture ON fixture.fixture_id=mapping.match_id
        WHERE ep.prediction_id=NEW.prediction_id AND fixture.fixture_id=NEW.fixture_id
            AND mapping.mapping_confidence=1
            AND mapping.mapping_method IN ('explicit_crosswalk','manual','deterministic')
            AND fixture.identity_status='VERIFIED'
            AND (mapping.valid_from IS NULL OR mapping.valid_from<=fixture.kickoff_at)
            AND (mapping.valid_to IS NULL OR mapping.valid_to>fixture.kickoff_at)
            AND mapping.first_seen_at<=statement_timestamp()
    ) THEN
        RAISE EXCEPTION 'external binding requires independently verified provider mapping';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER check_external_prediction_binding BEFORE INSERT ON football.external_prediction_bindings
    FOR EACH ROW EXECUTE FUNCTION football.check_external_prediction_binding();

CREATE TABLE football.external_prediction_date_reviews (
    review_id uuid PRIMARY KEY DEFAULT uuidv7(),
    prediction_id uuid NOT NULL UNIQUE REFERENCES football.external_predictions(prediction_id),
    source_date date,
    date_status text NOT NULL CHECK(date_status IN ('VERIFIED','MISMATCH','UNKNOWN','NOT_APPLICABLE')),
    reason text NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE football.external_prediction_collection_attempts (
    attempt_id uuid PRIMARY KEY DEFAULT uuidv7(),
    source_code text NOT NULL REFERENCES football.external_prediction_sources(source_code),
    prediction_date date NOT NULL,
    source_page text NOT NULL,
    status text NOT NULL,
    attempted boolean NOT NULL,
    parsed integer NOT NULL CHECK(parsed>=0),
    error_message text,
    collected_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX external_collection_latest_idx ON football.external_prediction_collection_attempts
    (source_code,collected_at DESC,attempt_id DESC);

CREATE TABLE football.external_prediction_captures (
    capture_id uuid PRIMARY KEY DEFAULT uuidv7(),
    prediction_id uuid NOT NULL REFERENCES football.external_predictions(prediction_id),
    observed_at timestamptz NOT NULL CHECK(isfinite(observed_at)),
    capture_kind text NOT NULL DEFAULT 'INPUT_CAPTURE'
        CHECK(capture_kind IN ('INPUT_CAPTURE','RETAINED_CAPTURE')),
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(prediction_id,observed_at)
);
CREATE INDEX external_capture_latest_idx ON football.external_prediction_captures
    (prediction_id,observed_at DESC);
INSERT INTO football.external_prediction_captures(prediction_id,observed_at,capture_kind)
    SELECT prediction_id,collected_at,'RETAINED_CAPTURE' FROM football.external_predictions;

CREATE TABLE football.external_prediction_refresh_work (
    prediction_id uuid PRIMARY KEY REFERENCES football.external_predictions(prediction_id),
    generation bigint NOT NULL DEFAULT 1 CHECK(generation>0),
    completed_generation bigint NOT NULL DEFAULT 0
        CHECK(completed_generation>=0 AND completed_generation<=generation),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz
);
CREATE INDEX external_prediction_refresh_pending_idx
    ON football.external_prediction_refresh_work(requested_at,prediction_id)
    WHERE generation>completed_generation;

-- The comparison detail row is always coordinated before settlement detail.
-- Workers use the same order with SKIP LOCKED, never holding a settlement row
-- while waiting on a provider's report invalidation transaction.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_prediction_refresh(prediction uuid)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.enqueue_product_report('COMPARISON',prediction,'LATEST');
    INSERT INTO football.external_prediction_refresh_work(prediction_id) VALUES(prediction)
    ON CONFLICT(prediction_id) DO UPDATE
    SET generation=football.external_prediction_refresh_work.generation+1,
        requested_at=CASE WHEN football.external_prediction_refresh_work.generation>
            football.external_prediction_refresh_work.completed_generation
            THEN football.external_prediction_refresh_work.requested_at ELSE clock_timestamp() END,
        completed_at=NULL;
END;
$$;
-- +goose StatementEnd

CREATE VIEW football.external_prediction_effective AS
    SELECT ep.*,coalesce(binding.fixture_id,CASE WHEN binding.binding_id IS NULL THEN ep.fixture_id END)
            AS effective_fixture_id,
        coalesce(binding.match_status,ep.match_status) AS effective_match_status,
        binding.binding_id,
        coalesce((SELECT max(capture.observed_at) FROM football.external_prediction_captures capture
            WHERE capture.prediction_id=ep.prediction_id),ep.collected_at) AS last_observed_at,
        coalesce(review.date_status,CASE WHEN ep.source_code IN ('r2bet','tips1960')
            THEN 'UNKNOWN' ELSE 'NOT_APPLICABLE' END) AS date_status
    FROM football.external_predictions ep
    LEFT JOIN LATERAL (
        SELECT b.* FROM football.external_prediction_bindings b
        WHERE b.prediction_id=ep.prediction_id AND NOT EXISTS (
            SELECT 1 FROM football.external_prediction_bindings successor
            WHERE successor.previous_binding_id=b.binding_id)
    ) binding ON true
    LEFT JOIN football.external_prediction_date_reviews review ON review.prediction_id=ep.prediction_id;
CREATE VIEW football.external_prediction_current AS
    WITH observed AS MATERIALIZED (SELECT * FROM football.external_prediction_effective),
    ranked AS (
        SELECT ep.*,
            row_number() OVER (PARTITION BY source_code,coalesce(effective_fixture_id,prediction_id),market
                ORDER BY last_observed_at DESC,prediction_id DESC) AS revision_rank,
            min(selection) OVER (PARTITION BY source_code,coalesce(effective_fixture_id,prediction_id),market,last_observed_at)
                IS DISTINCT FROM
            max(selection) OVER (PARTITION BY source_code,coalesce(effective_fixture_id,prediction_id),market,last_observed_at)
                AS source_revision_conflict
        FROM observed ep
    ), chosen AS (SELECT * FROM ranked WHERE revision_rank=1),
    last_other AS (
        SELECT chosen.prediction_id,max(other.last_observed_at) AS observed_at
        FROM chosen LEFT JOIN observed other ON other.source_code=chosen.source_code
            AND coalesce(other.effective_fixture_id,other.prediction_id)=
                coalesce(chosen.effective_fixture_id,chosen.prediction_id)
            AND other.market=chosen.market AND other.selection<>chosen.selection
        GROUP BY chosen.prediction_id
    )
    SELECT chosen.*,
        coalesce((SELECT min(capture.observed_at) FROM football.external_prediction_captures capture
            WHERE capture.prediction_id=chosen.prediction_id
              AND capture.observed_at>coalesce(last_other.observed_at,'-infinity'::timestamptz)),
            chosen.collected_at) AS revision_started_at
    FROM chosen JOIN last_other USING(prediction_id);
CREATE INDEX external_prediction_source_fixture_market_idx ON football.external_predictions
    (source_code,fixture_id,market,collected_at DESC,prediction_id DESC);

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_prediction_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.enqueue_external_prediction_refresh(NEW.prediction_id);
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_prediction_change AFTER INSERT ON football.external_predictions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_prediction_change();
CREATE TRIGGER enqueue_external_binding_change AFTER INSERT ON football.external_prediction_bindings
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_prediction_change();
CREATE TRIGGER enqueue_external_date_change AFTER INSERT ON football.external_prediction_date_reviews
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_prediction_change();
CREATE TRIGGER enqueue_external_capture_change AFTER INSERT ON football.external_prediction_captures
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_prediction_change();

-- +goose StatementBegin
CREATE FUNCTION football.record_external_initial_capture() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO football.external_prediction_captures(prediction_id,observed_at)
        VALUES(NEW.prediction_id,NEW.collected_at) ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER record_external_initial_capture AFTER INSERT ON football.external_predictions
    FOR EACH ROW EXECUTE FUNCTION football.record_external_initial_capture();


-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_fixture_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    FOR prediction IN SELECT ep.prediction_id FROM football.external_prediction_effective ep
        WHERE ep.effective_fixture_id=NEW.fixture_id ORDER BY ep.prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_fixture_change
    AFTER UPDATE OF status,home_score,away_score,result_score_basis,identity_status,kickoff_at,updated_at
    ON football.product_fixtures FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_fixture_change();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_observation_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    FOR prediction IN SELECT ep.prediction_id FROM football.external_prediction_effective ep
        WHERE ep.effective_fixture_id=NEW.canonical_fixture_id ORDER BY ep.prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_observation_change AFTER INSERT
    ON football.product_provider_fixture_observations FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_external_observation_change();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_mapping_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    FOR prediction IN SELECT ep.prediction_id FROM football.external_predictions ep
        JOIN football.providers provider ON provider.code=ep.provider_code
        WHERE provider.id=NEW.provider_id AND ep.provider_fixture_id=NEW.provider_match_id
        ORDER BY ep.prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    IF TG_OP='UPDATE' THEN
        FOR prediction IN SELECT ep.prediction_id FROM football.external_predictions ep
            JOIN football.providers provider ON provider.code=ep.provider_code
            WHERE provider.id=OLD.provider_id AND ep.provider_fixture_id=OLD.provider_match_id
            ORDER BY ep.prediction_id
        LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_mapping_change AFTER INSERT OR UPDATE
    ON football.match_provider_mappings FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_mapping_change();

-- All append-only source/result/correction records reject update, delete and truncate.
-- +goose StatementBegin
DO $$ DECLARE name text; BEGIN
    FOREACH name IN ARRAY ARRAY['external_predictions','external_prediction_results',
        'external_prediction_result_revisions','external_prediction_bindings',
        'external_prediction_date_reviews','external_prediction_collection_attempts','external_prediction_captures'] LOOP
        EXECUTE format('CREATE TRIGGER external_immutable BEFORE UPDATE OR DELETE ON football.%I
            FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable()',name);
        EXECUTE format('CREATE TRIGGER external_no_truncate BEFORE TRUNCATE ON football.%I
            FOR EACH STATEMENT EXECUTE FUNCTION football.guard_multi_model_immutable()',name);
        EXECUTE format('CREATE TRIGGER external_publication BEFORE INSERT ON football.%I
            FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication()',name);
    END LOOP;
END $$;
-- +goose StatementEnd
CREATE TRIGGER external_work_publication BEFORE INSERT OR UPDATE OR DELETE
    ON football.external_prediction_refresh_work FOR EACH STATEMENT
    EXECUTE FUNCTION football.check_worker_publication();

-- Comparison inputs bind effective mappings and date eligibility. Source rows
-- themselves remain byte-for-byte unchanged.
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
        SELECT forecast_id,payload_sha256,probabilities FROM football.product_forecasts
        WHERE fixture_id=ep.effective_fixture_id AND fixture.identity_status='VERIFIED'
            AND ep.date_status IN ('VERIFIED','NOT_APPLICABLE')
        ORDER BY created_at DESC,forecast_id DESC LIMIT 1
    ) f ON true WHERE ep.prediction_id=prediction_key;
$$;
-- +goose StatementEnd
SELECT football.enqueue_external_prediction_refresh(prediction_id)
    FROM football.external_predictions ORDER BY prediction_id;

CREATE VIEW football.external_prediction_current_results AS
    SELECT result.* FROM football.external_prediction_latest_results result
    JOIN football.external_prediction_refresh_work work USING(prediction_id)
    WHERE work.generation=work.completed_generation;

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'external source, binding and settlement histories are retained; roll forward'; END $$;
-- +goose StatementEnd
