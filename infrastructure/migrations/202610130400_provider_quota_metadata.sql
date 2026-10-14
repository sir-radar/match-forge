-- +goose Up
ALTER TABLE football.provider_request_budgets
    ADD COLUMN minute_window timestamptz,
    ADD COLUMN minute_remaining integer CHECK (minute_remaining >= 0);

-- +goose Down
-- Retain observed quota windows and cooldowns.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'provider quota metadata is a forward-only migration'; END $$;
-- +goose StatementEnd
