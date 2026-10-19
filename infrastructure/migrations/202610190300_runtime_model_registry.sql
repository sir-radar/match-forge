-- +goose Up

-- Runtime declarations reference existing immutable artifacts. They do not fit,
-- publish fitted bytes, modify historical registrations or confer promotion.
CREATE TABLE football.runtime_model_registrations (
    registration_sha256 football.sha256_hex PRIMARY KEY,
    model_id text NOT NULL CHECK (btrim(model_id) <> ''),
    artifact_sha256 football.sha256_hex NOT NULL,
    lifecycle_state text NOT NULL CHECK (
        lifecycle_state IN ('RESEARCH', 'CHALLENGER', 'CHAMPION', 'RETIRED')
    ),
    record_bytes bytea NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (encode(sha256(record_bytes), 'hex') = registration_sha256),
    CHECK (convert_from(record_bytes, 'UTF8')::jsonb->>'contract' IS NOT DISTINCT FROM 'ModelRegistration'),
    CHECK (convert_from(record_bytes, 'UTF8')::jsonb->>'model_id' IS NOT DISTINCT FROM model_id),
    CHECK (convert_from(record_bytes, 'UTF8')::jsonb->>'artifact_hash' IS NOT DISTINCT FROM artifact_sha256),
    CHECK (convert_from(record_bytes, 'UTF8')::jsonb->>'lifecycle_state' IS NOT DISTINCT FROM lifecycle_state),
    -- Compatibility import of the current serving champion only. Other future
    -- promotion routes retain their native scientific/owner gates.
    CHECK (lifecycle_state <> 'CHAMPION' OR (
        model_id = 'transferable-rolling-goals-poisson-v1'
        AND artifact_sha256 = 'e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4'
    ))
);
CREATE INDEX runtime_model_registrations_model_idx
    ON football.runtime_model_registrations (model_id, registered_at, registration_sha256);

CREATE TRIGGER runtime_model_registrations_immutable
BEFORE UPDATE OR DELETE ON football.runtime_model_registrations
FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER runtime_model_registrations_no_truncate
BEFORE TRUNCATE ON football.runtime_model_registrations
FOR EACH STATEMENT EXECUTE FUNCTION football.guard_multi_model_immutable();

-- +goose Down
-- +goose StatementBegin
DO $$
BEGIN
    RAISE EXCEPTION 'runtime model registrations are immutable; use a forward migration';
END;
$$;
-- +goose StatementEnd
