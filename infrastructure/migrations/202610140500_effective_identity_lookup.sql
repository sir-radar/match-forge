-- +goose Up

-- Historical identity projections include closed registrations. The active-only
-- match index cannot serve these lookups after prospective admissions at scale.
CREATE INDEX match_provider_mappings_history_match_idx
    ON football.match_provider_mappings (match_id, provider_id, created_at);
CREATE INDEX team_provider_mappings_history_team_idx
    ON football.team_provider_mappings (team_id, provider_id, created_at);

-- +goose Down
DROP INDEX football.team_provider_mappings_history_team_idx;
DROP INDEX football.match_provider_mappings_history_match_idx;
