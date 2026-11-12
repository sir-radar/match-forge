-- +goose Up
-- Acquire existing orchestration locks before any FK/DDL touches work_items.
LOCK TABLE football.product_sync_runs IN ACCESS EXCLUSIVE MODE;
LOCK TABLE football.work_items IN ACCESS EXCLUSIVE MODE NOWAIT;
-- Operational inventory references existing lineage; it never replaces source/artifact registrations.
CREATE TABLE football.storage_resources (
 resource_id text PRIMARY KEY CHECK (resource_id ~ '^[0-9a-f]{64}$'),
 backend text NOT NULL CHECK (backend IN ('filesystem','postgres','git')),
 location text NOT NULL,
 kind text NOT NULL,
 subsystem text NOT NULL,
 owner_name text NOT NULL DEFAULT '',
 logical_bytes bigint NOT NULL CHECK (logical_bytes>=0),
 allocated_bytes bigint CHECK (allocated_bytes>=0),
 sha256 text NOT NULL DEFAULT '' CHECK (sha256='' OR sha256 ~ '^[0-9a-f]{64}$'),
 protected boolean NOT NULL DEFAULT true,
 reference_count integer NOT NULL DEFAULT 0 CHECK(reference_count>=0),
 lease_until timestamptz,
 retain_until timestamptz,
 recovery_verified boolean NOT NULL DEFAULT false,
 reconstructable boolean NOT NULL DEFAULT false,
 complete boolean NOT NULL DEFAULT false,
 state text NOT NULL DEFAULT 'PROTECTED' CHECK(state IN ('PROTECTED','ACTIVE','ELIGIBLE','VERIFIED','QUARANTINED','DELETED')),
 blockers jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(blockers)='array'),
 details jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(details)='object'),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(backend,location)
);
CREATE TABLE football.storage_reviews (
 work_id uuid PRIMARY KEY REFERENCES football.work_items(work_id),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 policy_sha256 text NOT NULL CHECK(policy_sha256 ~ '^[0-9a-f]{64}$'),
 manifest_sha256 text NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
 manifest jsonb NOT NULL CHECK(jsonb_typeof(manifest)='object'),
 dry_run boolean NOT NULL DEFAULT true CHECK(dry_run),
 reclaimed_bytes bigint NOT NULL DEFAULT 0 CHECK(reclaimed_bytes=0)
);
CREATE TABLE football.storage_approvals (
 approval_id uuid PRIMARY KEY,
 work_id uuid NOT NULL REFERENCES football.storage_reviews(work_id),
 manifest_sha256 text NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
 resource_ids jsonb NOT NULL CHECK(jsonb_typeof(resource_ids)='array' AND jsonb_array_length(resource_ids)>0),
 approved_by text NOT NULL CHECK(length(approved_by)>0),
 approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL CHECK(expires_at>approved_at),
 disposition text NOT NULL CHECK(disposition IN ('REVIEWED','REJECTED'))
);
CREATE TABLE football.storage_reservations (
 resource_id uuid PRIMARY KEY,
 work_id uuid NOT NULL REFERENCES football.work_items(work_id),
 owner_name text NOT NULL,
 work_generation bigint NOT NULL CHECK(work_generation>0),
 backend_identity text NOT NULL,
 resource_identity jsonb NOT NULL DEFAULT '{}',
 reserved_bytes bigint NOT NULL CHECK(reserved_bytes>0),
 lease_until timestamptz NOT NULL,
 released_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX storage_open_reservation_device ON football.storage_reservations(backend_identity) WHERE released_at IS NULL;

-- +goose StatementBegin
CREATE FUNCTION football.storage_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'storage review and approval evidence is append-only' USING ERRCODE='55000'; END;
$$;
CREATE TRIGGER storage_reviews_immutable BEFORE UPDATE OR DELETE ON football.storage_reviews
 FOR EACH ROW EXECUTE FUNCTION football.storage_append_only();
CREATE TRIGGER storage_approvals_immutable BEFORE UPDATE OR DELETE ON football.storage_approvals
 FOR EACH ROW EXECUTE FUNCTION football.storage_append_only();
CREATE FUNCTION football.storage_no_destructive_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.state IN ('QUARANTINED','DELETED') THEN
  RAISE EXCEPTION 'destructive lifecycle transitions are disabled' USING ERRCODE='55000';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER storage_destructive_disabled BEFORE INSERT OR UPDATE ON football.storage_resources
 FOR EACH ROW EXECUTE FUNCTION football.storage_no_destructive_transition();
-- +goose StatementEnd

-- Extend the existing operator lane and common work state machine, not a second queue.
ALTER TABLE football.work_items DROP CONSTRAINT work_items_work_type_check;
ALTER TABLE football.work_items ADD CONSTRAINT work_items_work_type_check CHECK (work_type IN (
 'PROVIDER_ACQUISITION','HISTORICAL_ACQUISITION','NORMALIZATION','IDENTITY_REMEDIATION',
 'CANONICAL_RECONCILIATION','COVERAGE_REBUILD','READ_MODEL_PROJECTION','FEATURE_BUILD',
 'FORECAST_REFRESH','SIMULATION','POST_MATCH_EVALUATION','EXPERIMENT_EXECUTION','BACKUP','STORAGE_LIFECYCLE'));
ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
 sync_type IN ('MVP_SYNC','OPENFOOTBALL','FOOTBALL_DATA_UK','HISTORY_BACKFILL',
 'FORECAST_REFRESH','CONTEXT_REPORTS','PUBLIC_REPORTS','EXTERNAL_PREDICTIONS',
 'FOTMOB_SYNC','PITCHAPI_SYNC','ALL_DATA','MANUAL_BACKUP','STORAGE_LIFECYCLE'));
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.drive_sync_run_work() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item football.work_items; kind text; digest text;
BEGIN
 IF TG_OP='INSERT' THEN
  kind:=CASE WHEN NEW.sync_type='MANUAL_BACKUP' THEN 'BACKUP'
             WHEN NEW.sync_type='STORAGE_LIFECYCLE' THEN 'STORAGE_LIFECYCLE'
             WHEN NEW.sync_type='FORECAST_REFRESH' THEN 'FORECAST_REFRESH'
             ELSE 'PROVIDER_ACQUISITION' END;
  digest:=encode(sha256(convert_to(jsonb_build_object('run_id',NEW.run_id,
    'sync_type',NEW.sync_type,'parameters',NEW.parameters,'requested_date',NEW.requested_date)::text,'UTF8')),'hex');
  PERFORM football.enqueue_work(NEW.run_id,kind,'sync-run:'||NEW.run_id,digest,
    0,NEW.requested_at,1,0::double precision,0::double precision,1::double precision,
    ARRAY[]::uuid[],NULL::uuid,0::double precision);
 END IF;
 SELECT * INTO item FROM football.work_items WHERE work_id=NEW.run_id;
 IF NOT FOUND THEN RETURN NEW; END IF;
 IF NEW.status='RUNNING' AND item.state='PENDING' THEN
  SELECT * INTO item FROM football.claim_work(coalesce(NEW.worker_id,NEW.run_id::text),
    interval '2 minutes',ARRAY[item.work_type],ARRAY[NEW.run_id]);
  IF NOT FOUND THEN RAISE EXCEPTION 'sync work unavailable' USING ERRCODE='55000'; END IF;
  NEW.started_at:=item.started_at; NEW.heartbeat_at:=item.heartbeat_at;
 ELSIF NEW.status='RUNNING' AND item.state='RUNNING' THEN
  IF NEW.worker_id IS DISTINCT FROM OLD.worker_id THEN
   item:=football.cancel_work(item.work_id);NEW.status:='CANCELLED';NEW.finished_at:=clock_timestamp();NEW.error_message:='worker ownership replaced';
  ELSIF NEW.heartbeat_at>OLD.heartbeat_at THEN
   item:=football.heartbeat_work(item.work_id,NEW.worker_id,item.lease_token,item.generation,interval '2 minutes');NEW.heartbeat_at:=item.heartbeat_at;
  END IF;
 ELSIF NEW.status='CANCELLED' THEN item:=football.cancel_work(item.work_id);
 ELSIF NEW.status IN ('SUCCEEDED','FAILED') THEN
  PERFORM football.complete_sync_run_work(NEW.run_id,NEW.worker_id,NEW.status,NEW.summary,NEW.error_message);
 ELSIF NEW.status='RUNNING' THEN RAISE EXCEPTION 'sync work ownership lost' USING ERRCODE='55000';
 END IF;
 RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'storage lifecycle history requires a forward migration'; END $$;
-- +goose StatementEnd
