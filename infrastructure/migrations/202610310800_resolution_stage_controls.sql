-- +goose Up
ALTER TABLE football.resolution_review_events DROP CONSTRAINT resolution_review_events_action_check;
ALTER TABLE football.resolution_review_events ADD CONSTRAINT resolution_review_events_action_check
 CHECK(action IN ('APPROVE','REJECT','CORRECT','QUARANTINE','REQUEST_EVIDENCE','BLOCK',
 'REVALIDATE','RESOLVE_DUPLICATE','DEFER','VERIFY','RECOVER','EXCLUDE','RECHECK_PARITY',
 'REHEARSE_STAGE','ROLLBACK_STAGE','SWITCH_STAGE'));
CREATE TABLE football.resolution_stage_work (
 work_id uuid PRIMARY KEY REFERENCES football.work_items(work_id),
 request_id uuid NOT NULL UNIQUE REFERENCES football.resolution_review_events(request_id),
 inputs jsonb NOT NULL CHECK(jsonb_typeof(inputs)='object'),
 outcome jsonb CHECK(outcome IS NULL OR jsonb_typeof(outcome)='object')
);
CREATE TRIGGER preserve_resolution_stage_work BEFORE UPDATE OR DELETE
 ON football.resolution_stage_work FOR EACH ROW EXECUTE FUNCTION football.guard_resolution_recovery();
CREATE TRIGGER preserve_resolution_stage_work_truncate BEFORE TRUNCATE
 ON football.resolution_stage_work FOR EACH STATEMENT EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
CREATE TABLE football.resolution_stage_events (
 stage integer NOT NULL CHECK(stage BETWEEN 1 AND 13),
 generation bigint NOT NULL CHECK(generation>0),
 request_id uuid NOT NULL UNIQUE REFERENCES football.resolution_review_events(request_id),
 work_id uuid NOT NULL REFERENCES football.resolution_stage_work(work_id),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 result jsonb NOT NULL CHECK(jsonb_typeof(result)='object'),
 PRIMARY KEY(stage,generation)
);
-- +goose StatementBegin
CREATE FUNCTION football.guard_resolution_stage_event_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM football.resolution_stage_work b
               JOIN football.resolution_review_events e USING(request_id)
               WHERE b.work_id=NEW.work_id AND b.request_id=NEW.request_id
                 AND b.inputs->>'stage'=NEW.stage::text AND e.case_key='stage:'||NEW.stage::text) THEN
   RAISE EXCEPTION 'stage event must retain its exact approved stage and work request';
 END IF;
 RETURN NEW;
END $$;
-- +goose StatementEnd
CREATE TRIGGER guard_resolution_stage_event_scope BEFORE INSERT
 ON football.resolution_stage_events FOR EACH ROW EXECUTE FUNCTION football.guard_resolution_stage_event_scope();
CREATE TRIGGER preserve_resolution_stage_events BEFORE UPDATE OR DELETE
 ON football.resolution_stage_events FOR EACH ROW EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
CREATE TRIGGER preserve_resolution_stage_events_truncate BEFORE TRUNCATE
 ON football.resolution_stage_events FOR EACH STATEMENT EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
CREATE TABLE football.resolution_stage_settings (
 stage integer PRIMARY KEY CHECK(stage BETWEEN 1 AND 13),
 generation bigint NOT NULL DEFAULT 0 CHECK(generation>=0),
 route text NOT NULL DEFAULT 'LEGACY' CHECK(route IN('LEGACY','V2')),
 trial_work_id uuid REFERENCES football.resolution_stage_work(work_id),
 trial_lease_token uuid,
 trial_generation bigint,
 CHECK((trial_work_id IS NULL AND trial_lease_token IS NULL AND trial_generation IS NULL)
    OR (trial_work_id IS NOT NULL AND trial_lease_token IS NOT NULL AND trial_generation IS NOT NULL))
);
INSERT INTO football.resolution_stage_settings(stage) SELECT generate_series(1,13);
-- +goose StatementBegin
CREATE FUNCTION football.guard_resolution_stage_settings() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP<>'UPDATE' THEN RAISE EXCEPTION 'stage settings cannot be removed or added'; END IF;
 IF NEW.stage<>OLD.stage OR NEW.generation<>OLD.generation+1 THEN
   RAISE EXCEPTION 'stage configuration requires the next exact generation';
 END IF;
 IF NEW.route='V2' THEN
   IF current_database() !~ '^football_(correction|resolution_rehearsal)_[a-f0-9]{32}$'
      OR NEW.stage<>8 OR NEW.trial_work_id IS NULL THEN
     RAISE EXCEPTION 'only isolated leased read-model rehearsals have a runtime binding';
   END IF;
   IF NOT EXISTS(SELECT 1 FROM football.resolution_stage_work b JOIN football.work_items w USING(work_id)
       WHERE b.work_id=NEW.trial_work_id AND b.inputs->>'action'='REHEARSE_STAGE'
         AND b.inputs->>'stage'='8' AND w.state='RUNNING'
         AND w.lease_token=NEW.trial_lease_token AND w.generation=NEW.trial_generation
         AND w.lease_until>clock_timestamp()) THEN
     RAISE EXCEPTION 'stage rehearsal requires its current approved publication lease';
   END IF;
 ELSIF NOT EXISTS(SELECT 1 FROM football.resolution_stage_events e
                  JOIN football.resolution_stage_work b USING(work_id)
                  WHERE e.stage=NEW.stage AND e.generation=NEW.generation
                    AND b.request_id=e.request_id AND b.inputs->>'stage'=NEW.stage::text) THEN
   RAISE EXCEPTION 'stable stage configuration requires an immutable event';
 END IF;
 RETURN NEW;
END $$;
-- +goose StatementEnd
CREATE TRIGGER guard_resolution_stage_settings BEFORE UPDATE OR DELETE OR INSERT
 ON football.resolution_stage_settings FOR EACH ROW EXECUTE FUNCTION football.guard_resolution_stage_settings();
CREATE TRIGGER guard_resolution_stage_settings_truncate BEFORE TRUNCATE
 ON football.resolution_stage_settings FOR EACH STATEMENT EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
-- +goose StatementBegin
CREATE FUNCTION football.resolution_fixture_route() RETURNS text LANGUAGE sql VOLATILE AS $$
 SELECT CASE WHEN EXISTS(
   SELECT 1 FROM football.resolution_stage_settings s
   JOIN football.work_items w ON w.work_id=s.trial_work_id
   JOIN football.resolution_stage_work b ON b.work_id=w.work_id
   WHERE s.stage=8 AND s.route='V2' AND b.inputs->>'action'='REHEARSE_STAGE'
     AND current_database() ~ '^football_(correction|resolution_rehearsal)_[a-f0-9]{32}$'
     AND w.state='RUNNING' AND w.lease_token=s.trial_lease_token
     AND w.generation=s.trial_generation AND w.lease_until>clock_timestamp()
 ) THEN 'V2' ELSE 'LEGACY' END
$$;
-- +goose StatementEnd
-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'stage configuration evidence requires a forward migration'; END $$;
-- +goose StatementEnd
