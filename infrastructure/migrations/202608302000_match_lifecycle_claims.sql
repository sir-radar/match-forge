-- +goose Up

ALTER TABLE football.match_observations
    ADD CONSTRAINT match_observations_id_match_unique UNIQUE (id, match_id);

CREATE TABLE football.match_lifecycle_claims (
    id uuid PRIMARY KEY,
    match_id uuid NOT NULL REFERENCES football.matches (id),
    lifecycle text NOT NULL CHECK (lifecycle = 'completed'),
    claim_version text NOT NULL CHECK (claim_version <> ''),
    claim_sha256 football.sha256_hex NOT NULL UNIQUE,
    match_observation_id uuid NOT NULL,
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    dataset_file_id uuid NOT NULL,
    validation_run_id uuid NOT NULL,
    known_from timestamptz NOT NULL,
    terminal_period smallint NOT NULL CHECK (terminal_period > 0),
    terminal_event_count integer NOT NULL CHECK (terminal_event_count > 0),
    max_period smallint NOT NULL CHECK (max_period >= terminal_period),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (match_observation_id, match_id)
        REFERENCES football.match_observations (id, match_id),
    FOREIGN KEY (dataset_version_id, source_snapshot_id)
        REFERENCES football.dataset_versions (id, source_snapshot_id),
    FOREIGN KEY (dataset_version_id, source_resource_id)
        REFERENCES football.dataset_inputs (dataset_version_id, source_resource_id),
    FOREIGN KEY (dataset_file_id, dataset_version_id)
        REFERENCES football.dataset_files (id, dataset_version_id),
    FOREIGN KEY (validation_run_id, dataset_version_id, source_snapshot_id)
        REFERENCES football.validation_runs (
            id, dataset_version_id, source_snapshot_id
        ),
    UNIQUE (match_id, dataset_version_id, validation_run_id, claim_version)
);

CREATE INDEX match_lifecycle_claims_match_version_idx
    ON football.match_lifecycle_claims (match_id, claim_version, known_from DESC);
