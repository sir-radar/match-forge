-- +goose Up
-- Append-only raw-file bindings for legacy snapshots whose manifest_path names the raw provider
-- file and whose manifest_sha256 is the digest of that path (HistoricalBackfillStore before
-- 55a7e35d). A binding states which registered source resource already proves the bytes at
-- that path. It does not edit the snapshot, supply a checksum or say a manifest existed: the
-- bound checksum and size must equal a resource row, and the path must be named by that
-- checksum. A snapshot without resources may bind its sibling's resource only when the
-- sibling shares the provider, path and revision. This differs from
-- source_manifest_corrections, which records a manifest that was never written.

CREATE TABLE football.source_manifest_raw_file_bindings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    source_snapshot_id uuid NOT NULL UNIQUE REFERENCES football.source_snapshots (id),
    binding text NOT NULL CHECK (binding = 'MANIFEST_PATH_IS_RAW_RESOURCE'),
    registered_path text NOT NULL CHECK (registered_path <> ''),
    registered_sha256 football.sha256_hex NOT NULL,
    source_resource_id uuid NOT NULL REFERENCES football.source_resources (id),
    resource_sha256 football.sha256_hex NOT NULL,
    resource_size_bytes bigint NOT NULL CHECK (resource_size_bytes > 0),
    evidence_reference text NOT NULL CHECK (evidence_reference <> ''),
    evidence_sha256 football.sha256_hex NOT NULL,
    decision_reference text NOT NULL CHECK (decision_reference <> ''),
    recorded_at timestamptz NOT NULL,
    code_commit_sha text NOT NULL CHECK (code_commit_sha ~ '^[0-9a-f]{40}$'),
    contract_version text NOT NULL DEFAULT 'source-manifest-raw-file-binding-v1' CHECK (
        contract_version = 'source-manifest-raw-file-binding-v1'
    ),
    CONSTRAINT source_manifest_raw_file_bindings_path_digest CHECK (
        registered_sha256 = encode(sha256(convert_to(registered_path, 'UTF8')), 'hex')
    ),
    CONSTRAINT source_manifest_raw_file_bindings_content_named CHECK (
        registered_path ~ ('/' || resource_sha256 || '\.[A-Za-z0-9]+$')
    )
);

-- +goose StatementBegin
CREATE FUNCTION football.validate_source_manifest_raw_file_binding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    snapshot football.source_snapshots%ROWTYPE;
    resource football.source_resources%ROWTYPE;
    owner football.source_snapshots%ROWTYPE;
BEGIN
    SELECT * INTO snapshot FROM football.source_snapshots WHERE id = NEW.source_snapshot_id;
    IF snapshot.id IS NULL
       OR snapshot.manifest_path <> NEW.registered_path
       OR snapshot.manifest_sha256 <> NEW.registered_sha256
       OR snapshot.source_revision LIKE 'manifest-v1:%'
       OR snapshot.source_revision <> NEW.resource_sha256 THEN
        RAISE EXCEPTION 'source manifest raw-file binding differs from the registration'
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO resource FROM football.source_resources WHERE id = NEW.source_resource_id;
    IF resource.id IS NULL
       OR resource.sha256 <> NEW.resource_sha256
       OR resource.size_bytes <> NEW.resource_size_bytes THEN
        RAISE EXCEPTION 'source manifest raw-file binding differs from the resource'
            USING ERRCODE = 'check_violation';
    END IF;
    IF resource.source_snapshot_id <> snapshot.id THEN
        SELECT * INTO owner FROM football.source_snapshots WHERE id = resource.source_snapshot_id;
        IF EXISTS (
               SELECT 1 FROM football.source_resources WHERE source_snapshot_id = snapshot.id
           )
           OR owner.provider_id <> snapshot.provider_id
           OR owner.manifest_path <> snapshot.manifest_path
           OR owner.source_revision <> snapshot.source_revision THEN
            RAISE EXCEPTION 'source manifest raw-file binding names an unrelated resource'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF EXISTS (
        SELECT 1 FROM football.source_manifest_corrections
        WHERE source_snapshot_id = NEW.source_snapshot_id
    ) THEN
        RAISE EXCEPTION 'source manifest is already recorded as never written'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- A never-written correction and a raw-file binding are mutually exclusive.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.validate_source_manifest_correction()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM football.source_snapshots
        WHERE id = NEW.source_snapshot_id
          AND manifest_path = NEW.registered_path
          AND manifest_sha256 = NEW.registered_sha256
          AND source_revision NOT LIKE 'manifest-v1:%'
    ) THEN
        RAISE EXCEPTION 'source manifest correction differs from the registration'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM football.source_manifest_raw_file_bindings
        WHERE source_snapshot_id = NEW.source_snapshot_id
    ) THEN
        RAISE EXCEPTION 'source manifest is already bound to a raw resource file'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER source_manifest_raw_file_bindings_target
BEFORE INSERT ON football.source_manifest_raw_file_bindings
FOR EACH ROW EXECUTE FUNCTION football.validate_source_manifest_raw_file_binding();

CREATE TRIGGER source_manifest_raw_file_bindings_append_only
BEFORE UPDATE OR DELETE ON football.source_manifest_raw_file_bindings
FOR EACH ROW EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

CREATE TRIGGER source_manifest_raw_file_bindings_no_truncate
BEFORE TRUNCATE ON football.source_manifest_raw_file_bindings
FOR EACH STATEMENT EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

-- +goose Down
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.validate_source_manifest_correction()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM football.source_snapshots
        WHERE id = NEW.source_snapshot_id
          AND manifest_path = NEW.registered_path
          AND manifest_sha256 = NEW.registered_sha256
          AND source_revision NOT LIKE 'manifest-v1:%'
    ) THEN
        RAISE EXCEPTION 'source manifest correction differs from the registration'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
DROP TABLE football.source_manifest_raw_file_bindings;
DROP FUNCTION football.validate_source_manifest_raw_file_binding();
