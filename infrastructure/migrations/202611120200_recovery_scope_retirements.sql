-- +goose Up
-- Append-only recovery-scope dispositions. A retirement states that one registration is
-- synthetic test lineage, so its missing bytes are not a recovery dependency. A source
-- manifest correction states that a snapshot's manifest checksum is the digest of its path
-- and no manifest file was ever written. Neither deletes, edits or re-registers anything,
-- and neither supplies a file or checksum. Each row binds the registration's path and
-- checksum as observed, the evidence file's SHA-256 and the owner decision that approved it.

CREATE TABLE football.recovery_scope_retirements (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    registration_table text NOT NULL CHECK (registration_table IN (
        'source_snapshots', 'source_resources', 'dataset_versions', 'dataset_files',
        'model_artifacts', 'model_artifact_files', 'baseline_forecasts',
        'sprint2_evaluation_runs'
    )),
    registration_id uuid NOT NULL,
    reason text NOT NULL CHECK (reason = 'SYNTHETIC_TEST_LINEAGE'),
    registered_path text NOT NULL CHECK (registered_path <> ''),
    registered_sha256 football.sha256_hex NOT NULL,
    evidence_reference text NOT NULL CHECK (evidence_reference <> ''),
    evidence_sha256 football.sha256_hex NOT NULL,
    decision_reference text NOT NULL CHECK (decision_reference <> ''),
    recorded_at timestamptz NOT NULL,
    code_commit_sha text NOT NULL CHECK (code_commit_sha ~ '^[0-9a-f]{40}$'),
    contract_version text NOT NULL DEFAULT 'recovery-scope-retirement-v1' CHECK (
        contract_version = 'recovery-scope-retirement-v1'
    ),
    UNIQUE (registration_table, registration_id)
);

CREATE TABLE football.source_manifest_corrections (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    source_snapshot_id uuid NOT NULL UNIQUE REFERENCES football.source_snapshots (id),
    correction text NOT NULL CHECK (correction = 'MANIFEST_NEVER_WRITTEN_PATH_DIGEST'),
    registered_path text NOT NULL CHECK (registered_path <> ''),
    registered_sha256 football.sha256_hex NOT NULL,
    evidence_reference text NOT NULL CHECK (evidence_reference <> ''),
    evidence_sha256 football.sha256_hex NOT NULL,
    decision_reference text NOT NULL CHECK (decision_reference <> ''),
    recorded_at timestamptz NOT NULL,
    code_commit_sha text NOT NULL CHECK (code_commit_sha ~ '^[0-9a-f]{40}$'),
    contract_version text NOT NULL DEFAULT 'source-manifest-correction-v1' CHECK (
        contract_version = 'source-manifest-correction-v1'
    ),
    CONSTRAINT source_manifest_corrections_path_digest CHECK (
        registered_sha256 = encode(sha256(convert_to(registered_path, 'UTF8')), 'hex')
    )
);

-- +goose StatementBegin
CREATE FUNCTION football.synthetic_test_snapshot(snapshot_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM football.source_snapshots
        WHERE id = snapshot_id
          AND source_identity LIKE 'example/open-data/%'
          AND manifest_sha256 ~ '^([0-9a-f])\1{63}$'
    );
$$;
-- +goose StatementEnd

