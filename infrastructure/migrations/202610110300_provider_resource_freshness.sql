-- +goose Up

ALTER TABLE football.product_provider_fixture_observations
    ADD COLUMN last_fetched_at timestamptz;

UPDATE football.product_provider_fixture_observations
   SET last_fetched_at = observed_at;

ALTER TABLE football.product_provider_fixture_observations
    ALTER COLUMN last_fetched_at SET NOT NULL;

ALTER TABLE football.product_provider_resource_observations
    ADD COLUMN last_fetched_at timestamptz;

UPDATE football.product_provider_resource_observations
   SET last_fetched_at = observed_at;

ALTER TABLE football.product_provider_resource_observations
    ALTER COLUMN last_fetched_at SET NOT NULL;

-- +goose Down

ALTER TABLE football.product_provider_resource_observations
    DROP COLUMN last_fetched_at;

ALTER TABLE football.product_provider_fixture_observations
    DROP COLUMN last_fetched_at;
