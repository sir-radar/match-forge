-- +goose Up

-- Work identity and input keys are immutable. Exclude competing lease/status
-- writers while permitting foreign-key references to these unchanged keys.
-- This avoids publication/child-enqueue cycles during workflow fan-in.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.lock_work(
    work_key uuid,owner_key text,token uuid,epoch bigint
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
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

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'work publication and immutable references must stay compatible; roll forward';
END $$;
-- +goose StatementEnd
