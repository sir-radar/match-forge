-- +goose Up

-- Follow the existing derivation and governance dependencies: dataset, validation,
-- lifecycle, kickoff, labels, features, fitted models, forecasts, evaluation,
-- then promotion. Preserve every existing advisory key and hash convention.
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
    IF lock_class IS NULL OR lock_class NOT IN (10,20,30,40,50,55,56,57,58,59,60,65,70,75,80)
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

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'publication dependency lock order must remain enforced; roll forward';
END $$;
-- +goose StatementEnd
