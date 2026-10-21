-- +goose Up

-- Compatibility workers select their own registered items; claim eligibility,
-- exhausted-lease cleanup, fencing and retries stay in the shared state machine.

-- +goose StatementBegin
CREATE FUNCTION football.claim_work(owner_key text,lease_duration interval,allowed_types text[],allowed_work_ids uuid[])
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
CREATE OR REPLACE FUNCTION football.claim_work(
    owner_key text,lease_duration interval,allowed_types text[]
) RETURNS SETOF football.work_items LANGUAGE sql AS $$
    SELECT * FROM football.claim_work(owner_key,lease_duration,allowed_types,NULL::uuid[])
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'worker claim ownership must remain scoped; roll forward';
END $$;
-- +goose StatementEnd
