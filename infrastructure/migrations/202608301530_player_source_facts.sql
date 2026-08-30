-- +goose Up

ALTER TABLE football.player_observations
    DROP CONSTRAINT player_observations_full_name_check,
    ALTER COLUMN full_name DROP NOT NULL,
    ADD CONSTRAINT player_observations_full_name_check
        CHECK (full_name IS NULL OR full_name <> ''),
    ADD COLUMN fact_status text NOT NULL DEFAULT 'consistent'
        CHECK (fact_status IN ('consistent', 'conflicting'));

CREATE TABLE football.player_source_facts (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    player_id uuid NOT NULL REFERENCES football.players (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_player_id text NOT NULL CHECK (provider_player_id <> ''),
    full_name text NOT NULL CHECK (full_name <> ''),
    nickname text,
    country_provider_id text,
    nickname_observed boolean NOT NULL,
    country_observed boolean NOT NULL,
    observation_kind text NOT NULL CHECK (observation_kind IN ('lineup', 'event')),
    fact_sha256 football.sha256_hex NOT NULL UNIQUE,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (
        source_snapshot_id,
        source_resource_id,
        provider_player_id,
        observation_kind,
        fact_sha256
    )
);

CREATE INDEX player_source_facts_snapshot_player_idx
    ON football.player_source_facts (
        source_snapshot_id,
        provider_player_id,
        observation_kind,
        source_resource_id
    );
