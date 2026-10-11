-- +goose Up

ALTER TABLE football.product_provider_resource_observations
    DROP CONSTRAINT product_provider_resource_observations_resource_type_check;

ALTER TABLE football.product_provider_resource_observations
    ADD CONSTRAINT product_provider_resource_observations_resource_type_check CHECK (resource_type IN (
        'MATCH_DETAILS', 'EVENTS', 'STATISTICS', 'SHOTS', 'MOMENTUM',
        'LINEUPS', 'PLAYER_RATINGS', 'H2H',
        'NORMALIZED_EVENTS', 'NORMALIZED_STATISTICS'
    ));

-- +goose Down

DELETE FROM football.product_provider_resource_observations
 WHERE resource_type IN ('NORMALIZED_EVENTS', 'NORMALIZED_STATISTICS');

ALTER TABLE football.product_provider_resource_observations
    DROP CONSTRAINT product_provider_resource_observations_resource_type_check;

ALTER TABLE football.product_provider_resource_observations
    ADD CONSTRAINT product_provider_resource_observations_resource_type_check CHECK (resource_type IN (
        'MATCH_DETAILS', 'EVENTS', 'STATISTICS', 'SHOTS', 'MOMENTUM',
        'LINEUPS', 'PLAYER_RATINGS', 'H2H'
    ));
