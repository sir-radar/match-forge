-- +goose Up

ALTER TABLE football.product_team_match_history
    ADD COLUMN source_kickoff_precision text NOT NULL DEFAULT 'EXACT'
        CHECK (source_kickoff_precision IN ('EXACT', 'DATE_ONLY'));

CREATE TABLE football.product_source_result_conflicts (
    conflict_id uuid PRIMARY KEY DEFAULT uuidv7(),
    canonical_match_id uuid NOT NULL REFERENCES football.matches (id),
    existing_provider_code text NOT NULL CHECK (existing_provider_code <> ''),
    existing_home_goals smallint NOT NULL CHECK (existing_home_goals >= 0),
    existing_away_goals smallint NOT NULL CHECK (existing_away_goals >= 0),
    existing_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    incoming_provider_code text NOT NULL CHECK (incoming_provider_code <> ''),
    incoming_home_goals smallint NOT NULL CHECK (incoming_home_goals >= 0),
    incoming_away_goals smallint NOT NULL CHECK (incoming_away_goals >= 0),
    incoming_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    detected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    conflict_key football.sha256_hex NOT NULL UNIQUE
);

CREATE INDEX product_source_result_conflicts_match_idx
    ON football.product_source_result_conflicts (canonical_match_id, detected_at DESC);

CREATE TABLE football.product_sync_runs (
    run_id uuid PRIMARY KEY DEFAULT uuidv7(),
    sync_type text NOT NULL CHECK (sync_type IN (
        'MVP_SYNC', 'OPENFOOTBALL', 'FOOTBALL_DATA_UK', 'HISTORY_BACKFILL',
        'FORECAST_REFRESH', 'EXTERNAL_PREDICTIONS', 'ALL_DATA'
    )),
    status text NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    requested_date date,
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(parameters) = 'object'),
    summary jsonb CHECK (summary IS NULL OR jsonb_typeof(summary) = 'object'),
    error_message text,
    log_path text,
    CHECK (started_at IS NULL OR started_at >= requested_at),
    CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at),
    CHECK ((status = 'FAILED') = (error_message IS NOT NULL)),
    CHECK (status NOT IN ('SUCCEEDED', 'FAILED') OR finished_at IS NOT NULL)
);

CREATE UNIQUE INDEX product_sync_runs_one_active_idx
    ON football.product_sync_runs ((true))
    WHERE status IN ('QUEUED', 'RUNNING');

CREATE INDEX product_sync_runs_requested_idx
    ON football.product_sync_runs (requested_at DESC);

-- +goose Down

DROP TABLE football.product_sync_runs;
DROP TABLE football.product_source_result_conflicts;
ALTER TABLE football.product_team_match_history DROP COLUMN source_kickoff_precision;
