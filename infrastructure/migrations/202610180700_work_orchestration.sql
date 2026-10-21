-- +goose Up

CREATE TABLE football.work_items (
    work_id uuid PRIMARY KEY,
    work_type text NOT NULL CHECK (work_type IN (
        'PROVIDER_ACQUISITION','HISTORICAL_ACQUISITION','NORMALIZATION',
        'IDENTITY_REMEDIATION','CANONICAL_RECONCILIATION','COVERAGE_REBUILD',
        'READ_MODEL_PROJECTION','FEATURE_BUILD','FORECAST_REFRESH','SIMULATION',
        'POST_MATCH_EVALUATION','EXPERIMENT_EXECUTION')),
    semantic_key text NOT NULL CHECK (btrim(semantic_key)<>''),
    input_hash football.sha256_hex NOT NULL,
    state text NOT NULL DEFAULT 'PENDING' CHECK (state IN (
        'PENDING','RUNNING','RETRY_WAIT','SUCCEEDED','FAILED','CANCELLED','BLOCKED')),
    priority integer NOT NULL,
    available_at timestamptz NOT NULL CHECK (isfinite(available_at)),
    generation bigint NOT NULL DEFAULT 0 CHECK (generation>=0),
    lease_owner text CHECK (lease_owner IS NULL OR btrim(lease_owner)<>''),
    lease_token uuid,
    lease_until timestamptz,
    heartbeat_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
    max_attempts integer NOT NULL CHECK (max_attempts>0 AND attempt_count<=max_attempts),
    retry_base_seconds double precision NOT NULL CHECK (
        retry_base_seconds>=0 AND retry_base_seconds<'Infinity'::double precision),
    retry_cap_seconds double precision NOT NULL CHECK (
        retry_cap_seconds>=retry_base_seconds AND retry_cap_seconds<'Infinity'::double precision),
    retry_multiplier double precision NOT NULL CHECK (
        retry_multiplier>=1 AND retry_multiplier<'Infinity'::double precision),
    result_hash football.sha256_hex,
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    last_error_code text,
    last_error_message text,
    parent_work_id uuid REFERENCES football.work_items(work_id),
    dependencies_sealed boolean NOT NULL DEFAULT false,
    UNIQUE (work_type,semantic_key),
    CHECK (parent_work_id IS DISTINCT FROM work_id),
    CHECK (CASE WHEN state='RUNNING' THEN
        lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL
        AND heartbeat_at IS NOT NULL AND started_at IS NOT NULL AND dependencies_sealed
        ELSE lease_owner IS NULL AND lease_token IS NULL AND lease_until IS NULL
        AND heartbeat_at IS NULL END),
    CHECK (heartbeat_at IS NULL OR lease_until>heartbeat_at),
    CHECK ((state IN ('SUCCEEDED','FAILED','CANCELLED'))=(finished_at IS NOT NULL)),
    CHECK ((state='SUCCEEDED')=(result_hash IS NOT NULL))
);
CREATE INDEX work_items_runnable_idx ON football.work_items(
    priority DESC,available_at,work_id) WHERE state IN ('PENDING','RETRY_WAIT');
CREATE INDEX work_items_expired_idx ON football.work_items(lease_until,work_id)
    WHERE state='RUNNING';

CREATE TABLE football.work_dependencies (
    work_id uuid NOT NULL REFERENCES football.work_items(work_id),
    dependency_work_id uuid NOT NULL REFERENCES football.work_items(work_id),
    PRIMARY KEY (work_id,dependency_work_id),
    CHECK (work_id<>dependency_work_id)
);
CREATE INDEX work_dependencies_parent_idx ON football.work_dependencies(dependency_work_id,work_id);

-- A dependency points to an already sealed item. Sealed items cannot acquire
-- new edges, so graph construction cannot create a cycle, including concurrent
-- or transaction-local cycles. No global graph lock is needed.
-- +goose StatementBegin
CREATE FUNCTION football.guard_work_dependency() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sealed boolean;
BEGIN
    IF TG_OP<>'INSERT' THEN
        RAISE EXCEPTION 'work dependencies are immutable' USING ERRCODE='55000';
    END IF;
    SELECT dependencies_sealed INTO sealed FROM football.work_items
        WHERE work_id=NEW.work_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'dependent work does not exist' USING ERRCODE='23503';
    END IF;
    IF sealed THEN
        RAISE EXCEPTION 'work dependencies are already sealed' USING ERRCODE='55000';
    END IF;
    PERFORM 1 FROM football.work_items
        WHERE work_id=NEW.dependency_work_id AND dependencies_sealed;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'dependency must be an existing sealed work item' USING ERRCODE='23503';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER guard_work_dependency BEFORE INSERT OR UPDATE OR DELETE
    ON football.work_dependencies FOR EACH ROW EXECUTE FUNCTION football.guard_work_dependency();
