-- +goose Up

CREATE TABLE football.reconciliation_conflicts (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    conflict_key football.sha256_hex NOT NULL UNIQUE,
    subject_type text NOT NULL CHECK (subject_type <> ''),
    observation_refs jsonb NOT NULL CHECK (jsonb_typeof(observation_refs) = 'array'),
    policy_version text NOT NULL CHECK (policy_version <> ''),
    disposition text NOT NULL CHECK (disposition IN (
        'RESOLVED', 'REVIEW_REQUIRED', 'QUARANTINED'
    )),
    selected_observation_ref text,
    reason text NOT NULL CHECK (reason <> ''),
    created_at timestamptz NOT NULL,
    CHECK (disposition <> 'RESOLVED' OR selected_observation_ref IS NOT NULL)
);

CREATE INDEX reconciliation_conflicts_subject_created_idx
    ON football.reconciliation_conflicts (subject_type, created_at DESC);
