-- +goose Up

ALTER TABLE football.match_observations
    ADD CONSTRAINT match_observations_exact_teams_unique
    UNIQUE (id, match_id, home_team_id, away_team_id);

ALTER TABLE football.match_lifecycle_claims
    ADD CONSTRAINT match_lifecycle_claims_full_lineage_unique
    UNIQUE (
        id, match_id, match_observation_id, dataset_version_id,
        source_snapshot_id, source_resource_id, dataset_file_id, validation_run_id
    );

CREATE TABLE football.match_corner_labels (
    id uuid PRIMARY KEY,
    match_id uuid NOT NULL,
    claim_version text NOT NULL CHECK (claim_version <> ''),
    claim_sha256 football.sha256_hex NOT NULL UNIQUE,
    lifecycle_claim_id uuid NOT NULL,
    match_observation_id uuid NOT NULL,
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    dataset_file_id uuid NOT NULL,
    validation_run_id uuid NOT NULL,
    home_team_id uuid NOT NULL,
    away_team_id uuid NOT NULL,
    home_corners integer NOT NULL CHECK (home_corners >= 0),
    away_corners integer NOT NULL CHECK (away_corners >= 0),
    provider_event_type_id text NOT NULL CHECK (provider_event_type_id <> ''),
    provider_event_type_name text NOT NULL CHECK (provider_event_type_name <> ''),
    provider_pass_type_id integer NOT NULL CHECK (provider_pass_type_id > 0),
    provider_pass_type_name text NOT NULL CHECK (provider_pass_type_name <> ''),
    known_from timestamptz NOT NULL,
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (home_team_id <> away_team_id),
    FOREIGN KEY (
        lifecycle_claim_id, match_id, match_observation_id, dataset_version_id,
        source_snapshot_id, source_resource_id, dataset_file_id, validation_run_id
    ) REFERENCES football.match_lifecycle_claims (
        id, match_id, match_observation_id, dataset_version_id,
        source_snapshot_id, source_resource_id, dataset_file_id, validation_run_id
    ),
    FOREIGN KEY (match_observation_id, match_id, home_team_id, away_team_id)
        REFERENCES football.match_observations (
            id, match_id, home_team_id, away_team_id
        ),
    UNIQUE (match_id, lifecycle_claim_id, claim_version)
);

CREATE INDEX match_corner_labels_match_version_idx
    ON football.match_corner_labels (match_id, claim_version, known_from DESC);
