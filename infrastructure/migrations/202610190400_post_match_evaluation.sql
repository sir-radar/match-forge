-- +goose Up

-- Monitoring snapshots do not replace forecasts, final-result owners or research evaluations.
CREATE TABLE football.post_match_evaluation_inputs (
    input_sha256 football.sha256_hex PRIMARY KEY,
    work_id uuid NOT NULL UNIQUE REFERENCES football.work_items(work_id),
    forecast_id uuid NOT NULL REFERENCES football.product_forecasts(forecast_id),
    fixture_id uuid NOT NULL REFERENCES football.product_fixtures(fixture_id),
    horizon text NOT NULL CHECK (horizon IN ('LATEST','7D','3D','24H','6H','1H','15M')),
    outcome_known_at timestamptz NOT NULL CHECK (isfinite(outcome_known_at)),
    home_goals smallint NOT NULL CHECK (home_goals>=0),
    away_goals smallint NOT NULL CHECK (away_goals>=0),
    record_bytes bytea NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (encode(sha256(record_bytes),'hex')=input_sha256),
    CHECK (convert_from(record_bytes,'UTF8')::jsonb->>'contract'
           IS NOT DISTINCT FROM 'PostMatchEvaluationInput'),
    CHECK ((convert_from(record_bytes,'UTF8')::jsonb->>'forecast_id')::uuid
           IS NOT DISTINCT FROM forecast_id),
    CHECK ((convert_from(record_bytes,'UTF8')::jsonb->>'fixture_id')::uuid
           IS NOT DISTINCT FROM fixture_id),
    CHECK (convert_from(record_bytes,'UTF8')::jsonb->>'horizon' IS NOT DISTINCT FROM horizon),
    CHECK ((convert_from(record_bytes,'UTF8')::jsonb->>'outcome_known_at')::timestamptz
           IS NOT DISTINCT FROM outcome_known_at),
    CHECK ((convert_from(record_bytes,'UTF8')::jsonb->>'home_goals')::smallint
           IS NOT DISTINCT FROM home_goals),
    CHECK ((convert_from(record_bytes,'UTF8')::jsonb->>'away_goals')::smallint
           IS NOT DISTINCT FROM away_goals)
);
CREATE INDEX post_match_input_lookup_idx ON football.post_match_evaluation_inputs
    (forecast_id,horizon,outcome_known_at,home_goals,away_goals);

CREATE TABLE football.post_match_evaluations (
    input_sha256 football.sha256_hex PRIMARY KEY
        REFERENCES football.post_match_evaluation_inputs(input_sha256),
    result_sha256 football.sha256_hex NOT NULL,
    record_bytes bytea NOT NULL,
    evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (encode(sha256(record_bytes),'hex')=result_sha256),
    CHECK (convert_from(record_bytes,'UTF8')::jsonb->>'contract'
           IS NOT DISTINCT FROM 'PostMatchEvaluation'),
    CHECK (convert_from(record_bytes,'UTF8')::jsonb->>'input_sha256'
           IS NOT DISTINCT FROM input_sha256::text),
    CHECK (convert_from(record_bytes,'UTF8')::jsonb->>'status' IS NOT NULL
       AND convert_from(record_bytes,'UTF8')::jsonb->>'status' IN ('COMPLETE','PARTIAL','UNSCORABLE'))
);
CREATE INDEX post_match_evaluations_clock_idx ON football.post_match_evaluations(evaluated_at);

CREATE TRIGGER post_match_inputs_immutable BEFORE UPDATE OR DELETE
ON football.post_match_evaluation_inputs FOR EACH ROW
EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER post_match_inputs_no_truncate BEFORE TRUNCATE
ON football.post_match_evaluation_inputs FOR EACH STATEMENT
EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER post_match_evaluations_immutable BEFORE UPDATE OR DELETE
ON football.post_match_evaluations FOR EACH ROW
EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER post_match_evaluations_no_truncate BEFORE TRUNCATE
ON football.post_match_evaluations FOR EACH STATEMENT
EXECUTE FUNCTION football.guard_multi_model_immutable();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'post-match evidence is immutable; use a forward migration';
END $$;
-- +goose StatementEnd
