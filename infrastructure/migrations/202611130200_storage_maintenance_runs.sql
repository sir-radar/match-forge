-- +goose Up
-- Daily, weekly and monthly storage maintenance reports. One row per cadence and
-- slot makes each report idempotent across restarts and concurrent workers. A
-- report is read-only: it measures, detects and alerts. Deletion stays with the
-- owner-approved automatic rules and the five-hour lifecycle policy.

CREATE TABLE football.storage_maintenance_runs (
 run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 cadence text NOT NULL CHECK (cadence IN ('DAILY','WEEKLY','MONTHLY')),
 slot text NOT NULL CHECK (length(slot) BETWEEN 1 AND 32),
 state text NOT NULL DEFAULT 'RUNNING' CHECK (state IN ('RUNNING','SUCCEEDED','FAILED')),
 policy_sha256 text NOT NULL CHECK (policy_sha256 ~ '^[0-9a-f]{64}$'),
 measures jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(measures)='object'),
 findings jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(findings)='array'),
 alerts integer NOT NULL DEFAULT 0 CHECK (alerts>=0),
 error text,
 attempts integer NOT NULL DEFAULT 1 CHECK (attempts BETWEEN 1 AND 10),
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 finished_at timestamptz,
 UNIQUE (cadence, slot),
 CHECK ((state='RUNNING') = (finished_at IS NULL))
);
CREATE INDEX storage_maintenance_runs_recent ON football.storage_maintenance_runs(started_at DESC);

-- +goose StatementBegin
CREATE FUNCTION football.storage_maintenance_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR OLD.state<>'RUNNING' THEN
  RAISE EXCEPTION 'storage maintenance report % is final', OLD.run_id USING ERRCODE='55000';
 END IF;
 IF (NEW.run_id,NEW.cadence,NEW.slot) IS DISTINCT FROM (OLD.run_id,OLD.cadence,OLD.slot) THEN
  RAISE EXCEPTION 'storage maintenance identity is immutable' USING ERRCODE='55000';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER storage_maintenance_guard BEFORE UPDATE OR DELETE ON football.storage_maintenance_runs
 FOR EACH ROW EXECUTE FUNCTION football.storage_maintenance_guard();
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'storage maintenance history requires a forward migration'; END $$;
-- +goose StatementEnd