-- A model is synthetic only when it has inputs and every input snapshot is synthetic.
-- +goose StatementBegin
CREATE FUNCTION football.synthetic_test_model(artifact_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT count(*) > 0 AND bool_and(football.synthetic_test_snapshot(source_snapshot_id))
    FROM football.model_artifact_inputs
    WHERE model_artifact_id = artifact_id;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.validate_recovery_scope_retirement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    observed_path text;
    observed_sha256 text;
    synthetic boolean;
BEGIN
    CASE NEW.registration_table
    WHEN 'source_snapshots' THEN
        SELECT manifest_path, manifest_sha256, football.synthetic_test_snapshot(id)
        INTO observed_path, observed_sha256, synthetic
        FROM football.source_snapshots WHERE id = NEW.registration_id;
    WHEN 'source_resources' THEN
        SELECT provider_path, sha256, football.synthetic_test_snapshot(source_snapshot_id)
        INTO observed_path, observed_sha256, synthetic
        FROM football.source_resources WHERE id = NEW.registration_id;
    WHEN 'dataset_versions' THEN
        SELECT manifest_path, manifest_sha256, football.synthetic_test_snapshot(source_snapshot_id)
        INTO observed_path, observed_sha256, synthetic
        FROM football.dataset_versions WHERE id = NEW.registration_id;
    WHEN 'dataset_files' THEN
        SELECT file.relative_path, file.physical_sha256,
               football.synthetic_test_snapshot(version.source_snapshot_id)
        INTO observed_path, observed_sha256, synthetic
        FROM football.dataset_files AS file
        JOIN football.dataset_versions AS version ON version.id = file.dataset_version_id
        WHERE file.id = NEW.registration_id;
    WHEN 'model_artifacts' THEN
        SELECT manifest_path, manifest_sha256
        INTO observed_path, observed_sha256
        FROM football.model_artifacts WHERE id = NEW.registration_id;
        synthetic := football.synthetic_test_model(NEW.registration_id);
    WHEN 'model_artifact_files' THEN
        SELECT relative_path, physical_sha256, football.synthetic_test_model(model_artifact_id)
        INTO observed_path, observed_sha256, synthetic
        FROM football.model_artifact_files WHERE id = NEW.registration_id;
    WHEN 'baseline_forecasts' THEN
        SELECT payload_path, payload_sha256, football.synthetic_test_snapshot(source_snapshot_id)
               AND EXISTS (
                   SELECT 1 FROM football.artifact_retirement_events AS retirement
                   WHERE retirement.object_kind = 'FORECAST'
                     AND retirement.object_id = forecast.id
                     AND retirement.retirement_scope = 'TEST_ONLY_HARD_GATE_EXCLUSION'
                     AND retirement.reason = 'SYNTHETIC_TEST_LINEAGE'
               )
        INTO observed_path, observed_sha256, synthetic
        FROM football.baseline_forecasts AS forecast WHERE id = NEW.registration_id;
    WHEN 'sprint2_evaluation_runs' THEN
        SELECT report_path, report_sha256, football.synthetic_test_snapshot(source_snapshot_id)
               AND EXISTS (
                   SELECT 1 FROM football.artifact_retirement_events AS retirement
                   WHERE retirement.object_kind = 'EVALUATION'
                     AND retirement.object_id = evaluation.id
                     AND retirement.retirement_scope = 'TEST_ONLY_HARD_GATE_EXCLUSION'
                     AND retirement.reason = 'SYNTHETIC_TEST_LINEAGE'
               )
        INTO observed_path, observed_sha256, synthetic
        FROM football.sprint2_evaluation_runs AS evaluation WHERE id = NEW.registration_id;
    END CASE;

    IF observed_path IS NULL THEN
        RAISE EXCEPTION 'recovery-scope retirement target is not registered'
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF observed_path <> NEW.registered_path OR observed_sha256 <> NEW.registered_sha256 THEN
        RAISE EXCEPTION 'recovery-scope retirement differs from the registration'
            USING ERRCODE = 'check_violation';
    END IF;
    IF synthetic IS NOT TRUE THEN
        RAISE EXCEPTION 'recovery-scope retirement target lacks synthetic test lineage'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.validate_source_manifest_correction()
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

CREATE TRIGGER recovery_scope_retirements_target
BEFORE INSERT ON football.recovery_scope_retirements
FOR EACH ROW EXECUTE FUNCTION football.validate_recovery_scope_retirement();

CREATE TRIGGER recovery_scope_retirements_append_only
BEFORE UPDATE OR DELETE ON football.recovery_scope_retirements
FOR EACH ROW EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

CREATE TRIGGER recovery_scope_retirements_no_truncate
BEFORE TRUNCATE ON football.recovery_scope_retirements
FOR EACH STATEMENT EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

CREATE TRIGGER source_manifest_corrections_target
BEFORE INSERT ON football.source_manifest_corrections
FOR EACH ROW EXECUTE FUNCTION football.validate_source_manifest_correction();

CREATE TRIGGER source_manifest_corrections_append_only
BEFORE UPDATE OR DELETE ON football.source_manifest_corrections
FOR EACH ROW EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

CREATE TRIGGER source_manifest_corrections_no_truncate
BEFORE TRUNCATE ON football.source_manifest_corrections
FOR EACH STATEMENT EXECUTE FUNCTION football.reject_dependency_lineage_mutation();
