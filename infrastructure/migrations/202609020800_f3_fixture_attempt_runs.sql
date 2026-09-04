-- +goose Up

ALTER TABLE football.fixture_processing_attempts
    ADD COLUMN sync_run_id uuid NOT NULL REFERENCES football.provider_sync_runs (id);

CREATE INDEX fixture_processing_attempts_sync_run_idx
    ON football.fixture_processing_attempts (sync_run_id);