CREATE TRIGGER preserve_work_dependencies BEFORE TRUNCATE ON football.work_dependencies
    FOR EACH STATEMENT EXECUTE FUNCTION football.guard_work_dependency();

-- +goose StatementBegin
CREATE FUNCTION football.require_sealed_work() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM football.work_items WHERE work_id=NEW.work_id AND dependencies_sealed;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'work dependencies must be sealed before commit' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$;
-- +goose StatementEnd
CREATE CONSTRAINT TRIGGER require_sealed_work AFTER INSERT ON football.work_items
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION football.require_sealed_work();

-- +goose StatementBegin
CREATE FUNCTION football.guard_new_work() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state<>'PENDING' OR NEW.generation<>0 OR NEW.attempt_count<>0
       OR NEW.dependencies_sealed THEN
        RAISE EXCEPTION 'new work must start pending and unclaimed' USING ERRCODE='55000';
    END IF;
    IF NEW.parent_work_id IS NOT NULL THEN
        PERFORM 1 FROM football.work_items
            WHERE work_id=NEW.parent_work_id AND dependencies_sealed;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'parent work must already be sealed' USING ERRCODE='23503';
        END IF;
    END IF;
    NEW.requested_at:=clock_timestamp();
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER guard_new_work BEFORE INSERT ON football.work_items
    FOR EACH ROW EXECUTE FUNCTION football.guard_new_work();

-- +goose StatementBegin
CREATE FUNCTION football.work_transition_allowed(previous text,following text)
RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT previous=following OR CASE previous
        WHEN 'PENDING' THEN following IN ('RUNNING','FAILED','CANCELLED')
        WHEN 'RETRY_WAIT' THEN following IN ('RUNNING','FAILED','CANCELLED')
        WHEN 'RUNNING' THEN following IN ('RETRY_WAIT','SUCCEEDED','FAILED','CANCELLED','BLOCKED')
        WHEN 'BLOCKED' THEN following IN ('PENDING','FAILED','CANCELLED')
        ELSE false END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.guard_work_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP IN ('DELETE','TRUNCATE') THEN
        RAISE EXCEPTION 'work identity and outcomes must be retained' USING ERRCODE='55000';
    END IF;
    IF (NEW.work_id,NEW.work_type,NEW.semantic_key,NEW.input_hash,NEW.priority,
        NEW.max_attempts,NEW.retry_base_seconds,NEW.retry_cap_seconds,NEW.retry_multiplier,
        NEW.parent_work_id,NEW.requested_at) IS DISTINCT FROM
       (OLD.work_id,OLD.work_type,OLD.semantic_key,OLD.input_hash,OLD.priority,
        OLD.max_attempts,OLD.retry_base_seconds,OLD.retry_cap_seconds,OLD.retry_multiplier,
        OLD.parent_work_id,OLD.requested_at) THEN
        RAISE EXCEPTION 'semantic work inputs and policy are immutable' USING ERRCODE='55000';
    END IF;
    IF OLD.dependencies_sealed AND NOT NEW.dependencies_sealed THEN
        RAISE EXCEPTION 'work dependencies cannot be reopened' USING ERRCODE='55000';
    END IF;
    IF OLD.state IN ('SUCCEEDED','FAILED','CANCELLED') AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'terminal work cannot change' USING ERRCODE='55000';
    END IF;
    IF NEW.generation<OLD.generation OR NEW.attempt_count<OLD.attempt_count THEN
        RAISE EXCEPTION 'work fencing epochs and attempts cannot go backwards' USING ERRCODE='55000';
    END IF;
    IF NOT football.work_transition_allowed(OLD.state,NEW.state) THEN
        RAISE EXCEPTION 'invalid work state transition' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER guard_work_transition BEFORE UPDATE OR DELETE ON football.work_items
    FOR EACH ROW EXECUTE FUNCTION football.guard_work_transition();
CREATE TRIGGER preserve_work_items BEFORE TRUNCATE ON football.work_items
    FOR EACH STATEMENT EXECUTE FUNCTION football.guard_work_transition();

CREATE TRIGGER check_worker_publication BEFORE INSERT OR UPDATE OR DELETE ON football.work_items
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();
CREATE TRIGGER check_worker_publication BEFORE INSERT OR UPDATE OR DELETE ON football.work_dependencies
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();

