-- +goose Up

-- Transaction-local ordering state follows savepoint rollback and transaction
-- completion. Reentrant locks retain their original class and hash convention.
-- +goose StatementBegin
CREATE FUNCTION football.record_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean DEFAULT false
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    ledger jsonb:=coalesce(nullif(current_setting('matchforge.lock_order',true),''),
        '{"held":{}}')::jsonb;
    declaration jsonb;
    previous_class integer;
    previous_key text;
BEGIN
    IF lock_class IS NULL OR lock_class NOT IN (10,20,30,40,50,60,70)
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

-- +goose StatementBegin
CREATE FUNCTION football.acquire_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean DEFAULT false,
    wait_for_lock boolean DEFAULT true
) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE previous_ledger text:=coalesce(current_setting('matchforge.lock_order',true),'');
    acquired boolean;
BEGIN
    IF wait_for_lock IS NULL THEN
        RAISE EXCEPTION 'lock wait mode must be explicit' USING ERRCODE='22023';
    END IF;
    PERFORM football.record_transaction_lock(lock_class,lock_key,legacy_hash);
    IF wait_for_lock THEN
        IF legacy_hash THEN
            PERFORM pg_advisory_xact_lock(hashtext(lock_key)::bigint);
        ELSE
            PERFORM pg_advisory_xact_lock(hashtextextended(lock_key,0));
        END IF;
        RETURN true;
    END IF;
    acquired:=CASE WHEN legacy_hash THEN pg_try_advisory_xact_lock(hashtext(lock_key)::bigint)
        ELSE pg_try_advisory_xact_lock(hashtextextended(lock_key,0)) END;
    IF NOT acquired THEN
        PERFORM set_config('matchforge.lock_order',previous_ledger,true);
    END IF;
    RETURN acquired;
END;
$$;
-- +goose StatementEnd

-- Product scopes coordinate through competition rows before their fixtures.
-- A failed nonblocking attempt rolls back every lock and ordering entry acquired
-- by this call, including locks acquired before encountering the busy row.
-- +goose StatementBegin
CREATE FUNCTION football.lock_product_fixtures(fixture_keys uuid[],wait_for_locks boolean DEFAULT true)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE competition_keys uuid[]; competition_key uuid; fixture_key uuid; current_competition uuid;
    found_count bigint;
BEGIN
    IF fixture_keys IS NULL OR array_position(fixture_keys,NULL) IS NOT NULL OR wait_for_locks IS NULL THEN
        RAISE EXCEPTION 'fixture lock scope and wait mode must be explicit' USING ERRCODE='22023';
    END IF;
    fixture_keys:=ARRAY(SELECT DISTINCT value FROM unnest(fixture_keys) value ORDER BY value);
    SELECT count(*),coalesce(array_agg(DISTINCT competition_id ORDER BY competition_id),ARRAY[]::uuid[])
        INTO found_count,competition_keys FROM football.product_fixtures WHERE fixture_id=ANY(fixture_keys);
    IF found_count<>cardinality(fixture_keys) THEN
        RAISE EXCEPTION 'fixture lock scope contains an unknown fixture' USING ERRCODE='23503';
    END IF;
    BEGIN
        FOREACH competition_key IN ARRAY competition_keys LOOP
            IF NOT football.acquire_transaction_lock(30,'competition:'||competition_key::text,false,wait_for_locks) THEN
                RAISE EXCEPTION 'competition lock is busy' USING ERRCODE='55P03';
            END IF;
            IF wait_for_locks THEN
                PERFORM 1 FROM football.product_competitions WHERE competition_id=competition_key FOR UPDATE;
            ELSE
                PERFORM 1 FROM football.product_competitions WHERE competition_id=competition_key FOR UPDATE NOWAIT;
            END IF;
        END LOOP;
        FOREACH fixture_key IN ARRAY fixture_keys LOOP
            IF NOT football.acquire_transaction_lock(40,'fixture:'||fixture_key::text,false,wait_for_locks) THEN
                RAISE EXCEPTION 'fixture lock is busy' USING ERRCODE='55P03';
            END IF;
            IF wait_for_locks THEN
                SELECT competition_id INTO current_competition FROM football.product_fixtures
                    WHERE fixture_id=fixture_key FOR UPDATE;
            ELSE
                SELECT competition_id INTO current_competition FROM football.product_fixtures
                    WHERE fixture_id=fixture_key FOR UPDATE NOWAIT;
            END IF;
            IF NOT FOUND OR NOT current_competition=ANY(competition_keys) THEN
                RAISE EXCEPTION 'fixture changed competition while acquiring scope; retry transaction' USING ERRCODE='40001';
            END IF;
        END LOOP;
    EXCEPTION WHEN lock_not_available THEN
        IF wait_for_locks THEN RAISE; END IF;
        RETURN false;
    END;
    RETURN true;
END;
$$;
-- +goose StatementEnd

-- Work publication takes its row lock after any required canonical scope.
-- Skip-locked claims remain independent short transactions with no blocking
-- canonical acquisition; new downstream inserts do not acquire existing work.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.lock_work(
    work_key uuid,owner_key text,token uuid,epoch bigint
) RETURNS football.work_items LANGUAGE plpgsql AS $$
DECLARE item football.work_items;
BEGIN
    PERFORM football.record_transaction_lock(50,'work:'||work_key::text);
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

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'shared transaction lock ordering must be preserved; roll forward';
END $$;
-- +goose StatementEnd
