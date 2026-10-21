-- +goose Up

-- Attempt observations do not choose work eligibility or mutate existing work.
CREATE TABLE football.work_attempt_metrics (
    work_id uuid NOT NULL REFERENCES football.work_items(work_id),
    generation bigint NOT NULL,
    work_type text NOT NULL,
    attempt_count integer NOT NULL,
    claimed_at timestamptz NOT NULL,
    claim_latency_seconds double precision NOT NULL CHECK (claim_latency_seconds>=0),
    execution_seconds double precision CHECK (execution_seconds>=0),
    lease_expired boolean NOT NULL DEFAULT false,
    PRIMARY KEY (work_id,generation)
);
CREATE TABLE football.work_lock_metrics (
    backend_pid integer NOT NULL,
    backend_start timestamptz NOT NULL,
    duration_seconds double precision NOT NULL CHECK (duration_seconds>=0),
    observation_count bigint NOT NULL CHECK (observation_count>0),
    PRIMARY KEY (backend_pid,backend_start)
);
-- Sequences preserve rejected-operation counts even when the caller rolls back.
CREATE SEQUENCE football.work_fencing_rejections MINVALUE 0 START 0;
CREATE SEQUENCE football.work_deadlocks MINVALUE 0 START 0;

-- +goose StatementBegin
CREATE FUNCTION football.observe_work_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE stamp timestamptz:=clock_timestamp();
BEGIN
    IF OLD.state='RUNNING' AND (NEW.state<>'RUNNING' OR NEW.attempt_count>OLD.attempt_count) THEN
        UPDATE football.work_attempt_metrics SET
            execution_seconds=greatest(0,extract(epoch FROM (least(stamp,OLD.lease_until)-claimed_at))),
            lease_expired=(OLD.lease_until<=stamp)
            WHERE work_id=OLD.work_id AND generation=OLD.generation;
    END IF;
    IF NEW.attempt_count>OLD.attempt_count THEN
        INSERT INTO football.work_attempt_metrics(work_id,generation,work_type,attempt_count,
            claimed_at,claim_latency_seconds)
        VALUES (NEW.work_id,NEW.generation,NEW.work_type,NEW.attempt_count,stamp,
            greatest(0,extract(epoch FROM (stamp-greatest(OLD.requested_at,OLD.available_at,
                CASE WHEN OLD.state='RUNNING' THEN OLD.lease_until+make_interval(secs=>
                    coalesce(OLD.lease_retry_delay_seconds,football.work_retry_seconds(
                        OLD.retry_base_seconds,OLD.retry_cap_seconds,OLD.retry_multiplier,OLD.attempt_count)))
                END)))));
    END IF;
    RETURN NULL;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER observe_work_attempt AFTER UPDATE ON football.work_items
    FOR EACH ROW WHEN (OLD.state IS DISTINCT FROM NEW.state OR OLD.attempt_count<>NEW.attempt_count)
    EXECUTE FUNCTION football.observe_work_attempt();

-- Each session writes only its own accumulator: no global metrics row lock.
-- Samples commit with the acquisition transaction; failed samples are excluded.
-- +goose StatementBegin
CREATE FUNCTION football.observe_work_lock(started timestamptz) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('transaction_read_only')='on' THEN RETURN; END IF;
    INSERT INTO football.work_lock_metrics(backend_pid,backend_start,duration_seconds,observation_count)
    SELECT pg_backend_pid(),backend_start,
        greatest(0,extract(epoch FROM (clock_timestamp()-started))),1
        FROM pg_stat_activity WHERE pid=pg_backend_pid()
        AND current_setting('transaction_read_only')='off'
    ON CONFLICT (backend_pid,backend_start) DO UPDATE SET
        duration_seconds=football.work_lock_metrics.duration_seconds+excluded.duration_seconds,
        observation_count=football.work_lock_metrics.observation_count+1;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.acquire_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean,
    wait_for_lock boolean,shared_mode boolean
) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE previous_ledger text; acquired boolean; lock_hash bigint; metric_started timestamptz:=clock_timestamp();
BEGIN
    IF wait_for_lock IS NULL THEN
        RAISE EXCEPTION 'lock wait mode must be explicit' USING ERRCODE='22023';
    END IF;
    PERFORM football.authorize_worker_publication();
    previous_ledger:=coalesce(current_setting('matchforge.lock_order',true),'');
    PERFORM football.record_transaction_lock(lock_class,lock_key,legacy_hash,shared_mode);
    lock_hash:=CASE WHEN legacy_hash THEN hashtext(lock_key)::bigint
        ELSE hashtextextended(lock_key,0) END;
    IF wait_for_lock THEN
        IF shared_mode THEN PERFORM pg_advisory_xact_lock_shared(lock_hash);
        ELSE PERFORM pg_advisory_xact_lock(lock_hash); END IF;
        PERFORM football.observe_work_lock(metric_started);
        RETURN true;
    END IF;
    acquired:=CASE WHEN shared_mode THEN pg_try_advisory_xact_lock_shared(lock_hash)
        ELSE pg_try_advisory_xact_lock(lock_hash) END;
    IF NOT acquired THEN
        PERFORM set_config('matchforge.lock_order',previous_ledger,true);
    END IF;
    PERFORM football.observe_work_lock(metric_started);
    RETURN acquired;
