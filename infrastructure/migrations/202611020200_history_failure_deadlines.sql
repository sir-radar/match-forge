-- +goose Up
-- Keep shared retry deadlines and the history queue projection in one fenced transaction.
-- +goose StatementBegin
CREATE FUNCTION football.fail_history_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,classification text,
    error_code text,error_message text,retry_after timestamptz,provider_cooldown timestamptz
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items; owned_lease_until timestamptz;
BEGIN
    item:=football.lock_work(work_key,owner_key,token,epoch);
    owned_lease_until:=item.lease_until;
    item:=football.fail_work(work_key,owner_key,token,epoch,classification,
        error_code,error_message,retry_after,provider_cooldown);
    PERFORM football.project_history_work(work_key);
    PERFORM football.authorize_worker_publication();
    IF owned_lease_until<=clock_timestamp() THEN
        RAISE EXCEPTION 'history lease expired during domain projection' USING ERRCODE='55000';
    END IF;
    RETURN item;
END;
$$;
-- +goose StatementEnd

-- Preserve the deployed seven-argument API.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.fail_history_work(
    work_key uuid,owner_key text,token uuid,epoch bigint,classification text,
    error_code text,error_message text
) RETURNS football.work_items LANGUAGE sql AS $$
    SELECT * FROM football.fail_history_work(work_key,owner_key,token,epoch,
        classification,error_code,error_message,NULL::timestamptz,NULL::timestamptz);
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'history failure evidence and compatibility APIs are retained; roll forward';
END $$;
-- +goose StatementEnd
