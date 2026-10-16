-- +goose Up

-- Retain the provider's distinct Apertura and Clausura labels as scope keys.
-- Existing keys, attempt counts, and retry deadlines are unchanged.
ALTER TABLE football.product_provider_history_scopes
    DROP CONSTRAINT product_provider_history_scopes_season_label_check;
ALTER TABLE football.product_provider_history_scopes
    ADD CONSTRAINT product_provider_history_scopes_season_label_check
    CHECK (season_label ~ '^[0-9]{4}(/[0-9]{4})?( - (Apertura|Clausura))?$');

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'native split-season scope keys must be preserved; migration is forward-only';
END $$;
-- +goose StatementEnd
