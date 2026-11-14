-- +goose Up
-- External-only contextual associations (EXTERNAL_PREDICTION_CONTEXTUAL_MATCHING_V1).
-- Each decision is appended; a later decision supersedes the earlier one. Decisions
-- reference an existing fixture for external settlement only. They never create a
-- provider mapping, identity admission, duplicate resolution or history row.
CREATE TABLE football.external_prediction_context_matches (
    context_match_id uuid PRIMARY KEY DEFAULT uuidv7(),
    prediction_id uuid NOT NULL REFERENCES football.external_predictions(prediction_id),
    previous_context_match_id uuid UNIQUE,
    policy_version text NOT NULL CHECK (policy_version<>''),
    basis text NOT NULL CHECK (basis IN ('POLICY','REVIEW')),
    classification text NOT NULL
        CHECK (classification IN ('CONTEXTUAL_MATCH','NEEDS_REVIEW','UNMATCHED')),
    reason text NOT NULL CHECK (reason<>''),
    fixture_id uuid REFERENCES football.product_fixtures(fixture_id),
    candidate_fixture_ids uuid[] NOT NULL,
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence)='object'),
    evidence_sha256 football.sha256_hex NOT NULL,
    review_reason text,
    reviewer text,
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (context_match_id,prediction_id),
    FOREIGN KEY (previous_context_match_id,prediction_id)
        REFERENCES football.external_prediction_context_matches(context_match_id,prediction_id),
    CHECK ((classification='CONTEXTUAL_MATCH')=(fixture_id IS NOT NULL)),
    CHECK (basis='POLICY' OR (length(btrim(review_reason))>0 AND reviewer ~ '^owner:[a-f0-9]{16}$'))
);
CREATE UNIQUE INDEX external_context_root_idx ON football.external_prediction_context_matches
    (prediction_id) WHERE previous_context_match_id IS NULL;
CREATE INDEX external_context_fixture_idx ON football.external_prediction_context_matches
    (fixture_id,prediction_id) WHERE fixture_id IS NOT NULL;
CREATE INDEX external_context_candidates_idx ON football.external_prediction_context_matches
    USING gin (candidate_fixture_ids);

-- A contextual match may only name a fixture whose canonical identity is not
-- quarantined and that is its own representative.
-- +goose StatementBegin
CREATE FUNCTION football.check_external_context_match() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.classification='CONTEXTUAL_MATCH' AND EXISTS (
        SELECT 1 FROM football.product_fixtures fixture
        LEFT JOIN football.fixture_identity_resolutions r
            ON r.member_fixture_id=fixture.fixture_id AND r.active
        WHERE fixture.fixture_id=NEW.fixture_id AND (fixture.identity_status='QUARANTINED'
            OR (r.resolution_status IS NOT NULL
                AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                     OR r.representative_fixture_id<>fixture.fixture_id)))
    ) THEN
        RAISE EXCEPTION 'contextual match requires an unquarantined representative fixture';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER check_external_context_match BEFORE INSERT
    ON football.external_prediction_context_matches
    FOR EACH ROW EXECUTE FUNCTION football.check_external_context_match();
CREATE TRIGGER external_immutable BEFORE UPDATE OR DELETE
    ON football.external_prediction_context_matches
    FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER external_no_truncate BEFORE TRUNCATE
    ON football.external_prediction_context_matches
    FOR EACH STATEMENT EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER external_publication BEFORE INSERT
    ON football.external_prediction_context_matches
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();
CREATE TRIGGER enqueue_external_context_change AFTER INSERT
    ON football.external_prediction_context_matches
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_prediction_change();

CREATE VIEW football.external_prediction_context_current AS
    SELECT c.* FROM football.external_prediction_context_matches c
    WHERE NOT EXISTS (SELECT 1 FROM football.external_prediction_context_matches successor
        WHERE successor.previous_context_match_id=c.context_match_id);

-- Same columns as before. A verified binding, or a verified import-time fixture,
-- always wins; a current contextual match is used only when neither exists.
CREATE OR REPLACE VIEW football.external_prediction_effective AS
    SELECT ep.*,coalesce(binding.fixture_id,
            CASE WHEN binding.binding_id IS NULL THEN ep.fixture_id END,
            context.fixture_id) AS effective_fixture_id,
        CASE WHEN coalesce(binding.fixture_id,
                CASE WHEN binding.binding_id IS NULL THEN ep.fixture_id END) IS NULL
              AND context.fixture_id IS NOT NULL THEN 'CONTEXTUAL'
             ELSE coalesce(binding.match_status,ep.match_status) END AS effective_match_status,
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
    LEFT JOIN football.external_prediction_context_current context
        ON context.prediction_id=ep.prediction_id
    LEFT JOIN football.external_prediction_date_reviews review ON review.prediction_id=ep.prediction_id;

-- Predictions whose association could change when the catalogue near their date
-- changes: no verified association and no owner review holding the decision.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_context_dates(first_day date, last_day date)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    IF first_day IS NULL THEN RETURN; END IF;
    FOR prediction IN SELECT ep.prediction_id FROM football.external_prediction_effective ep
        LEFT JOIN football.external_prediction_context_current context USING (prediction_id)
        WHERE ep.prediction_date BETWEEN first_day-2 AND last_day+2
          AND ep.effective_match_status<>'MATCHED'
          AND (context.basis IS NULL OR context.basis='POLICY')
        ORDER BY ep.prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_context_fixtures() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE first_day date; last_day date;
