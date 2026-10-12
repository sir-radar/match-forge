-- +goose Up

ALTER TABLE football.product_sync_runs
    ADD COLUMN worker_id text,
    ADD COLUMN heartbeat_at timestamptz;

UPDATE football.product_sync_runs
   SET worker_id = 'legacy', heartbeat_at = requested_at
 WHERE status IN ('QUEUED', 'RUNNING');

-- +goose Down

ALTER TABLE football.product_sync_runs
    DROP COLUMN heartbeat_at,
    DROP COLUMN worker_id;
