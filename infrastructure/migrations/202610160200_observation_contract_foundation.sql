-- +goose Up

-- Immutable normalized documents are shadow artifacts, not canonical admissions.
-- Resource-specific relational projections are added separately, after parsing.
CREATE TABLE football.observation_contract_schemas (
    contract_name text NOT NULL CHECK (contract_name <> ''),
    observation_contract_version text NOT NULL CHECK (observation_contract_version <> ''),
    schema_sha256 football.sha256_hex NOT NULL,
    schema_document jsonb NOT NULL CHECK (jsonb_typeof(schema_document) = 'object'),
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (contract_name, observation_contract_version),
    UNIQUE (contract_name, observation_contract_version, schema_sha256)
);

CREATE TABLE football.resource_observation_artifacts (
    observation_id uuid PRIMARY KEY,
    contract_name text NOT NULL,
    observation_contract_version text NOT NULL,
    schema_sha256 football.sha256_hex NOT NULL,
    provider_id uuid NOT NULL REFERENCES football.providers(id),
    provider_native_id text CHECK (provider_native_id <> ''),
    source_record_key text CHECK (source_record_key <> ''),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots(id),
    source_resource_id uuid NOT NULL REFERENCES football.source_resources(id),
    source_sha256 football.sha256_hex NOT NULL,
    provider_schema_version text CHECK (provider_schema_version <> ''),
    adapter_version text NOT NULL CHECK (adapter_version <> ''),
    normalizer_version text NOT NULL CHECK (normalizer_version <> ''),
    resolution_version text CHECK (resolution_version <> ''),
    observed_at timestamptz NOT NULL,
    acquired_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    event_time timestamptz,
    provider_updated_at timestamptz,
    valid_from timestamptz,
    valid_to timestamptz,
    artifact_path text NOT NULL CHECK (
        artifact_path <> '' AND artifact_path !~ '(^/|(^|/)\.\.(/|$))'),
    artifact_sha256 football.sha256_hex NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (contract_name, observation_contract_version, schema_sha256)
        REFERENCES football.observation_contract_schemas(
            contract_name, observation_contract_version, schema_sha256),
    CHECK (provider_native_id IS NOT NULL OR source_record_key IS NOT NULL),
    CHECK (known_at >= acquired_at AND known_at >= observed_at),
    CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_to > valid_from))
);

CREATE INDEX resource_observation_artifacts_source_idx
    ON football.resource_observation_artifacts(source_resource_id, contract_name, known_at);

-- +goose StatementBegin
CREATE FUNCTION football.guard_observation_source() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM football.source_resources r
        JOIN football.source_snapshots s ON s.id = r.source_snapshot_id
        WHERE r.id = NEW.source_resource_id AND s.id = NEW.source_snapshot_id
          AND s.provider_id = NEW.provider_id AND r.sha256 = NEW.source_sha256
          AND r.acquired_at = NEW.acquired_at
    ) THEN
        RAISE EXCEPTION 'observation provenance does not match its registered source';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER resource_observation_source_guard
    BEFORE INSERT ON football.resource_observation_artifacts
    FOR EACH ROW EXECUTE FUNCTION football.guard_observation_source();

-- +goose StatementBegin
CREATE FUNCTION football.reject_observation_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'observation artifacts and contract versions are immutable';
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER observation_contract_immutable
    BEFORE UPDATE OR DELETE ON football.observation_contract_schemas
    FOR EACH ROW EXECUTE FUNCTION football.reject_observation_mutation();
CREATE TRIGGER resource_observation_immutable
    BEFORE UPDATE OR DELETE ON football.resource_observation_artifacts
    FOR EACH ROW EXECUTE FUNCTION football.reject_observation_mutation();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'normalized observation evidence must be preserved; roll forward';
END $$;
-- +goose StatementEnd
