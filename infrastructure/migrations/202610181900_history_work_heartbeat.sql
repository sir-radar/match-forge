-- +goose Up

-- Keep legacy lease/operator detail aligned with the authoritative heartbeat.
-- +goose StatementBegin
CREATE FUNCTION football.heartbeat_history_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,lease_duration interval,run_key uuid
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; request football.product_history_work;
BEGIN
    item:=football.heartbeat_work(work_key,owner_key,token,epoch,lease_duration);
    SELECT * INTO STRICT request FROM football.product_history_work WHERE work_id=work_key;
    PERFORM football.record_transaction_lock(51,
        'history-queue:'||request.provider_competition_id||':'||request.season);
    UPDATE football.product_history_sync_queue queue SET
        claimed_at=item.heartbeat_at,sync_run_id=coalesce(run_key,queue.sync_run_id),
        updated_at=clock_timestamp()
    WHERE queue.job_id=request.job_id AND queue.queued_at=request.queued_at
      AND queue.job_status='RUNNING' AND queue.attempt_count=request.attempt_offset+item.attempt_count;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'history request changed before heartbeat' USING ERRCODE='23505';
    END IF;
    PERFORM football.lock_work(work_key,owner_key,token,epoch);
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.cancel_history_work(work_key uuid) RETURNS football.work_items
LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
    item:=football.cancel_work(work_key);
    PERFORM football.project_history_work(work_key);
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'shared history lease projection must be retained; roll forward';
END $$;
-- +goose StatementEnd
