-- +goose Up

CREATE TABLE football.resolution_decisions (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    decision_key football.sha256_hex NOT NULL UNIQUE,
    subject_type text NOT NULL CHECK (subject_type IN (
        'competition', 'season', 'team', 'player', 'match'
    )),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_entity_id text NOT NULL CHECK (provider_entity_id <> ''),
    evidence_refs jsonb NOT NULL CHECK (jsonb_typeof(evidence_refs) = 'array'),
    candidate_canonical_ids jsonb NOT NULL CHECK (jsonb_typeof(candidate_canonical_ids) = 'array'),
    rule_version text NOT NULL CHECK (rule_version <> ''),
    confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    status text NOT NULL CHECK (status IN (
        'AUTO_ACCEPTED', 'REVIEW_REQUIRED', 'MANUALLY_APPROVED',
        'MANUALLY_REJECTED', 'SUPERSEDED'
    )),
    selected_canonical_id uuid,
    actor text NOT NULL CHECK (actor <> ''),
    reason text NOT NULL CHECK (reason <> ''),
    created_at timestamptz NOT NULL,
    supersedes_decision_id uuid REFERENCES football.resolution_decisions (id),
    CHECK (
        status NOT IN ('AUTO_ACCEPTED', 'MANUALLY_APPROVED')
        OR selected_canonical_id IS NOT NULL
    )
);

CREATE INDEX resolution_decisions_subject_provider_idx
    ON football.resolution_decisions (subject_type, provider_id, provider_entity_id, created_at DESC);
