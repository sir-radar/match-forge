-- +goose Up

-- Bound public_context_source's next-fixture lookup by participant and kickoff.
CREATE INDEX product_fixtures_home_kickoff_idx
    ON football.product_fixtures (home_team_id, kickoff_at);
CREATE INDEX product_fixtures_away_kickoff_idx
    ON football.product_fixtures (away_team_id, kickoff_at);

-- +goose Down
DROP INDEX football.product_fixtures_away_kickoff_idx;
DROP INDEX football.product_fixtures_home_kickoff_idx;
