-- +goose Up
CREATE SCHEMA IF NOT EXISTS gate_a;

CREATE TABLE IF NOT EXISTS gate_a.providers (
    id uuid PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    display_name text NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_a.source_snapshots (
    id uuid PRIMARY KEY,
    provider_id uuid NOT NULL REFERENCES gate_a.providers(id),
    source_repository text NOT NULL,
    source_revision text NOT NULL,
    acquired_at timestamptz NOT NULL,
    manifest_sha256 text NOT NULL,
    UNIQUE (provider_id, source_revision)
);

CREATE TABLE IF NOT EXISTS gate_a.source_resources (
    id uuid PRIMARY KEY,
    source_snapshot_id uuid NOT NULL REFERENCES gate_a.source_snapshots(id),
    provider_path text NOT NULL,
    sha256 text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    raw_path text NOT NULL,
    acquired_at timestamptz NOT NULL,
    UNIQUE (source_snapshot_id, provider_path)
);

CREATE TABLE IF NOT EXISTS gate_a.canonical_entities (
    id uuid PRIMARY KEY,
    entity_type text NOT NULL CHECK (entity_type IN ('competition', 'season', 'team', 'player', 'match', 'event')),
    display_name text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_a.provider_mappings (
    id uuid PRIMARY KEY,
    provider_id uuid NOT NULL REFERENCES gate_a.providers(id),
    entity_type text NOT NULL,
    provider_entity_id text NOT NULL,
    canonical_entity_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    source_snapshot_id uuid NOT NULL REFERENCES gate_a.source_snapshots(id),
    UNIQUE (provider_id, entity_type, provider_entity_id)
);

CREATE TABLE IF NOT EXISTS gate_a.match_observations (
    id uuid PRIMARY KEY,
    canonical_match_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    source_snapshot_id uuid REFERENCES gate_a.source_snapshots(id),
    source_resource_id uuid REFERENCES gate_a.source_resources(id),
    provider_match_id text NOT NULL,
    observation_kind text NOT NULL,
    payload jsonb NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (known_to IS NULL OR known_to > known_from),
    UNIQUE (canonical_match_id, observation_kind, known_from)
);

CREATE TABLE IF NOT EXISTS gate_a.match_teams (
    canonical_match_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    canonical_team_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    side text NOT NULL CHECK (side IN ('home', 'away')),
    PRIMARY KEY (canonical_match_id, canonical_team_id)
);

CREATE TABLE IF NOT EXISTS gate_a.match_players (
    canonical_match_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    canonical_team_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    canonical_player_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    provider_player_id text NOT NULL,
    jersey_number integer,
    starter boolean NOT NULL,
    PRIMARY KEY (canonical_match_id, canonical_team_id, canonical_player_id)
);

CREATE TABLE IF NOT EXISTS gate_a.position_stints (
    id uuid PRIMARY KEY,
    canonical_match_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    canonical_team_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    canonical_player_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    stint_index integer NOT NULL,
    provider_position_id text,
    provider_position_name text,
    from_minute integer,
    to_minute integer,
    start_reason text,
    end_reason text,
    UNIQUE (canonical_match_id, canonical_player_id, stint_index)
);

CREATE TABLE IF NOT EXISTS gate_a.lineup_cards (
    id uuid PRIMARY KEY,
    canonical_match_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    canonical_team_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    canonical_player_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    card_index integer NOT NULL,
    provider_time text,
    card_type text NOT NULL,
    reason text,
    period integer,
    UNIQUE (canonical_match_id, canonical_player_id, card_index)
);

CREATE TABLE IF NOT EXISTS gate_a.event_catalogue (
    canonical_event_id uuid PRIMARY KEY REFERENCES gate_a.canonical_entities(id),
    canonical_match_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    source_snapshot_id uuid NOT NULL REFERENCES gate_a.source_snapshots(id),
    source_resource_id uuid NOT NULL REFERENCES gate_a.source_resources(id),
    provider_event_id text NOT NULL,
    event_index integer NOT NULL,
    UNIQUE (source_snapshot_id, provider_event_id),
    UNIQUE (source_snapshot_id, canonical_match_id, event_index)
);

CREATE TABLE IF NOT EXISTS gate_a.ingestion_runs (
    id uuid PRIMARY KEY,
    source_snapshot_id uuid NOT NULL REFERENCES gate_a.source_snapshots(id),
    scope text NOT NULL,
    normalizer_version text NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    report_path text
);

CREATE TABLE IF NOT EXISTS gate_a.ingestion_components (
    source_snapshot_id uuid NOT NULL REFERENCES gate_a.source_snapshots(id),
    canonical_match_id uuid NOT NULL REFERENCES gate_a.canonical_entities(id),
    component text NOT NULL CHECK (component IN ('metadata', 'lineup', 'events', '360')),
    normalizer_version text NOT NULL,
    status text NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    last_error_code text,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (source_snapshot_id, canonical_match_id, component, normalizer_version)
);

CREATE TABLE IF NOT EXISTS gate_a.dataset_versions (
    id uuid PRIMARY KEY,
    dataset_name text NOT NULL,
    layer text NOT NULL,
    identity_hash text NOT NULL UNIQUE,
    schema_version text NOT NULL,
    schema_sha256 text NOT NULL,
    normalizer_version text NOT NULL,
    source_snapshot_id uuid NOT NULL REFERENCES gate_a.source_snapshots(id),
    status text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_a.dataset_inputs (
    dataset_version_id uuid NOT NULL REFERENCES gate_a.dataset_versions(id),
    source_resource_id uuid NOT NULL REFERENCES gate_a.source_resources(id),
    input_role text NOT NULL,
    PRIMARY KEY (dataset_version_id, source_resource_id)
);

CREATE TABLE IF NOT EXISTS gate_a.dataset_files (
    id uuid PRIMARY KEY,
    dataset_version_id uuid NOT NULL REFERENCES gate_a.dataset_versions(id),
    relative_path text NOT NULL,
    physical_sha256 text NOT NULL,
    logical_sha256 text NOT NULL,
    row_count bigint NOT NULL,
    size_bytes bigint NOT NULL,
    schema_sha256 text NOT NULL,
    UNIQUE (dataset_version_id, relative_path)
);

CREATE TABLE IF NOT EXISTS gate_a.validation_findings (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    finding_key text NOT NULL UNIQUE,
    rule_code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('FATAL', 'QUARANTINE', 'WARNING', 'INFO')),
    action text NOT NULL,
    scope_type text NOT NULL,
    source_resource_id uuid,
    provider_entity_id text,
    field_path text,
    message text NOT NULL,
    evidence jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

-- +goose Down
DROP SCHEMA IF EXISTS gate_a CASCADE;
