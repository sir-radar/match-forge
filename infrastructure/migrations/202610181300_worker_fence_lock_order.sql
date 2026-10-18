-- +goose Up

-- Existing run/scope fencing precedes domain coordination. Retain the same
-- ownership checks, heartbeat windows and cancellation serialization.

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean DEFAULT false
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    ledger jsonb:=coalesce(nullif(current_setting('matchforge.lock_order',true),''),
        '{"held":{}}')::jsonb;
    declaration jsonb;
    previous_class integer;
    previous_key text;
BEGIN
    IF lock_class IS NULL OR lock_class NOT IN (5,10,20,30,40,50,55,56,57,58,59,60,65,70,75,80)
       OR lock_key IS NULL OR btrim(lock_key)='' OR legacy_hash IS NULL THEN
        RAISE EXCEPTION 'explicit lock class, key and hash convention required' USING ERRCODE='22023';
    END IF;
    declaration:=jsonb_build_object('class',lock_class,'legacy_hash',legacy_hash);
    IF (ledger->'held') ? lock_key THEN
        IF ledger->'held'->lock_key IS DISTINCT FROM declaration THEN
            RAISE EXCEPTION 'held lock cannot change class or hash convention' USING ERRCODE='MFL01';
        END IF;
        RETURN;
    END IF;
    previous_class:=(ledger->>'class')::integer;
    previous_key:=ledger->>'key';
    IF lock_class<previous_class OR (lock_class=previous_class
        AND (lock_key COLLATE "C")<(previous_key COLLATE "C")) THEN
        RAISE EXCEPTION 'transaction lock order violation: %/% follows %/%',
            lock_class,lock_key,previous_class,previous_key USING ERRCODE='MFL01';
    END IF;
    ledger:=jsonb_set(ledger,'{held}',coalesce(ledger->'held','{}'::jsonb)
        ||jsonb_build_object(lock_key,declaration))
        ||jsonb_build_object('class',lock_class,'key',lock_key);
    PERFORM set_config('matchforge.lock_order',ledger::text,true);
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.authorize_worker_publication() RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    run_key text := NULLIF(current_setting('matchforge.sync_run_id', true), '');
    worker_key text := NULLIF(current_setting('matchforge.sync_worker_id', true), '');
    scope_key text := NULLIF(current_setting('matchforge.history_claim_token', true), '');
BEGIN
    IF run_key IS NOT NULL THEN
        PERFORM football.record_transaction_lock(5,'matchforge-run:'||run_key);
        PERFORM pg_advisory_xact_lock_shared(hashtextextended('matchforge-run:'||run_key,0));
        PERFORM 1 FROM football.product_sync_runs
         WHERE run_id=run_key::uuid AND worker_id=worker_key
           AND status='RUNNING'
           AND heartbeat_at>=clock_timestamp()-interval '2 minutes';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'sync worker ownership lost' USING ERRCODE='55000';
        END IF;
    END IF;
    IF scope_key IS NOT NULL THEN
        PERFORM football.record_transaction_lock(5,'matchforge-scope:'||scope_key);
        UPDATE football.product_provider_history_scopes SET claimed_at=clock_timestamp()
         WHERE claim_token=scope_key::uuid AND status='RUNNING'
           AND claimed_at>=clock_timestamp()-interval '30 minutes';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'history scope ownership lost' USING ERRCODE='55000';
        END IF;
    END IF;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.check_worker_publication() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.authorize_worker_publication();
    RETURN NULL;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.acquire_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean DEFAULT false,
    wait_for_lock boolean DEFAULT true
) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE previous_ledger text;
    acquired boolean;
