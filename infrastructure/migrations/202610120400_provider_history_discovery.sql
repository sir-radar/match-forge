-- +goose Up

CREATE TABLE football.product_provider_history_discovery (
    provider_code text NOT NULL CHECK (provider_code IN ('fotmob', 'pitchapi')),
    provider_competition_id text NOT NULL,
    last_attempt_at timestamptz NOT NULL,
    next_attempt_at timestamptz NOT NULL,
    last_error text,
    PRIMARY KEY (provider_code, provider_competition_id)
);
CREATE INDEX product_history_kickoff_idx ON football.product_team_match_history (kickoff_at);

-- +goose Down
DROP INDEX football.product_history_kickoff_idx;
DROP TABLE football.product_provider_history_discovery;
