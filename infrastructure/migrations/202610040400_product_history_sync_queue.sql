-- +goose Up

CREATE TABLE football.product_history_sync_queue (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_competition_id text NOT NULL,
    season integer NOT NULL,
    sync_run_id uuid REFERENCES football.product_sync_runs(run_id) ON DELETE SET NULL,
    job_status text NOT NULL DEFAULT 'PENDING'
        CHECK (job_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    queued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at timestamptz,
    last_error text,
    claimed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (provider_competition_id, season)
);

CREATE INDEX product_history_sync_queue_runnable_idx
    ON football.product_history_sync_queue (queued_at, job_id)
    WHERE job_status = 'PENDING';

CREATE INDEX product_history_sync_queue_run_status_idx
    ON football.product_history_sync_queue (sync_run_id, job_status);

-- +goose Down

DROP TABLE football.product_history_sync_queue;
