-- +goose Up

-- Shared identity fences permit independent competition history qualification.
-- Identity-wide mutation retains exclusive fencing; upgrades fail before waiting.

-- +goose StatementBegin
CREATE FUNCTION football.record_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean,shared_mode boolean
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    ledger jsonb:=coalesce(nullif(current_setting('matchforge.lock_order',true),''),
        '{"held":{}}')::jsonb;
    declaration jsonb;
    previous_class integer;
    previous_key text;
BEGIN
    IF lock_class IS NULL OR lock_class NOT IN (5,10,20,25,30,40,50,55,56,57,58,59,60,65,70,75,80)
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

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean DEFAULT false
) RETURNS void LANGUAGE sql AS $$
    SELECT football.record_transaction_lock(lock_class,lock_key,legacy_hash,false)
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.acquire_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean,
    wait_for_lock boolean,shared_mode boolean
) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE previous_ledger text; acquired boolean; lock_hash bigint;
BEGIN
    IF wait_for_lock IS NULL THEN
        RAISE EXCEPTION 'lock wait mode must be explicit' USING ERRCODE='22023';
    END IF;
    PERFORM football.authorize_worker_publication();
    previous_ledger:=coalesce(current_setting('matchforge.lock_order',true),'');
    PERFORM football.record_transaction_lock(lock_class,lock_key,legacy_hash,shared_mode);
    lock_hash:=CASE WHEN legacy_hash THEN hashtext(lock_key)::bigint
        ELSE hashtextextended(lock_key,0) END;
    IF wait_for_lock THEN
        IF shared_mode THEN PERFORM pg_advisory_xact_lock_shared(lock_hash);
        ELSE PERFORM pg_advisory_xact_lock(lock_hash); END IF;
        RETURN true;
    END IF;
    acquired:=CASE WHEN shared_mode THEN pg_try_advisory_xact_lock_shared(lock_hash)
        ELSE pg_try_advisory_xact_lock(lock_hash) END;
    IF NOT acquired THEN
        PERFORM set_config('matchforge.lock_order',previous_ledger,true);
    END IF;
    RETURN acquired;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.acquire_transaction_lock(
    lock_class integer,lock_key text,legacy_hash boolean DEFAULT false,
    wait_for_lock boolean DEFAULT true
) RETURNS boolean LANGUAGE sql AS $$
    SELECT football.acquire_transaction_lock(lock_class,lock_key,legacy_hash,wait_for_lock,false)
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.lock_history_qualification(fixture_keys uuid[]) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE competition_key uuid; ledger jsonb;
BEGIN
    PERFORM football.authorize_worker_publication();
    ledger:=coalesce(nullif(current_setting('matchforge.lock_order',true),''),'{}')::jsonb;
    -- An existing exclusive identity fence already protects this transaction's
    -- fan-out. Preserve the bounded original lock count for fact mutations.
    IF (ledger->'held'->'product-identity-admission'->>'shared')::boolean=false THEN
        PERFORM football.record_transaction_lock(20,'product-identity-admission');
        RETURN;
    END IF;
    PERFORM football.acquire_transaction_lock(20,'product-identity-admission',false,true,true);
    FOR competition_key IN SELECT DISTINCT competition_id
        FROM football.product_team_match_history WHERE fixture_id=ANY(fixture_keys)
        ORDER BY competition_id
    LOOP
        PERFORM football.acquire_transaction_lock(25,'history:competition:'||competition_key::text,
            false,true,false);
    END LOOP;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_history_decisions(fixture_keys uuid[]) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.lock_history_qualification(fixture_keys);
    INSERT INTO football.product_match_history_decisions (
        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
        home_goals, away_goals, home_xg, away_xg, source_provider_code,
        source_snapshot_id, source_kickoff_precision, eligible, reason, source_known_at)
    SELECT proposed.* FROM (
    SELECT h.fixture_id, h.competition_id, COALESCE(hm.identity, h.home_team_id) AS home_team_id,
           COALESCE(am.identity, h.away_team_id) AS away_team_id, h.kickoff_at,
           h.home_goals, h.away_goals, h.home_xg, h.away_xg, h.source_provider_code,
           h.source_snapshot_id, h.source_kickoff_precision,
           s.status = 'validated' AND COALESCE(f.identity_status, 'VERIFIED') = 'VERIFIED'
           AND COALESCE(f.status NOT IN ('AWARDED', 'ABANDONED', 'CANCELLED'), true)
           AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
               WHERE r.member_fixture_id = h.fixture_id AND r.active
                 AND (r.resolution_status NOT IN ('UNIQUE', 'DUPLICATE_RESOLVED')
                      OR r.representative_fixture_id <> h.fixture_id))
           AND EXISTS (SELECT 1 FROM football.competition_provider_mappings m
               WHERE m.competition_id = h.competition_id AND m.provider_id = s.provider_id
                 AND m.valid_to IS NULL AND m.mapping_confidence = 1
                 AND football.product_mapping_trusted('competition', m.id, m.competition_id))
           AND COALESCE(hm.trusted, false)
           AND COALESCE(am.trusted, false) AS eligible,
           CASE WHEN f.status IN ('AWARDED', 'ABANDONED', 'CANCELLED')
                THEN 'non-played terminal status' ELSE 'ProductIdentityTrustV1' END AS reason, s.acquired_at AS source_known_at
    FROM football.product_team_match_history h
    JOIN football.source_snapshots s ON s.id = h.source_snapshot_id
    LEFT JOIN football.product_fixtures f ON f.fixture_id = h.fixture_id
    LEFT JOIN LATERAL (
        SELECT CASE WHEN count(DISTINCT effective.identity) = 1
                    THEN min(effective.identity::text)::uuid END AS identity,
               count(DISTINCT effective.identity) = 1 AND bool_and(
                   football.product_mapping_trusted('team', mapping.id, effective.identity)) AS trusted
        FROM football.team_provider_mappings mapping
        CROSS JOIN LATERAL (SELECT COALESCE(
            football.product_team_identity_at(mapping.id, clock_timestamp()),
            mapping.team_id) AS identity) effective
        WHERE mapping.team_id = h.home_team_id AND mapping.provider_id = s.provider_id
          AND mapping.valid_to IS NULL
    ) hm ON true
    LEFT JOIN LATERAL (
        SELECT CASE WHEN count(DISTINCT effective.identity) = 1
                    THEN min(effective.identity::text)::uuid END AS identity,
               count(DISTINCT effective.identity) = 1 AND bool_and(
                   football.product_mapping_trusted('team', mapping.id, effective.identity)) AS trusted
        FROM football.team_provider_mappings mapping
        CROSS JOIN LATERAL (SELECT COALESCE(
            football.product_team_identity_at(mapping.id, clock_timestamp()),
            mapping.team_id) AS identity) effective
        WHERE mapping.team_id = h.away_team_id AND mapping.provider_id = s.provider_id
          AND mapping.valid_to IS NULL
    ) am ON true
    WHERE h.fixture_id = ANY(fixture_keys)) proposed
    WHERE NOT EXISTS (
        SELECT 1 FROM (SELECT * FROM football.product_match_history_decisions
                      WHERE fixture_id = proposed.fixture_id
                      ORDER BY decided_at DESC, decision_id DESC LIMIT 1) previous
        WHERE (to_jsonb(previous) - 'decision_id' - 'decided_at') = to_jsonb(proposed)
    ) ORDER BY proposed.fixture_id;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_source_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE snapshot_key uuid := (to_jsonb(NEW)->> CASE TG_TABLE_NAME
    WHEN 'source_snapshots' THEN 'id' ELSE 'source_snapshot_id' END)::uuid;
    fixture_keys uuid[];