-- +goose StatementBegin
CREATE FUNCTION football.work_retry_seconds(
    base_seconds double precision,cap_seconds double precision,
    multiplier double precision,attempt integer
) RETURNS double precision LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE WHEN base_seconds=0 THEN 0
        WHEN multiplier=1 OR attempt<=1 THEN base_seconds
        WHEN (attempt-1)::double precision>=ln(cap_seconds/base_seconds)/ln(multiplier)
            THEN cap_seconds
        ELSE least(cap_seconds,base_seconds*power(multiplier,attempt-1)) END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_work(
    requested_id uuid,kind text,semantic text,input_digest football.sha256_hex,
    work_priority integer,run_at timestamptz,attempt_limit integer,
    base_seconds double precision,cap_seconds double precision,multiplier double precision,
    dependency_keys uuid[],parent_key uuid
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; edges uuid[];
BEGIN
    SET CONSTRAINTS football.require_sealed_work DEFERRED;
    IF dependency_keys IS NULL OR cardinality(dependency_keys)<>
       (SELECT count(DISTINCT value) FROM unnest(dependency_keys) value) THEN
        RAISE EXCEPTION 'work dependencies must be explicit and unique' USING ERRCODE='22023';
    END IF;
    PERFORM make_interval(secs=>cap_seconds);
    IF EXISTS (SELECT 1 FROM unnest(dependency_keys) dependency
        LEFT JOIN football.work_items parent ON parent.work_id=dependency AND parent.dependencies_sealed
        WHERE parent.work_id IS NULL) THEN
        RAISE EXCEPTION 'dependency must already exist and be sealed' USING ERRCODE='23503';
    END IF;
    INSERT INTO football.work_items(work_id,work_type,semantic_key,input_hash,priority,
        available_at,max_attempts,retry_base_seconds,retry_cap_seconds,retry_multiplier,parent_work_id)
    VALUES (requested_id,kind,semantic,input_digest,work_priority,run_at,attempt_limit,
        base_seconds,cap_seconds,multiplier,parent_key)
    ON CONFLICT (work_type,semantic_key) DO NOTHING RETURNING * INTO item;
    IF FOUND THEN
        INSERT INTO football.work_dependencies(work_id,dependency_work_id)
            SELECT requested_id,value FROM unnest(dependency_keys) value ORDER BY value;
        UPDATE football.work_items SET dependencies_sealed=true WHERE work_id=requested_id
            RETURNING * INTO item;
    ELSE
        SELECT * INTO STRICT item FROM football.work_items WHERE work_type=kind AND semantic_key=semantic;
    END IF;
    SELECT coalesce(array_agg(dependency_work_id ORDER BY dependency_work_id),ARRAY[]::uuid[])
        INTO edges FROM football.work_dependencies WHERE work_id=item.work_id;
    IF (item.work_id,item.input_hash,item.priority,item.max_attempts,item.retry_base_seconds,
        item.retry_cap_seconds,item.retry_multiplier,item.parent_work_id,edges)
        IS DISTINCT FROM (requested_id,input_digest,work_priority,attempt_limit,base_seconds,
        cap_seconds,multiplier,parent_key,ARRAY(SELECT value FROM unnest(dependency_keys) value ORDER BY value)) THEN
        RAISE EXCEPTION 'semantic work inputs or policy differ from existing work' USING ERRCODE='23505';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.claim_work(owner_key text,lease_duration interval,allowed_types text[])
RETURNS SETOF football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; stamp timestamptz:=clock_timestamp();
BEGIN
    IF owner_key IS NULL OR btrim(owner_key)='' OR lease_duration IS NULL
       OR lease_duration<=interval '0' OR NOT isfinite(lease_duration) OR allowed_types IS NULL OR cardinality(allowed_types)=0 THEN
        RAISE EXCEPTION 'claim requires owner, positive lease and supported work types' USING ERRCODE='22023';
    END IF;
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

-- Publication callers acquire their canonical coordination locks before this
-- work-row lock. The same lock serializes cancellation and lease replacement.
-- +goose StatementBegin
CREATE FUNCTION football.lock_work(
    work_key uuid,owner_key text,token uuid,epoch bigint
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
    SELECT * INTO item FROM football.work_items WHERE work_id=work_key
        AND state='RUNNING' AND lease_owner=owner_key AND lease_token=token
        AND generation=epoch FOR UPDATE;
    IF NOT FOUND OR item.lease_until<=clock_timestamp() THEN
        RAISE EXCEPTION 'work lease ownership lost' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.heartbeat_work(
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
        RAISE EXCEPTION 'work lease expired before heartbeat' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.finish_work(
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
        RAISE EXCEPTION 'work lease expired before completion' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.fail_work(
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
        RAISE EXCEPTION 'work lease expired before failure acknowledgement' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.cancel_work(work_key uuid) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
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
CREATE FUNCTION football.release_blocked_work(work_key uuid,run_at timestamptz)
RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
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

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'work identities, dependencies and outcomes must be retained; roll forward';
END $$;
-- +goose StatementEnd
