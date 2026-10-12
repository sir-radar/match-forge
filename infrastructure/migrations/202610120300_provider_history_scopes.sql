-- +goose Up

CREATE TABLE football.product_provider_history_scopes (
    provider_code text NOT NULL CHECK (provider_code IN ('fotmob', 'pitchapi')),
    provider_competition_id text NOT NULL,
    season_label text NOT NULL CHECK (season_label ~ '^[0-9]{4}(/[0-9]{4})?$'),
    status text NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    source_snapshot_id uuid REFERENCES football.source_snapshots (id),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    claimed_at timestamptz,
    next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_error text,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (provider_code, provider_competition_id, season_label)
);

-- +goose Down
DROP TABLE football.product_provider_history_scopes;
