-- +goose Up
-- Manual backup reuses operator-run and shared-work ownership; no new scheduler/registry.
-- Sync-run transactions can reach work_items through triggers. Let them finish
-- before taking the work lock. Work-led readers can take the reverse order, so
-- fail the transaction rather than waiting for work_items while holding sync runs.
LOCK TABLE football.product_sync_runs IN ACCESS EXCLUSIVE MODE;
LOCK TABLE football.work_items IN ACCESS EXCLUSIVE MODE NOWAIT;

ALTER TABLE football.work_items DROP CONSTRAINT work_items_work_type_check;
ALTER TABLE football.work_items ADD CONSTRAINT work_items_work_type_check CHECK (work_type IN (
 'PROVIDER_ACQUISITION','HISTORICAL_ACQUISITION','NORMALIZATION','IDENTITY_REMEDIATION',
 'CANONICAL_RECONCILIATION','COVERAGE_REBUILD','READ_MODEL_PROJECTION','FEATURE_BUILD',
 'FORECAST_REFRESH','SIMULATION','POST_MATCH_EVALUATION','EXPERIMENT_EXECUTION','BACKUP'));
ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
 sync_type IN ('MVP_SYNC','OPENFOOTBALL','FOOTBALL_DATA_UK','HISTORY_BACKFILL',
 'FORECAST_REFRESH','CONTEXT_REPORTS','PUBLIC_REPORTS','EXTERNAL_PREDICTIONS',
 'FOTMOB_SYNC','PITCHAPI_SYNC','ALL_DATA','MANUAL_BACKUP'));
-- Backup deliberately shares the existing BULK exclusion lane and preserves live lanes.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.drive_sync_run_work() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item football.work_items; kind text; digest text;
BEGIN
    IF TG_OP='INSERT' THEN
        kind:=CASE WHEN NEW.sync_type='MANUAL_BACKUP' THEN 'BACKUP'
                   WHEN NEW.sync_type='FORECAST_REFRESH' THEN 'FORECAST_REFRESH'
                   ELSE 'PROVIDER_ACQUISITION' END;
        digest:=encode(sha256(convert_to(jsonb_build_object(
            'run_id',NEW.run_id,'sync_type',NEW.sync_type,'parameters',NEW.parameters,
            'requested_date',NEW.requested_date)::text,'UTF8')),'hex');
        PERFORM football.enqueue_work(NEW.run_id,kind,'sync-run:'||NEW.run_id,digest,
            0,NEW.requested_at,1,0::double precision,0::double precision,
            1::double precision,ARRAY[]::uuid[],NULL::uuid,0::double precision);
    END IF;
    SELECT * INTO item FROM football.work_items WHERE work_id=NEW.run_id;
    IF NOT FOUND THEN RETURN NEW; END IF; -- In-flight pre-migration runs drain normally.
    IF NEW.status='RUNNING' AND item.state='PENDING' THEN
        SELECT * INTO item FROM football.claim_work(coalesce(NEW.worker_id,NEW.run_id::text),
            interval '2 minutes',ARRAY[item.work_type],ARRAY[NEW.run_id]);
        IF NOT FOUND THEN RAISE EXCEPTION 'sync work unavailable' USING ERRCODE='55000'; END IF;
        NEW.started_at:=item.started_at;
        NEW.heartbeat_at:=item.heartbeat_at;
    ELSIF NEW.status='RUNNING' AND item.state='RUNNING' THEN
        IF NEW.worker_id IS DISTINCT FROM OLD.worker_id THEN
            item:=football.cancel_work(item.work_id);
            NEW.status:='CANCELLED'; NEW.finished_at:=clock_timestamp();
            NEW.error_message:='worker ownership replaced';
        ELSIF NEW.heartbeat_at>OLD.heartbeat_at THEN
            item:=football.heartbeat_work(item.work_id,NEW.worker_id,item.lease_token,
                item.generation,interval '2 minutes');
            NEW.heartbeat_at:=item.heartbeat_at;
        END IF;
    ELSIF NEW.status='CANCELLED' THEN
        item:=football.cancel_work(item.work_id);
    ELSIF NEW.status IN ('SUCCEEDED','FAILED') THEN
        PERFORM football.complete_sync_run_work(NEW.run_id,NEW.worker_id,NEW.status,
            NEW.summary,NEW.error_message);
    ELSIF NEW.status='RUNNING' THEN
        RAISE EXCEPTION 'sync work ownership lost' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'manual backup history requires a forward migration'; END $$;
-- +goose StatementEnd