BEGIN
    SELECT array_agg(h.fixture_id ORDER BY h.fixture_id) INTO fixture_keys
    FROM football.product_team_match_history h
    WHERE h.source_snapshot_id = snapshot_key OR EXISTS (
        SELECT 1 FROM football.product_identity_admissions a
        WHERE a.source_snapshot_id = snapshot_key
          AND ((a.entity_type = 'competition' AND a.canonical_id = h.competition_id)
               OR (a.entity_type = 'team' AND a.canonical_id IN (h.home_team_id, h.away_team_id)))
    );
    IF fixture_keys IS NOT NULL THEN
        PERFORM football.acquire_transaction_lock(20,'product-identity-admission');
        PERFORM football.record_product_history_decisions(fixture_keys);
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.acquire_transaction_lock(20,'product-identity-admission');
    PERFORM football.record_product_history_decision(NEW.fixture_id);
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_resolution_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.acquire_transaction_lock(20,'product-identity-admission');
    PERFORM football.record_product_history_decision(COALESCE(NEW.member_fixture_id, OLD.member_fixture_id));
    RETURN COALESCE(NEW, OLD);
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.authorize_worker_publication() RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    run_key text := NULLIF(current_setting('matchforge.sync_run_id', true), '');
    worker_key text := NULLIF(current_setting('matchforge.sync_worker_id', true), '');
    scope_key text := NULLIF(current_setting('matchforge.history_claim_token', true), '');
BEGIN
    IF run_key IS NOT NULL THEN
        PERFORM football.record_transaction_lock(5,'matchforge-run:'||run_key,false,true);
        PERFORM pg_advisory_xact_lock_shared(hashtextextended('matchforge-run:'||run_key,0));
        PERFORM 1 FROM football.product_sync_runs
         WHERE run_id=run_key::uuid AND worker_id=worker_key
           AND status='RUNNING'
           AND heartbeat_at>=clock_timestamp()-interval '2 minutes';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'sync worker ownership lost' USING ERRCODE='55000';
        END IF;
    END IF;
    IF scope_key IS NOT NULL THEN
        PERFORM football.record_transaction_lock(5,'matchforge-scope:'||scope_key);
        UPDATE football.product_provider_history_scopes SET claimed_at=clock_timestamp()
         WHERE claim_token=scope_key::uuid AND status='RUNNING'
           AND claimed_at>=clock_timestamp()-interval '30 minutes';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'history scope ownership lost' USING ERRCODE='55000';
        END IF;
    END IF;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'scoped identity coordination must retain fencing; roll forward';
END $$;
-- +goose StatementEnd
