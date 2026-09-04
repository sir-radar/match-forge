-- +goose Up

CREATE TABLE football.quarantine_reprocess_requests (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    request_key football.sha256_hex NOT NULL UNIQUE,
    source_quarantine_record_id uuid NOT NULL REFERENCES football.quarantine_records (id),
    trigger text NOT NULL CHECK (trigger IN (
        'MAPPING_REVIEWED', 'SCHEMA_FIXED', 'PROVIDER_CORRECTION', 'POLICY_VERSIONED'
    )),
    trigger_ref text NOT NULL CHECK (trigger_ref <> ''),
    policy_version text NOT NULL CHECK (policy_version <> ''),
    scheduled_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX quarantine_reprocess_requests_source_scheduled_idx
    ON football.quarantine_reprocess_requests (source_quarantine_record_id, scheduled_at);