EXCEPTION WHEN deadlock_detected THEN
    IF current_setting('transaction_read_only')='off' THEN
        PERFORM nextval('football.work_deadlocks');
    END IF;
    RAISE;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.lock_work(
    work_key uuid,owner_key text,token uuid,epoch bigint
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; metric_started timestamptz:=clock_timestamp();
BEGIN
    PERFORM football.authorize_worker_publication();
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
    SELECT * INTO item FROM football.work_items WHERE work_id=work_key
        AND state='RUNNING' AND lease_owner=owner_key AND lease_token=token
        AND generation=epoch FOR NO KEY UPDATE;
    IF NOT FOUND OR item.lease_until<=clock_timestamp() THEN
        IF current_setting('transaction_read_only')='off' THEN
            PERFORM nextval('football.work_fencing_rejections');
        END IF;
        RAISE EXCEPTION 'work lease ownership lost' USING ERRCODE='55000';
    END IF;
    PERFORM football.observe_work_lock(metric_started);
    RETURN item;
EXCEPTION WHEN deadlock_detected THEN
    IF current_setting('transaction_read_only')='off' THEN
        PERFORM nextval('football.work_deadlocks');
    END IF;
    RAISE;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.heartbeat_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,lease_duration interval
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; stamp timestamptz;
BEGIN
    IF lease_duration IS NULL OR lease_duration<=interval '0' OR NOT isfinite(lease_duration) THEN
        RAISE EXCEPTION 'heartbeat requires a positive lease duration' USING ERRCODE='22023';
    END IF;
    item:=football.lock_work(work_key,owner_key,token,epoch);
    stamp:=clock_timestamp();
    UPDATE football.work_items SET heartbeat_at=stamp,
        lease_until=greatest(lease_until,stamp+lease_duration)
        WHERE work_id=work_key AND lease_until>stamp RETURNING * INTO item;
    IF NOT FOUND THEN
        IF current_setting('transaction_read_only')='off' THEN
            PERFORM nextval('football.work_fencing_rejections');
        END IF;
        RAISE EXCEPTION 'work lease expired before heartbeat' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.finish_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,result_digest football.sha256_hex
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
    item:=football.lock_work(work_key,owner_key,token,epoch);
    UPDATE football.work_items SET state='SUCCEEDED',result_hash=result_digest,
        lease_owner=NULL,lease_token=NULL,lease_until=NULL,heartbeat_at=NULL,
        finished_at=clock_timestamp() WHERE work_id=work_key AND lease_until>clock_timestamp()
        RETURNING * INTO item;
    IF NOT FOUND THEN
        IF current_setting('transaction_read_only')='off' THEN
            PERFORM nextval('football.work_fencing_rejections');
        END IF;
        RAISE EXCEPTION 'work lease expired before completion' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.fail_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,classification text,
    error_code text,error_message text,retry_after timestamptz,provider_cooldown timestamptz
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; outcome text; stamp timestamptz; retry_at timestamptz;
BEGIN
    IF classification IS NULL OR classification NOT IN (
        'RETRYABLE','NON_RETRYABLE','BLOCKED_EXTERNAL','CANCELLED')
        OR error_code IS NULL OR btrim(error_code)=''
        OR error_message IS NULL OR btrim(error_message)='' THEN
        RAISE EXCEPTION 'work failure requires classification and actionable error' USING ERRCODE='22023';
    END IF;
    item:=football.lock_work(work_key,owner_key,token,epoch);
    stamp:=clock_timestamp();
    outcome:=CASE classification WHEN 'NON_RETRYABLE' THEN 'FAILED'
        WHEN 'BLOCKED_EXTERNAL' THEN 'BLOCKED' WHEN 'CANCELLED' THEN 'CANCELLED'
        ELSE CASE WHEN item.attempt_count>=item.max_attempts THEN 'FAILED' ELSE 'RETRY_WAIT' END END;
    retry_at:=greatest(stamp+make_interval(secs=>football.work_retry_seconds(
        item.retry_base_seconds,item.retry_cap_seconds,item.retry_multiplier,item.attempt_count)),
        retry_after,provider_cooldown);
    UPDATE football.work_items SET state=outcome,generation=generation+1,
        available_at=CASE WHEN outcome='RETRY_WAIT' THEN retry_at ELSE available_at END,
        lease_owner=NULL,lease_token=NULL,lease_until=NULL,heartbeat_at=NULL,
        finished_at=CASE WHEN outcome IN ('FAILED','CANCELLED') THEN stamp ELSE NULL END,
        last_error_code=error_code,last_error_message=error_message
        WHERE work_id=work_key AND lease_until>clock_timestamp() RETURNING * INTO item;
    IF NOT FOUND THEN
        IF current_setting('transaction_read_only')='off' THEN
            PERFORM nextval('football.work_fencing_rejections');
        END IF;
        RAISE EXCEPTION 'work lease expired before failure acknowledgement' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

CREATE VIEW football.work_metrics AS
WITH kinds AS (
    SELECT unnest(ARRAY['PROVIDER_ACQUISITION','HISTORICAL_ACQUISITION','NORMALIZATION',
        'IDENTITY_REMEDIATION','CANONICAL_RECONCILIATION','COVERAGE_REBUILD',
        'READ_MODEL_PROJECTION','FEATURE_BUILD','FORECAST_REFRESH','SIMULATION',
        'POST_MATCH_EVALUATION','EXPERIMENT_EXECUTION']) AS work_type
), states AS (
    SELECT unnest(ARRAY['PENDING','RUNNING','RETRY_WAIT','FAILED','BLOCKED']) AS state
), state_counts AS (
    SELECT work_type,state,count(*) AS n FROM football.work_items GROUP BY work_type,state
), attempts AS (
    SELECT work_type,count(*) AS claim_count,sum(claim_latency_seconds) AS claim_sum,
        count(execution_seconds) AS execution_count,sum(execution_seconds) AS execution_sum,
        count(*) FILTER (WHERE attempt_count>1) AS retries,
        count(*) FILTER (WHERE lease_expired) AS expirations
        FROM football.work_attempt_metrics GROUP BY work_type
)
SELECT 'work_'||lower(states.state) AS name,kinds.work_type,
    coalesce(state_counts.n,0)::double precision AS value
FROM kinds CROSS JOIN states LEFT JOIN state_counts USING (work_type,state)
UNION ALL
SELECT metric.name,kinds.work_type,coalesce(metric.value,0)::double precision
FROM kinds LEFT JOIN attempts USING (work_type)
CROSS JOIN LATERAL (VALUES
    ('work_claim_latency_count',claim_count),('work_claim_latency_sum',claim_sum),
    ('work_execution_duration_count',execution_count),('work_execution_duration_sum',execution_sum),
    ('work_retry_count',retries),('work_lease_expirations',expirations)
) metric(name,value)
UNION ALL
SELECT 'work_fencing_rejections',NULL::text,
    CASE WHEN is_called THEN last_value+1 ELSE 0 END::double precision
    FROM football.work_fencing_rejections
UNION ALL
SELECT 'work_deadlocks',NULL::text,
    CASE WHEN is_called THEN last_value+1 ELSE 0 END::double precision
    FROM football.work_deadlocks
UNION ALL
SELECT 'work_lock_wait_duration_sum',NULL::text,coalesce(sum(duration_seconds),0)::double precision
    FROM football.work_lock_metrics
UNION ALL
SELECT 'work_lock_wait_duration_count',NULL::text,coalesce(sum(observation_count),0)::double precision
    FROM football.work_lock_metrics;

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'work observations and rollback-safe counters must be retained; roll forward';
END $$;
-- +goose StatementEnd
