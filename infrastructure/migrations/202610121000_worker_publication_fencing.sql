-- +goose Up
ALTER TABLE football.product_provider_history_scopes ADD COLUMN claim_token uuid;
CREATE UNIQUE INDEX product_history_scope_claim_token_idx
    ON football.product_provider_history_scopes (claim_token) WHERE claim_token IS NOT NULL;

-- +goose StatementBegin
CREATE FUNCTION football.prevent_sync_run_resurrection() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> OLD.status THEN
        PERFORM pg_advisory_xact_lock(hashtextextended('matchforge-run:' || OLD.run_id::text, 0));
    END IF;
    IF OLD.status IN ('FAILED', 'CANCELLED', 'SUCCEEDED') AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION 'terminal sync run cannot change status' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER prevent_sync_run_resurrection BEFORE UPDATE ON football.product_sync_runs
    FOR EACH ROW EXECUTE FUNCTION football.prevent_sync_run_resurrection();

-- +goose StatementBegin
CREATE FUNCTION football.check_worker_publication() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    run_key text := NULLIF(current_setting('matchforge.sync_run_id', true), '');
    worker_key text := NULLIF(current_setting('matchforge.sync_worker_id', true), '');
    scope_key text := NULLIF(current_setting('matchforge.history_claim_token', true), '');
BEGIN
    IF run_key IS NOT NULL THEN
        -- Cancellation/replacement waits for authorized publication to commit.
        -- Heartbeat-only updates remain independent of this lock.
        PERFORM pg_advisory_xact_lock_shared(hashtextextended('matchforge-run:' || run_key, 0));
        PERFORM 1 FROM football.product_sync_runs
         WHERE run_id = run_key::uuid AND worker_id = worker_key
           AND status = 'RUNNING'
           AND heartbeat_at >= clock_timestamp() - interval '2 minutes';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'sync worker ownership lost' USING ERRCODE = '55000';
        END IF;
    END IF;
    IF scope_key IS NOT NULL THEN
        UPDATE football.product_provider_history_scopes
           SET claimed_at = clock_timestamp()
         WHERE claim_token = scope_key::uuid AND status = 'RUNNING'
           AND claimed_at >= clock_timestamp() - interval '30 minutes';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'history scope ownership lost' USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NULL;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
DO $$
DECLARE target record;
BEGIN
    FOR target IN SELECT tablename FROM pg_tables WHERE schemaname = 'football'
        AND tablename NOT IN ('product_sync_runs', 'product_provider_history_scopes')
    LOOP
        EXECUTE format('CREATE TRIGGER check_worker_publication
            BEFORE INSERT OR UPDATE OR DELETE ON football.%I
            FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication()',
            target.tablename);
    END LOOP;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$
DECLARE target record;
BEGIN
    FOR target IN SELECT tablename FROM pg_tables WHERE schemaname = 'football'
        AND tablename NOT IN ('product_sync_runs', 'product_provider_history_scopes')
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS check_worker_publication ON football.%I',
            target.tablename);
    END LOOP;
END;
$$;
-- +goose StatementEnd
DROP FUNCTION football.check_worker_publication();
DROP TRIGGER prevent_sync_run_resurrection ON football.product_sync_runs;
DROP FUNCTION football.prevent_sync_run_resurrection();
ALTER TABLE football.product_provider_history_scopes DROP COLUMN claim_token;
