-- +goose Up

CREATE TABLE football.bitemporal_corrections (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    correction_key football.sha256_hex NOT NULL UNIQUE,
    canonical_entity_id uuid NOT NULL,
    prior_observation_ref text NOT NULL CHECK (prior_observation_ref <> ''),
    replacement_observation_ref text NOT NULL CHECK (replacement_observation_ref <> ''),
    source_snapshot_ref text NOT NULL CHECK (source_snapshot_ref <> ''),
    source_resource_ref text NOT NULL CHECK (source_resource_ref <> ''),
    football_valid_from timestamptz,
    football_valid_to timestamptz,
    known_from timestamptz NOT NULL,
    reason text NOT NULL CHECK (reason <> ''),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (prior_observation_ref <> replacement_observation_ref),
    CHECK (football_valid_to IS NULL OR football_valid_from IS NULL OR football_valid_to >= football_valid_from)
);
