-- +goose Up

CREATE TABLE football.product_history_sync_attempts (
    provider_competition_id text NOT NULL CHECK (provider_competition_id <> ''),
    season integer NOT NULL CHECK (season > 0),
    last_attempted_at timestamptz NOT NULL,
    last_status text NOT NULL CHECK (last_status IN ('STORED', 'EMPTY', 'UNAVAILABLE')),
    attempt_count integer NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    PRIMARY KEY (provider_competition_id, season)
);

CREATE INDEX product_history_sync_attempts_order_idx
    ON football.product_history_sync_attempts (last_attempted_at);

INSERT INTO football.product_history_sync_attempts (
    provider_competition_id, season, last_attempted_at, last_status
)
SELECT split_part(source_identity, '-', 2),
       split_part(source_identity, '-', 3)::integer,
       max(acquired_at),
       'STORED'
FROM football.source_snapshots
WHERE source_identity ~ '^history-[0-9]+-[0-9]+$'
GROUP BY source_identity;

-- +goose Down

DROP TABLE football.product_history_sync_attempts;
