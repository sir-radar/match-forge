-- +goose Up

CREATE TABLE football.artifact_retirement_events (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    object_kind text NOT NULL CHECK (object_kind = 'FORECAST'),
    object_id uuid NOT NULL REFERENCES football.baseline_forecasts (id),
    retirement_scope text NOT NULL CHECK (
        retirement_scope = 'TEST_ONLY_HARD_GATE_EXCLUSION'
    ),
    reason text NOT NULL CHECK (reason = 'SYNTHETIC_TEST_LINEAGE'),
    evidence_reference text NOT NULL CHECK (evidence_reference <> ''),
    recorded_at timestamptz NOT NULL,
    code_commit_sha text NOT NULL CHECK (code_commit_sha ~ '^[0-9a-f]{40}$'),
    contract_version text NOT NULL DEFAULT 'artifact-retirement-event-v1' CHECK (
        contract_version = 'artifact-retirement-event-v1'
    ),
    UNIQUE (object_kind, object_id, retirement_scope, reason)
);

CREATE INDEX artifact_retirement_events_scope_idx
    ON football.artifact_retirement_events (retirement_scope, object_kind, object_id);

CREATE TRIGGER artifact_retirement_events_append_only
BEFORE UPDATE OR DELETE ON football.artifact_retirement_events
FOR EACH ROW EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
