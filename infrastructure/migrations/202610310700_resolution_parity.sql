-- +goose Up
ALTER TABLE football.resolution_review_events DROP CONSTRAINT resolution_review_events_action_check;
ALTER TABLE football.resolution_review_events ADD CONSTRAINT resolution_review_events_action_check
 CHECK(action IN ('APPROVE','REJECT','CORRECT','QUARANTINE','REQUEST_EVIDENCE','BLOCK',
 'REVALIDATE','RESOLVE_DUPLICATE','DEFER','VERIFY','RECOVER','EXCLUDE','RECHECK_PARITY'));
CREATE TABLE football.resolution_parity_work (
 work_id uuid PRIMARY KEY REFERENCES football.work_items(work_id),
 request_id uuid NOT NULL UNIQUE REFERENCES football.resolution_review_events(request_id),
 inputs jsonb NOT NULL CHECK(jsonb_typeof(inputs)='object'),
 outcome jsonb CHECK(outcome IS NULL OR jsonb_typeof(outcome)='object')
);
CREATE TRIGGER preserve_resolution_parity_work BEFORE UPDATE OR DELETE
 ON football.resolution_parity_work FOR EACH ROW EXECUTE FUNCTION football.guard_resolution_recovery();
CREATE TRIGGER preserve_resolution_parity_truncate BEFORE TRUNCATE
 ON football.resolution_parity_work FOR EACH STATEMENT EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'parity verification history requires a forward migration'; END $$;
-- +goose StatementEnd
