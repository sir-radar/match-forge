-- +goose Up

-- Hold typed qualification failures until an explicit due-scope refresh.
-- Transient failures and live-priority deferrals keep their retry deadlines.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.drive_provider_scope_work() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item football.work_items; identity uuid; digest text; current_work uuid;
BEGIN
    SELECT work_id INTO current_work FROM football.product_provider_scope_work
        WHERE provider_code=OLD.provider_code
          AND provider_competition_id=OLD.provider_competition_id
          AND season_label=OLD.season_label;
    IF NEW.status='PENDING' AND OLD.status='FAILED' AND EXISTS (
        SELECT 1 FROM football.work_items WHERE work_id=current_work AND state='BLOCKED'
    ) THEN
        PERFORM football.authorize_worker_publication();
        PERFORM football.release_blocked_work(current_work,NEW.next_attempt_at);
    ELSIF NEW.status='RUNNING' AND (OLD.status<>'RUNNING' OR
        NEW.claim_token IS DISTINCT FROM OLD.claim_token) THEN
        PERFORM football.authorize_worker_publication();
        PERFORM football.record_transaction_lock(5,'matchforge-scope:'||NEW.claim_token::text);
        SELECT * INTO item FROM football.work_items WHERE work_id=current_work;
        IF FOUND AND item.state='CANCELLED' AND OLD.status<>'PENDING' THEN RETURN NULL; END IF;
        IF NOT FOUND OR item.state IN ('SUCCEEDED','FAILED','CANCELLED') THEN
            identity:=gen_random_uuid();
            digest:=encode(sha256(convert_to(jsonb_build_object('provider',NEW.provider_code,
                'competition',NEW.provider_competition_id,'season',NEW.season_label,
                'attempt_offset',OLD.attempts,'requested_at',OLD.next_attempt_at)::text,'UTF8')),'hex');
            PERFORM football.enqueue_work(identity,'HISTORICAL_ACQUISITION',
                'provider-scope:'||NEW.provider_code||':'||NEW.provider_competition_id
                ||':'||NEW.season_label||':'||identity,digest,0,OLD.next_attempt_at,
                2147483647-OLD.attempts,0::double precision,0::double precision,
                1::double precision,ARRAY[]::uuid[],NULL::uuid,0::double precision);
        ELSE identity:=item.work_id;
        END IF;
        SELECT * INTO item FROM football.claim_work('provider-scope:'||identity,
            interval '30 minutes',ARRAY['HISTORICAL_ACQUISITION'],ARRAY[identity]);
        IF NOT FOUND THEN RETURN NULL; END IF;
        INSERT INTO football.product_provider_scope_work
            (provider_code,provider_competition_id,season_label,work_id)
            VALUES(NEW.provider_code,NEW.provider_competition_id,NEW.season_label,identity)
            ON CONFLICT(provider_code,provider_competition_id,season_label)
            DO UPDATE SET work_id=EXCLUDED.work_id;
        NEW.claim_token:=item.lease_token;
        NEW.claimed_at:=item.heartbeat_at;
    ELSIF OLD.status='RUNNING' AND NEW.status IN ('SUCCEEDED','FAILED','DEFERRED')
        AND current_work IS NOT NULL THEN
        SELECT * INTO STRICT item FROM football.work_items WHERE work_id=current_work;
        IF item.state='CANCELLED' AND NEW.status='FAILED' THEN RETURN NEW; END IF;
        IF NEW.status='SUCCEEDED' THEN
            digest:=encode(sha256(convert_to(NEW.summary::text,'UTF8')),'hex');
            item:=football.finish_work(item.work_id,'provider-scope:'||item.work_id,
                OLD.claim_token,item.generation,digest::football.sha256_hex);
        ELSE
            item:=football.fail_work(item.work_id,'provider-scope:'||item.work_id,
                OLD.claim_token,item.generation,
                CASE WHEN NEW.status='FAILED' AND NEW.last_error IN (
                    'BLOCKED_IDENTITY','BLOCKED_SCORE_BASIS',
                    'BLOCKED_HISTORY_ADMISSION','BLOCKED_RESULT_CONFLICT')
                    AND NEW.summary->>'status'=NEW.last_error
                    THEN 'BLOCKED_EXTERNAL' ELSE 'RETRYABLE' END,
                'PROVIDER_SCOPE_FAILED',
                coalesce(nullif(NEW.last_error,''),'provider scope did not complete'),
                NEW.next_attempt_at,NULL);
            IF item.state='RETRY_WAIT' THEN NEW.next_attempt_at:=item.available_at; END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- Held work and its attempt history require an explicit forward repair.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'provider scope qualification holds require forward repair'; END $$;
-- +goose StatementEnd