BEGIN
    IF wait_for_lock IS NULL THEN
        RAISE EXCEPTION 'lock wait mode must be explicit' USING ERRCODE='22023';
    END IF;
    PERFORM football.authorize_worker_publication();
    previous_ledger:=coalesce(current_setting('matchforge.lock_order',true),'');
    PERFORM football.record_transaction_lock(lock_class,lock_key,legacy_hash);
    IF wait_for_lock THEN
        IF legacy_hash THEN
            PERFORM pg_advisory_xact_lock(hashtext(lock_key)::bigint);
        ELSE
            PERFORM pg_advisory_xact_lock(hashtextextended(lock_key,0));
        END IF;
        RETURN true;
    END IF;
    acquired:=CASE WHEN legacy_hash THEN pg_try_advisory_xact_lock(hashtext(lock_key)::bigint)
        ELSE pg_try_advisory_xact_lock(hashtextextended(lock_key,0)) END;
    IF NOT acquired THEN
        PERFORM set_config('matchforge.lock_order',previous_ledger,true);
    END IF;
    RETURN acquired;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.lock_work(
    work_key uuid,owner_key text,token uuid,epoch bigint
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
    PERFORM football.authorize_worker_publication();
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
    SELECT * INTO item FROM football.work_items WHERE work_id=work_key
        AND state='RUNNING' AND lease_owner=owner_key AND lease_token=token
        AND generation=epoch FOR NO KEY UPDATE;
    IF NOT FOUND OR item.lease_until<=clock_timestamp() THEN
        RAISE EXCEPTION 'work lease ownership lost' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.claim_work(owner_key text,lease_duration interval,allowed_types text[])
RETURNS SETOF football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; stamp timestamptz:=clock_timestamp();
BEGIN
    IF owner_key IS NULL OR btrim(owner_key)='' OR lease_duration IS NULL
       OR lease_duration<=interval '0' OR NOT isfinite(lease_duration) OR allowed_types IS NULL OR cardinality(allowed_types)=0 THEN
        RAISE EXCEPTION 'claim requires owner, positive lease and supported work types' USING ERRCODE='22023';
    END IF;
    PERFORM football.authorize_worker_publication();
    -- Reap at most one exhausted claim without hiding other runnable work.
    SELECT w.* INTO item FROM football.work_items w
        WHERE w.work_type=ANY(allowed_types) AND w.state='RUNNING'
          AND w.lease_until<=stamp AND w.attempt_count>=w.max_attempts
        ORDER BY w.lease_until,w.work_id LIMIT 1 FOR UPDATE OF w SKIP LOCKED;
    IF FOUND THEN
        UPDATE football.work_items SET state='FAILED',generation=generation+1,
            lease_owner=NULL,lease_token=NULL,lease_until=NULL,heartbeat_at=NULL,
            finished_at=clock_timestamp(),last_error_code='LEASE_EXPIRED',
            last_error_message='Final work attempt expired before completion'
            WHERE work_id=item.work_id;
    END IF;
    SELECT w.* INTO item FROM football.work_items w
    WHERE w.work_type=ANY(allowed_types) AND w.dependencies_sealed
      AND w.attempt_count<w.max_attempts
      AND ((w.state IN ('PENDING','RETRY_WAIT') AND w.available_at<=stamp)
        OR (w.state='RUNNING' AND w.lease_until<=stamp
            AND w.lease_until+make_interval(secs=>football.work_retry_seconds(
                w.retry_base_seconds,w.retry_cap_seconds,w.retry_multiplier,w.attempt_count))<=stamp))
      AND NOT EXISTS (SELECT 1 FROM football.work_dependencies d
          JOIN football.work_items parent ON parent.work_id=d.dependency_work_id
          WHERE d.work_id=w.work_id AND parent.state<>'SUCCEEDED')
    ORDER BY w.priority DESC,w.available_at,w.work_id LIMIT 1 FOR UPDATE OF w SKIP LOCKED;
    IF NOT FOUND THEN RETURN; END IF;
    stamp:=clock_timestamp();
    RETURN QUERY UPDATE football.work_items SET state='RUNNING',generation=generation+1,
        lease_owner=owner_key,lease_token=gen_random_uuid(),lease_until=stamp+lease_duration,
        heartbeat_at=stamp,attempt_count=attempt_count+1,started_at=coalesce(started_at,stamp)
        WHERE work_id=item.work_id RETURNING *;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.cancel_work(work_key uuid) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
    PERFORM football.authorize_worker_publication();
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
    SELECT * INTO STRICT item FROM football.work_items WHERE work_id=work_key FOR UPDATE;
    IF item.state IN ('SUCCEEDED','FAILED','CANCELLED') THEN RETURN item; END IF;
    UPDATE football.work_items SET state='CANCELLED',generation=generation+1,
        lease_owner=NULL,lease_token=NULL,lease_until=NULL,heartbeat_at=NULL,
        finished_at=clock_timestamp(),last_error_code='CANCELLED',
        last_error_message='Work cancelled; publication rights revoked'
        WHERE work_id=work_key RETURNING * INTO item;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.release_blocked_work(work_key uuid,run_at timestamptz)
RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
    PERFORM football.authorize_worker_publication();
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
    SELECT * INTO STRICT item FROM football.work_items WHERE work_id=work_key FOR UPDATE;
    IF item.state<>'BLOCKED' OR run_at IS NULL THEN
        RAISE EXCEPTION 'only explicitly blocked work can be released' USING ERRCODE='55000';
    END IF;
    UPDATE football.work_items SET
        state=CASE WHEN attempt_count>=max_attempts THEN 'FAILED' ELSE 'PENDING' END,
        finished_at=CASE WHEN attempt_count>=max_attempts THEN clock_timestamp() ELSE NULL END,
        available_at=run_at,generation=generation+1
        WHERE work_id=work_key RETURNING * INTO item;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.prevent_sync_run_resurrection() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> OLD.status THEN
        PERFORM football.record_transaction_lock(5,'matchforge-run:'||OLD.run_id::text);
        PERFORM pg_advisory_xact_lock(hashtextextended('matchforge-run:' || OLD.run_id::text, 0));
    END IF;
    IF OLD.status IN ('FAILED', 'CANCELLED', 'SUCCEEDED') AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION 'terminal sync run cannot change status' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- Run controls must stay independent of publication transactions. This rejects
-- shared-to-exclusive advisory upgrades and heartbeat/run-row cycles before
-- any run row can be locked. Separate heartbeat connections remain valid.
-- +goose StatementBegin
CREATE FUNCTION football.guard_sync_run_control_transaction() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE ledger jsonb:=coalesce(nullif(current_setting('matchforge.lock_order',true),''),'{}')::jsonb;
BEGIN
    IF nullif(current_setting('matchforge.sync_run_id',true),'') IS NOT NULL
       OR nullif(current_setting('matchforge.history_claim_token',true),'') IS NOT NULL
       OR coalesce((ledger->>'class')::integer,0)>5
       OR EXISTS (SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid()
                  AND locktype='advisory' AND mode='ShareLock') THEN
        RAISE EXCEPTION 'sync-run control requires a separate transaction' USING ERRCODE='MFL01';
    END IF;
    RETURN NULL;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER guard_sync_run_control_transaction
    BEFORE INSERT OR UPDATE OR DELETE ON football.product_sync_runs
    FOR EACH STATEMENT EXECUTE FUNCTION football.guard_sync_run_control_transaction();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'worker fencing must precede domain coordination; roll forward';
END $$;
-- +goose StatementEnd
