-- +goose Up

ALTER TABLE football.product_sync_runs
    DROP CONSTRAINT product_sync_runs_status_check,
    DROP CONSTRAINT product_sync_runs_check2,
    DROP CONSTRAINT product_sync_runs_check3;

ALTER TABLE football.product_sync_runs
    ADD CONSTRAINT product_sync_runs_status_check CHECK (
        status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
    ),
    ADD CONSTRAINT product_sync_runs_error_check CHECK (
        (status IN ('FAILED', 'CANCELLED')) = (error_message IS NOT NULL)
    ),
    ADD CONSTRAINT product_sync_runs_finished_check CHECK (
        status NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED') OR finished_at IS NOT NULL
    );

-- +goose Down

ALTER TABLE football.product_sync_runs
    DROP CONSTRAINT product_sync_runs_status_check,
    DROP CONSTRAINT product_sync_runs_error_check,
    DROP CONSTRAINT product_sync_runs_finished_check;

UPDATE football.product_sync_runs
SET status = 'FAILED', error_message = COALESCE(error_message, 'sync was cancelled')
WHERE status = 'CANCELLED';

ALTER TABLE football.product_sync_runs
    ADD CONSTRAINT product_sync_runs_status_check CHECK (
        status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')
    ),
    ADD CONSTRAINT product_sync_runs_check2 CHECK (
        (status = 'FAILED') = (error_message IS NOT NULL)
    ),
    ADD CONSTRAINT product_sync_runs_check3 CHECK (
        status NOT IN ('SUCCEEDED', 'FAILED') OR finished_at IS NOT NULL
    );
