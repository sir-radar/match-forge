-- +goose Up

CREATE INDEX match_provider_mappings_active_match_idx
    ON football.match_provider_mappings (match_id) WHERE valid_to IS NULL;

-- +goose Down
DROP INDEX football.match_provider_mappings_active_match_idx;
