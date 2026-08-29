-- +goose Up

ALTER TABLE football.dataset_files
    ADD CONSTRAINT dataset_files_id_version_unique
    UNIQUE (id, dataset_version_id);

CREATE TABLE football.validation_runs (
    id uuid PRIMARY KEY,
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    identity_hash football.sha256_hex NOT NULL UNIQUE,
    policy_version text NOT NULL CHECK (policy_version <> ''),
    policy_sha256 football.sha256_hex NOT NULL,
    validator_version text NOT NULL CHECK (validator_version <> ''),
    status text NOT NULL CHECK (status IN (
        'passed', 'warnings', 'quarantined', 'failed'
    )),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (completed_at >= started_at),
    FOREIGN KEY (dataset_version_id, source_snapshot_id)
        REFERENCES football.dataset_versions (id, source_snapshot_id),
    UNIQUE (id, dataset_version_id, source_snapshot_id)
);

CREATE INDEX validation_runs_dataset_idx
    ON football.validation_runs (dataset_version_id, completed_at DESC);

CREATE TABLE football.validation_findings (
    id uuid PRIMARY KEY,
    validation_run_id uuid NOT NULL,
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    dataset_file_id uuid,
    source_resource_id uuid,
    finding_key football.sha256_hex NOT NULL UNIQUE,
    rule_code text NOT NULL CHECK (rule_code ~ '^[A-Z][A-Z0-9_]+$'),
    severity text NOT NULL CHECK (severity IN (
        'FATAL', 'QUARANTINE', 'WARNING', 'INFO'
    )),
    action text NOT NULL CHECK (action ~ '^[A-Z][A-Z0-9_]+$'),
    scope_type text NOT NULL CHECK (scope_type IN (
        'dataset', 'file', 'match', 'event', 'lineup'
    )),
    provider_entity_id text,
    field_path text,
    message text NOT NULL CHECK (message <> ''),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (validation_run_id, dataset_version_id, source_snapshot_id)
        REFERENCES football.validation_runs (id, dataset_version_id, source_snapshot_id),
    FOREIGN KEY (dataset_file_id, dataset_version_id)
        REFERENCES football.dataset_files (id, dataset_version_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id)
);

CREATE INDEX validation_findings_run_severity_idx
    ON football.validation_findings (validation_run_id, severity, rule_code);
