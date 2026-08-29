-- +goose Up

CREATE TABLE football.dataset_versions (
    id uuid PRIMARY KEY,
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    dataset_name text NOT NULL CHECK (dataset_name ~ '^[a-z][a-z0-9_]*$'),
    layer text NOT NULL CHECK (layer IN ('normalized', 'curated', 'features')),
    identity_hash football.sha256_hex NOT NULL UNIQUE,
    schema_version text NOT NULL CHECK (schema_version <> ''),
    schema_sha256 football.sha256_hex NOT NULL,
    normalizer_version text NOT NULL CHECK (normalizer_version <> ''),
    manifest_path text NOT NULL CHECK (
        manifest_path <> ''
        AND manifest_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    manifest_sha256 football.sha256_hex NOT NULL,
    status text NOT NULL CHECK (status IN ('published')),
    published_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (id, source_snapshot_id)
);

CREATE TABLE football.dataset_inputs (
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    input_role text NOT NULL CHECK (input_role IN ('source')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (dataset_version_id, source_resource_id),
    FOREIGN KEY (dataset_version_id, source_snapshot_id)
        REFERENCES football.dataset_versions (id, source_snapshot_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id)
);

CREATE TABLE football.dataset_files (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    dataset_version_id uuid NOT NULL REFERENCES football.dataset_versions (id),
    relative_path text NOT NULL CHECK (
        relative_path <> ''
        AND relative_path !~ '(^/|(^|/)\.\.(/|$))'
        AND relative_path LIKE '%.parquet'
    ),
    physical_sha256 football.sha256_hex NOT NULL,
    logical_sha256 football.sha256_hex NOT NULL,
    row_count bigint NOT NULL CHECK (row_count >= 0),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    schema_sha256 football.sha256_hex NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (dataset_version_id, relative_path)
);

CREATE INDEX dataset_versions_source_snapshot_idx
    ON football.dataset_versions (source_snapshot_id, dataset_name);
