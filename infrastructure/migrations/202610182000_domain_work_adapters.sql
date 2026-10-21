-- +goose Up
-- Existing operator runs and scope rows remain control/detail records. Their
-- transitions delegate ownership, expiry and retry decisions to shared work.
CREATE TABLE football.product_provider_scope_work (
    provider_code text NOT NULL,
    provider_competition_id text NOT NULL,
    season_label text NOT NULL,
    work_id uuid NOT NULL UNIQUE REFERENCES football.work_items(work_id),
    PRIMARY KEY(provider_code,provider_competition_id,season_label),
    FOREIGN KEY(provider_code,provider_competition_id,season_label)
        REFERENCES football.product_provider_history_scopes ON DELETE CASCADE
);

-- +goose StatementBegin
CREATE FUNCTION football.complete_sync_run_work(
    work_key uuid,worker_key text,outcome text,summary_value jsonb,error_value text
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE item football.work_items; digest text;
BEGIN
    SELECT * INTO STRICT item FROM football.work_items WHERE work_id=work_key;
    IF item.state IN ('PENDING','RUNNING') AND
       (item.state='PENDING' OR item.lease_until<=clock_timestamp()) THEN
        PERFORM football.claim_work(coalesce(worker_key,work_key::text),
            interval '2 minutes',ARRAY[item.work_type],ARRAY[item.work_id]);
        SELECT * INTO STRICT item FROM football.work_items WHERE work_id=work_key;
    END IF;
    IF item.state='RUNNING' THEN
        IF outcome='SUCCEEDED' THEN
            digest:=encode(sha256(convert_to(coalesce(summary_value,'null'::jsonb)::text,'UTF8')),'hex');
            item:=football.finish_work(item.work_id,coalesce(worker_key,work_key::text),item.lease_token,
                item.generation,digest::football.sha256_hex);
        ELSE
            item:=football.fail_work(item.work_id,coalesce(worker_key,work_key::text),
                item.lease_token,item.generation,'NON_RETRYABLE','SYNC_FAILED',
                coalesce(nullif(error_value,''),'sync command failed'),NULL,NULL);
        END IF;
    END IF;
    IF item.state<>outcome THEN
        RAISE EXCEPTION 'sync outcome differs from shared work' USING ERRCODE='55000';
    END IF;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.drive_sync_run_work() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item football.work_items; kind text; digest text;
BEGIN
    IF TG_OP='INSERT' THEN
        kind:=CASE WHEN NEW.sync_type='FORECAST_REFRESH' THEN 'FORECAST_REFRESH'
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
CREATE TRIGGER z_drive_sync_run_work BEFORE INSERT OR UPDATE ON football.product_sync_runs
    FOR EACH ROW EXECUTE FUNCTION football.drive_sync_run_work();

-- +goose StatementBegin
CREATE FUNCTION football.drive_provider_scope_work() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item football.work_items; identity uuid; digest text; current_work uuid;
BEGIN
    SELECT work_id INTO current_work FROM football.product_provider_scope_work
        WHERE provider_code=OLD.provider_code
          AND provider_competition_id=OLD.provider_competition_id
          AND season_label=OLD.season_label;
    IF NEW.status='RUNNING' AND (OLD.status<>'RUNNING' OR
        NEW.claim_token IS DISTINCT FROM OLD.claim_token) THEN
        PERFORM football.authorize_worker_publication();
        PERFORM football.record_transaction_lock(5,'matchforge-scope:'||NEW.claim_token::text);
        SELECT * INTO item FROM football.work_items WHERE work_id=current_work;
        IF FOUND AND item.state='CANCELLED' AND OLD.status<>'PENDING' THEN RETURN NULL; END IF;
        IF NOT FOUND OR item.state IN ('SUCCEEDED','FAILED','CANCELLED') THEN
            identity:=gen_random_uuid();
            digest:=encode(sha256(convert_to(jsonb_build_object('provider',NEW.provider_code,
                'competition',NEW.provider_competition_id,'season',NEW.season_label,
                'attempt_offset',OLD.attempts,'requested_at',OLD.next_attempt_at)::text,'UTF8')),'hex');
            PERFORM football.enqueue_work(identity,'HISTORICAL_ACQUISITION',
                'provider-scope:'||NEW.provider_code||':'||NEW.provider_competition_id
                ||':'||NEW.season_label||':'||identity,digest,0,OLD.next_attempt_at,
                2147483647-OLD.attempts,0::double precision,0::double precision,
                1::double precision,ARRAY[]::uuid[],NULL::uuid,0::double precision);
        ELSE identity:=item.work_id;
        END IF;
        SELECT * INTO item FROM football.claim_work('provider-scope:'||identity,
            interval '30 minutes',ARRAY['HISTORICAL_ACQUISITION'],ARRAY[identity]);
        IF NOT FOUND THEN RETURN NULL; END IF;
        INSERT INTO football.product_provider_scope_work
            (provider_code,provider_competition_id,season_label,work_id)
            VALUES(NEW.provider_code,NEW.provider_competition_id,NEW.season_label,identity)
            ON CONFLICT(provider_code,provider_competition_id,season_label)
            DO UPDATE SET work_id=EXCLUDED.work_id;
        NEW.claim_token:=item.lease_token;
        NEW.claimed_at:=item.heartbeat_at;
    ELSIF OLD.status='RUNNING' AND NEW.status IN ('SUCCEEDED','FAILED','DEFERRED')
        AND current_work IS NOT NULL THEN
        SELECT * INTO STRICT item FROM football.work_items WHERE work_id=current_work;
        IF item.state='CANCELLED' AND NEW.status='FAILED' THEN RETURN NEW; END IF;
        IF NEW.status='SUCCEEDED' THEN
            digest:=encode(sha256(convert_to(NEW.summary::text,'UTF8')),'hex');
            item:=football.finish_work(item.work_id,'provider-scope:'||item.work_id,
                OLD.claim_token,item.generation,digest::football.sha256_hex);
        ELSE
            item:=football.fail_work(item.work_id,'provider-scope:'||item.work_id,
                OLD.claim_token,item.generation,'RETRYABLE','PROVIDER_SCOPE_FAILED',
                coalesce(nullif(NEW.last_error,''),'provider scope did not complete'),
                NEW.next_attempt_at,NULL);
            NEW.next_attempt_at:=item.available_at;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER drive_provider_scope_work BEFORE UPDATE ON football.product_provider_history_scopes
    FOR EACH ROW EXECUTE FUNCTION football.drive_provider_scope_work();

-- +goose StatementBegin
CREATE FUNCTION football.heartbeat_provider_scope_work() RETURNS void LANGUAGE plpgsql AS $$
DECLARE token text:=nullif(current_setting('matchforge.history_claim_token',true),'');
    item football.work_items;
BEGIN
    IF token IS NULL THEN RETURN; END IF;
    SELECT work.* INTO item FROM football.product_provider_history_scopes scope
        JOIN football.product_provider_scope_work binding USING
            (provider_code,provider_competition_id,season_label)
        JOIN football.work_items work USING(work_id) WHERE scope.claim_token=token::uuid;
    IF NOT FOUND THEN RETURN; END IF; -- Compatibility for an in-flight legacy scope.
    item:=football.heartbeat_work(item.work_id,'provider-scope:'||item.work_id,
        token::uuid,item.generation,interval '30 minutes');
    UPDATE football.product_provider_history_scopes SET claimed_at=item.heartbeat_at
        WHERE claim_token=token::uuid;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.authorize_worker_publication() RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    run_key text:=nullif(current_setting('matchforge.sync_run_id',true),'');
    worker_key text:=nullif(current_setting('matchforge.sync_worker_id',true),'');
    scope_key text:=nullif(current_setting('matchforge.history_claim_token',true),'');
BEGIN
    IF run_key IS NOT NULL THEN
        PERFORM football.record_transaction_lock(5,'matchforge-run:'||run_key);
        PERFORM pg_advisory_xact_lock_shared(hashtextextended('matchforge-run:'||run_key,0));
        PERFORM 1 FROM football.product_sync_runs run
        LEFT JOIN football.work_items work ON work.work_id=run.run_id
        WHERE run.run_id=run_key::uuid AND run.worker_id=worker_key AND run.status='RUNNING'
          AND run.heartbeat_at>=clock_timestamp()-interval '2 minutes'
          AND (work.work_id IS NULL OR (work.state='RUNNING' AND work.lease_owner=worker_key
               AND work.lease_until>clock_timestamp()));
        IF NOT FOUND THEN RAISE EXCEPTION 'sync worker ownership lost' USING ERRCODE='55000'; END IF;
    END IF;
    IF scope_key IS NOT NULL THEN
        PERFORM football.record_transaction_lock(5,'matchforge-scope:'||scope_key);
        PERFORM 1 FROM football.product_provider_history_scopes scope
        WHERE scope.claim_token=scope_key::uuid AND scope.status='RUNNING'
          AND scope.claimed_at>=clock_timestamp()-interval '30 minutes'
          AND NOT EXISTS (
              SELECT 1 FROM football.product_provider_scope_work binding
              JOIN football.work_items work USING(work_id)
              WHERE binding.provider_code=scope.provider_code
                AND binding.provider_competition_id=scope.provider_competition_id
                AND binding.season_label=scope.season_label
                AND (work.state<>'RUNNING' OR work.lease_token IS DISTINCT FROM scope_key::uuid
                     OR work.lease_until<=clock_timestamp())) FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'history scope ownership lost' USING ERRCODE='55000'; END IF;
        IF NOT EXISTS (SELECT 1 FROM football.product_provider_history_scopes scope
            JOIN football.product_provider_scope_work binding USING
                (provider_code,provider_competition_id,season_label)
            WHERE scope.claim_token=scope_key::uuid) THEN
            UPDATE football.product_provider_history_scopes SET claimed_at=clock_timestamp()
                WHERE claim_token=scope_key::uuid;
        END IF;
    END IF;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.check_provider_scope_work() RETURNS void LANGUAGE plpgsql AS $$
DECLARE token text:=nullif(current_setting('matchforge.history_claim_token',true),'');
    item football.work_items;
BEGIN
    IF token IS NULL THEN RETURN; END IF;
    SELECT work.* INTO item FROM football.product_provider_history_scopes scope
        JOIN football.product_provider_scope_work binding USING
            (provider_code,provider_competition_id,season_label)
        JOIN football.work_items work USING(work_id) WHERE scope.claim_token=token::uuid;
    IF FOUND THEN
        PERFORM football.lock_work(item.work_id,'provider-scope:'||item.work_id,
            token::uuid,item.generation);
    END IF;
END;
$$;
-- +goose StatementEnd

-- Operator cancellation also fences children when invoked through WorkRegistry.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.cancel_work(work_key uuid) RETURNS football.work_items
LANGUAGE plpgsql AS $$
DECLARE item football.work_items; scope_token uuid;
BEGIN
    IF EXISTS (SELECT 1 FROM football.product_sync_runs WHERE run_id=work_key) THEN
        IF nullif(current_setting('matchforge.sync_run_id',true),'') IS NOT NULL THEN
            RAISE EXCEPTION 'sync-run control requires a separate transaction' USING ERRCODE='MFL01';
        END IF;
        PERFORM football.record_transaction_lock(5,'matchforge-run:'||work_key::text);
        PERFORM pg_advisory_xact_lock(hashtextextended('matchforge-run:'||work_key::text,0));
        IF pg_trigger_depth()=0 THEN
            UPDATE football.product_sync_runs SET status='CANCELLED',
                finished_at=clock_timestamp(),error_message='Work cancelled; publication rights revoked'
                WHERE run_id=work_key AND status IN ('QUEUED','RUNNING');
        END IF;
    END IF;
    SELECT scope.claim_token INTO scope_token FROM football.product_provider_scope_work binding
        JOIN football.product_provider_history_scopes scope USING
            (provider_code,provider_competition_id,season_label) WHERE binding.work_id=work_key;
    IF FOUND THEN
        PERFORM football.record_transaction_lock(5,'matchforge-scope:'||scope_token::text);
        PERFORM 1 FROM football.product_provider_history_scopes
            WHERE claim_token=scope_token FOR UPDATE;
    END IF;
    PERFORM football.authorize_worker_publication();
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
    SELECT * INTO STRICT item FROM football.work_items WHERE work_id=work_key FOR UPDATE;
    IF item.state IN ('SUCCEEDED','FAILED','CANCELLED') THEN RETURN item; END IF;
    UPDATE football.work_items SET state='CANCELLED',generation=generation+1,
        lease_owner=NULL,lease_token=NULL,lease_until=NULL,heartbeat_at=NULL,
        finished_at=clock_timestamp(),last_error_code='CANCELLED',
        last_error_message='Work cancelled; publication rights revoked'
        WHERE work_id=work_key RETURNING * INTO item;
    IF scope_token IS NOT NULL THEN
        UPDATE football.product_provider_history_scopes SET status='FAILED',
            last_error='Work cancelled; publication rights revoked'
            WHERE claim_token=scope_token AND status='RUNNING';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'domain queue ownership must remain in shared work; roll forward';
END $$;
-- +goose StatementEnd
