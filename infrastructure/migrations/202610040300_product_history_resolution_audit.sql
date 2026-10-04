-- +goose Up

ALTER TABLE football.product_history_sync_attempts
    ADD COLUMN last_resolution_path jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(last_resolution_path) = 'array'),
    ADD COLUMN last_provider_codes jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(last_provider_codes) = 'array');

-- +goose Down

ALTER TABLE football.product_history_sync_attempts
    DROP COLUMN last_provider_codes,
    DROP COLUMN last_resolution_path;