BEGIN
    IF TG_OP='INSERT' THEN
        SELECT min(kickoff_at)::date,max(kickoff_at)::date INTO first_day,last_day FROM inserted;
    ELSE
        SELECT min(least(o.kickoff_at,n.kickoff_at))::date,max(greatest(o.kickoff_at,n.kickoff_at))::date
        INTO first_day,last_day FROM changed_old o JOIN changed_new n USING (fixture_id)
        WHERE (o.kickoff_at,o.home_team_id,o.away_team_id,o.competition_id,o.identity_status)
            IS DISTINCT FROM (n.kickoff_at,n.home_team_id,n.away_team_id,n.competition_id,n.identity_status);
    END IF;
    PERFORM football.enqueue_external_context_dates(first_day,last_day);
    RETURN NULL;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_context_fixture_insert AFTER INSERT ON football.product_fixtures
    REFERENCING NEW TABLE AS inserted
    FOR EACH STATEMENT EXECUTE FUNCTION football.enqueue_external_context_fixtures();
CREATE TRIGGER enqueue_external_context_fixture_update AFTER UPDATE ON football.product_fixtures
    REFERENCING OLD TABLE AS changed_old NEW TABLE AS changed_new
    FOR EACH STATEMENT EXECUTE FUNCTION football.enqueue_external_context_fixtures();

-- New trusted spellings or competition facts reopen dates where the team or
-- competition plays.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_context_names() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE first_day date; last_day date;
BEGIN
    IF TG_TABLE_NAME='product_team_aliases' THEN
        SELECT min(f.kickoff_at)::date,max(f.kickoff_at)::date INTO first_day,last_day
        FROM football.product_fixtures f WHERE f.home_team_id IN (SELECT team_id FROM inserted)
            OR f.away_team_id IN (SELECT team_id FROM inserted);
    ELSE
        SELECT min(f.kickoff_at)::date,max(f.kickoff_at)::date INTO first_day,last_day
        FROM football.product_fixtures f JOIN changed_new n USING (competition_id)
        JOIN changed_old o USING (competition_id)
        WHERE (o.name,o.country,o.competition_type,o.division)
            IS DISTINCT FROM (n.name,n.country,n.competition_type,n.division);
    END IF;
    -- Only dates that hold retained predictions are scanned.
    SELECT greatest(first_day,min(prediction_date)-2),least(last_day,max(prediction_date)+2)
        INTO first_day,last_day FROM football.external_predictions;
    IF first_day<=last_day THEN
        PERFORM football.enqueue_external_context_dates(first_day,last_day);
    END IF;
    RETURN NULL;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_context_alias AFTER INSERT ON football.product_team_aliases
    REFERENCING NEW TABLE AS inserted
    FOR EACH STATEMENT EXECUTE FUNCTION football.enqueue_external_context_names();
CREATE TRIGGER enqueue_external_context_competition AFTER UPDATE ON football.product_competitions
    REFERENCING OLD TABLE AS changed_old NEW TABLE AS changed_new
    FOR EACH STATEMENT EXECUTE FUNCTION football.enqueue_external_context_names();

-- Resolution changes reopen every prediction that listed the fixture as a candidate.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_external_context_resolution() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    FOR prediction IN SELECT DISTINCT c.prediction_id FROM football.external_prediction_context_current c
        WHERE c.candidate_fixture_ids @> ARRAY[coalesce(NEW.member_fixture_id,OLD.member_fixture_id)]
           OR c.fixture_id=coalesce(NEW.member_fixture_id,OLD.member_fixture_id)
        ORDER BY 1
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    RETURN coalesce(NEW,OLD);
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_external_context_resolution
    AFTER INSERT OR UPDATE OR DELETE ON football.fixture_identity_resolutions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_external_context_resolution();

-- Settlement evidence on a contextually matched fixture reaches its predictions too.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.enqueue_external_settlement_evidence_change() RETURNS trigger LANGUAGE plpgsql AS $$
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
        ) OR EXISTS (
            SELECT 1 FROM football.external_prediction_context_matches context
            WHERE context.prediction_id=ep.prediction_id AND context.fixture_id=fixture
        ))) OR (native_provider IS NOT NULL AND ep.provider_code=native_provider
                                     AND ep.provider_fixture_id=native_id)
        ORDER BY ep.prediction_id
    LOOP PERFORM football.enqueue_external_prediction_refresh(prediction); END LOOP;
    RETURN COALESCE(NEW,OLD);
END;
$$;
-- +goose StatementEnd

CREATE INDEX product_team_aliases_team_idx ON football.product_team_aliases(team_id);
CREATE INDEX product_provider_fixture_kickoff_idx
    ON football.product_provider_fixture_observations(kickoff_at)
    WHERE canonical_fixture_id IS NOT NULL;

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'external contextual association history is retained; roll forward'; END $$;
-- +goose StatementEnd
