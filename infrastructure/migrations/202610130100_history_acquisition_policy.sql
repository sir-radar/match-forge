-- +goose Up

ALTER TABLE football.product_provider_history_discovery
    ADD COLUMN resource_name text,
    ADD COLUMN source_snapshot_id uuid REFERENCES football.source_snapshots (id);
UPDATE football.product_provider_history_discovery
    SET resource_name = 'league-catalogue-' || provider_competition_id;
ALTER TABLE football.product_provider_history_discovery
    ALTER COLUMN resource_name SET NOT NULL,
    DROP CONSTRAINT product_provider_history_discovery_pkey,
    ALTER COLUMN provider_competition_id DROP NOT NULL,
    ADD PRIMARY KEY (provider_code, resource_name);

ALTER TABLE football.product_provider_history_scopes
    DROP CONSTRAINT product_provider_history_scopes_status_check,
    ADD CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'DEFERRED')),
    ADD COLUMN first_observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ADD COLUMN completed_at timestamptz;

ALTER TABLE football.provider_request_budgets
    ADD COLUMN historical_requests_used integer NOT NULL DEFAULT 0
        CHECK (historical_requests_used >= 0),
    ADD COLUMN deferred_until timestamptz;

-- +goose Down
-- Preserve measured progress and cache checks rather than discard their timestamps.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'history acquisition policy is a forward-only migration'; END $$;
-- +goose StatementEnd
