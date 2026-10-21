-- +goose Up

-- History jobs recover expired ownership immediately, while acknowledged
-- provider failures retain their exponential backoff. NULL preserves the
-- existing shared policy of using the error backoff for expired leases too.
ALTER TABLE football.work_items ADD COLUMN lease_retry_delay_seconds double precision
    CHECK (lease_retry_delay_seconds>=0 AND lease_retry_delay_seconds<'Infinity'::double precision);

-- +goose StatementBegin
CREATE FUNCTION football.guard_work_lease_retry_policy() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.lease_retry_delay_seconds IS DISTINCT FROM OLD.lease_retry_delay_seconds THEN
        RAISE EXCEPTION 'semantic work retry policy is immutable' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER guard_work_lease_retry_policy BEFORE UPDATE ON football.work_items
    FOR EACH ROW EXECUTE FUNCTION football.guard_work_lease_retry_policy();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_work(
    requested_id uuid,kind text,semantic text,input_digest football.sha256_hex,
    work_priority integer,run_at timestamptz,attempt_limit integer,
    base_seconds double precision,cap_seconds double precision,multiplier double precision,
    dependency_keys uuid[],parent_key uuid,expiry_delay_seconds double precision
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
        available_at,max_attempts,retry_base_seconds,retry_cap_seconds,retry_multiplier,parent_work_id,lease_retry_delay_seconds)
    VALUES (requested_id,kind,semantic,input_digest,work_priority,run_at,attempt_limit,
        base_seconds,cap_seconds,multiplier,parent_key,expiry_delay_seconds)
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
        item.retry_cap_seconds,item.retry_multiplier,item.parent_work_id,edges,item.lease_retry_delay_seconds)
        IS DISTINCT FROM (requested_id,input_digest,work_priority,attempt_limit,base_seconds,
        cap_seconds,multiplier,parent_key,ARRAY(SELECT value FROM unnest(dependency_keys) value ORDER BY value),expiry_delay_seconds) THEN
        RAISE EXCEPTION 'semantic work inputs or policy differ from existing work' USING ERRCODE='23505';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.enqueue_work(
    requested_id uuid,kind text,semantic text,input_digest football.sha256_hex,
    work_priority integer,run_at timestamptz,attempt_limit integer,
    base_seconds double precision,cap_seconds double precision,multiplier double precision,
    dependency_keys uuid[],parent_key uuid
) RETURNS football.work_items LANGUAGE sql AS $$
    SELECT football.enqueue_work(requested_id,kind,semantic,input_digest,work_priority,
        run_at,attempt_limit,base_seconds,cap_seconds,multiplier,dependency_keys,parent_key,
        NULL::double precision)
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.claim_work(owner_key text,lease_duration interval,allowed_types text[],allowed_work_ids uuid[])
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
        WHERE w.work_type=ANY(allowed_types)
          AND (allowed_work_ids IS NULL OR w.work_id=ANY(allowed_work_ids))
          AND w.state='RUNNING'
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
    WHERE w.work_type=ANY(allowed_types)
      AND (allowed_work_ids IS NULL OR w.work_id=ANY(allowed_work_ids))
      AND w.dependencies_sealed
      AND w.attempt_count<w.max_attempts
      AND ((w.state IN ('PENDING','RETRY_WAIT') AND w.available_at<=stamp)
        OR (w.state='RUNNING' AND w.lease_until<=stamp
            AND w.lease_until+make_interval(secs=>coalesce(w.lease_retry_delay_seconds,
                football.work_retry_seconds(w.retry_base_seconds,w.retry_cap_seconds,
                    w.retry_multiplier,w.attempt_count)))<=stamp))
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

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'registered work retry policy must be retained; roll forward';
END $$;
-- +goose StatementEnd
