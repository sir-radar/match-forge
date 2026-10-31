-- +goose Up
ALTER TABLE football.resolution_review_events DROP CONSTRAINT resolution_review_events_action_check;
ALTER TABLE football.resolution_review_events ADD CONSTRAINT resolution_review_events_action_check
    CHECK(action IN ('APPROVE','REJECT','CORRECT','QUARANTINE','REQUEST_EVIDENCE','BLOCK',
                    'REVALIDATE','RESOLVE_DUPLICATE','DEFER','VERIFY','RECOVER','EXCLUDE'));
CREATE TABLE football.resolution_file_recovery_work (
    work_id uuid PRIMARY KEY REFERENCES football.work_items(work_id),
    request_id uuid NOT NULL UNIQUE REFERENCES football.resolution_review_events(request_id),
    plan jsonb NOT NULL CHECK(jsonb_typeof(plan)='object'),
    outcome jsonb CHECK(outcome IS NULL OR jsonb_typeof(outcome)='object')
);
-- +goose StatementBegin
CREATE FUNCTION football.guard_resolution_file_work() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'file recovery evidence is retained'; END IF;
    IF (to_jsonb(NEW)-'outcome') IS DISTINCT FROM (to_jsonb(OLD)-'outcome')
       OR (OLD.outcome IS NOT NULL AND NEW.outcome IS DISTINCT FROM OLD.outcome) THEN
        RAISE EXCEPTION 'approved file recovery inputs and published outcome are immutable';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER preserve_resolution_file_work BEFORE UPDATE OR DELETE
    ON football.resolution_file_recovery_work FOR EACH ROW
    EXECUTE FUNCTION football.guard_resolution_file_work();
CREATE TRIGGER preserve_resolution_file_work_truncate BEFORE TRUNCATE
    ON football.resolution_file_recovery_work FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'file recovery evidence requires a forward migration'; END $$;
-- +goose StatementEnd
