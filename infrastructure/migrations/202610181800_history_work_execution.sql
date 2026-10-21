-- +goose Up

-- Concurrent identical requests can conflict on either unique identity. Handle
-- both indexes, then retain all semantic/policy checks; a primary identity
-- already used by another semantic request remains an explicit conflict.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.enqueue_work(
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
    ON CONFLICT DO NOTHING RETURNING * INTO item;
    IF FOUND THEN
        INSERT INTO football.work_dependencies(work_id,dependency_work_id)
            SELECT requested_id,value FROM unnest(dependency_keys) value ORDER BY value;
        UPDATE football.work_items SET dependencies_sealed=true WHERE work_id=requested_id
            RETURNING * INTO item;
    ELSE
        SELECT * INTO item FROM football.work_items WHERE work_type=kind AND semantic_key=semantic;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'work identifier is bound to different semantic inputs' USING ERRCODE='23505';
        END IF;
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

-- Shared work remains the only lease/retry state machine. Legacy queue rows
-- retain operator detail; each state projection commits with the work change.
-- +goose StatementBegin
CREATE FUNCTION football.project_history_work(work_key uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE item football.work_items; request football.product_history_work;
BEGIN
    PERFORM football.authorize_worker_publication();
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
    SELECT * INTO STRICT item FROM football.work_items WHERE work_id=work_key FOR NO KEY UPDATE;
    SELECT * INTO STRICT request FROM football.product_history_work WHERE work_id=work_key;
    IF item.work_type<>'HISTORICAL_ACQUISITION' THEN
        RAISE EXCEPTION 'history request requires historical acquisition work' USING ERRCODE='22023';
    END IF;
    PERFORM football.record_transaction_lock(51,
        'history-queue:'||request.provider_competition_id||':'||request.season);
    WITH target AS (
        SELECT queue.job_id,queue.queued_at,
            CASE item.state WHEN 'RUNNING' THEN 'RUNNING'
                WHEN 'SUCCEEDED' THEN 'SUCCEEDED' WHEN 'FAILED' THEN 'FAILED'
                WHEN 'CANCELLED' THEN 'FAILED' ELSE 'PENDING' END AS job_status,
            request.attempt_offset+item.attempt_count AS attempt_count,
            item.heartbeat_at AS claimed_at,
            CASE WHEN item.state='RUNNING' THEN item.heartbeat_at
                WHEN item.state IN ('PENDING','RETRY_WAIT','BLOCKED') THEN NULL
                ELSE queue.started_at END AS started_at,
            item.finished_at AS finished_at,
            CASE WHEN item.state IN ('PENDING','RETRY_WAIT','BLOCKED')
                THEN item.available_at ELSE NULL END AS next_attempt_at,
            CASE WHEN item.state='SUCCEEDED' THEN NULL
                ELSE left(item.last_error_message,4000) END AS last_error
        FROM football.product_history_sync_queue queue
        WHERE queue.job_id=request.job_id AND queue.queued_at=request.queued_at
          AND queue.provider_competition_id=request.provider_competition_id
          AND queue.season=request.season
    )
    UPDATE football.product_history_sync_queue queue SET
        job_status=target.job_status,attempt_count=target.attempt_count,
        claimed_at=target.claimed_at,started_at=target.started_at,
        finished_at=target.finished_at,next_attempt_at=target.next_attempt_at,
        last_error=target.last_error,updated_at=clock_timestamp()
    FROM target WHERE queue.job_id=target.job_id AND queue.queued_at=target.queued_at
      AND queue.provider_competition_id=request.provider_competition_id AND queue.season=request.season
      AND (queue.job_status,queue.attempt_count,queue.claimed_at,queue.started_at,
           queue.finished_at,queue.next_attempt_at,queue.last_error) IS DISTINCT FROM
          (target.job_status,target.attempt_count,target.claimed_at,target.started_at,
           target.finished_at,target.next_attempt_at,target.last_error);
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.claim_history_work(
    work_key uuid,owner_key text,lease_duration interval,batch_started_at timestamptz
) RETURNS SETOF football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; request football.product_history_work;
        detail football.product_history_sync_queue;
BEGIN
    IF batch_started_at IS NULL OR NOT isfinite(batch_started_at) THEN
        RAISE EXCEPTION 'history batch start must be finite' USING ERRCODE='22023';
    END IF;
    PERFORM football.authorize_worker_publication();
    SELECT * INTO STRICT request FROM football.product_history_work WHERE work_id=work_key;
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
    BEGIN
        SELECT * INTO item FROM football.claim_work(owner_key,lease_duration,
            ARRAY['HISTORICAL_ACQUISITION'],ARRAY[work_key]);
        IF NOT FOUND THEN
            IF EXISTS (SELECT 1 FROM football.work_items WHERE work_id=work_key
                       AND state IN ('FAILED','CANCELLED','SUCCEEDED')) THEN
                PERFORM football.record_transaction_lock(51,
                    'history-queue:'||request.provider_competition_id||':'||request.season);
                PERFORM 1 FROM football.product_history_sync_queue queue
                    WHERE queue.job_id=request.job_id AND queue.queued_at=request.queued_at
                    FOR UPDATE SKIP LOCKED;
                IF NOT FOUND AND EXISTS (SELECT 1 FROM football.product_history_sync_queue queue
                    WHERE queue.job_id=request.job_id AND queue.queued_at=request.queued_at) THEN
                    RAISE EXCEPTION 'terminal history detail is busy' USING ERRCODE='55P03';
                END IF;
                PERFORM football.project_history_work(work_key);
                PERFORM football.authorize_worker_publication();
            END IF;
            RETURN;
        END IF;
        PERFORM football.record_transaction_lock(51,
            'history-queue:'||request.provider_competition_id||':'||request.season);
        SELECT * INTO detail FROM football.product_history_sync_queue queue
            WHERE queue.job_id=request.job_id AND queue.queued_at=request.queued_at
              AND queue.updated_at<batch_started_at
              AND queue.job_status IN ('PENDING','RUNNING')
            FOR UPDATE SKIP LOCKED;
        IF NOT FOUND THEN
            -- The block rollback also revokes the tentative shared claim.
            RAISE EXCEPTION 'history detail is busy or no longer eligible for this batch'
                USING ERRCODE='55P03';
        END IF;
        IF (detail.provider_competition_id,detail.season,detail.attempt_count) IS DISTINCT FROM
           (request.provider_competition_id,request.season,request.attempt_offset+item.attempt_count-1)
           OR (detail.job_status='RUNNING' AND item.attempt_count=1)
           OR (detail.next_attempt_at IS NOT NULL AND detail.next_attempt_at<>item.available_at) THEN
            RAISE EXCEPTION 'history request changed or retains legacy ownership' USING ERRCODE='23505';
        END IF;
        PERFORM football.project_history_work(work_key);
        PERFORM football.lock_work(work_key,owner_key,item.lease_token,item.generation);
        RETURN NEXT item;
    EXCEPTION WHEN lock_not_available THEN
        RETURN;
    END;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.finish_history_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,result_digest football.sha256_hex
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; owned_lease_until timestamptz;
BEGIN
    item:=football.lock_work(work_key,owner_key,token,epoch);
    owned_lease_until:=item.lease_until;
    item:=football.finish_work(work_key,owner_key,token,epoch,result_digest);
    PERFORM football.project_history_work(work_key);
    PERFORM football.authorize_worker_publication();
    IF owned_lease_until<=clock_timestamp() THEN
        RAISE EXCEPTION 'history lease expired during domain projection' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.fail_history_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,classification text,
    error_code text,error_message text
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; owned_lease_until timestamptz;
BEGIN
    item:=football.lock_work(work_key,owner_key,token,epoch);
    owned_lease_until:=item.lease_until;
    item:=football.fail_work(work_key,owner_key,token,epoch,classification,
        error_code,error_message,NULL,NULL);
    PERFORM football.project_history_work(work_key);
    PERFORM football.authorize_worker_publication();
    IF owned_lease_until<=clock_timestamp() THEN
        RAISE EXCEPTION 'history lease expired during domain projection' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'shared history ownership must be retained; roll forward';
END $$;
-- +goose StatementEnd
