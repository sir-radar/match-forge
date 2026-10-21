-- +goose Up

-- Work rows precede their legacy domain detail. Existing queue batches retain
-- sorted keys and their original transaction boundaries at the new detail rank.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean,shared_mode boolean
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    ledger jsonb:=coalesce(nullif(current_setting('matchforge.lock_order',true),''),
        '{"held":{}}')::jsonb;
    declaration jsonb;
    previous_class integer;
    previous_key text;
BEGIN
    IF lock_class IS NULL OR lock_class NOT IN (5,10,20,25,30,40,50,51,55,56,57,58,59,60,65,70,75,80)
       OR lock_key IS NULL OR btrim(lock_key)='' OR legacy_hash IS NULL OR shared_mode IS NULL THEN
        RAISE EXCEPTION 'explicit lock class, key and hash convention required' USING ERRCODE='22023';
    END IF;
    declaration:=jsonb_build_object('class',lock_class,'legacy_hash',legacy_hash,'shared',shared_mode);
    IF (ledger->'held') ? lock_key THEN
        IF ((ledger->'held'->lock_key) - 'shared') IS DISTINCT FROM (declaration - 'shared')
           OR (coalesce((ledger->'held'->lock_key->>'shared')::boolean,false) AND NOT shared_mode) THEN
            RAISE EXCEPTION 'held lock cannot change class, hash convention or upgrade shared mode' USING ERRCODE='MFL01';
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

CREATE TABLE football.product_history_work (
    work_id uuid PRIMARY KEY REFERENCES football.work_items(work_id),
    job_id uuid NOT NULL,
    queued_at timestamptz NOT NULL CHECK (isfinite(queued_at)),
    provider_competition_id text NOT NULL CHECK (btrim(provider_competition_id)<>''),
    season integer NOT NULL,
    attempt_offset integer NOT NULL CHECK (attempt_offset>=0),
    UNIQUE (job_id,queued_at)
);

-- Keep request context after a legacy detail row is retired. Old request/work
-- associations cannot be repointed to a new request or fencing generation.
-- +goose StatementBegin
CREATE FUNCTION football.reject_history_work_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'history request/work associations are immutable' USING ERRCODE='55000';
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER preserve_history_work BEFORE UPDATE OR DELETE ON football.product_history_work
    FOR EACH ROW EXECUTE FUNCTION football.reject_history_work_mutation();
CREATE TRIGGER preserve_history_work_truncate BEFORE TRUNCATE ON football.product_history_work
    FOR EACH STATEMENT EXECUTE FUNCTION football.reject_history_work_mutation();
CREATE TRIGGER check_worker_publication BEFORE INSERT ON football.product_history_work
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'history request/work associations must be retained; roll forward';
END $$;
-- +goose StatementEnd
