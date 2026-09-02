-- +goose Up

CREATE TABLE football.provider_sync_runs (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    policy_version text NOT NULL CHECK (policy_version <> ''),
    status text NOT NULL CHECK (status IN (
        'queued', 'running', 'succeeded', 'partial', 'failed', 'stopped'
    )),
    run_key football.sha256_hex NOT NULL UNIQUE,
    started_at timestamptz,
    completed_at timestamptz,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX provider_sync_runs_provider_created_idx
    ON football.provider_sync_runs (provider_id, created_at DESC);

CREATE TABLE football.provider_resource_cursors (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    resource_key text NOT NULL CHECK (resource_key <> ''),
    scope_key text NOT NULL CHECK (scope_key <> ''),
    cursor_kind text NOT NULL CHECK (cursor_kind <> ''),
    cursor_value text,
    source_snapshot_id uuid,
    observed_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (provider_id, resource_key, scope_key),
    CHECK (updated_at >= observed_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id)
);

CREATE TABLE football.acquisition_jobs (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    sync_run_id uuid NOT NULL REFERENCES football.provider_sync_runs (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    resource_key text NOT NULL CHECK (resource_key <> ''),
    scope_key text NOT NULL CHECK (scope_key <> ''),
    resource_identity text NOT NULL CHECK (resource_identity <> ''),
    resource_revision text NOT NULL CHECK (resource_revision <> ''),
    status text NOT NULL CHECK (status IN (
        'discovered', 'acquiring', 'acquired', 'validated', 'quarantined', 'failed'
    )),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (provider_id, resource_key, scope_key, resource_identity, resource_revision),
    UNIQUE (id, provider_id)
);

CREATE INDEX acquisition_jobs_run_status_idx
    ON football.acquisition_jobs (sync_run_id, status);

CREATE TABLE football.acquired_resources (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    acquisition_job_id uuid NOT NULL REFERENCES football.acquisition_jobs (id),
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    raw_path text NOT NULL CHECK (
        raw_path <> '' AND raw_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    raw_sha256 football.sha256_hex NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    status text NOT NULL CHECK (status IN ('acquired', 'validated', 'quarantined')),
    acquired_at timestamptz NOT NULL,
    UNIQUE (source_resource_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id)
);

CREATE TABLE football.quarantine_records (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    acquisition_job_id uuid NOT NULL REFERENCES football.acquisition_jobs (id),
    source_resource_id uuid,
    finding_key football.sha256_hex NOT NULL UNIQUE,
    reason_code text NOT NULL CHECK (reason_code <> ''),
    details jsonb NOT NULL CHECK (jsonb_typeof(details) = 'object'),
    status text NOT NULL CHECK (status IN ('open', 'reprocessed', 'resolved')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    resolved_at timestamptz,
    CHECK (resolved_at IS NULL OR resolved_at >= created_at),
    FOREIGN KEY (source_resource_id)
        REFERENCES football.source_resources (id)
);

CREATE INDEX quarantine_records_status_created_idx
    ON football.quarantine_records (status, created_at DESC);

CREATE TABLE football.canonical_change_sets (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    sync_run_id uuid NOT NULL REFERENCES football.provider_sync_runs (id),
    change_key football.sha256_hex NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('published', 'verified_existing')),
    changes jsonb NOT NULL CHECK (jsonb_typeof(changes) = 'object'),
    published_at timestamptz NOT NULL,
    UNIQUE (id, sync_run_id)
);
